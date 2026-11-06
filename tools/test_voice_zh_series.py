"""配音、中文和系列：字段格式、合并后检查、原样打包和统计。"""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import build_pack
from check_pack import check, series_problem, series_problems, voice_problem, zh_problem


class VoiceZhSeries(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.games = [{"id": "steam-1", "src": "steam", "cat": "adv"},
                      {"id": "steam-2", "src": "steam", "cat": "adv"}]
        self.write(self.data / "meta.json", {"version": 2, "updated": "2026-11-06"})
        self.save_games()
        data_patch = patch.object(build_pack, "DATA", self.data)
        data_patch.start()
        self.addCleanup(data_patch.stop)

    def write(self, path, value):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def save_games(self):
        self.write(self.data / "adv.json", self.games)

    def check_catalog(self, catalog):
        pack = self.root / "pack.zip"
        with zipfile.ZipFile(pack, "w") as z:
            z.writestr("catalog.json", json.dumps(catalog, ensure_ascii=False))
        return check(pack, None)

    def test_missing(self):
        for validate in (voice_problem, zh_problem, series_problem):
            self.assertIsNone(validate({}))
        self.assertEqual(series_problems(self.games), [])
        catalog = build_pack.build_catalog()
        self.assertEqual(catalog["games"], self.games)
        problems, notes = self.check_catalog(catalog)
        self.assertEqual(problems, [])
        self.assertIn("有配音 0 部，无配音 0 部，官方中文 0 部，民间汉化 0 部，同系列 0 部、0 个系列", notes)

    def test_valid_and_stats(self):
        for n, (voice, zh) in enumerate(((True, "official"), (False, "fan"))):
            self.games[n].update(voice=voice, zh=zh, series=" 不存在的作品 / 系列键 ")
            self.assertIsNone(voice_problem(self.games[n]))
            self.assertIsNone(zh_problem(self.games[n]))
            self.assertIsNone(series_problem(self.games[n]))
        self.save_games()
        catalog = build_pack.build_catalog()
        self.assertEqual(catalog["games"], self.games)
        problems, notes = self.check_catalog(catalog)
        self.assertEqual(problems, [])
        self.assertIn("有配音 1 部，无配音 1 部，官方中文 1 部，民间汉化 1 部，同系列 2 部、1 个系列", notes)

    def test_invalid_fields(self):
        cases = (("voice", voice_problem, [None, 0, 1, 1.0, "true", "false", [], {}]),
                 ("zh", zh_problem, [None, True, False, 1, [], {}, "", "zh", "OFFICIAL", "official "]),
                 ("series", series_problem, [None, True, False, 1, [], {}, "", " \t\n"]))
        baseline = build_pack.build_catalog()
        extra = self.root / "extra.json"
        for key, validate, values in cases:
            for value in values:
                with self.subTest(key=key, value=value):
                    self.assertTrue(validate({key: value}))
                    bad = {**self.games[0], key: value}
                    self.write(self.data / "adv.json", [bad, self.games[1]])
                    with self.assertRaisesRegex(ValueError, key):
                        build_pack.build_catalog()
                    self.save_games()
                    self.write(extra, {"games": [{**bad, "id": "steam-extra"}]})
                    with self.assertRaisesRegex(ValueError, key):
                        build_pack.build_catalog([extra])
                    problems, _ = self.check_catalog({**baseline, "games": [bad, self.games[1]]})
                    self.assertTrue(any(key in p for p in problems), problems)

    def test_single_series(self):
        self.games[0]["series"] = "single"
        self.save_games()
        self.assertTrue(series_problems(self.games))
        with self.assertRaisesRegex(ValueError, "series.*single"):
            build_pack.build_catalog()
        problems, _ = self.check_catalog({"version": 2, "updated": "2026-11-06", "games": self.games})
        self.assertTrue(any("series" in p and "single" in p for p in problems), problems)

    def test_extra_all_sources_and_merged_series(self):
        self.games[0]["series"] = "shared"
        self.save_games()
        extras = []
        for src in build_pack.SRCS:
            g = {"id": src + "-extra", "src": src, "cat": "other",
                 "voice": False, "zh": "official", "series": "shared"}
            if src == "dlsite":
                g["url"] = "https://example.com/work"
            extras.append(g)
        extra = self.root / "extra.json"
        self.write(extra, {"games": extras})
        catalog = build_pack.build_catalog([extra])
        self.assertEqual(catalog["games"], self.games + sorted(extras, key=lambda g: g["id"]))
        problems, notes = self.check_catalog(catalog)
        self.assertEqual(problems, [])
        self.assertTrue(any("同系列 7 部、1 个系列" in n for n in notes))
        self.games[0].pop("series")
        self.save_games()
        self.write(extra, {"games": [{**extras[0], "series": "extra-only"}]})
        with self.assertRaisesRegex(ValueError, "series.*extra-only"):
            build_pack.build_catalog([extra])


if __name__ == "__main__":
    unittest.main()
