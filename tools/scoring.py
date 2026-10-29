r"""按 data/scoring.json（version 2）给作品打分，是配方的参考实现：软件（scoring2.ts）、tools/community.py（神作结算）
和 tools/calibrate.py 都按这里的规则算。规则的文字说明见 README「综合榜配方」。

    py tools/scoring.py                   # 按 data/ 打分，列出神作、神作提名、各档作品数、评价不足的作品
    py tools/scoring.py --top 30          # 再列出前 30 名
    py tools/scoring.py --dump 文件.json   # 把每部的分、档、名次写成 JSON（软件的对照测试用）

玩家修正（players）只在软件里影响个人排序，这里不算：公共分档和神作资格只看公共资料和已结算的投票。
"""
import argparse
import collections
import datetime
import json
import math
import statistics
import sys

EPS = 1e-9  # 显示分 = floor(F + EPS)
SCORED = ("dlsite", "commercial", "steam")  # 只给这三个来源的已发售作品打分；热度也只在这三个来源里比
# 社区评分从哪读：(来源, 字段, 评分, 人数)；DLsite 只读 DLsite 作品的 rate / rc。顺序固定（加起来的先后和软件一样）
RATINGS = (("commercial", "egs", "median", "count"), ("steam", "steam", "positive", "reviews"),
           ("vndb", "vndb", "rating", "votes"), ("bgm", "bgm", "score", "votes"), ("community", "community", "avg", "count"))


def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def ratings(g):
    """作品上每个社区的评分 [(来源, 评分 x, 人数 n)]，人数要 > 0"""
    out = []

    def add(s, x, n):
        x, n = num(x), num(n)
        if x is not None and n is not None and n > 0:
            out.append((s, x, n))

    if g.get("src") == "dlsite":
        add("dlsite", g.get("rate"), g.get("rc"))
    for s, key, xk, nk in RATINGS:
        v = g.get(key) if isinstance(g.get(key), dict) else {}
        add(s, v.get(xk), v.get(nk))
    return out


def heat_count(g):
    """热度用的人气数：DLsite 销量 dl、商业 egs.count、Steam steam.reviews；没有是 None"""
    s = g.get("src")
    if s == "dlsite":
        return num(g.get("dl"))
    key, field = {"commercial": ("egs", "count"), "steam": ("steam", "reviews")}.get(s, ("", ""))
    v = g.get(key) if key else None
    return num(v.get(field)) if isinstance(v, dict) else None


def release_date(g, updated):
    """合法、且不晚于资料日期的发售日；不然 None（不给新作补偿，也不算进哪一年）"""
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


def list_hits(catalog):
    """作品 id → 上过几次民间榜单（条目的 rj 对上作品）"""
    return collections.Counter(it["rj"] for r in catalog.get("rankings") or [] for it in r.get("items") or []
                               if isinstance(it, dict) and isinstance(it.get("rj"), str) and it["rj"])


def listed_ids(catalog):
    return set(list_hits(catalog))


def counted(g, sc):
    """口碑认的评分：配方 anchors 里有这个社区，并且 appliesTo 没限制、或者作品来源在限制里（VNDB 只看商业作；Steam 是空数组，不参与打分）"""
    pr = sc["praise"]
    return [(s, x, n) for s, x, n in ratings(g)
            if s in pr["anchors"] and (s not in pr["appliesTo"] or g.get("src") in pr["appliesTo"][s])]


def anchor(sc, s, src):
    """社区 s 对来源 src 的作品用的锚点：anchorsBySource[s][src] 写了就用它（Bangumi 按来源分开校准），不然用 anchors[s]"""
    pr = sc["praise"]
    return (pr.get("anchorsBySource") or {}).get(s, {}).get(src) or pr["anchors"][s]


def top_line(sc, s, src):
    """社区 s 对来源 src 的作品的口★线 (评分线, 人数线)：gates.praiseTopBySource[s] 写了这个来源就用它，不然用 gates.praiseTop；
    都没有返回 None"""
    gt = sc["gates"]
    by = (gt.get("praiseTopBySource") or {}).get(s, {})
    if src in by.get("rating", {}) and src in by.get("raters", {}):
        return by["rating"][src], by["raters"][src]
    top = gt["praiseTop"]
    return (top["rating"][s], top["raters"][s]) if s in top["rating"] and s in top["raters"] else None


def cap_secondary(per, sec, src):
    """本平台（社区名和作品来源相同的那项）算进来时，sec["sources"] 里的社区证据量合计不超过本平台的 sec["maxShareOfNative"] 倍：
    超了就每项乘同一个系数 f = 上限 ÷ 合计。没有本平台评分的作品（Steam 作品、只有 Bangumi 的作品等）不限。sec 是 None 时不限"""
    native = next((e for s, x, n, R, e in per if s == src), None)
    if not sec or native is None:
        return per
    cap = sec["maxShareOfNative"] * native
    total = sum(e for s, x, n, R, e in per if s in sec["sources"])
    if total <= cap:
        return per
    f = cap / total
    return [(s, x, n, R, e * f if s in sec["sources"] else e) for s, x, n, R, e in per]


