"""Tests for the crag pages: the "why" sentences, the sun-on-face hours, the swell wording and the water-on-rock words.

Standard library only. Run from the repository root or anywhere: python3 tests/test_detail.py
"""
import os
import sys
import unittest
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import grip  # noqa: E402

TODAY = "2026-10-05"
TOMORROW = "2026-10-06"
QUIET = {"air": 0.5, "fog": 0, "dew": 1, "wdir": 0.3, "wind": 1, "sun": 1, "sea": 0, "wet": 0, "dry": 1, "seep": 0}


def hours(start, rows, day=TODAY):
    """Hour dicts as the build makes them: consecutive hours from start, each with a score and its factor points.
    rows: (score, {factor: points}) with unnamed factors taken from QUIET."""
    return [{"t": f"{day}T{start + i:02d}:00", "index": v, "d": {"f": {**QUIET, **f}}} for i, (v, f) in enumerate(rows)]


HUMID = {"air": -3, "dew": -2, "wet": -1}
DRY_SUNNY = {"air": 3, "sun": 3, "dry": 1}


class Why(unittest.TestCase):
    def test_held_back_then_driven(self):
        hs = hours(8, [(2, HUMID)] * 4 + [(7, DRY_SUNNY)] * 3 + [(5, {})] * 3)
        self.assertEqual(grip.why_text(hs, 8),
                         "Held back this morning by humid air and rock close to the dew point. "
                         "The best window comes from dry air and sun on the face.")

    def test_nothing_worth_mentioning(self):
        hs = hours(8, [(4, {}), (4.5, {}), (5, {}), (4, {}), (3.5, {})])
        self.assertEqual(grip.why_text(hs, 8),
                         "No single factor is worth 2 points or more either way; the score comes from several small ones.")

    def test_eases_with_nothing_in_the_window(self):
        hs = hours(8, [(2, {"wet": -3})] * 3 + [(4, {})] * 3)
        self.assertEqual(grip.why_text(hs, 8),
                         "Held back this morning by water on the rock. "
                         "The best window comes as that eases, with no single factor worth 2 points or more.")

    def test_tomorrow_afternoon_window(self):
        hs = hours(8, [(1, {"fog": -4, "wet": -2})] * 6 + [(6, {"sun": 3})] * 3, TOMORROW)
        self.assertEqual(grip.why_text(hs, None, tomorrow=True),
                         "Held back tomorrow until 14:00 by haar and water on the rock. The best window comes from sun on the face.")

    def test_window_at_the_start_held_back(self):
        hs = hours(9, [(2, {"wet": -3, "sun": 2})] * 3 + [(1, {"wet": -5})] * 3)
        self.assertEqual(grip.why_text(hs, 9),
                         "The best window comes from sun on the face, though water on the rock still holds it back.")
        hs = hours(9, [(2, {"wet": -3})] * 3 + [(1, {"wet": -5})] * 3)
        self.assertEqual(grip.why_text(hs, 9), "Even the best window is held back by water on the rock.")

    def test_at_most_two_each_side(self):
        hs = hours(8, [(1, {"fog": -4, "seep": -3, "air": -2})] * 3 + [(7, {"air": 4, "sun": 3, "dry": 2, "wind": 2})] * 3)
        self.assertEqual(grip.why_text(hs, 8),
                         "Held back this morning by haar and seepage after heavy rain. The best window comes from dry air and sun on the face.")

    def test_window_is_plain_lines(self):
        """The window explained is the one the plain-words line names, from the current hour on; earlier hours count as early."""
        past = {"air": 0, "dew": 0}
        hs = hours(8, [(8, past)] * 3 + [(2, {"air": -4, "dew": -4})] * 3 + [(7, {"sun": 3})] * 3)
        self.assertIn("best 08:00 to 11:00", grip.plain_line(hs, None, tomorrow=True))
        self.assertIn("best 14:00 to 17:00", grip.plain_line(hs, 11))
        self.assertEqual(grip.why_text(hs, 11),
                         "Held back until 14:00 by humid air and rock close to the dew point. The best window comes from sun on the face.")

    def test_mean_below_the_threshold_is_not_named(self):
        hs = hours(8, [(3, {"air": -3}), (3, {"air": -0.5})] + [(6, {"sun": 1.9})] * 3)
        self.assertEqual(grip.why_text(hs, 8),
                         "No single factor is worth 2 points or more either way; the score comes from several small ones.")

    def test_no_hours(self):
        self.assertEqual(grip.why_text([], 18), "No daylight hours left to explain.")


