"""旧 id 对照表：格式、作品引用、打包和包内检查。"""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import build_pack
from check_pack import check, moved_problems


IDS = {"steam-1", "steam-2"}
BAD = [None, [], "旧 id", 1, False,
       {"": "steam-1"}, {"  ": "steam-1"},
       {"old": ""}, {"old": "  "}, {"old": None}, {"old": 1}, {"old": []}, {"old": {}},
       {"steam-2": "steam-1"}, {"old": "missing"}, {"steam-1": "steam-1"},
       {"old": "middle", "middle": "steam-1"},
       {"a": "b", "b": "a"}, {"a": "b", "b": "c", "c": "a"}]


class Moved(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.write("meta.json", {"version": 2, "updated": "2026-10-30"})
        self.write("adv.json", [{"id": wid, "src": "steam", "cat": "adv"} for wid in sorted(IDS)])
        data_patch = patch.object(build_pack, "DATA", self.data)
        data_patch.start()
        self.addCleanup(data_patch.stop)

    def write(self, name, value):
        (self.data / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def check_catalog(self, catalog):
        pack = self.root / "pack.zip"
        with zipfile.ZipFile(pack, "w") as z:
            z.writestr("catalog.json", json.dumps(catalog, ensure_ascii=False))
        return check(pack, None)

    def test_valid(self):
        for moved in ({"old": "steam-1"}, {"old": "steam-1", "older": "steam-1", "other": "steam-2"}):
            with self.subTest(moved=moved):
                self.assertEqual(moved_problems(moved, IDS), [])
                self.write("moved.json", moved)
                catalog = build_pack.build_catalog()
                self.assertEqual(catalog["moved"], moved)
                problems, notes = self.check_catalog(catalog)
                self.assertEqual(problems, [])
                self.assertIn(f"旧 id → 新 id 对照 moved {len(moved)} 条", notes)

    def test_missing_and_empty(self):
        catalog = build_pack.build_catalog()
        self.assertNotIn("moved", catalog)
        self.assertEqual(self.check_catalog(catalog)[0], [])
        self.write("moved.json", {})
        self.assertEqual(moved_problems({}, IDS), [])
        self.assertEqual(build_pack.build_catalog(), catalog)
        problems, notes = self.check_catalog({**catalog, "moved": {}})
        self.assertEqual(problems, [])
        self.assertIn("旧 id → 新 id 对照 moved 0 条", notes)

    def test_invalid(self):
        catalog = build_pack.build_catalog()
        for moved in BAD:
            with self.subTest(moved=moved):
                self.assertTrue(moved_problems(moved, IDS))
                self.write("moved.json", moved)
                with self.assertRaisesRegex(ValueError, "data/moved.json"):
                    build_pack.build_catalog()
                problems, _ = self.check_catalog({**catalog, "moved": moved})
                self.assertTrue(any(p.startswith("moved ") for p in problems), problems)

    def test_non_string_key(self):
        # JSON 的对象键只能是字符串；函数本身也要拒绝别的类型。
        for old in (None, 1, False):
            with self.subTest(old=old):
                self.assertTrue(moved_problems({old: "steam-1"}, IDS))

    def test_chain_and_cycle_reported(self):
        # 即使目标是否存在的检查也会失败，仍要明确报告链和环。
        for moved in ({"a": "b", "b": "steam-1"}, {"a": "b", "b": "a"}):
            with self.subTest(moved=moved):
                self.assertTrue(any("链或环" in p for p in moved_problems(moved, IDS)))


if __name__ == "__main__":
    unittest.main()
