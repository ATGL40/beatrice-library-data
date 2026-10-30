"""community.py 的黑榜、识别报告、标签报告部分和 check_pack.py 对应的检查：py -m unittest discover -s tools（不读写 data/ 以外的东西，不改 data/）"""
import datetime
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_pack import build_catalog  # noqa: E402
from check_pack import blacklist_problem, scoring_problems  # noqa: E402
from community import Source, aggregate, extract, extract_recognition, extract_tags, place, settle_blacklist, spam_reason, write_reasons  # noqa: E402

RULES = {"reasonRequired": "oppose", "reasonMinChars": 20}
IDS = {"RJ1", "RJ2", "RJ3"}
DAY = datetime.date(2026, 11, 1)


def sub(ratings=None, votes=None, blacklist=None, kind="beatrice-ratings-submission", recognition=None, tags=None):
    obj = {"kind": kind, "version": 1, "app": "x", "catalog": "2026-10-29", "ratings": ratings or {}}
    if votes is not None:
        obj["votes"] = votes
    if blacklist is not None:
        obj["blacklist"] = blacklist
    if recognition is not None:
        obj["recognition"] = recognition
    if tags is not None:
        obj["tags"] = tags
    return obj


def src(key, when, obj):
    return Source(key, when, f"{key}.json", json.dumps(obj, ensure_ascii=False), None, "邮件 / 文件")


def catalog(old=None, rule=None):
    """settle_blacklist 只看 scoring.blacklist、canon.cooldownDays 和作品上旧的 blacklist"""
    scoring = {"canon": {"cooldownDays": 90}}
    if rule is not None:
        scoring["blacklist"] = rule
    return {"scoring": scoring, "games": [{"id": i, **({"blacklist": old[i]} if old and i in old else {})} for i in sorted(IDS)]}


RULE = {"minVoters": 5, "minShare": 0.3}


class Extract(unittest.TestCase):
    def test_blacklist_entries(self):
        ratings, votes, black, unknown, bad, drops = extract(
            sub({"RJ1": 4}, blacklist={"RJ2": {"reason": "  踩雷  ", "x": 1}, "RJ3": {}, "RJ9": {}, "RJ1": "坏", "RJ4": {"reason": 3}}),
            IDS, RULES)
        self.assertEqual(black, {"RJ2": "踩雷", "RJ3": ""})
        self.assertEqual(ratings, {"RJ1": 4})
        self.assertEqual(len(drops), 3)
        self.assertTrue(all(d.startswith("黑榜 ") for d in drops))

    def test_old_submissions_and_marks_files(self):
        self.assertEqual(extract(sub({"RJ1": 5}), IDS, RULES)[2], {})  # 旧版软件：没有 blacklist
        marks = {"kind": "beatrice-marks", "version": 1, "marks": {"RJ1": {"score": 3}}, "blacklist": {"RJ2": {}}}
        self.assertEqual(extract(marks, IDS, RULES)[2], {})  # 普通评分文件不看 blacklist

    def test_bad_shape(self):
        with self.assertRaises(ValueError):
            extract(sub({"RJ1": 4}, blacklist=["RJ2"]), IDS, RULES)

    def test_spam(self):
        self.assertIsNone(spam_reason({"RJ1": 4}, {"RJ2": ""}))
        self.assertIn("黑榜", spam_reason({}, {f"RJ{i}": "" for i in range(2001)}))


