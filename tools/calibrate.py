r"""重新校准综合榜配方：按 data/ 现在的作品，算出热度刻度和分数线，打印和 data/scoring.json 的差别。

    py tools/calibrate.py           # 只打印
    py tools/calibrate.py --write   # 把算出的 heat.scale 和 curve.points 写进 data/scoring.json（别的不动）

资料大版本更新、或者新加了一种评分（比如 VNDB / Bangumi）以后跑一次。校准规则（下面的常量）：
- 热度刻度 heat.scale：每个来源的 d（见 scoring.py 的 heat_offsets）从小到大排，取第 SCALE_PCT 百分位
  （下标 int(0.9 × (个数 − 1))，不插值），保留 6 位小数。这个值让同时期第 90 百分位的作品热度约 85。
- 分数线 curve.points：用（新的）热度刻度算全部已打分作品的综合分，取 KNOTS 里各百分位的综合分对上最终分，
  向下截到 6 位小数（卡在分数线上的作品不会因为截位掉档）。
下面两项只打印参考值，要不要改由维护者人工决定：
- 口碑锚点 praise.anchors：每个社区换算后 R 的中位数和第 95 百分位（目标约 50 / 80），以及按这个目标建议的锚点。
- 神作提名的口碑线 gates.praiseTop：同来源评分前 TOP_PCT% 的最低评分（同分取平均名次），人数第 RATERS_PCT 百分位（向上取整）。
"""
import argparse
import bisect
import copy
import datetime
import json
import math
import re
import statistics
import sys

from build_pack import DATA, build_catalog
from scoring import SCORED, composite, heat_offsets, ratings, scoped

KNOTS = [(0, 40), (20, 60), (50, 70), (80, 80), (95, 90), (99, 95), (99.5, 97), (100, 99)]
SCALE_PCT = 90
TOP_PCT, RATERS_PCT = 0.5, 85
R_MED, R_P95 = 50, 80
DECIMALS = 6


def pct(v, sv):
    if len(sv) <= 1:
        return 50.0
    lo, hi = bisect.bisect_left(sv, v), bisect.bisect_right(sv, v)
    return (lo + (hi - lo - 1) / 2) / (len(sv) - 1) * 100


def q(xs, p):
    return statistics.quantiles(xs, n=100, method="inclusive")[p - 1]


def floor_to(v, d=DECIMALS):
    return math.floor(v * 10 ** d) / 10 ** d


def at(sv, p):
    """升序 sv 的第 p 百分位（线性插值）"""
    pos = p / 100 * (len(sv) - 1)
    i = int(pos)
    return sv[i] if i + 1 >= len(sv) else sv[i] + (pos - i) * (sv[i + 1] - sv[i])


def calibrate(catalog):
    """返回新的配方（只改 heat.scale 和 curve.points）"""
    sc = copy.deepcopy(catalog["scoring"])
    updated = datetime.date.fromisoformat(catalog["updated"])
    works = scoped(catalog)
    src = {g["id"]: g["src"] for g in works}
    d = heat_offsets(works, sc, updated)
    for s in SCORED:
        ds = sorted(v for u, v in d.items() if src[u] == s)
        if ds:
            sc["heat"]["scale"][s] = round(ds[int(SCALE_PCT / 100 * (len(ds) - 1))], DECIMALS)
    cs = sorted(r["C"] for r in composite(dict(catalog, scoring=sc)).values())
    sc["curve"]["points"] = [[floor_to(at(cs, p)), f] for p, f in KNOTS]
    return sc


def write(new):
    """只换 scoring.json 里 scale 和 points 两行，别的格式不动"""
    path = DATA / "scoring.json"
    text = path.read_text(encoding="utf-8")
    for key, value in (("scale", new["heat"]["scale"]), ("points", new["curve"]["points"])):
        text, n = re.subn(rf'("{key}": )(\{{[^\n]*\}}|\[[^\n]*\])', lambda m: m.group(1) + json.dumps(value, ensure_ascii=False), text, count=1)
        if n != 1:
            raise ValueError(f"scoring.json 里找不到一行写完的 \"{key}\"")
    path.write_text(text, encoding="utf-8", newline="\n")


def main():
    ap = argparse.ArgumentParser(description="重新校准综合榜配方")
    ap.add_argument("--write", action="store_true", help="把 heat.scale 和 curve.points 写进 data/scoring.json")
    args = ap.parse_args()
    try:
        catalog = build_catalog()
    except (OSError, ValueError) as e:
        print(f"读资料失败：{e}", file=sys.stderr)
        return 1
    sc = catalog["scoring"]
    new = calibrate(catalog)
    rows = composite(dict(catalog, scoring=new))
    print(f"按 {len(rows)} 部已打分作品（资料日期 {catalog['updated']}）校准。\n")
    changed = False
    for path in (("heat", "scale"), ("curve", "points")):
        a, b = sc[path[0]][path[1]], new[path[0]][path[1]]
        name = ".".join(path)
        if a == b:
            print(f"{name}：不变")
        else:
            changed = True
            print(f"{name}：\n  现在 {json.dumps(a, ensure_ascii=False)}\n  新的 {json.dumps(b, ensure_ascii=False)}")

    # 参考值：各社区的 R 和口碑线（只打印）
    games = {g["id"]: g for g in scoped(catalog)}
    per = {}
    for u in rows:
        for s, x, n in ratings(games[u]):
            per.setdefault(s, []).append((x, n))
    print("\n口碑锚点（参考，不自动改）：各社区换算后 R 的中位数 / 第 95 百分位，目标约 "
          f"{R_MED} / {R_P95}；括号里是按目标建议的锚点")
    for s, xn in per.items():
        if s not in sc["praise"]["anchors"] or len(xn) < 2:
            continue
        lo, hi = sc["praise"]["anchors"][s]
        xs = sorted(x for x, _ in xn)
        med, p95 = statistics.median(xs), q(xs, 95)
        r = lambda x: (x - lo) / (hi - lo) * 100
        span = (p95 - med) * 100 / (R_P95 - R_MED) if p95 > med else hi - lo
        print(f"  {s}：{len(xs)} 部，R 中位数 {r(med):.1f}，第 95 百分位 {r(p95):.1f}"
              f"（建议 [{med - span * R_MED / 100:.2f}, {med + span * (100 - R_MED) / 100:.2f}]）")
    print(f"\n神作提名的口碑线（参考，不自动改）：评分前 {TOP_PCT}% 的最低评分、人数第 {RATERS_PCT} 百分位")
    top = sc["gates"]["praiseTop"]
    for s in sc["nominee"]["praiseSources"]:
        xn = per.get(s, [])
        if len(xn) < 2:
            print(f"  {s}：评分不到 2 部，没有参考值")
            continue
        xs = sorted(x for x, _ in xn)
        ok = [x for x in sorted(set(xs)) if pct(x, xs) >= 100 - TOP_PCT]
        line = ok[0] if ok else xs[-1]
        raters = math.ceil(q([n for _, n in xn], RATERS_PCT))
        now = f"现在 {top['rating'].get(s, '无')} / {top['raters'].get(s, '无')}"
        print(f"  {s}：参考 {line} / {raters:,} 人（{now}）")

    if args.write and changed:
        write(new)
        print("\n已写进 data/scoring.json。再跑 py tools/scoring.py 看结果，然后 build_pack.py / check_pack.py。")
    elif changed:
        print("\n要采用的话：py tools/calibrate.py --write")
    else:
        print("\n热度刻度和分数线和现在的资料一致，不用改。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