class FaceHours(unittest.TestCase):
    LAT, LON = 57.0, -2.2
    DAY = date(2026, 10, 5)

    def test_matches_the_scoring(self):
        """Every hour listed is one the scoring counts as sun on the face under a clear sky, and no other hour is."""
        for aspect in grip.COMPASS:
            listed = {h for a, b in grip.face_hours(self.LAT, self.LON, aspect, self.DAY) for h in range(a, b)}
            for h in range(24):
                dt = datetime(2026, 10, 5, h, tzinfo=grip.TZ)
                az, el = grip.sun_position(dt.astimezone(timezone.utc), self.LAT, self.LON)
                on = el >= 5 and grip.ang_diff(az, grip.COMPASS[aspect]) <= 60
                self.assertEqual(h in listed, on, f"{aspect} {h:02d}:00")

    def test_known_days(self):
        self.assertEqual(grip.face_hours(self.LAT, self.LON, "S", self.DAY), [(10, 17)])
        self.assertEqual(grip.face_hours(self.LAT, self.LON, "E", self.DAY), [(9, 12)])
        self.assertEqual(grip.face_hours(self.LAT, self.LON, "N", self.DAY), [])
        self.assertEqual(grip.face_hours(self.LAT, self.LON, "N", date(2026, 6, 21)), [(21, 22)])

    def test_unknown_aspect(self):
        self.assertIsNone(grip.face_hours(self.LAT, self.LON, None, self.DAY))
        self.assertEqual(grip.face_text(None), "Aspect unknown, so Grip never counts the sun as on the face.")

    def test_text(self):
        self.assertEqual(grip.face_text([(10, 17)]), "Sun on the face today, when it shines: 10:00 to 17:00.")
        self.assertEqual(grip.face_text([], "tomorrow"), "The sun does not reach this face at any hour tomorrow.")


class Swell(unittest.TestCase):
    def test_side(self):
        for wave_dir, side in ((90, "onto"), (45, "onto"), (180, "onto"), (0, "onto"), (200, "along"), (225, "along"),
                               (226, "behind"), (270, "behind"), (315, "along")):
            with self.subTest(wave_dir):
                self.assertEqual(grip.swell_side(wave_dir, "E"), side)
        self.assertIsNone(grip.swell_side(None, "E"))
        self.assertIsNone(grip.swell_side(90, None))

    def test_side_agrees_with_the_scoring(self):
        """'onto' exactly when f_sea counts the height in full, for an open wall."""
        for aspect in grip.COMPASS:
            for wave_dir in range(0, 360, 5):
                full = grip.f_sea(1.0, wave_dir, 6, grip.COMPASS[aspect])[2] == 1.0
                self.assertEqual(grip.swell_side(wave_dir, aspect) == "onto", full, f"{aspect} {wave_dir}")

    def test_wording(self):
        self.assertEqual(grip.sea_text(1.0, 100, 6, "E"),
                         "Coming from the E, onto the face, period 6.0 s (short wind sea). Grip counts it in full. "
                         "That is 3.3 ft at the wall, -1 point for the sea; spray starts adding water to the rock over 2.5 m at the wall.")
        self.assertEqual(grip.sea_text(1.0, 270, 6, "E"),
                         "Coming from the W, from behind the face, period 6.0 s (short wind sea). Grip counts it at 40% of its height. "
                         "That is 1.3 ft at the wall, +0 points for the sea; spray starts adding water to the rock over 2.5 m at the wall.")
        self.assertIn("along the face, period 11.0 s (long swell). Grip counts it at 70% of its height, as long swell wraps round headlands.",
                      grip.sea_text(1.0, 200, 11, "E"))
        self.assertIn("1.5 times its height from any direction", grip.sea_text(1.0, 270, 6, "E", inlet=True))
        self.assertIn("5.9 ft at the wall, -2 points", grip.sea_text(1.2, 270, 6, "E", inlet=True))
        self.assertIn("Offshore rock breaks it, so Grip counts it at half height.", grip.sea_text(1.0, 90, 6, "E", sea_sheltered=True))
        self.assertIn("spray is adding water to the rock (over 2 m)", grip.sea_text(2.2, 90, 6, "E", tidal=True))
        self.assertIn("spray starts adding water to the rock over 2.5 m", grip.sea_text(2.2, 90, 6, "E"))
        self.assertIn("the face's aspect is unknown, so Grip counts it in full", grip.sea_text(1.0, 90, 6, None))
        self.assertEqual(grip.sea_text(None, 90, 6, "E"), "No sea forecast for this hour.")


class WaterOnRock(unittest.TestCase):
    def test_words(self):
        for film, words in ((0, "dry"), (0.02, "dry"), (0.021, "a trace"), (0.1, "a trace"), (0.11, "damp"),
                            (0.5, "damp"), (0.51, "wet"), (2.0, "wet")):
            with self.subTest(film):
                self.assertEqual(grip.water_words(film), words)

    def test_words_follow_the_scoring(self):
        pts = {"dry": 0, "a trace": -1, "damp": -2, "wet": -3}
        for i in range(0, 201):
            film = i / 100
            self.assertEqual(grip.f_wet(0, film)[0], pts[grip.water_words(film)], film)


class Rain(unittest.TestCase):
    def test_totals(self):
        h = {"time": [f"2026-10-0{1 + i // 24}T{i % 24:02d}:00" for i in range(96)], "precipitation": [0.1] * 95 + [5]}
        now = datetime(2026, 10, 4, 23, 40, tzinfo=grip.TZ)
        r24, r72 = grip.rain_totals(h, now)
        self.assertAlmostEqual(r24, 2.4)  # the hours before 23:00, not 23:00 itself
        self.assertAlmostEqual(r72, 7.2)
        r24, r72 = grip.rain_totals(h, datetime(2026, 10, 2, 5, tzinfo=grip.TZ))
        self.assertAlmostEqual(r24, 2.4)
        self.assertIsNone(r72)  # the data does not reach back 72 hours


if __name__ == "__main__":
    unittest.main(verbosity=2)
