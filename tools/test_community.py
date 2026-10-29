"""community.py 的黑榜部分和 check_pack.py 对应的检查：py -m unittest discover -s tools（不读写 data/ 以外的东西，不改 data/）"""
import datetime
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_pack import build_catalog  # noqa: E402
from check_pack import blacklist_problem, scoring_problems  # noqa: E402
from community import Source, aggregate, extract, place, settle_blacklist, spam_reason  # noqa: E402

RULES = {"reasonRequired": "oppose", "reasonMinChars": 20}
IDS = {"RJ1", "RJ2", "RJ3"}
DAY = datetime.date(2026, 11, 1)


def sub(ratings=None, votes=None, blacklist=None, kind="beatrice-ratings-submission"):
    obj = {"kind": kind, "version": 1, "app": "x", "catalog": "2026-10-29", "ratings": ratings or {}}
    if votes is not None:
        obj["votes"] = votes
    if blacklist is not None:
        obj["blacklist"] = blacklist
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
