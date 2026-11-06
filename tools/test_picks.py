"""Manual picks validation and build/pack integration."""
import copy
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import build_pack
from check_pack import check, picks_problems


class Picks(unittest.TestCase):
    def test_build_and_check(self):
        games = [{"id": "steam-1", "src": "steam", "cat": "adv"},
                 {"id": "steam-2", "src": "steam", "cat": "adv"},
                 {"id": "steam-3", "src": "steam", "cat": "adv"}]
        picks = {"name": "Picks", "note": "Manual", "items": [
            {"id": "steam-2", "why": "Second first"}, {"id": "steam-1", "why": "First second"}]}
        bad = [None, {}, [], {**picks, "name": " "}, {**picks, "note": False},
               {**picks, "items": {}}, {**picks, "extra": 1}]
        for item in (None, {}, {"id": [], "why": "x"}, {"id": "", "why": "x"},
                     {"id": "steam-1", "why": " "}, {"id": "missing", "why": "x"},
                     {"id": "steam-1", "why": "x", "extra": 1}):
            bad.append({**picks, "items": [item]})
        bad.append({**picks, "items": [picks["items"][0]] * 2})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def write(name, value):
                (root / name).write_text(json.dumps(value), encoding="utf-8")
            write("meta.json", {"version": 2, "updated": "2026-11-06"})
            write("adv.json", games)
            with patch.object(build_pack, "DATA", root):
                base = build_pack.build_catalog()
                self.assertNotIn("picks", base)
                for value in [picks, {**picks, "items": []}] + bad:
                    with self.subTest(value=value):
                        before = copy.deepcopy(value)
                        write("picks.json", value)
                        if value in bad:
                            self.assertTrue(picks_problems(value, games))
                            with self.assertRaisesRegex(ValueError, "data/picks.json"):
                                build_pack.build_catalog()
                            catalog = {**base, "picks": value}
                        else:
                            catalog = build_pack.build_catalog()
                            self.assertEqual(catalog["picks"], value)
                        pack = root / "pack.zip"
                        with zipfile.ZipFile(pack, "w") as z:
                            z.writestr("catalog.json", json.dumps(catalog))
                        errors, _ = check(pack, None)
                        self.assertEqual(bool(errors), value in bad, errors)
                        self.assertEqual(value, before)
                extra = root / "extra.local"
                extra.write_text(json.dumps({"games": [{"id": "steam-4", "cat": "adv"}]}))
                write("picks.json", {**picks, "items": [{"id": "steam-4", "why": "Local"}]})
                self.assertEqual(build_pack.build_catalog(extras=[extra])["picks"]["items"][0]["id"], "steam-4")

