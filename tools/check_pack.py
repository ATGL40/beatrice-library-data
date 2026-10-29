r"""按软件导入时的规则检查数据包，再多查几项资料格式。

    py tools/check_pack.py dist/碧翠子禁书库数据包-2026-10-27.zip
    py tools/check_pack.py 包.zip --min-updated 2026-10-28 --min-revision 1   # 软件自带资料的日期和 revision，比它旧的包软件不收

有问题时退出码是 1。
"""
import argparse
import datetime
import json
import re
import sys
import zipfile
from pathlib import Path

CATALOG_VERSION = 2
MAX_ENTRIES = 20000
MAX_FILE = 50 << 20
MAX_TOTAL = 1 << 30
CATS = {"f-rpg", "m-rpg", "adv", "slg", "act", "other"}
SRCS = {"dlsite", "fanza", "commercial", "steam", "cien", "fanbox"}
SIGNALS = {"egs": "commercial", "steam": "steam", "followers": "cien"}  # 分数信号字段 → 写它的来源
RATED = {"vndb": ("rating", 10, 100), "bgm": ("score", 1, 10)}  # VNDB / Bangumi 的评分：任何来源的作品都可以有
POVS = ("female", "male", "both", "multi", "none")  # 主角视角：女主 / 男主 / 男女双视角 / 多视角 / 无固定主角
LANGS = ("ja", "zh", "en")
EXTS = {"jpg", "jpeg", "png", "webp"}
NAME_OK = re.compile(r"[A-Za-z0-9._-]+")
RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10)}


def safe_name(name):
    return (bool(NAME_OK.fullmatch(name)) and not name.startswith(".") and not name.endswith((".", " "))
            and name.split(".")[0].upper() not in RESERVED)


def entry_target(name):
    """和软件一样：只认根目录的 catalog.json 和 covers/、thumbs/（缩略图）下一层的图片，别的返回 None（导入时跳过）"""
    name = name.replace("\\", "/")
    if name == "catalog.json":
        return name
    folder, _, file = name.partition("/")
    if folder not in ("covers", "thumbs"):
        return None
    ext = file.rsplit(".", 1)[-1].lower() if "." in file else ""
    return f"{folder}/{file}" if safe_name(file) and ext in EXTS else None


def read_limited(z, info, limit):
    """按实际解压出的字节数算大小，不看 zip 里写的大小；超过上限返回 None"""
    with z.open(info) as f:
        data = f.read(limit + 1)
    return None if len(data) > limit else data


def is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def aliases_ok(v):
    """aliases（核实过的别名，识别游戏文件夹用）：非空字符串的数组，不重复"""
    return (isinstance(v, list) and len(v) > 0 and all(isinstance(a, str) and a.strip() for a in v)
            and len(set(v)) == len(v))


def signal_problem(g):
    """egs / steam / followers：只有对应来源的作品写；vndb / bgm：任何来源都可以写。都可以没有或 null；有就查类型和范围，返回问题说明或 None"""
    for key, src in SIGNALS.items():
        v = g.get(key)
        if v is None:
            continue
        if g.get("src") != src:
            return f"的来源是 {g.get('src')}，只有 {src} 的作品写 {key}"
        if key == "egs" and not (isinstance(v, dict) and set(v) == {"median", "count"} and is_int(v["median"])
                                 and 0 <= v["median"] <= 100 and is_int(v["count"]) and v["count"] >= 1):
            return "的 egs 要是 {\"median\": 0–100 的整数, \"count\": 正整数}"
        if key == "steam" and not (isinstance(v, dict) and set(v) == {"positive", "reviews"} and is_int(v["positive"])
                                   and 0 <= v["positive"] <= 100 and is_int(v["reviews"]) and v["reviews"] >= 1):
            return "的 steam 要是 {\"positive\": 0–100 的整数, \"reviews\": 正整数}"
        if key == "followers" and not (is_int(v) and v >= 0):
            return "的 followers 要是非负整数"
    for key, (field, lo, hi) in RATED.items():
        v = g.get(key)
        if v is None:
            continue
        if not (isinstance(v, dict) and set(v) == {"id", field, "votes"} and isinstance(v["id"], (str, int)) and not isinstance(v["id"], bool)
                and str(v["id"]).strip() != "" and (v[field] is None or is_num(v[field]) and lo <= v[field] <= hi)
                and is_int(v["votes"]) and v["votes"] >= 0):
            return f"的 {key} 要是 {{\"id\": 编号, \"{field}\": {lo}–{hi} 的数或 null, \"votes\": 非负整数}}"
    return None