class Aggregate(unittest.TestCase):
    def test_counts_dedup_and_participants(self):
        sources = [
            src("a", 1, sub({"RJ1": 1}, blacklist={"RJ1": {"reason": "旧的"}})),
            src("a", 2, sub({"RJ2": 4}, blacklist={"RJ1": {"reason": "新的理由"}})),  # 同一个投票人：新的顶掉旧的
            src("b", 1, sub(blacklist={"RJ1": {}})),  # 只有黑榜也收
            src("c", 1, sub({"RJ1": 5})),
            src("d", 1, sub({}, votes={"RJ1": {"vote": "support"}})),
            src("e@x.com", 1, sub({"RJ1": 2}, blacklist={"RJ1": {}})),
        ]
        voters = {"e@x.com": "c"}  # e 和 c 是同一个人：取新的（时间一样时按名字）
        community, tally, black, reasons, used, dropped, notes, replaced = aggregate(sources, IDS, voters, RULES)
        # RJ1：拉黑的 a、b、c(e)；参与的 a、b、c(e)、d
        self.assertEqual(black, {"RJ1": (3, 4)})
        self.assertEqual([r[5] for r in reasons if r[1] == "black"], ["新的理由"])
        self.assertEqual(replaced, 2)
        self.assertEqual(dropped, [])

    def test_empty_submission_dropped(self):
        *_, dropped, _, _ = aggregate([src("a", 1, sub(blacklist={"RJ9": {}}))], IDS, {}, RULES)
        self.assertEqual(len(dropped), 1)


class Recognition(unittest.TestCase):
    REP = {"folder": "汉化\\Velmorin v1.2", "exes": ["Game.exe", 3], "titles": ["Velmorin"], "names": ["Velmorin v1.2"], "rjs": [],
           "matched": "RJ1", "rule": "folder", "reason": "", "correct": "RJ2", "date": "2026-10-29", "path": "C:\\x", "user": "alice"}

    def test_whitelist_and_paths(self):
        bad = [{"folder": "C:\\Users\\alice\\Games\\x"}, {"folder": "\\\\nas\\share"}, {"folder": "/home/a"}, "坏", {"exes": []}]
        reps, drops = extract_recognition(sub(recognition=[self.REP, {**self.REP, "matched": "RJ9", "rule": "?", "date": "x"}] + bad), IDS)
        self.assertEqual(reps[0], {"folder": "汉化\\Velmorin v1.2", "exes": ["Game.exe"], "titles": ["Velmorin"], "names": ["Velmorin v1.2"],
                                   "rjs": [], "rule": "folder", "reason": "", "date": "2026-10-29", "matched": "RJ1", "correct": "RJ2"})
        self.assertNotIn("matched", reps[1])  # 资料里没有的作品 id 不留
        self.assertEqual((reps[1]["rule"], reps[1]["date"]), ("unknown", ""))
        self.assertEqual(len(reps), 2)
        self.assertEqual(len(drops), 5)
        self.assertEqual(extract_recognition({"kind": "beatrice-marks", "recognition": [self.REP]}, IDS), ([], []))
        with self.assertRaises(ValueError):
            extract_recognition(sub(recognition={"folder": "x"}), IDS)

    def test_only_reports_accepted_and_written_locally(self):
        community, tally, black, reasons, used, dropped, notes, replaced = aggregate(
            [src("a", 1, sub(recognition=[self.REP]))], IDS, {}, RULES)
        self.assertEqual((dropped, community), ([], {}))
        self.assertEqual([r[1] for r in reasons], ["recog"])
        out = Path(__file__).resolve().parent.parent / "submissions" / "_test_reasons.md"
        try:
            write_reasons(out, reasons, {}, {"RJ1": "维尔莫林", "RJ2": "另一部"}, DAY)
            text = out.read_text(encoding="utf-8")
        finally:
            out.unlink(missing_ok=True)
        self.assertIn("# 识别报告（本地，不发布）", text)
        self.assertIn("## 认成 维尔莫林（RJ1）", text)
        self.assertIn("文件夹 `汉化\\Velmorin v1.2` · 凭 folder，应该是 另一部（RJ2）", text)


