"""Tests for the band names, log parsing and the front page's popular crags table.

Standard library only. Run from the repository root or anywhere: python3 tests/test_front.py
"""
import csv
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import date
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import grip  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Every feel option the Google Form has offered, and the internal key each is stored and scored under
FEELS = [
    ("Soaked: wet rock", "Soaked"),
    ("Greasy: damp and slippery, training at best", "Greasy"),
    ("Usable: climbable with care", "Usable"),  # before October 2026
    ("Climbable: fine with care", "Usable"),
    ("Crisp: good friction", "Crisp"),  # before October 2026
    ("Grippy: good friction", "Crisp"),
    ("Prime: as dry as this coast gets", "Prime"),
]


class Feels(unittest.TestCase):
    def test_all_seven_strings(self):
        for text, key in FEELS:
            with self.subTest(text):
                self.assertEqual(grip.parse_feel(text), key)

    def test_unknown(self):
        for text in ("", "  ", "Damp: meh", "Usable climbable with care"):
            with self.subTest(text):
                self.assertIsNone(grip.parse_feel(text))

    def test_page_form_sends_the_new_strings(self):
        self.assertEqual(grip.LOG_FEELS, [t for t, _k in FEELS if not t.startswith(("Usable", "Crisp"))])
        page = grip.render_log({"crags": []})
        for t in grip.LOG_FEELS:
            self.assertIn(f'value="{t}"', page)
        self.assertNotIn("Usable", page)
        self.assertNotIn("Crisp", page)

    def test_fetch_log_maps_old_and_new(self):
        """The response sheet as published: old and new wordings both become the internal keys."""
        head = ["Timestamp", "Crag", "Date", "On the rock from", "On the rock until", "How did the rock feel overall?",
                "If it was poor, what was the problem?", "Wall or sector"]
        rows = [["", "Logie Head", "2026-10-0" + str(i + 1), "10:00:00", "12:00:00", text, "", ""] for i, (text, _k) in enumerate(FEELS)]
        buf = io.StringIO()
        csv.writer(buf).writerows([head] + rows)

        class Reply(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        with mock.patch.object(grip.urllib.request, "urlopen", return_value=Reply(buf.getvalue().encode())):
            got = grip.fetch_log()
        self.assertEqual([e["feel"] for e in got], [k for _t, k in FEELS])


class Names(unittest.TestCase):
    def test_band_names(self):
        self.assertEqual([grip.band(x)[0] for x in (0, 2, 4, 6, 8)], ["Soaked", "Greasy", "Climbable", "Grippy", "Prime"])
        self.assertEqual(grip.band(3.5)[0], "Climbable")  # as shown: 3.5 rounds to 4

    def test_internal_keys_unchanged(self):
        self.assertEqual(list(grip.FEEL_RANGE), ["Soaked", "Greasy", "Usable", "Crisp", "Prime"])
        self.assertEqual(list(grip.FEEL), list(grip.FEEL_RANGE))
        self.assertEqual([grip.FEEL_NAME[k] for k in grip.FEEL_RANGE], [b[1] for b in reversed(grip.BANDS)])

    def test_calibration_csv_felt_column(self):
        cache = {f"{grip.MODEL_VERSION}|X|2026-10-0{i}|10|12|{k}": {"crag": "X", "date": f"2026-10-0{i}", "from": 10, "to": 12,
                                                                     "feel": k, "grip": 5.0, "models": {}, "base_models": {}}
                 for i, k in enumerate(grip.FEEL_RANGE, 1)}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(grip, "CAL_CSV", os.path.join(d, "c.csv")):
            grip.write_calibration_csv(cache)
            with open(grip.CAL_CSV) as f:
                felt = [r["felt"] for r in csv.DictReader(f)]
        self.assertEqual(felt, ["Soaked", "Greasy", "Climbable", "Grippy", "Prime"])


def wall(name, zone="z", tidal=False, **days):
    """A wall result as build() makes it, with daily entries {date: (index, climbable hours)}."""
    return {"crag": {"name": name, "zone": zone, "tidal": tidal},
            "daily": {d.replace("_", "-")[1:]: {"index": s, "start": "10:00", "end": "13:00", "usable": u, "hours": 9}
                      for d, (s, u) in days.items()}}


D1, D2 = date(2026, 10, 5), date(2026, 10, 6)


class Popular(unittest.TestCase):
    def test_sort_by_score_as_shown_then_hours_then_list_order(self):
        groups = [
            ("A", [wall("A", d2026_10_05=(6.2, 5))]),
            ("B", [wall("B", d2026_10_05=(5.6, 7))]),   # shows 6 like A, more climbable hours: ahead of A
            ("C", [wall("C", d2026_10_05=(5.9, 5))]),   # shows 6, same hours as A, later in the list: after A
            ("D", [wall("D", d2026_10_05=(8.0, 1))]),   # highest score first whatever its hours
            ("E", [wall("E", d2026_10_06=(9.0, 9))]),   # no hours left today: last
            ("F", [wall("F", d2026_10_05=(2.0, 0))]),
        ]
        names = ["E", "C", "A", "B", "D", "F"]
        rows = grip.popular_rows(groups, names, (D1, D2))
        self.assertEqual([n for n, _w, _c in rows], ["D", "B", "C", "A", "F", "E"])

    def test_best_wall_per_day(self):
        g = [("A", [wall("A", d2026_10_05=(4, 3), d2026_10_06=(7, 6)), wall("A", d2026_10_05=(6, 4), d2026_10_06=(5, 2))])]
        (_n, walls, cells), = grip.popular_rows(g, ["A"], (D1, D2))
        self.assertIs(cells[0][0], walls[1])
        self.assertIs(cells[1][0], walls[0])

    def test_cell(self):
        tides = {"z": {"2026-10-05": ["09:12", "21:40"]}}
        r = wall("A", tidal=True, d2026_10_05=(7.6, 5))
        cell = grip.popular_cell(r, r["daily"]["2026-10-05"], "2026-10-05", tides)
        self.assertIn('class="num b5">8<', cell)
        self.assertIn('10:00 to 13:00</span><span class="h"><span class="dot"> &middot; </span>5 h', cell)
        self.assertIn("Low water 09:12, 21:40", cell)
        r = wall("A", tidal=False, d2026_10_05=(7.6, 5))
        self.assertNotIn("Low water", grip.popular_cell(r, r["daily"]["2026-10-05"], "2026-10-05", tides))
        self.assertIn("No daylight hours left", grip.popular_cell(None, None, "2026-10-05", tides))

    def test_every_popular_name_is_a_crag(self):
        with open(os.path.join(ROOT, "data", "popular.json")) as f:
            names = json.load(f)
        with open(os.path.join(ROOT, "crags.json")) as f:
            cfg = json.load(f)
        known = {c["name"] for c in cfg["crags"]}
        self.assertEqual(len(names), 15)
        self.assertEqual(len(set(names)), 15)
        self.assertEqual([n for n in names if n not in known], [])
        self.assertEqual(grip.load_popular(cfg), names)

    def test_unknown_name_warns_and_is_left_out(self):
        cfg = {"crags": [{"name": "Logie Head"}]}
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "p.json")
            with open(p, "w") as f:
                json.dump(["Logie Head", "Nowhere Crag"], f)
            with mock.patch.object(grip, "POPULAR_FILE", p), mock.patch.object(grip, "log") as lg:
                self.assertEqual(grip.load_popular(cfg), ["Logie Head"])
            self.assertIn("Nowhere Crag", lg.call_args[0][0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
