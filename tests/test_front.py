"""Tests for the band names, log parsing and the front page's popular crags table.

Standard library only. Run from the repository root or anywhere: python3 tests/test_front.py
"""
import csv
import io
import json
import os
import re
import sys
import tempfile
import unittest
from datetime import date, datetime
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


class Reply(io.BytesIO):
    """A urlopen reply that works as a context manager."""
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


SHEET_HEAD = ["Timestamp", "Crag or wall", "Date", "On the rock from", "On the rock until", "How did the rock feel overall?",
              "If it was poor, what was the problem? Tick any that apply", "Initials (optional)", "Wall or sector, if you know it (optional)"]
SHEET_ROWS = [
    ["10/4/2026 11:04:48", "Crag A", "10/3/2026", "11:00:00 AM", "3:00:00 PM", "Grippy: good friction", "", "", ""],
    ["11/2/2026 22:25:39", "Crag B", "11/2/2026", "1:24:00 PM", "10:24:00 PM", "Climbable: fine with care", "", "", ""],
    ["11/3/2026 9:43:31", "Crag C", "11/1/2026", "10:00:00 AM", "1:00:00 PM", "Climbable: fine with care", "", "", ""],
]
EXCLUDE_B = {"timestamp": "11/2/2026 22:25:39", "date": "2026-11-02", "crag": "Crag B", "reason": "Doubtful: a test."}


