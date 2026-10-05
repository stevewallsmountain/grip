"""Tests for the Coast panel and the crag pages' strips: the plain-words line and the median per stretch of coast.

Standard library only. Run from the repository root or anywhere: python3 tests/test_today.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import grip  # noqa: E402

TODAY = "2026-10-05"
TOMORROW = "2026-10-06"


def series(start, vals, day=TODAY):
    """Hour dicts as the build makes them: consecutive hours from start, with an unrounded blended index."""
    return [{"t": f"{day}T{start + i:02d}:00", "index": v} for i, v in enumerate(vals)]


# (case, scores from 08:00 to 17:00, current hour or None for a whole later day, expected line)
LINES = [
    ("low all day", [1, 1.5, 2, 2.4, 3, 3.4, 3.2, 2.5, 2, 1], 11,
     "Greasy now. Not climbable today. Best 12:00 to 15:00."),
    ("low morning then rising", [1, 2, 2.5, 3, 3.6, 4.6, 5.8, 6.2, 5.5, 4.4], 9,
     "Greasy now. Climbable from 12:00. Best 14:00 to 17:00."),
    ("climbable now for one hour, then a dip", [2, 4, 3, 3, 4, 5, 6, 6, 5, 3], 9,
     "Climbable now. Best 13:00 to 16:00."),
    ("climbable every hour, before daylight", [4.5, 5, 6, 6.5, 7, 7, 6, 5, 4, 4], 7,
     "Climbable all day. Best 11:00 to 14:00."),
    ("one hour below climbable, before daylight", [4.5, 5, 6, 6.5, 7, 7, 6, 5, 4, 3.4], 7,
     "Climbable from 08:00. Best 11:00 to 14:00."),
    ("climbable every hour, from the first daylight hour", [4.5, 5, 6, 6.5, 7, 7, 6, 5, 4, 4], 8,
     "Climbable now. Best 11:00 to 14:00."),
    ("climbable from the first hour, mid-morning", [4.5, 5, 6, 6.5, 7, 7, 6, 5, 4, 4], 10,
     "Grippy now. Best 11:00 to 14:00."),
    ("climbable then falling away, still climbable", [5, 6, 5.5, 4.6, 3.4, 2, 1, 1, 1, 0], 10,
     "Grippy now. Best 10:00 to 13:00."),
    ("climbable then falling away, now past it", [5, 6, 5.5, 4.6, 3.4, 2, 1, 1, 1, 0], 13,
     "Greasy now. Not climbable today. Best 13:00 to 16:00."),
    ("a single climbable hour at the end does not count", [1, 1, 2, 2, 2, 2, 2, 3, 3, 4], 15,
     "Greasy now. Not climbable today. Best 16:00 to 18:00."),
    ("3.5 shows as 4 and counts as climbable", [2, 3.5, 3.5, 2, 2, 2, 2, 2, 2, 2], 8,
     "Greasy now. Climbable from 09:00. Best 08:00 to 11:00."),
    ("last daylight hour", [5, 5, 5, 5, 5, 5, 5, 5, 5, 3], 17,
     "Greasy now. Not climbable today."),
    ("whole day: rising", [2, 2.5, 3, 4, 5, 6.4, 6.6, 6, 5, 4], None,
     "Climbable from 11:00. Best 13:00 to 16:00."),
    ("whole day: low all day", [1, 1, 2, 2, 3, 3, 2, 2, 1, 1], None,
     "Not climbable. Best 11:00 to 14:00."),
    ("whole day: climbable every hour", [4, 5, 6, 8, 8.4, 8, 6, 5, 4, 4], None,
     "Climbable all day. Best 11:00 to 14:00."),
    ("whole day: climbable from the start, one hour below", [4, 5, 6, 8, 8.4, 8, 6, 5, 4, 3.4], None,
     "Climbable from 08:00. Best 11:00 to 14:00."),
    ("whole day: one hour below in the middle", [4, 5, 6, 8, 3.4, 8, 6, 5, 4, 4], None,
     "Climbable from 08:00. Best 11:00 to 14:00."),
    ("whole day: 3.5 shows as 4, so every hour counts", [3.5, 5, 6, 8, 8.4, 8, 6, 5, 4, 4], None,
     "Climbable all day. Best 11:00 to 14:00."),
]


class PlainLine(unittest.TestCase):
    def test_lines(self):
        for case, vals, now_hour, expected in LINES:
            with self.subTest(case):
                tomorrow = now_hour is None
                hs = series(8, vals, TOMORROW if tomorrow else TODAY)
                self.assertEqual(grip.plain_line(hs, now_hour, tomorrow), expected)

    def test_best_window_is_the_builds_own(self):
        """The line's best window is the one the popular crags table and the grid show for the same hours."""
        for case, vals, now_hour, _expected in LINES:
            with self.subTest(case):
                tomorrow = now_hour is None
                hs = series(8, vals, TOMORROW if tomorrow else TODAY)
                rest = hs if tomorrow else [h for h in hs if grip.hour_of(h) >= now_hour]
                bw = grip.best_window(rest)
                if bw:
                    self.assertIn(f"Best {bw[1][0]['t'][11:16]} to {grip.end_of(bw[1][-1])}.",
                                  grip.plain_line(hs, now_hour, tomorrow))

    def test_no_hours(self):
        self.assertEqual(grip.plain_line([], 18), "No daylight hours left today.")
        self.assertEqual(grip.plain_line([], None, True), "No hours scored.")

    def test_usable_from_needs_consecutive_hours(self):
        hs = series(8, [2, 2, 2, 4]) + series(13, [4, 4])  # 12:00 missing, so 11:00 and 13:00 are not consecutive
        self.assertEqual(grip.usable_from(hs)["t"][11:16], "13:00")


class Median(unittest.TestCase):
    def test_median_per_zone_and_hour(self):
        results = [
            {"crag": {"zone": "a"}, "earlier": series(9, [1.0, 2.0]), "hours": series(11, [3.0, 4.0])},
            {"crag": {"zone": "a"}, "earlier": series(9, [2.0, 3.0]), "hours": series(11, [5.0, 6.0])},
            {"crag": {"zone": "a"}, "earlier": series(9, [9.0, 9.0]), "hours": series(11, [4.4, 4.6])},
            {"crag": {"zone": "b"}, "earlier": [], "hours": series(11, [2.4, 7.0]) + series(8, [5.0], TOMORROW)},
            {"crag": {"zone": "b"}, "earlier": [], "hours": series(11, [3.0, 8.0])},
        ]
        zones = {"a": {"name": "Zone A"}, "b": {"name": "Zone B"}}
        rows = grip.coast_rows(results, zones, TODAY)
        self.assertEqual([(z, n) for z, n, _v in rows], [("a", "Zone A"), ("b", "Zone B")])  # in coast order
        vals = {z: v for z, _n, v in rows}
        self.assertEqual(vals["a"], {9: 2.0, 10: 3.0, 11: 4.4, 12: 4.6})  # odd count: the middle wall
        self.assertEqual(vals["b"], {11: 2.7, 12: 7.5})  # even count: halfway between; tomorrow's hour left out
        self.assertEqual([grip.rnd(v) for v in vals["b"].values()], [3, 8])
        self.assertEqual(grip.band(vals["a"][11])[0], "Climbable")


if __name__ == "__main__":
    unittest.main(verbosity=2)
