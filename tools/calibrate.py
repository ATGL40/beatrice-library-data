r"""重新校准综合榜配方：按 data/ 现在的作品，算出建议的分数线、热度刻度和提名线，打印和 data/scoring.json 的差别。
只打印，不写文件：要不要改、改多少，由维护者决定后手动改 data/scoring.json（资料大版本更新时才做）。

    py tools/calibrate.py

校准规则（下面的常量）：
- 热度刻度 heat.anchors：每个来源按配方的年龄修正算 L = log10(人气数 / 年龄修正)，让中位数对上 H 50、
  第 90 百分位对上 H 85，两端取到 0.05。
- 分数线 curve.points：用（建议的）热度刻度算全部已打分作品的综合分，取 KNOTS 里各百分位的综合分对上最终分，
  向下截到 6 位小数（卡在分数线上的作品不会因为截位掉档）。
- 提名线 gates.praiseTop：评分线 = 同来源已打分作品里百分位（同分取平均名次）≥ 100 − TOP_PCT 的最低评分，
  没有作品够得上就保留现在的线；人数线 = 同来源评价人数的第 RATERS_PCT 百分位，向上取整。
- 口碑刻度 praise.anchors 不自动建议，只打印各来源口碑分 R 的中位数和第 90 百分位（定刻度时的目标约 52 / 75）。
"""
import bisect
import copy
import datetime
import json
import math
import statistics
import sys

from build_pack import build_catalog
from scoring import composite, raw_inputs, release_date

KNOTS = [(0, 40), (20, 60), (50, 70), (80, 80), (95, 90), (99, 95), (99.5, 97), (100, 99)]
TOP_PCT, RATERS_PCT = 0.5, 85
HEAT_MED, HEAT_P90, HEAT_STEP = 50, 85, 0.05
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


def main():
    try:
        catalog = build_catalog()
    except (OSError, ValueError) as e:
        print(f"读资料失败：{e}", file=sys.stderr)
        return 1
    sc = catalog["scoring"]
    updated = datetime.date.fromisoformat(catalog["updated"])
    srcs = list(sc["praise"]["k"])
    works = [g for g in catalog["games"] if composite(g, sc, updated) is not None]
    by_src = {s: [g for g in works if g["src"] == s] for s in srcs}
    new = copy.deepcopy(sc)

    # 热度刻度
    hp = sc["heat"]
    for s, gs in by_src.items():
        L = []
        for g in gs:
            h = raw_inputs(g)[2]
            if h is None:
                continue
            d = release_date(g, updated)
            age = 1.0 if d is None else min(max((updated - d).days / 365.25, hp["age"]["min"]), hp["age"]["max"])
            L.append(math.log10(max(h, 1) / age ** hp["age"]["exp"]))
        med, p90 = statistics.median(L), q(L, 90)
        slope = (HEAT_P90 - HEAT_MED) / (p90 - med)
        lo = med - HEAT_MED / slope
        new["heat"]["anchors"][s] = [round(round(lo / HEAT_STEP) * HEAT_STEP, 2), round(round((lo + 100 / slope) / HEAT_STEP) * HEAT_STEP, 2)]

    # 分数线（用建议的热度刻度）
    cs = sorted(composite(g, new, updated)["C"] for g in works)

    def at(p):
        pos = p / 100 * (len(cs) - 1)
        i = int(pos)
        return cs[i] if i + 1 >= len(cs) else cs[i] + (pos - i) * (cs[i + 1] - cs[i])

    new["curve"]["points"] = [[floor_to(at(p)), f] for p, f in KNOTS]

    # 提名线
    notes = []
    for s, gs in by_src.items():
        xs = sorted(raw_inputs(g)[0] for g in gs)
        ok = [x for x in sorted(set(xs)) if pct(x, xs) >= 100 - TOP_PCT]
        if ok:
            new["gates"]["praiseTop"]["rating"][s] = ok[0]
        else:
            notes.append(f"{s}：没有评分在前 {TOP_PCT}%（最高分 {xs[-1]} 有 {xs.count(xs[-1])} 部并列，百分位 {pct(xs[-1], xs):.3f}），评分线保留现在的值")
        new["gates"]["praiseTop"]["raters"][s] = math.ceil(q([raw_inputs(g)[1] for g in gs], RATERS_PCT))

    print(f"按 {len(works)} 部已打分作品（资料日期 {catalog['updated']}）校准；只是建议，不会写文件。\n")
    changed = False
    for path in (("heat", "anchors"), ("curve", "points"), ("gates", "praiseTop", "rating"), ("gates", "praiseTop", "raters")):
        a, b = sc, new
        for k in path:
            a, b = a[k], b[k]
        name = ".".join(path)
        if a == b:
            print(f"{name}：不变")
        else:
            changed = True
            print(f"{name}：\n  现在 {json.dumps(a, ensure_ascii=False)}\n  建议 {json.dumps(b, ensure_ascii=False)}")
    for n in notes:
        print("  注意：" + n)
    print("\n口碑分 R 的分布（现在的 praise.anchors；定刻度时的目标是中位数约 52、第 90 百分位约 75）：")
    for s, gs in by_src.items():
        lo, hi = sc["praise"]["anchors"][s]
        R = [(raw_inputs(g)[0] - lo) / (hi - lo) * 100 for g in gs]
        print(f"  {s}：{len(R)} 部，中位数 {statistics.median(R):.1f}，第 90 百分位 {q(R, 90):.1f}")
    print("\n要采用的话，手动改 data/scoring.json，再跑 build_pack.py / check_pack.py。" if changed else "\n配方和现在的资料一致，不用改。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