class LogExclusions(unittest.TestCase):
    """data/log_exclusions.json: an excluded log is skipped by fetch_log() and disappears from the calibration everywhere."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.excl = os.path.join(self.dir.name, "log_exclusions.json")
        p = mock.patch.object(grip, "LOG_EXCLUSIONS_FILE", self.excl)
        p.start()
        self.addCleanup(p.stop)

    def exclude(self, *logs):
        with open(self.excl, "w", encoding="utf-8") as f:
            json.dump({"logs": list(logs)}, f)

    def fetch(self, rows=SHEET_ROWS):
        """fetch_log() on the synthetic Public tab, and the warnings it logged."""
        buf = io.StringIO()
        csv.writer(buf).writerows([SHEET_HEAD] + rows)
        with mock.patch.object(grip.urllib.request, "urlopen", return_value=Reply(buf.getvalue().encode())), \
                mock.patch.object(grip, "log") as lg:
            got = grip.fetch_log()
        return got, [" ".join(map(str, c.args)) for c in lg.call_args_list if str(c.args[0]).startswith("Warning")]

    def test_excluded_row_is_skipped(self):
        self.exclude(EXCLUDE_B)
        got, warns = self.fetch()
        self.assertEqual([(e["crag"], e["date"]) for e in got], [("Crag A", "2026-10-03"), ("Crag C", "2026-11-01")])
        self.assertEqual(warns, [])

    def test_missing_file_excludes_nothing(self):
        got, warns = self.fetch()  # no file written
        self.assertEqual([e["crag"] for e in got], ["Crag A", "Crag B", "Crag C"])
        self.assertEqual(len(warns), 1)
        self.assertIn("cannot read data/log_exclusions.json", warns[0])

    def test_unreadable_file_excludes_nothing(self):
        with open(self.excl, "w", encoding="utf-8") as f:
            f.write("{not json")
        got, warns = self.fetch()
        self.assertEqual(len(got), 3)
        self.assertEqual(len(warns), 1)

    def test_no_matching_row_warns_once(self):
        self.exclude(EXCLUDE_B, {"timestamp": "1/1/2026 0:00:00", "date": "2025-12-31", "crag": "Crag Z", "reason": "Doubtful: a test."})
        got, warns = self.fetch()
        self.assertEqual(len(got), 2)
        self.assertEqual(len(warns), 1)
        self.assertIn("1/1/2026 0:00:00", warns[0])
        self.assertIn("matches no row", warns[0])

    def test_date_or_crag_differing_warns_once_and_still_excludes(self):
        self.exclude({**EXCLUDE_B, "date": "2026-11-01"})
        got, warns = self.fetch(SHEET_ROWS + [SHEET_ROWS[1]])  # the same row twice still warns once
        self.assertEqual([e["crag"] for e in got], ["Crag A", "Crag C"])
        self.assertEqual(len(warns), 1)
        self.assertIn("but its row is Crag B on 2026-11-02", warns[0])
        self.exclude({**EXCLUDE_B, "crag": "Crag Q"})
        got, warns = self.fetch()
        self.assertEqual(len(got), 2)
        self.assertEqual(len(warns), 1)
        self.assertIn("Crag Q", warns[0])

    def scored_cache(self):
        """A cache holding fully scored entries for all three logs, keyed as the build keys them."""
        self.exclude()
        entries, _w = self.fetch()
        self.assertEqual(len(entries), 3)
        return {grip.log_key(e): {**e, "grip": 5.0, "wet": 0.0, "models": {"Met Office": 5.0}, "base": 5.0, "base_models": {},
                                  "era": 5.0, "era_base": 5.0, "tries": 1} for e in entries}

    def calibrate(self, cache, rows=SHEET_ROWS, fail=False):
        """calibrate() on the given cache and sheet; returns the summary, the CSV's rows and the cache file as written.
        The warnings it logged are left in self.warns."""
        cal_file, cal_csv = os.path.join(self.dir.name, "calibration.json"), os.path.join(self.dir.name, "calibration.csv")
        with open(cal_file, "w", encoding="utf-8") as f:
            json.dump(cache, f)
        buf = io.StringIO()
        csv.writer(buf).writerows([SHEET_HEAD] + rows)
        reply = OSError("offline") if fail else None
        with mock.patch.object(grip, "CAL_FILE", cal_file), mock.patch.object(grip, "CAL_CSV", cal_csv), \
                mock.patch.object(grip.urllib.request, "urlopen", side_effect=reply, return_value=Reply(buf.getvalue().encode())), \
                mock.patch.object(grip, "backscore", side_effect=AssertionError("nothing should be scored")), \
                mock.patch.object(grip, "log") as lg, mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GRIP_FAKE", None)
            cal = grip.calibrate({"crags": [], "zones": {}})
        self.warns = [" ".join(map(str, c.args)) for c in lg.call_args_list if str(c.args[0]).startswith("Warning")]
        with open(cal_csv, encoding="utf-8") as f:
            csv_rows = list(csv.DictReader(f))
        with open(cal_file, encoding="utf-8") as f:
            written = json.load(f)
        return cal, csv_rows, written

    def test_scored_excluded_log_leaves_calibration(self):
        cache = self.scored_cache()
        self.exclude(EXCLUDE_B)
        cal, csv_rows, written = self.calibrate(cache)  # backscore raises if called: the excluded log is never scored again
        self.assertEqual(cal["n"], 2)
        self.assertEqual(cal["pending"], 0)
        self.assertEqual(sorted(v["crag"] for v in cal["rows"]), ["Crag A", "Crag C"])
        self.assertEqual([(r["date"], r["crag"]) for r in csv_rows], [("2026-10-03", "Crag A"), ("2026-11-01", "Crag C")])
        self.assertEqual(sorted(v["crag"] for v in written.values()), ["Crag A", "Crag C"])
        self.assertEqual({k: v for k, v in cache.items() if v["crag"] != "Crag B"}, written)  # the others unchanged
        html = grip.render_sure(cal)
        self.assertEqual(len(re.findall(r'<i class="(in|near|out)"></i>', html.split('class="sql"')[0])), 2)
        self.assertIn("2 days have been logged", html)

    def test_logged_days_follow_the_written_cache(self):
        cache = self.scored_cache()
        self.exclude(EXCLUDE_B)
        _cal, _rows, written = self.calibrate(cache)
        with mock.patch.object(grip, "CAL_FILE", os.path.join(self.dir.name, "calibration.json")):
            self.assertEqual(sorted(v["crag"] for v, _w in grip.logged_days({"crags": []})), ["Crag A", "Crag C"])

    def test_failed_fetch_keeps_the_cache(self):
        cache = self.scored_cache()
        cal, csv_rows, written = self.calibrate(cache, fail=True)
        self.assertEqual(cal["n"], 3)
        self.assertEqual(len(csv_rows), 3)
        self.assertEqual(written, cache)

    def test_without_exclusions_nothing_changes(self):
        cache = self.scored_cache()
        cal, csv_rows, written = self.calibrate(cache)
        self.assertEqual(cal["n"], 3)
        self.assertEqual(len(csv_rows), 3)
        self.assertEqual(written, cache)

    def with_orphans(self, cache, n):
        """The cache with n scored entries whose logs have no row in the sheet (edited or deleted), and their keys."""
        orphans = {}
        for i in range(n):
            e = {"crag": f"Gone {i}", "wall": "", "date": f"2026-09-0{i + 1}", "from": 10, "to": 12, "feel": "Crisp", "problems": ""}
            orphans[grip.log_key(e)] = {**e, "grip": 6.0, "wet": 0.0, "models": {}, "base": 6.0, "base_models": {}, "era": 6.0,
                                        "era_base": 6.0, "tries": 1}
        return {**cache, **orphans}, set(orphans)

    def test_four_orphans_are_kept_with_one_warning(self):
        cache, orphans = self.with_orphans(self.scored_cache(), 4)
        self.exclude(EXCLUDE_B)
        cal, csv_rows, written = self.calibrate(cache)
        self.assertEqual(set(written), set(cache) - {k for k, v in cache.items() if v["crag"] == "Crag B"})  # the exclusion still applies
        self.assertTrue(orphans <= set(written))
        self.assertEqual(cal["n"], 6)
        self.assertEqual(len(csv_rows), 6)
        self.assertEqual(len(self.warns), 1)
        self.assertIn("4 scored logs have no current row", self.warns[0])
        for i in range(4):
            self.assertIn(f"Gone {i} on 2026-09-0{i + 1}, 10:00 to 12:00", self.warns[0])
        self.assertNotIn("Crag B", self.warns[0])

    def test_up_to_three_orphans_are_pruned(self):
        for n in (1, 3):
            with self.subTest(n=n):
                base = self.scored_cache()
                cache, orphans = self.with_orphans(base, n)
                self.exclude(EXCLUDE_B)
                cal, csv_rows, written = self.calibrate(cache)
                self.assertFalse(orphans & set(written))
                self.assertEqual(sorted(v["crag"] for v in written.values()), ["Crag A", "Crag C"])
                self.assertEqual(cal["n"], 2)
                self.assertEqual(len(csv_rows), 2)
                self.assertEqual(self.warns, [])

    def test_excluded_logs_do_not_count_as_orphans(self):
        """Four excluded logs, all scored, all go: the limit is for logs with no row, not for exclusions."""
        rows = [[f"11/2/2026 22:0{i}:00", f"Crag {i}", "11/1/2026", "10:00:00 AM", "1:00:00 PM", "Grippy: good friction", "", "", ""]
                for i in range(4)] + [SHEET_ROWS[0]]
        self.exclude()
        entries, _w = self.fetch(rows)
        cache = {grip.log_key(e): {**e, "grip": 5.0, "wet": 0.0, "models": {}, "base": 5.0, "base_models": {}, "era": 5.0,
                                   "era_base": 5.0, "tries": 1} for e in entries}
        self.exclude(*({"timestamp": r[0], "date": "2026-11-01", "crag": r[1], "reason": "Doubtful: a test."} for r in rows[:4]))
        cal, csv_rows, written = self.calibrate(cache, rows)
        self.assertEqual([v["crag"] for v in written.values()], ["Crag A"])
        self.assertEqual(cal["n"], 1)
        self.assertEqual(self.warns, [])

    def test_committed_file(self):
        with open(os.path.join(ROOT, "data", "log_exclusions.json"), encoding="utf-8") as f:
            logs = json.load(f)["logs"]
        self.assertTrue(logs)
        for x in logs:
            with self.subTest(x["timestamp"]):
                self.assertEqual(set(x), {"timestamp", "date", "crag", "reason"})
                self.assertIsNotNone(grip.parse_date(x["date"]))
                datetime.strptime(x["timestamp"], "%m/%d/%Y %H:%M:%S")
                self.assertTrue(x["reason"].startswith("Doubtful"))
                self.assertNotIn("\u2014", x["reason"])


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
            with open(grip.CAL_CSV, encoding="utf-8") as f:
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

    def test_popular_crags_are_the_top_of_the_committed_rank(self):
        """The table lists the first POPULAR_COUNT crags of data/crag_rank.json: 15 names, no repeats, every one a crag."""
        with open(os.path.join(ROOT, "data", "crag_rank.json"), encoding="utf-8") as f:
            names = json.load(f)["rank"][:grip.POPULAR_COUNT]
        with open(os.path.join(ROOT, "crags.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        known = {c["name"] for c in cfg["crags"]}
        self.assertEqual(grip.POPULAR_COUNT, 15)
        self.assertEqual(len(names), 15)
        self.assertEqual(len(set(names)), 15)
        self.assertEqual([n for n in names if n not in known], [])
        with mock.patch.object(grip, "CRAG_RANK_FILE", os.path.join(ROOT, "data", "crag_rank.json")):
            self.assertEqual(grip.load_crag_rank(cfg)[:grip.POPULAR_COUNT], names)

    def test_unknown_name_warns_and_is_left_out(self):
        cfg = {"crags": [{"name": "Logie Head"}], "zones": {"z": {"name": "Point"}}}
        results = [wall("Logie Head", d2026_10_05=(6, 4))]
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "r.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"as_of": "2026-10-07", "window": "w", "rank": ["Nowhere Crag", "Logie Head"]}, f)
            with mock.patch.object(grip, "CRAG_RANK_FILE", p), mock.patch.object(grip, "log") as lg, \
                    mock.patch.object(grip, "coast_view", return_value=(D1, False, None, None, None)):
                html = grip.render_popular(results, {}, None, cfg)
            self.assertIn("Nowhere Crag", lg.call_args[0][0])
        self.assertIn('<a href="detail/logie-head.html">Logie Head</a>', html)
        self.assertNotIn("Nowhere Crag", html)

class DateFormats(unittest.TestCase):
    def test_day_without_leading_zero(self):
        """dfmt gives the day without a leading zero for every "%-d" format grip.py uses, on any platform."""
        oct6, oct31 = date(2026, 10, 6), date(2026, 10, 31)
        for d, form, want in ((oct6, "%a %-d %b", "Tue 6 Oct"), (oct6, "%A %-d %B", "Tuesday 6 October"),
                              (oct6, "%-d %b %Y", "6 Oct 2026"), (oct6, "%a %-d", "Tue 6"),
                              (oct31, "%a %-d %b", "Sat 31 Oct"), (oct31, "%A %-d %B", "Saturday 31 October"),
                              (oct31, "%-d %b %Y", "31 Oct 2026"), (oct31, "%a %-d", "Sat 31"),
                              (datetime(2026, 10, 6, 7, 5, tzinfo=grip.TZ), "%a %-d %b, %H:%M", "Tue 6 Oct, 07:05")):
            with self.subTest(form=form, d=d):
                self.assertEqual(grip.dfmt(d, form), want)


if __name__ == "__main__":
    unittest.main(verbosity=2)