class Tags(unittest.TestCase):
    GENRES = {"070": {"ja": "触手", "zh": "触手", "en": "Tentacles"}, "400": {"ja": "学生", "zh": "学生", "en": "Student"},
              "206": {"ja": "少女", "zh": "少女", "en": "Girl"}, "900": {"ja": "x", "zh": "x", "en": "x", "hidden": True}}

    def test_cleaning(self):
        reps, drops = extract_tags(sub(tags={
            "RJ1": {"wrong": ["070", "070", "206", "999", 3], "missing": ["400", "070", "900"], "note": "  标签\n不对  " + "字" * 300,
                    "date": "2026-10-30", "user": "alice"},
            "RJ2": {"wrong": ["206"], "missing": [], "date": "x"},  # 只剩年龄类：整条丢掉
            "RJ3": {"note": "只有说明也收"}, "RJ9": {"wrong": ["070"]}, "RJ4": "坏"}), IDS | {"RJ4"}, self.GENRES)
        self.assertEqual(reps["RJ1"]["wrong"], ["070"])
        self.assertEqual(reps["RJ1"]["missing"], ["400"])  # 和 wrong 重复的、hidden 的去掉
        self.assertEqual(len(reps["RJ1"]["note"]), 200)
        self.assertTrue(reps["RJ1"]["note"].startswith("标签 不对 字"))
        self.assertEqual(set(reps["RJ1"]), {"wrong", "missing", "note", "date"})
        self.assertEqual(reps["RJ3"], {"wrong": [], "missing": [], "note": "只有说明也收", "date": ""})
        self.assertEqual(sorted(reps), ["RJ1", "RJ3"])
        self.assertEqual(len(drops), 4)  # RJ1 去掉的题材 id、RJ2、RJ9、RJ4
        self.assertTrue(all(d.startswith("标签报告") for d in drops))
        self.assertEqual(extract_tags({"kind": "beatrice-marks", "tags": {"RJ1": {"wrong": ["070"]}}}, IDS, self.GENRES), ({}, []))
        with self.assertRaises(ValueError):
            extract_tags(sub(tags=[{"wrong": ["070"]}]), IDS, self.GENRES)

    def test_bad_field_drops_submission_and_latest_wins(self):
        sources = [src("a", 1, sub(tags={"RJ1": {"wrong": ["070"]}})), src("a", 2, sub(tags={"RJ2": {"missing": ["400"], "date": "2026-10-30"}})),
                   src("b", 1, sub({"RJ1": 4}, tags="坏"))]
        community, tally, black, reasons, used, dropped, notes, replaced = aggregate(sources, IDS, {}, RULES, self.GENRES)
        self.assertEqual([r[0] for r in reasons if r[1] == "tags"], ["RJ2"])  # 只有标签报告也收；新的顶掉旧的
        self.assertEqual([d[0] for d in dropped], ["b.json"])  # tags 不是对象：整份不要
        self.assertEqual(community, {})

    def test_written_locally(self):
        sources = [src("a", 1, sub(tags={"RJ1": {"wrong": ["070"], "missing": ["400"], "note": "其实没有触手", "date": "2026-10-30"}})),
                   src("b", 1, sub(tags={"RJ1": {"missing": ["400"], "date": "2026-10-29"}}))]
        *_, reasons, _, _, _, _ = aggregate(sources, IDS, {}, RULES, self.GENRES)
        out = Path(__file__).resolve().parent.parent / "submissions" / "_test_tags.md"
        try:
            write_reasons(out, reasons, {}, {"RJ1": "维尔莫林"}, DAY, genres=self.GENRES)
            text = out.read_text(encoding="utf-8")
        finally:
            out.unlink(missing_ok=True)
        self.assertIn("# 标签报告（本地，不发布）", text)
        self.assertIn("## 维尔莫林（RJ1）· 2 人报告", text)
        self.assertIn("- 2026-10-29 · 少了：学生（400）\n- 2026-10-30 · 不对：触手（070）；少了：学生（400）；说明：其实没有触手", text)
        self.assertNotIn("· a ·", text)  # 不写是谁
        self.assertIn("（现在没有写了理由的投票）", text)


