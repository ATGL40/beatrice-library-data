r"""按 data/scoring.json（version 2）给作品打分，是配方的参考实现：软件、tools/community.py（神作结算）
和 tools/calibrate.py 都按这里的规则算。规则的文字说明见 README「综合榜配方」。

    py tools/scoring.py                 # 按 data/ 打分，列出神作、神作提名、各档作品数
    py tools/scoring.py --top 30        # 再列出前 30 名

社区评分按 community.minCount / prior / weight 并进口碑（和软件的 scoring2.ts 一样）；玩家修正（players）只在软件里
影响个人排序，这里不算：公共分档和神作资格只看公共资料和已结算的投票。
"""
import argparse
import datetime
import math
import sys

EPS = 1e-9  # 显示分 = floor(F + EPS)


def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def raw_inputs(g):
    """(评分 x, 评价人数 n, 人气数 h)；没有评分或人数的返回 None"""
    s = g.get("src")
    if s == "dlsite":
        x, n, h = num(g.get("rate")), num(g.get("rc")), num(g.get("dl"))
    elif s == "commercial":
        e = g.get("egs") or {}
        x, n = num(e.get("median")), num(e.get("count"))
        h = n
    elif s == "steam":
        e = g.get("steam") or {}
        x, n = num(e.get("positive")), num(e.get("reviews"))
        h = n
    else:
        return None
    if x is None or n is None or n <= 0:
        return None
    return x, n, h


def release_date(g, updated):
    """合法、且不晚于资料日期的发售日；不然 None（不给新作补偿，作品标上 date）"""
    try:
        d = datetime.date.fromisoformat(g.get("date") or "")
    except (TypeError, ValueError):
        return None
    return d if d <= updated else None


def curve(points, c):
    if c <= points[0][0]:
        return points[0][1]
    for (c0, f0), (c1, f1) in zip(points, points[1:]):
        if c <= c1:
            return f0 + (f1 - f0) * (c - c0) / (c1 - c0)
    return points[-1][1]


def composite(g, sc, updated):
    """返回 {x, n, Q, H, hot_ok, C, flags}；不打分的作品返回 None"""
    if g.get("state") == "dev" or g.get("src") not in sc["praise"]["k"]:
        return None
    raw = raw_inputs(g)
    if raw is None:
        return None
    x, n, h = raw
    s = g["src"]
    lo, hi = sc["praise"]["anchors"][s]
    k = sc["praise"]["k"][s]
    Q = 50 + n / (n + k) * ((x - lo) / (hi - lo) * 100 - 50)
    hp, flags = sc["heat"], []
    if h is None:  # 没有人气数：H 按 50 算，拿不到「热」
        H, hot_ok = 50.0, False
        flags.append("no-heat")
    else:
        d = release_date(g, updated)
        if d is None:  # 有人气数但发售日缺失 / 不合法 / 晚于资料日期：不给新作补偿
            div = 1.0
            flags.append("date")
        else:
            age = min(max((updated - d).days / 365.25, hp["age"]["min"]), hp["age"]["max"])
            div = age ** hp["age"]["exp"]
        a, b = hp["anchors"][s]
        H = min(100.0, max(0.0, (math.log10(max(h, 1) / div) - a) / (b - a) * 100))
        hot_ok = True
    cm, cr = g.get("community") if isinstance(g.get("community"), dict) else {}, sc["community"]
    avg, cnt = num(cm.get("avg")), num(cm.get("count"))
    P = Q  # 口碑；社区评分人数够 minCount 时和社区分混合（和软件一样）
    if avg is not None and cnt is not None and cnt >= cr["minCount"]:
        S = 50 + cnt / (cnt + cr["prior"]) * ((avg - 1) * 25 - 50)
        P = (1 - cr["weight"]) * Q + cr["weight"] * S
    C = (1 - hp["weight"]) * P + hp["weight"] * H
    return {"x": x, "n": n, "Q": Q, "P": P, "H": H, "hot_ok": hot_ok, "C": C, "flags": flags}


def listed_ids(catalog):
    return {it["rj"] for r in catalog.get("rankings") or [] for it in r.get("items") or []
            if isinstance(it, dict) and isinstance(it.get("rj"), str) and it["rj"]}