def praise(g, sc, hits=0):
    """口碑 P = 50 + Σe(R − 50) ÷ (1 + Σe)。每个社区（counted 认的）：评分按锚点（anchor：可以按作品来源分开）换成 R（截到 clamp），证据量 e = 人数 ÷ k
    （R > 50 用 kUp、不然用 k：样本少只许虚高不许虚低）；人数不到 minN 的社区不算；民间榜单每上一次是一份 R = lists.R 的证据。
    本平台的评分算进来时（DLsite 作品的 DLsite、商业作的批评空间），secondary.sources 里的社区（VNDB、Bangumi）合起来的证据量
    最多是本平台的 maxShareOfNative 倍，超了就按同一个比例缩小（本平台至少占一半的话语权）。
    返回 {P, E, per: [(来源, x, n, R, e)]}（e 是缩小后的）；没有一个社区够人数（评价不足）返回 None"""
    pr = sc["praise"]
    lo_c, hi_c = pr["clamp"]
    per = []
    for s, x, n in counted(g, sc):
        if n < pr["minN"][s]:
            continue
        lo, hi = anchor(sc, s, g.get("src"))
        R = min(hi_c, max(lo_c, (x - lo) / (hi - lo) * 100))
        per.append((s, x, n, R, n / (pr["kUp"][s] if R > 50 else pr["k"][s])))
    if not per:
        return None
    per = cap_secondary(per, pr.get("secondary"), g.get("src"))
    total, E = 0.0, 0.0
    for *_, R, e in per:
        total += e * (R - 50)
        E += e
    L = pr["lists"]
    if hits:
        c = min(hits, L["max"])
        total += c * L["e"] * (L["R"] - 50)
        E += c * L["e"]
    return {"P": 50 + total / (1 + E), "E": E, "per": per}


def adjusted_count(g, sc, updated):
    """年龄补偿后的人气数：发售不到一年的 ÷ t^exp（t 是年数，夹在 age.min～age.max）；发售日不可用的不补偿"""
    h = heat_count(g)
    if h is None:
        return None
    d, age = release_date(g, updated), sc["heat"]["age"]
    if d is None:
        return max(h, 1.0)
    t = (updated - d).days / 365.25
    return max(h, 1.0) / (min(max(t, age["min"]), age["max"]) ** age["exp"] if t < 1 else 1.0)


def heat_offsets(games, sc, updated):
    """时代基准：d = log10(补偿后的人气数) − 同来源、发售年前后 window 年作品的中位数（log10）。
    这几年不到 minGroup 部就每次多放宽一年，直到全部年份。返回 {作品 id: d}"""
    hp = sc["heat"]
    logs, years = {}, collections.defaultdict(list)
    for g in games:
        v = adjusted_count(g, sc, updated)
        if v is None:
            continue
        d = release_date(g, updated)
        logs[g["id"]] = (g["src"], d.year if d else None, math.log10(v))
    for src, y, x in logs.values():
        if y is not None:
            years[src].append((y, x))
    cache = {}

    def baseline(src, y):
        if (src, y) not in cache:
            ys, w = years[src], hp["window"]
            far = max(abs(yy - y) for yy, _ in ys)
            vals = [x for _, x in ys]
            while w < far:
                near = [x for yy, x in ys if abs(yy - y) <= w]
                if len(near) >= hp["minGroup"]:
                    vals = near
                    break
                w += 1
            cache[(src, y)] = statistics.median(vals)
        return cache[(src, y)]

    out = {}
    for u, (src, y, x) in logs.items():
        if y is not None:
            out[u] = x - baseline(src, y)
        else:  # 发售日不可用：和同来源有发售日的全部作品比（都没有发售日就和同来源全部比）
            pool = [v for _, v in years[src]] or [v for s, _, v in logs.values() if s == src]
            out[u] = x - statistics.median(pool)
    return out


def heat(d, src, sc):
    """H = 50 + 35·d ÷ scale[来源]，截到 0–100；没有人气数的按 heat.missing 算"""
    hp = sc["heat"]
    if d is None:
        return hp["missing"]
    return min(100.0, max(0.0, 50 + 35 * d / hp["scale"][src]))


def scoped(catalog):
    """参与打分的作品：已发售的 DLsite / 商业 / Steam 作品"""
    return [g for g in catalog["games"] if g.get("state") != "dev" and g.get("src") in SCORED]


def composite(catalog):
    """每部参与打分的作品的口碑和热度：{作品 id: {P, E, per, H, C}}，评价不足的不在里面"""
    sc = catalog["scoring"]
    updated = datetime.date.fromisoformat(catalog["updated"])
    works = scoped(catalog)
    hits = list_hits(catalog)
    offsets = heat_offsets(works, sc, updated)
    w = sc["heat"]["weight"]
    out = {}
    for g in works:
        p = praise(g, sc, hits.get(g["id"], 0))
        if p is None:
            continue
        H = heat(offsets.get(g["id"]), g["src"], sc)
        out[g["id"]] = dict(p, H=H, C=(1 - w) * p["P"] + w * H)
    return out