class Settle(unittest.TestCase):
    def test_threshold_and_share(self):
        out, moves = settle_blacklist(catalog(rule=RULE), {"RJ1": (5, 10), "RJ2": (5, 20), "RJ3": (4, 4)}, DAY)
        self.assertEqual(out["RJ1"], {"count": 5, "flagged": True, "settled": "2026-11-01", "changed": "2026-11-01"})
        self.assertEqual(out["RJ2"], {"count": 5, "flagged": False, "settled": "2026-11-01"})  # 只占 25%
        self.assertEqual(out["RJ3"], {"count": 4, "flagged": False, "settled": "2026-11-01"})  # 不到 5 人
        self.assertEqual(len(moves), 1)

    def test_no_rule_means_no_flag(self):
        out, _ = settle_blacklist(catalog(), {"RJ1": (50, 50)}, DAY)
        self.assertFalse(out["RJ1"]["flagged"])

    def test_cooldown(self):
        old = {"RJ1": {"count": 9, "flagged": True, "settled": "2026-10-01", "changed": "2026-10-01"},
               "RJ2": {"count": 9, "flagged": True, "settled": "2026-10-01", "changed": "2026-10-01"},
               "RJ3": {"count": 9, "flagged": True, "settled": "2026-01-01", "changed": "2026-01-01"}}
        out, moves = settle_blacklist(catalog(old, RULE), {"RJ1": (2, 10), "RJ3": (2, 10)}, DAY)
        # 冷却中（31 天）：人少了也先不去掉
        self.assertEqual(out["RJ1"], {"count": 2, "flagged": True, "settled": "2026-11-01", "changed": "2026-10-01"})
        # 没人拉黑了：冷却中也马上去掉标注，留着 changed
        self.assertEqual(out["RJ2"], {"count": 0, "flagged": False, "settled": "2026-11-01", "changed": "2026-11-01"})
        # 过了冷却：去掉
        self.assertEqual(out["RJ3"], {"count": 2, "flagged": False, "settled": "2026-11-01", "changed": "2026-11-01"})
        self.assertTrue(any("冷却中" in m for m in moves))
        self.assertTrue(all(blacklist_problem({"blacklist": v}) is None for v in out.values()))

    def test_unflagged_without_people_disappears(self):
        old = {"RJ1": {"count": 1, "flagged": False, "settled": "2026-10-01"}}
        out, _ = settle_blacklist(catalog(old, RULE), {}, DAY)
        self.assertEqual(out, {})


class Place(unittest.TestCase):
    def test_order(self):
        g = {"id": "RJ1", "rc": 3, "blacklist": {"count": 1}, "url": "https://x", "note": ""}
        bl = {"count": 2, "flagged": False, "settled": "2026-11-01"}
        self.assertEqual(list(place(g, {"avg": 4, "count": 1}, None, bl)), ["id", "rc", "community", "blacklist", "url", "note"])
        self.assertEqual(list(place(g, None, None)), ["id", "rc", "url", "note"])


class Checks(unittest.TestCase):
    def test_blacklist_field(self):
        ok = [{"count": 3, "flagged": False, "settled": "2026-11-01"},
              {"count": 7, "flagged": True, "settled": "2026-11-01", "changed": "2026-11-01"},
              {"count": 0, "flagged": False, "settled": "2026-11-01", "changed": "2026-11-01"}]
        bad = [{"count": 0, "flagged": False, "settled": "2026-11-01"}, {"count": 0, "flagged": True, "settled": "2026-11-01", "changed": "2026-11-01"},
               {"count": 3, "flagged": "yes", "settled": "2026-11-01"}, {"count": 3, "flagged": True}, {"count": 3, "flagged": True, "settled": "x"},
               {"count": 3, "flagged": True, "settled": "2026-11-01", "share": 0.5}, [3], {"count": True, "flagged": True, "settled": "2026-11-01"}]
        self.assertTrue(all(blacklist_problem({"blacklist": v}) is None for v in ok))
        self.assertTrue(all(blacklist_problem({"blacklist": v}) for v in bad))
        self.assertIsNone(blacklist_problem({}))

    def test_recipe_block(self):
        sc = build_catalog()["scoring"]  # data/scoring.json 带 blacklist，检查通过
        self.assertEqual(sc["blacklist"], RULE)
        self.assertEqual(scoring_problems(sc), [])
        for b in ({"minVoters": 0, "minShare": 0.3}, {"minVoters": 5, "minShare": 0}, {"minVoters": 5, "minShare": 1.5}, {"minVoters": 5}):
            self.assertTrue(any("blacklist" in p for p in scoring_problems({**sc, "blacklist": b})), b)
        self.assertEqual(scoring_problems({k: v for k, v in sc.items() if k != "blacklist"}), [])  # 可以没有


if __name__ == "__main__":
    unittest.main()