def score(catalog):
    """返回 {作品 id: 结果}；结果有 F0（曲线分）、F（最终分）、shown（显示分）、band、dims、C、Q、H、flags"""
    sc = catalog["scoring"]
    updated = datetime.date.fromisoformat(catalog["updated"])
    canon = catalog.get("canon") or {}
    listed = listed_ids(catalog)
    G = sc["gates"]
    out = {}
    for g in catalog["games"]:
        r = composite(g, sc, updated)
        if r is None:
            continue
        s, x, n = g["src"], r["x"], r["n"]
        cm = g.get("community") if isinstance(g.get("community"), dict) else {}
        dims = {
            "praise": x >= G["praise"]["rating"][s] and n >= G["praise"]["raters"][s],
            "praiseTop": x >= G["praiseTop"]["rating"][s] and n >= G["praiseTop"]["raters"][s],
            "heat": r["hot_ok"] and r["H"] >= G["heat"]["min"],
            "lists": g["id"] in listed or (G["lists"]["also"] and bool(g.get("also"))),
            "community": (num(cm.get("avg")) or 0) >= G["community"]["minAvg"]
                         and (num(cm.get("count")) or 0) >= G["community"]["minCount"],
        }
        others = dims["heat"] + dims["lists"] + dims["community"]
        tiers_ok = [dims[t["praise"]] and others >= t["others"] for t in G["tiers"]]
        nm = sc["nominee"]
        F0 = curve(sc["curve"]["points"], r["C"])
        if g["id"] in canon:  # 神作：不封顶，至少 canon.minScore
            F = max(F0, sc["canon"]["minScore"])
        elif F0 >= nm["minF0"] and all(tiers_ok) and dims[nm["praise"]] and others >= nm["others"]:  # 神作提名：固定 nominee.score
            F = nm["score"]
        else:  # 其他：没过的档硬封顶在 capTo，再整体封顶在 cap.max
            F = F0
            for t, ok in zip(G["tiers"], tiers_ok):
                if not ok:
                    F = min(F, t["capTo"])
            F = min(F, sc["cap"]["max"])
        shown = math.floor(F + EPS)
        band = next(lbl for lbl, lo in sc["bands"] if shown >= lo)
        out[g["id"]] = dict(r, F0=F0, F=F, shown=shown, band=band, dims=dims, date=g.get("date") or "")
    return out


def ranking(res):
    """名次：最终分高的在前；同分按未封顶的综合分（F0 由它算出）排，再同分按发售日新的在前"""
    ids = sorted(res, key=lambda u: res[u]["date"], reverse=True)
    ids.sort(key=lambda u: (res[u]["F"], res[u]["C"]), reverse=True)
    return ids


BADGES = (("praiseTop", "口★"), ("praise", "口"), ("heat", "热"), ("lists", "榜"), ("community", "玩"))


def badges(dims):
    out = []
    for key, label in BADGES:
        if dims[key] and not (key == "praise" and dims["praiseTop"]):
            out.append(label)
    return out


def main():
    from build_pack import build_catalog
    ap = argparse.ArgumentParser(description="按 data/scoring.json 给作品打分")
    ap.add_argument("--top", type=int, default=0, help="列出前 N 名")
    args = ap.parse_args()
    try:
        catalog = build_catalog()
    except (OSError, ValueError) as e:
        print(f"读资料失败：{e}", file=sys.stderr)
        return 1
    res = score(catalog)
    names = {g["id"]: (g.get("names") or {}).get("zh") or g.get("title") or g["id"] for g in catalog["games"]}
    order = ranking(res)
    counts = {lbl: 0 for lbl, _ in catalog["scoring"]["bands"]}
    for r in res.values():
        counts[r["band"]] += 1
    print(f"打分作品 {len(res)} 部：" + "，".join(f"{k} {v}" for k, v in counts.items()))
    for lbl in ("神作", "神作提名"):
        for u in (u for u in order if res[u]["band"] == lbl):
            r = res[u]
            print(f"  {lbl} {r['shown']}（F0 {r['F0']:.2f}）{names[u]}（{u}）评分 {r['x']}、{r['n']:,} 人，"
                  f"H {r['H']:.1f}，{' '.join(badges(r['dims'])) or '无徽章'}")
    flagged = sorted(u for u, r in res.items() if "date" in r["flags"])
    if flagged:
        print(f"发售日不可用、没给新作补偿的作品 {len(flagged)} 部：{flagged[:10]}{' …' if len(flagged) > 10 else ''}")
    for i, u in enumerate(order[:args.top], 1):
        r = res[u]
        print(f"{i:4} {r['shown']:3} {r['band']:4} F0 {r['F0']:6.2f} {names[u]}（{u}）{' '.join(badges(r['dims']))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