def score(catalog):
    """返回 {作品 id: 结果}（评价不足的不在里面）；结果有 P、H、C、F0（曲线分）、F（最终分）、shown（显示分）、band、dims、nominee"""
    sc = catalog["scoring"]
    canon = catalog.get("canon") or {}
    listed = listed_ids(catalog)
    games = {g["id"]: g for g in catalog["games"]}
    nm, gt = sc["nominee"], sc["gates"]
    rows = composite(catalog)
    bench = rows.get(nm["benchmark"])
    for u, r in rows.items():
        g = games[u]
        cm = g.get("community") if isinstance(g.get("community"), dict) else {}
        strong = [s for s, x, n, R, e in r["per"] if R >= nm["second"]["R"] and e >= nm["second"]["e"]]
        dims = {
            "praiseTop": any(s in nm["praiseSources"] and (line := top_line(sc, s, g["src"])) is not None
                             and x >= line[0] and n >= line[1] for s, x, n, R, e in r["per"]),
            "lists": u in listed,
            "community": (num(cm.get("avg")) or 0) >= gt["community"]["minAvg"]
                         and (num(cm.get("count")) or 0) >= gt["community"]["minCount"],
            "second": len(strong) >= 2,
        }
        others = dims["lists"] + dims["community"] + dims["second"]
        F0 = curve(sc["curve"]["points"], r["C"])
        nominee = (u not in canon and F0 >= nm["minF0"] and dims["praiseTop"] and others >= nm["others"]
                   and (bench is None or r["P"] >= nm["benchmarkPct"] * bench["P"]))
        if u in canon:  # 神作：不封顶，至少 canon.minScore
            F = max(F0, sc["canon"]["minScore"])
        elif nominee:  # 神作提名：固定 nominee.score
            F = nm["score"]
        else:
            F = min(F0, sc["cap"]["max"])
        shown = math.floor(F + EPS)
        band = next(lbl for lbl, lo in sc["bands"] if shown >= lo)
        r.update(F0=F0, F=F, shown=shown, band=band, dims=dims, nominee=nominee, date=g.get("date") or "")
    return rows


def insufficient(catalog, res):
    """评价不足的作品 id：参与打分、但没有一个社区的评价人数够下限（不打分、不分档，列表里单独一组）"""
    return [g["id"] for g in scoped(catalog) if g["id"] not in res]


def ranking(res):
    """名次：最终分高的在前；同分按综合分 C（F0 由它算出）排，再同分按发售日新的在前"""
    ids = sorted(res, key=lambda u: res[u]["date"], reverse=True)
    ids.sort(key=lambda u: (res[u]["F"], res[u]["C"]), reverse=True)
    return ids


BADGES = (("praiseTop", "口★"), ("lists", "榜"), ("community", "玩"), ("second", "多"))


def badges(dims):
    return [label for key, label in BADGES if dims[key]]


def main():
    from build_pack import build_catalog
    ap = argparse.ArgumentParser(description="按 data/scoring.json 给作品打分")
    ap.add_argument("--top", type=int, default=0, help="列出前 N 名")
    ap.add_argument("--dump", help="把每部的分、档、名次写成 JSON（软件的对照测试用）")
    args = ap.parse_args()
    try:
        catalog = build_catalog()
    except (OSError, ValueError) as e:
        print(f"读资料失败：{e}", file=sys.stderr)
        return 1
    res = score(catalog)
    thin = insufficient(catalog, res)
    names = {g["id"]: (g.get("names") or {}).get("zh") or g.get("title") or g["id"] for g in catalog["games"]}
    order = ranking(res)
    counts = {lbl: 0 for lbl, _ in catalog["scoring"]["bands"]}
    for r in res.values():
        counts[r["band"]] += 1
    print(f"打分作品 {len(res)} 部：" + "，".join(f"{k} {v}" for k, v in counts.items()) + f"；评价不足 {len(thin)} 部")
    for lbl in ("神作", "神作提名"):
        for u in (u for u in order if res[u]["band"] == lbl):
            r = res[u]
            print(f"  {lbl} {r['shown']}（F0 {r['F0']:.2f}）{names[u]}（{u}）口碑 {r['P']:.1f}，热度 {r['H']:.1f}，"
                  f"{' '.join(badges(r['dims'])) or '无徽章'}")
    if thin:
        print(f"评价不足：{thin[:10]}{' …' if len(thin) > 10 else ''}")
    for i, u in enumerate(order[:args.top], 1):
        r = res[u]
        print(f"{i:4} {r['shown']:3} {r['band']:4} F0 {r['F0']:6.2f} P {r['P']:5.1f} H {r['H']:5.1f} {names[u]}（{u}）"
              f"{' '.join(badges(r['dims']))}")
    if args.dump:
        out = {"updated": catalog["updated"], "revision": catalog.get("revision", 0),
               "ranked": [[u, round(res[u]["F"], 6), res[u]["band"], round(res[u]["P"], 6), round(res[u]["H"], 6)] for u in order],
               "insufficient": thin}
        with open(args.dump, "w", encoding="utf-8", newline="\n") as f:
            json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
            f.write("\n")
        print(f"写好 {args.dump}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