def pov_problem(g):
    """pov（主角视角）：可以不写（不知道）；有就要是 POVS 之一，返回问题说明或 None"""
    if "pov" in g and g["pov"] not in POVS:
        return f"的 pov 是 {g['pov']!r}，要是 {' / '.join(POVS)} 之一（不知道就不写）"
    return None


def community_problem(g):
    """community（社区评分汇总，tools/community.py 写的）：任何来源都可以有，可以没有或 null；
    有就要是 {"avg": 1–5 的数, "count": 正整数}，返回问题说明或 None"""
    v = g.get("community")
    if v is None:
        return None
    if not (isinstance(v, dict) and set(v) == {"avg", "count"} and isinstance(v["avg"], (int, float))
            and not isinstance(v["avg"], bool) and 1 <= v["avg"] <= 5 and is_int(v["count"]) and v["count"] >= 1):
        return "的 community 要是 {\"avg\": 1–5 的数, \"count\": 正整数}"
    return None


def raw_problem(g):
    """DLsite 的原始数据：rate 是 0–5 的数，rc 是正整数，dl 是非负整数，都可以没有或 null；返回问题说明或 None"""
    rate, rc, dl = g.get("rate"), g.get("rc"), g.get("dl")
    if rate is not None and not (is_num(rate) and 0 <= rate <= 5):
        return f"的 rate 要是 0–5 的数：{rate!r}"
    if rc is not None and not (is_int(rc) and rc >= 1):
        return f"的 rc 要是正整数：{rc!r}"
    if dl is not None and not (is_int(dl) and dl >= 0):
        return f"的 dl 要是非负整数：{dl!r}"
    return None


def godvote_problem(g):
    """godvote（神作复议的结算结果，tools/community.py 写的）：可以没有；有就要是
    {"support": 非负整数, "oppose": 非负整数, "settled": 结算日期, "changed": 上次因投票升降的日期（可以没有）}，
    没有 changed 时至少 1 票，返回问题说明或 None"""
    v = g.get("godvote")
    if v is None:
        return None
    if not (isinstance(v, dict) and {"support", "oppose", "settled"} <= set(v) <= {"support", "oppose", "settled", "changed"}
            and is_int(v["support"]) and is_int(v["oppose"]) and v["support"] >= 0 and v["oppose"] >= 0
            and is_date(v["settled"]) and ("changed" not in v or is_date(v["changed"]))
            and (v["support"] + v["oppose"] >= 1 or "changed" in v)):
        return ("的 godvote 要是 {\"support\": 非负整数, \"oppose\": 非负整数, \"settled\": \"YYYY-MM-DD\"}"
                "（可以再有 \"changed\": \"YYYY-MM-DD\"），没有 changed 时至少 1 票")
    return None


def blacklist_problem(g):
    """blacklist（社区黑榜的结算结果，tools/community.py 写的）：可以没有；有就要是
    {"count": 非负整数, "flagged": true / false, "settled": 结算日期, "changed": 上次标注变化的日期（可以没有）}；
    没有 changed 时至少 1 人，标上了的（flagged）也至少 1 人；返回问题说明或 None"""
    v = g.get("blacklist")
    if v is None:
        return None
    if not (isinstance(v, dict) and {"count", "flagged", "settled"} <= set(v) <= {"count", "flagged", "settled", "changed"}
            and is_int(v["count"]) and v["count"] >= 0 and isinstance(v["flagged"], bool)
            and is_date(v["settled"]) and ("changed" not in v or is_date(v["changed"]))
            and (v["count"] >= 1 or ("changed" in v and not v["flagged"]))):
        return ("的 blacklist 要是 {\"count\": 非负整数, \"flagged\": true 或 false, \"settled\": \"YYYY-MM-DD\"}"
                "（可以再有 \"changed\": \"YYYY-MM-DD\"），没有 changed 或 flagged 是 true 时至少 1 人")
    return None


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def is_date(v):
    return isinstance(v, str) and bool(DATE_RE.fullmatch(v))


DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
SCORED = ("dlsite", "commercial", "steam")  # 综合榜只给这三个来源的已发售作品打分
SCORING_KEYS = {"name", "version", "praise", "heat", "players", "curve", "bands", "cap", "nominee", "gates",
                "canon", "development", "hiddenGems", "blacklist"}
RATING_SRCS = ("dlsite", "commercial", "steam", "vndb", "bgm", "community")  # 口碑能合并的社区评分
REASON_RULES = ("oppose", "all", "none")
GEM_SORTS = ("praise",)  # 冷门佳作榜的排序依据：praise = 口碑分 P


def scoring_problems(sc, ids=None):
    """综合榜配方（version 2，见 README「综合榜配方」），返回问题列表；给了 ids（作品 id 集合）时再查基准作品在不在"""
    if not isinstance(sc, dict):
        return ["scoring 不是对象"]
    out = []

    def need(ok, msg):
        if not ok:
            out.append("scoring " + msg)
        return ok

    def obj(v, keys):
        return isinstance(v, dict) and set(v) == set(keys)

    def table(v, keys, test):  # 按来源的表：正好是这些来源，值都过 test
        return obj(v, keys) and all(test(v[s]) for s in keys)

    def span(v):
        return isinstance(v, list) and len(v) == 2 and all(map(is_num, v)) and v[0] < v[1]

    extra = sorted(set(sc) - SCORING_KEYS)
    need(not extra, f"有不认识的字段：{extra}")
    need(isinstance(sc.get("name"), str) and sc["name"].strip() != "", "的 name 要是非空字符串")
    if not need(is_int(sc.get("version")) and sc["version"] == 2, f"的 version 要是 2：{sc.get('version')!r}"):
        return out
    pr = sc.get("praise")
    anchors = pr.get("anchors") if isinstance(pr, dict) else None
    srcs = list(anchors) if isinstance(anchors, dict) else []  # 口碑认的社区：anchors 里写了的
    lists = pr.get("lists") if isinstance(pr, dict) else None
    applies = pr.get("appliesTo") if isinstance(pr, dict) else None
    by_src = pr.get("anchorsBySource", {}) if isinstance(pr, dict) else {}  # 可以没有
    sec = pr.get("secondary") if isinstance(pr, dict) else None  # 可以没有
    need(isinstance(pr, dict) and obj({k: v for k, v in pr.items() if k not in ("anchorsBySource", "secondary")},
                                      ("k", "kUp", "minN", "anchors", "appliesTo", "clamp", "lists")) and set(SCORED) <= set(srcs) <= set(RATING_SRCS)
         and isinstance(applies, dict) and set(applies) <= set(srcs)
         and all(isinstance(v, list) and len(set(v)) == len(v) and set(v) <= set(SCORED) for v in applies.values())
         and table(anchors, srcs, span) and table(pr["k"], srcs, lambda v: is_num(v) and v > 0)
         and table(pr["kUp"], srcs, lambda v: is_num(v) and v > 0) and table(pr["minN"], srcs, lambda v: is_int(v) and v >= 1)
         and span(pr["clamp"]) and obj(lists, ("R", "e", "max")) and is_num(lists["R"])
         and is_num(lists["e"]) and lists["e"] >= 0 and is_int(lists["max"]) and lists["max"] >= 0,
         "的 praise 要是 {k, kUp: {社区: 正数}, minN: {社区: 正整数}, anchors: {社区: [低, 高]}, "
         "appliesTo: {社区: [只对这些来源的作品算…]}（没写的社区对所有作品都算，空数组是不参与打分）, clamp: [低, 高], "
         f"lists: {{R: 数, e: ≥0, max: 非负整数}}}}，四张表的社区一样，至少有 {' / '.join(SCORED)}，"
         f"只认 {' / '.join(RATING_SRCS)}")
    need(isinstance(by_src, dict) and set(by_src) <= set(srcs)
         and all(isinstance(v, dict) and set(v) <= set(SCORED) and all(map(span, v.values())) for v in by_src.values()),
         "的 praise.anchorsBySource（可以没有）要是 {社区: {来源: [低, 高]}}，社区要在 anchors 里，来源是 "
         f"{' / '.join(SCORED)}（没写的来源用 anchors[社区]）")
    need(sec is None or (obj(sec, ("sources", "maxShareOfNative")) and isinstance(sec["sources"], list)
                         and len(set(sec["sources"])) == len(sec["sources"]) and set(sec["sources"]) <= set(srcs) - set(SCORED)
                         and is_num(sec["maxShareOfNative"]) and sec["maxShareOfNative"] >= 0),
         "的 praise.secondary（可以没有）要是 {sources: [社区…], maxShareOfNative: ≥0}，社区要在 anchors 里、不是 "
         f"{' / '.join(SCORED)} 这几个本平台评分（本平台的评分算进来时，这些社区合起来的证据量最多是 maxShareOfNative × 本平台人数 ÷ kUp[本平台]）")
    h = sc.get("heat")
    age = h.get("age") if isinstance(h, dict) else None
    need(obj(h, ("method", "weight", "window", "minGroup", "scale", "missing", "age")) and h["method"] == "era-median"
         and is_num(h["weight"]) and 0 <= h["weight"] <= 1 and is_int(h["window"]) and h["window"] >= 0
         and is_int(h["minGroup"]) and h["minGroup"] >= 1 and table(h["scale"], SCORED, lambda v: is_num(v) and v > 0)
         and is_num(h["missing"]) and 0 <= h["missing"] <= 100
         and obj(age, ("min", "max", "exp")) and all(is_num(age[k]) for k in age)
         and 0 < age["min"] <= age["max"] and age["exp"] >= 0,
         "的 heat 要是 {method: \"era-median\", weight: 0–1, window: 非负整数, minGroup: 正整数, scale: {来源: 正数}, "
         "missing: 0–100, age: {min: >0, max: ≥min, exp: ≥0}}")
    pl = sc.get("players")
    need(obj(pl, ("neutral", "prior", "cap")) and is_num(pl["neutral"]) and 1 <= pl["neutral"] <= 5
         and is_num(pl["prior"]) and pl["prior"] >= 0 and is_num(pl["cap"]) and pl["cap"] >= 0,
         "的 players 要是 {neutral: 1–5, prior: ≥0, cap: ≥0}")
    cv = sc.get("curve")
    pts = cv.get("points") if obj(cv, ("on", "points")) and cv["on"] == "composite" else None
    need(isinstance(pts, list) and len(pts) >= 2 and all(isinstance(q, list) and len(q) == 2 and all(map(is_num, q)) for q in pts)
         and all(a[0] < b[0] and a[1] <= b[1] for a, b in zip(pts, pts[1:])) and 0 <= pts[0][1] and pts[-1][1] <= 100,
         "的 curve 要是 {on: \"composite\", points: [[综合分, 最终分]…]}，综合分严格递增、最终分不减、在 0–100")
    bands = sc.get("bands")
    band_min = {}
    if need(isinstance(bands, list) and len(bands) >= 3
            and all(isinstance(b, list) and len(b) == 2 and isinstance(b[0], str) and b[0] and is_num(b[1]) for b in bands),
            "的 bands 要是 [[档名, 最低分]…]"):
        labels, band_min = [b[0] for b in bands], dict(bands)
        need(labels[:2] == ["神作", "神作提名"], "的 bands 前两档要是 神作、神作提名（只由神作名单 / 投票和提名门槛给）")
        need(len(set(labels)) == len(labels), "的 bands 档名重复")
        need(all(a[1] > b[1] for a, b in zip(bands, bands[1:])) and bands[-1][1] == 0, "的 bands 最低分要从高到低排、最后一档是 0")
    cap, nm, cn = sc.get("cap"), sc.get("nominee"), sc.get("canon")
    need(obj(cap, ("max",)) and is_num(cap["max"]) and 0 < cap["max"] < band_min.get("神作提名", 100),
         "的 cap 要是 {max: 分}，比神作提名的最低分小（神作和神作提名以外的作品都封顶在 max）")
    ps = nm.get("praiseSources") if isinstance(nm, dict) else None
    if need(obj(nm, ("score", "minF0", "praiseSources", "others", "second", "benchmark", "benchmarkPct"))
            and nm["score"] == band_min.get("神作提名") and is_num(nm["minF0"]) and 0 <= nm["minF0"] <= 100
            and isinstance(ps, list) and ps and len(set(ps)) == len(ps) and all(s in RATING_SRCS for s in ps)
            and is_int(nm["others"]) and 0 <= nm["others"] <= 3
            and obj(nm["second"], ("R", "e")) and is_num(nm["second"]["R"]) and is_num(nm["second"]["e"]) and nm["second"]["e"] >= 0
            and isinstance(nm["benchmark"], str) and nm["benchmark"] != ""
            and is_num(nm["benchmarkPct"]) and 0 <= nm["benchmarkPct"] <= 1,
            "的 nominee 要是 {score: 神作提名档的最低分, minF0: 0–100, praiseSources: [社区…], others: 0–3, "
            "second: {R: 数, e: ≥0}, benchmark: 基准作品 id, benchmarkPct: 0–1}"):
        need(ids is None or nm["benchmark"] in ids, f"的 nominee.benchmark（{nm['benchmark']}）不在作品资料里")
    gt = sc.get("gates")
    if need(isinstance(gt, dict) and obj({k: v for k, v in gt.items() if k != "praiseTopBySource"}, ("praiseTop", "community")),
            "的 gates 要是 {praiseTop, community, praiseTopBySource（可以没有）}"):
        top, tb = gt["praiseTop"], gt.get("praiseTopBySource", {})
        need(isinstance(tb, dict) and set(tb) <= set(RATING_SRCS)
             and all(obj(v, ("rating", "raters")) and isinstance(v["rating"], dict) and isinstance(v["raters"], dict)
                     and set(v["rating"]) == set(v["raters"]) and set(v["rating"]) <= set(SCORED)
                     and all(is_num(x) for x in v["rating"].values()) and all(is_int(n) and n >= 1 for n in v["raters"].values())
                     for v in tb.values()),
             "的 gates.praiseTopBySource（可以没有）要是 {社区: {rating: {来源: 数}, raters: {来源: 正整数}}}，两张表的来源一样，"
             f"来源是 {' / '.join(SCORED)}（没写的来源用 gates.praiseTop）")
        need(obj(top, ("rating", "raters")) and isinstance(top["rating"], dict) and isinstance(top["raters"], dict)
             and set(top["rating"]) == set(top["raters"]) and set(top["rating"]) <= set(RATING_SRCS)
             and all(is_num(v) for v in top["rating"].values()) and all(is_int(n) and n >= 1 for n in top["raters"].values()),
             "的 gates.praiseTop 要是 {rating: {社区: 数}, raters: {社区: 正整数}}，两张表的社区一样（神作提名的原始评分线和人数线）")
        c = gt["community"]
        need(obj(c, ("minAvg", "minCount")) and is_num(c["minAvg"]) and 1 <= c["minAvg"] <= 5
             and is_int(c["minCount"]) and c["minCount"] >= 1, "的 gates.community 要是 {minAvg: 1–5, minCount: 正整数}")
    need(obj(cn, ("rulesVersion", "minScore", "promote", "demote", "cooldownDays", "reasonRequired", "reasonMinChars"))
         and is_int(cn["rulesVersion"]) and cn["rulesVersion"] >= 1 and cn["minScore"] == band_min.get("神作")
         and obj(cn["promote"], ("minVoters", "support")) and obj(cn["demote"], ("minVoters", "oppose"))
         and all(is_int(cn[k]["minVoters"]) and cn[k]["minVoters"] >= 1 for k in ("promote", "demote"))
         and all(is_num(cn[k][f]) and 0 < cn[k][f] <= 1 for k, f in (("promote", "support"), ("demote", "oppose")))
         and is_int(cn["cooldownDays"]) and cn["cooldownDays"] >= 0 and cn["reasonRequired"] in REASON_RULES
         and is_int(cn["reasonMinChars"]) and cn["reasonMinChars"] >= 0,
         "的 canon 要是 {rulesVersion: 正整数, minScore: 神作档的最低分, promote: {minVoters: 正整数, support: 0–1}, "
         "demote: {minVoters: 正整数, oppose: 0–1}, cooldownDays: 非负整数, reasonRequired: oppose / all / none, reasonMinChars: 非负整数}")
    dv = sc.get("development")
    need(obj(dv, ("name", "field")) and all(isinstance(dv[k], str) and dv[k] for k in ("name", "field")),
         "的 development 要是 {name: 榜名, field: 字段名}")
    hg = sc.get("hiddenGems")  # 冷门佳作榜（可以没有）
    if hg is not None:
        need(obj(hg, ("name", "rating", "raters", "sortBy", "limit")) and isinstance(hg["name"], str) and hg["name"].strip() != ""
             and table(hg["rating"], SCORED, is_num)
             and table(hg["raters"], SCORED, lambda v: span(v) and all(is_int(n) and n >= 1 for n in v))
             and hg["sortBy"] in GEM_SORTS and is_int(hg["limit"]) and hg["limit"] >= 1,
             "的 hiddenGems 要是 {name: 榜名, rating: {来源: 数}, raters: {来源: [下限, 上限]（正整数，下限 < 上限）}, "
             f"sortBy: {' / '.join(GEM_SORTS)}, limit: 正整数}}")
    bl = sc.get("blacklist")  # 社区黑榜的标注线（可以没有：不标注）
    if bl is not None:
        need(obj(bl, ("minVoters", "minShare")) and is_int(bl["minVoters"]) and bl["minVoters"] >= 1
             and is_num(bl["minShare"]) and 0 < bl["minShare"] <= 1,
             "的 blacklist 要是 {minVoters: 正整数, minShare: 0–1}")
    return out


def canon_problems(canon, ids):
    """神作名单 canon：{作品 id: {"by": "manual" 或 "vote", "since": "YYYY-MM-DD", "note": 说明（可以没有）}}，作品要在资料里"""
    if not isinstance(canon, dict):
        return ["canon 不是对象（作品 id → {by, since, note}）"]
    out = []
    for wid, v in canon.items():
        if wid not in ids:
            out.append(f"canon 里的 {wid} 不在作品资料里")
        if not (isinstance(v, dict) and {"by", "since"} <= set(v) <= {"by", "since", "note"} and v["by"] in ("manual", "vote")
                and is_date(v["since"]) and ("note" not in v or isinstance(v["note"], str))):
            out.append(f"canon 的 {wid} 要是 {{\"by\": \"manual\" 或 \"vote\", \"since\": \"YYYY-MM-DD\", \"note\": 说明（可选）}}")
    return out

def check(path, min_updated, min_revision=0):
    problems, notes = [], []
    try:
        z = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile):
        return ["不是有效的数据包（.zip）"], notes
    with z:
        infos = z.infolist()
        if len(infos) > MAX_ENTRIES:
            return [f"文件太多：{len(infos)} 个，上限 {MAX_ENTRIES}"], notes
        cat_info = next((i for i in infos if entry_target(i.filename) == "catalog.json"), None)
        if cat_info is None:
            return ["包里没有 catalog.json"], notes
        raw = read_limited(z, cat_info, MAX_FILE)
        if raw is None:
            return ["catalog.json 超过 50 MiB"], notes

        # 解压时的检查：只算软件认的文件
        total, cover_files, skipped = 0, set(), []
        for info in infos:
            target = entry_target(info.filename)
            if target is None:
                if not info.is_dir():
                    skipped.append(info.filename)
                continue
            data = raw if info is cat_info else read_limited(z, info, MAX_FILE)
            if data is None:
                problems.append(f"{info.filename} 超过 50 MiB")
                continue
            total += len(data)
            if target != "catalog.json":
                cover_files.add(target)
        if total > MAX_TOTAL:
            problems.append(f"解压后共 {total / 1024 / 1024:.0f} MiB，超过 1 GiB")
        if skipped:
            notes.append(f"软件会跳过的文件 {len(skipped)} 个：{skipped[:5]}{' …' if len(skipped) > 5 else ''}")

    # 导入时对 catalog.json 的检查（不合格整包拒绝）
    if raw.startswith(b"\xef\xbb\xbf"):
        problems.append("catalog.json 带 BOM（软件能读，但约定不带）")
    try:
        cat = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        return problems + ["catalog.json 读不懂（不是 UTF-8 的 JSON）"], notes
    games = cat.get("games") if isinstance(cat, dict) else None
    if not isinstance(games, list):
        return problems + ["catalog.json 的 games 不是数组"], notes
    covers = set()
    for n, g in enumerate(games):
        gid = g.get("id") if isinstance(g, dict) else None
        if not isinstance(gid, str) or not gid.strip():
            problems.append(f"games[{n}] 缺少 id")
            continue
        for key, folder in (("cover", "covers/"), ("thumb", "thumbs/")):  # thumb 是卡片用的缩略图
            cover = g.get(key)
            if cover is None or cover == "":
                continue
            if not isinstance(cover, str) or entry_target(cover) != cover or not cover.startswith(folder):
                problems.append(f"{gid} 的 {key} 不合规：{cover!r}")
            elif cover not in cover_files:
                problems.append(f"{gid} 的{'封面' if key == 'cover' else '缩略图'} {cover} 不在包里")
            else:
                covers.add(cover)
    version = cat.get("version")
    if not is_int(version) or version > CATALOG_VERSION:
        problems.append(f"version 是 {version!r}，软件只认到 {CATALOG_VERSION}")
    updated = cat.get("updated")
    revision = cat.get("revision", 0)  # 同一天的资料用 revision 分新旧，没有就是 0
    if not (is_int(revision) and revision >= 0):
        problems.append(f"revision 要是 0 或正整数：{revision!r}")
    if not isinstance(updated, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", updated):
        problems.append(f"updated 要写成 YYYY-MM-DD：{updated!r}")
    elif min_updated and is_int(revision) and (updated, revision) < (min_updated, min_revision):
        problems.append(f"资料 {updated} revision {revision} 比软件自带的 {min_updated} revision {min_revision} 旧，软件不会导入")

    # 资料格式（软件不会因此拒收，但会显示不对）
    ids = [g.get("id") for g in games if isinstance(g, dict)]
    dup = sorted({i for i in ids if ids.count(i) > 1}, key=str)
    if dup:
        problems.append(f"id 重复：{dup}")
    genres = cat.get("genres", {})
    if not isinstance(genres, dict):
        problems.append("genres 不是对象（题材 id → 各语言名称）")
        genres = {}
    for gid, names in genres.items():
        if not (gid.isdigit() and isinstance(names, dict) and all(isinstance(names.get(k), str) and names[k] for k in LANGS)):
            problems.append(f"题材 {gid!r} 格式不对：要有 {', '.join(LANGS)} 三个名称")
    tagged, signals, povs, aliased, flagged = 0, {}, {}, 0, 0
    for g in games:
        if not isinstance(g, dict) or not g.get("id"):
            continue
        if g.get("cat") not in CATS:
            problems.append(f"{g.get('id')} 的 cat 不合法：{g.get('cat')!r}")
        src = g.get("src")
        if src not in SRCS:
            problems.append(f"{g.get('id')} 的 src 不合法：{src!r}（要是 {', '.join(sorted(SRCS))} 之一）")
        elif src == "dlsite":
            if not str(g.get("url", "")).startswith("https://"):
                problems.append(f"{g.get('id')} 是 DLsite 作品，url 要是 https 链接：{g.get('url')!r}")
        elif src in ("cien", "fanbox"):  # 赞助站：支持页链接可有可无，有就要是 https
            if g.get("url") and not str(g["url"]).startswith("https://"):
                problems.append(f"{g.get('id')} 的 url 要是 https 链接：{g.get('url')!r}")
        elif g.get("url"):  # 其他来源不写 url；rate / dl / rc 可以没有或 null
            problems.append(f"{g.get('id')} 的来源是 {src}，不该有 url")
        if "also" in g and not (isinstance(g["also"], list) and all(s in SRCS for s in g["also"])):
            problems.append(f"{g.get('id')} 的 also 要是来源数组")
        if "aliases" in g:
            if aliases_ok(g["aliases"]):
                aliased += 1
            else:
                problems.append(f"{g.get('id')} 的 aliases 要是非空字符串的数组（不重复）")
        if "genres" in g:
            if src != "dlsite":
                problems.append(f"{g.get('id')} 的来源是 {src}，只有 DLsite 的作品写 genres")
            if not (isinstance(g["genres"], list) and all(isinstance(x, str) and x in genres for x in g["genres"])):
                problems.append(f"{g.get('id')} 的 genres 要是字符串数组，每个 id 都要在 genres 字典里")
            else:
                tagged += 1
        for problem in (signal_problem(g), pov_problem(g), community_problem(g), godvote_problem(g), blacklist_problem(g),
                        raw_problem(g) if src == "dlsite" else None):
            if problem:
                problems.append(f"{g.get('id')} {problem}")
        if g.get("pov") in POVS:
            povs[g["pov"]] = povs.get(g["pov"], 0) + 1
        for key in list(SIGNALS) + list(RATED) + ["community", "godvote", "blacklist"]:
            if g.get(key) is not None:
                signals[key] = signals.get(key, 0) + 1
        if isinstance(g.get("blacklist"), dict) and g["blacklist"].get("flagged") is True:
            flagged += 1

    rankings = cat.get("rankings", [])
    rk_items = rk_rj = rk_hit = 0
    if not isinstance(rankings, list):
        problems.append("rankings 不是数组")
        rankings = []
    id_set = set(ids)
    for r in rankings:
        rid = r.get("id") if isinstance(r, dict) else None
        if not isinstance(r, dict) or not isinstance(r.get("items"), list):
            problems.append(f"榜单 {rid} 格式不对")
            continue
        if not str(r.get("url", "")).startswith("https://"):
            problems.append(f"榜单 {rid} 的 url 不是 https")
        for it in r["items"]:
            rk_items += 1
            if not isinstance(it, dict) or not it.get("title"):
                problems.append(f"榜单 {rid} 有条目没有 title")
                continue
            if not (is_int(it.get("rank")) and it["rank"] > 0):
                problems.append(f"榜单 {rid} 有 rank 不是正整数：{it.get('rank')!r}")
            if "url" in it and not str(it["url"]).startswith("https://"):
                problems.append(f"榜单 {rid} 有条目 url 不是 https：{it['url']!r}")
            if it.get("rj") is not None:
                rk_rj += 1
                # rj 是作品 id（RJ 号、vndb-v…、steam-… 都行），软件按原样去对作品，超过 40 个字符会被截掉
                if not (isinstance(it["rj"], str) and len(it["rj"]) <= 40 and NAME_OK.fullmatch(it["rj"])):
                    problems.append(f"榜单 {rid} 有 rj 格式不对：{it['rj']!r}")
                elif it["rj"] in id_set:
                    rk_hit += 1

    scoring, canon = cat.get("scoring"), cat.get("canon")
    if scoring is not None:
        problems.extend(scoring_problems(scoring, id_set))
    if canon is not None:
        problems.extend(canon_problems(canon, id_set))

    srcs = {}
    for g in games:
        if isinstance(g, dict):
            srcs[g.get("src")] = srcs.get(g.get("src"), 0) + 1
    notes.insert(0, f"资料日期 {updated}（revision {revision}），作品 {len(games)} 部（{', '.join(f'{k} {v}' for k, v in sorted(srcs.items(), key=lambda kv: -kv[1]))}），"
                    f"封面 {sum(c.startswith('covers/') for c in covers)} 张、缩略图 {sum(c.startswith('thumbs/') for c in covers)} 张（包里图片 {len(cover_files)} 张）")
    notes.insert(1, f"榜单 {len(rankings)} 个、{rk_items} 条，带 rj 的 {rk_rj} 条，对得上作品的 {rk_hit} 条")
    notes.insert(2, f"题材标签 {len(genres)} 个，带题材的作品 {tagged} 部（DLsite 作品 {srcs.get('dlsite', 0)} 部）")
    notes.insert(3, "分数信号：" + "，".join(f"{key} {signals.get(key, 0)} 部（{src} 作品 {srcs.get(src, 0)} 部）"
                                          for key, src in SIGNALS.items()))
    notes.insert(4, f"VNDB 评分 vndb {signals.get('vndb', 0)} 部，Bangumi 评分 bgm {signals.get('bgm', 0)} 部，"
                    f"社区评分 community {signals.get('community', 0)} 部，神作复议票 godvote {signals.get('godvote', 0)} 部，"
                    f"社区黑榜 blacklist {signals.get('blacklist', 0)} 部（标注多人拉黑 {flagged} 部）；"
                    f"主角视角 pov {sum(povs.values())} 部（{'，'.join(f'{k} {povs.get(k, 0)}' for k in POVS)}）；别名 aliases {aliased} 部")
    recipe = f"{scoring.get('name')} version {scoring.get('version')}" if isinstance(scoring, dict) else "没有（用软件自带的）"
    notes.insert(5, f"综合榜配方：{recipe}；神作名单 {len(canon) if isinstance(canon, dict) else 0} 部")
    undated = 0
    for g in games:  # 发售日不可用的已发售作品：有人气数也不给新作补偿（见 README「综合榜配方」）
        if isinstance(g, dict) and g.get("state") != "dev" and g.get("src") in SCORED:
            try:
                ok = datetime.date.fromisoformat(g.get("date") or "") <= datetime.date.fromisoformat(updated)
            except (TypeError, ValueError):
                ok = False
            undated += not ok
    notes.append(f"发售日缺失 / 不合法 / 晚于资料日期的已发售作品 {undated} 部（不给新作补偿）")
    if len(cover_files) > len(covers):
        notes.append(f"有 {len(cover_files) - len(covers)} 张图片没有作品用到")
    return problems, notes


def main():
    ap = argparse.ArgumentParser(description="检查碧翠子禁书库数据包")
    ap.add_argument("pack", type=Path)
    ap.add_argument("--min-updated", help="软件自带资料的日期 YYYY-MM-DD")
    ap.add_argument("--min-revision", type=int, default=0, help="软件自带资料的 revision（同一天时比它）")
    args = ap.parse_args()
    problems, notes = check(args.pack, args.min_updated, args.min_revision)
    for n in notes:
        print(n)
    if problems:
        print("检查不通过：\n  " + "\n  ".join(problems))
        return 1
    print("检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
