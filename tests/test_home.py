"""Tests for the home page redesign: summary cards, the stale notice, the pop-up's models sentence, How sure,
grid sub-labels and the header nav on every page.

Standard library only. Run from the repository root or anywhere: python3 tests/test_home.py
"""
import os
import re
import sys
import unittest
import unittest.mock
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import grip  # noqa: E402

TODAY, TOMORROW, LATER = "2026-10-05", "2026-10-06", "2026-10-07"
LABS = ["Met Office", "ECMWF", "ICON"]


def hours(day, start, rows):
    """Hour dicts as score_crag() makes them, from consecutive hours at start. Each row is one score for all three models,
    or a tuple of per-model scores (None for a model with no data that hour)."""
    out = []
    for i, row in enumerate(rows):
        vals = [(lab, v) for lab, v in zip(LABS, row if isinstance(row, tuple) else (row,) * 3) if v is not None]
        scores = [v for _l, v in vals]
        out.append({"t": f"{day}T{start + i:02d}:00", "index": sum(scores) / len(scores), "models": vals,
                    "spread": max(scores) - min(scores), "n": len(vals), "wet": 0.0})
    return out


def daily(hs):
    """A day's entry as build() makes it from its hours."""
    best = grip.best_window(hs)
    win = best[1]
    return {"index": best[0], "start": win[0]["t"][11:16], "end": grip.end_of(win[-1]),
            "spread": max(x["spread"] for x in win), "n": min(x["n"] for x in win), "wet": 0.0,
            "usable": sum(1 for x in hs if grip.rnd(x["index"]) >= grip.USABLE), "hours": len(hs), "drying": "",
            "models": []}


def result(name, zone, by_day, earlier=None):
    """A wall result: by_day is {date: hour dicts}; earlier holds today's hours already gone. Its SMC section is
    deliberately unlike its weather point, so a test can tell which one the summary names."""
    hs = [hr for d in sorted(by_day) for hr in by_day[d]]
    return {"crag": {"name": name, "zone": zone, "section": "SMC section " + zone}, "hours": hs, "earlier": earlier or [],
            "daily": {d: daily(v) for d, v in by_day.items() if v}}


CFG = {"zones": {"S": {"name": "Weather point"}, "south": {"name": "Nigg Bay to Findon"},
                 "north": {"name": "Cullen and Portsoy"}, "mid": {"name": "Stonehaven and south"},
                 "First": {"name": "First point"}, "Second": {"name": "Second point"}}}


class Summary(unittest.TestCase):
    def test_best_stretch_and_grippy_count(self):
        results = [
            result("A", "south", {TOMORROW: hours(TOMORROW, 9, [5, 6, 7, 7, 7, 6, 5, 5, 5])}),
            # same score as shown (7), but holds Grippy for longer: its stretch wins the tie
            result("B", "north", {TOMORROW: hours(TOMORROW, 9, [6, 6, 7, 7, 7, 6, 6, 6, 5])}),
            result("B", "north", {TOMORROW: hours(TOMORROW, 9, [3, 3, 3, 3, 3, 3, 3, 3, 3])}),
            result("C", "mid", {TOMORROW: hours(TOMORROW, 9, [4, 4, 5, 5, 5, 4, 4, 4, 4])}),
        ]
        s = grip.day_summary(results, CFG, TOMORROW)
        self.assertEqual(s["best"]["stretch"], "Cullen and Portsoy")  # the coast panel's row, not the SMC section
        self.assertEqual((s["best"]["run"][0]["t"][11:16], grip.end_of(s["best"]["run"][-1])), ("09:00", "17:00"))
        self.assertEqual((s["grippy"], s["crags"]), (2, 3))  # A and B reach 6; C does not; B's second wall is not a crag
        card = grip.summary_card("Tomorrow", date(2026, 10, 6), s)
        self.assertIn("Grippy most of the day, 09:00 to 17:00", card)
        self.assertIn("Best from Cullen and Portsoy. 2 of 3 crags reach Grippy.", card)
        self.assertNotIn("SMC section", card)
        self.assertIn("Tomorrow, Tue 6 Oct", card)

    def test_tie_on_score_and_run_goes_to_coast_order(self):
        results = [result("A", "First", {TOMORROW: hours(TOMORROW, 9, [7, 7, 7])}),
                   result("B", "Second", {TOMORROW: hours(TOMORROW, 9, [7, 7, 7])})]
        self.assertEqual(grip.day_summary(results, CFG, TOMORROW)["best"]["stretch"], "First point")

    def test_count_uses_the_score_as_shown(self):
        results = [result("A", "S", {TOMORROW: hours(TOMORROW, 9, [5.5, 5.5, 5.5])}),   # shows 6
                   result("B", "S", {TOMORROW: hours(TOMORROW, 9, [5.4, 5.4, 5.4])})]   # shows 5
        s = grip.day_summary(results, CFG, TOMORROW)
        self.assertEqual(s["grippy"], 1)
        self.assertIn("1 of 2 crags reaches Grippy.", grip.summary_card("Tomorrow", date(2026, 10, 6), s))

    def test_nowhere_climbable(self):
        results = [result("Souter Head", "S", {TOMORROW: hours(TOMORROW, 9, [2, 3, 3, 3, 2])}),
                   result("Cove", "S", {TOMORROW: hours(TOMORROW, 9, [1, 1, 2, 1, 1])})]
        card = grip.summary_card("Tomorrow", date(2026, 10, 6), grip.day_summary(results, CFG, TOMORROW))
        self.assertIn("Nowhere climbable. Best is Greasy, 3, at Souter Head.", card)
        self.assertIn("0 of 2 crags reach Grippy.", card)
        self.assertNotIn("Best from", card)
        # 3.5 shows as 4, which is climbable
        results = [result("Souter Head", "S", {TOMORROW: hours(TOMORROW, 9, [3.5, 3.5, 3.5])})]
        self.assertNotIn("Nowhere", grip.summary_card("Tomorrow", date(2026, 10, 6), grip.day_summary(results, CFG, TOMORROW)))

    def test_after_dark(self):
        """Once today's daylight is over: Tomorrow first, then the day after headed by its date alone, in the same format."""
        gone = hours(TODAY, 9, [5, 6, 8, 8, 8, 6])
        results = [result("A", "south", {TOMORROW: hours(TOMORROW, 9, [6, 6, 6]), LATER: hours(LATER, 9, [4, 5, 7, 7, 7, 5])},
                          earlier=gone),
                   result("B", "north", {TOMORROW: hours(TOMORROW, 9, [3, 3, 3]), LATER: hours(LATER, 9, [6, 6, 6, 4, 4, 4])})]
        html = grip.render_summary(results, datetime(2026, 10, 5, 20, 0, tzinfo=grip.TZ), CFG)
        first, second = html.split('<div class="card">')[1:]
        self.assertIn('<p class="ovl">Tomorrow, Tue 6 Oct</p>', first)
        self.assertIn("Grippy all day, 09:00 to 12:00", first)
        self.assertIn('<p class="ovl">Wed 7 Oct</p>', second)
        self.assertIn('class="num sz-xl b4" role="img" aria-label="7, Grippy">7<', second)
        self.assertIn("Grippy around midday, 11:00 to 14:00", second)
        self.assertIn("Best from Nigg Bay to Findon. 2 of 2 crags reach Grippy.", second)
        self.assertIn('aria-label="Best tomorrow and the day after"', html)
        for gone_words in ("Today", "Today is over", "past"):
            self.assertNotIn(gone_words, html)

    def test_after_dark_day_after_nowhere_climbable(self):
        results = [result("Souter Head", "S", {TOMORROW: hours(TOMORROW, 9, [6, 6, 6]), LATER: hours(LATER, 9, [2, 3, 3, 3, 2])}),
                   result("Cove", "S", {TOMORROW: hours(TOMORROW, 9, [5, 5, 5]), LATER: hours(LATER, 9, [1, 1, 2, 1, 1])})]
        html = grip.render_summary(results, datetime(2026, 10, 5, 20, 0, tzinfo=grip.TZ), CFG)
        second = html.split('<div class="card">')[2]
        self.assertIn('<p class="ovl">Wed 7 Oct</p>', second)
        self.assertIn("Nowhere climbable. Best is Greasy, 3, at Souter Head.", second)
        self.assertIn("0 of 2 crags reach Grippy.", second)
        self.assertNotIn("Best from", second)

    def test_after_dark_day_after_not_scored(self):
        results = [result("A", "S", {TOMORROW: hours(TOMORROW, 9, [6, 6, 6])})]
        html = grip.render_summary(results, datetime(2026, 10, 5, 20, 0, tzinfo=grip.TZ), CFG)
        self.assertIn('<p class="ovl">Wed 7 Oct</p><p class="ln">No hours scored.</p>', html)

    def test_daytime_unchanged(self):
        """During the day: Today first, from the hours still to come, then Tomorrow; the day after is not shown."""
        results = [result("A", "S", {TODAY: hours(TODAY, 14, [6, 6, 6]), TOMORROW: hours(TOMORROW, 9, [7, 7, 7]),
                                     LATER: hours(LATER, 9, [9, 9, 9])})]
        html = grip.render_summary(results, datetime(2026, 10, 5, 14, 5, tzinfo=grip.TZ), CFG)
        self.assertLess(html.index('<p class="ovl">Today, Mon 5 Oct</p>'), html.index('<p class="ovl">Tomorrow, Tue 6 Oct</p>'))
        self.assertIn('aria-label="Best today and tomorrow"', html)
        self.assertNotIn("Wed 7 Oct", html)
        self.assertNotIn("Prime", html)

    def test_band_run_and_when_words(self):
        day = hours(TOMORROW, 8, [3, 4, 5, 6, 6, 5, 6, 8, 9, 8])  # 08:00 to 18:00
        r = result("A", "S", {TOMORROW: day})
        run = grip.band_run(day, r["daily"][TOMORROW])
        self.assertEqual([hr["t"][11:13] for hr in run], ["15", "16", "17"])  # Prime, the last three hours
        self.assertEqual(grip.when_words(run, day), "late on")
        self.assertEqual(grip.when_words(day[0:2], day), "early on")
        self.assertEqual(grip.when_words(day[3:6], day), "around midday")
        self.assertEqual(grip.when_words(day[1:4], day), "in the morning")
        self.assertEqual(grip.when_words(day[5:8], day), "in the afternoon")
        self.assertEqual(grip.when_words(day[1:9], day), "most of the day")
        self.assertEqual(grip.when_words(day, day), "all day")


class SearchAndPopular(unittest.TestCase):
    def test_empty_search_wording(self):
        self.assertIn("var miss='No crag matches \u201c'+said+'\u201d. Try part of a name, such as Souter or Cove.';", grip.FIND_JS)

    def test_all_crags_link(self):
        results = [result("A", "S", {TODAY: hours(TODAY, 14, [6, 6, 6])}), result("A", "S", {TODAY: hours(TODAY, 14, [5, 5, 5])}),
                   result("B", "S", {TODAY: hours(TODAY, 14, [6, 6, 6])})]
        with unittest.mock.patch.object(grip, "load_popular", return_value=["A"]):
            html = grip.render_popular(results, {}, datetime(2026, 10, 5, 14, 5, tzinfo=grip.TZ), CFG)
        self.assertIn('<a class="all" href="#week-h">All 2 crags, next 7 days</a></div></section>', html)


class PopularTop(unittest.TestCase):
    """The Popular crags table shows the best POPULAR_TOP rows, ranked as before, and folds the rest behind a button."""

    def render(self, results, names, now, top=5):
        with unittest.mock.patch.object(grip, "load_popular", return_value=names), \
                unittest.mock.patch.object(grip, "POPULAR_TOP", top):
            return grip.render_popular(results, {}, now, CFG)

    @staticmethod
    def shown(html):
        """The crag names in the table's rows, in order, and which rows are folded away."""
        rows = re.findall(r'<tr role="row"( class="more")?><th scope="row" role="rowheader"><a href="[^"]+">([^<]+)</a>', html)
        return [n for _m, n in rows], [n for m, n in rows if m]

    def test_top_rows_and_ties(self):
        # day scores as shown: A 7; B 6 with 5 climbable hours; C and H 6 with 3 hours; E and D 5 with 3 hours, the fifth and
        # sixth rows, a tie broken by list order; F 4; G 3
        spec = {"A": [7, 7, 7], "B": [6, 6, 6, 6, 6], "C": [6, 6, 6], "H": [6, 6, 6], "D": [5, 5, 5], "E": [5, 5, 5],
                "F": [4, 4, 4], "G": [3, 3, 3]}
        results = [result(n, "S", {TODAY: hours(TODAY, 12, v), TOMORROW: hours(TOMORROW, 9, [5, 5, 5])}) for n, v in spec.items()]
        names = ["G", "F", "E", "D", "C", "H", "B", "A"]  # list order puts C before H and E before D
        html = self.render(results, names, datetime(2026, 10, 5, 11, 5, tzinfo=grip.TZ))
        order, folded = self.shown(html)
        self.assertEqual(order, ["A", "B", "C", "H", "E", "D", "F", "G"])  # every row is in the page: all show without JavaScript
        self.assertEqual(folded, ["D", "F", "G"])
        self.assertIn('<button type="button" class="pmore" id="pop-more" aria-controls="pop-rows" aria-expanded="true" hidden>'
                      "Show all 8 popular crags</button>", html)
        self.assertIn('<tbody role="rowgroup" id="pop-rows">', html)
        self.assertLess(html.index('id="pop-more"'), html.index('<a class="all"'))  # the grid link stays at the foot
        self.assertIn("<script>" + grip.POPULAR_JS + "</script>", html)

    def test_after_dark_ranks_by_tomorrow(self):
        gone = hours(TODAY, 9, [9, 9, 9])
        spec = {"A": 3, "B": 8, "C": 5, "D": 6, "E": 7, "F": 4, "G": 2}
        results = [result(n, "S", {TOMORROW: hours(TOMORROW, 9, [v] * 3), LATER: hours(LATER, 9, [10 - v] * 3)}, earlier=gone)
                   for n, v in spec.items()]
        html = self.render(results, list(spec), datetime(2026, 10, 5, 20, 0, tzinfo=grip.TZ))
        order, folded = self.shown(html)
        self.assertEqual(order, ["B", "E", "D", "C", "F", "A", "G"])
        self.assertEqual(folded, ["A", "G"])
        self.assertIn("Tomorrow <small>Tue 6 Oct</small>", html)
        self.assertIn("Day after <small>Wed 7 Oct</small>", html)

    def test_no_button_when_nothing_to_fold(self):
        results = [result(n, "S", {TODAY: hours(TODAY, 12, [6, 6, 6])}) for n in "ABCDE"]
        html = self.render(results, list("ABCDE"), datetime(2026, 10, 5, 11, 5, tzinfo=grip.TZ))
        self.assertEqual(self.shown(html), (list("ABCDE"), []))
        self.assertNotIn("pop-more", html)
        self.assertNotIn("<script>", html)

    def test_default_top(self):
        self.assertEqual(grip.POPULAR_TOP, 5)


class Stale(unittest.TestCase):
    def test_threshold(self):
        run = datetime(2026, 10, 5, 8, 17, tzinfo=grip.TZ)
        self.assertIsNone(grip.stale_age(run, run + timedelta(hours=9)))
        self.assertEqual(grip.stale_age(run, run + timedelta(hours=9, seconds=1)), 9)
        self.assertEqual(grip.stale_age(run, run + timedelta(hours=11, minutes=40)), 11)
        self.assertIsNone(grip.stale_age(run, run + timedelta(minutes=50)))

    def test_page_script_uses_the_same_threshold(self):
        self.assertEqual(grip.STALE_HOURS, 9)
        self.assertIn("age>9*3600000", grip.STALE_JS)
        self.assertIn("The next run is late, so treat it with care.", grip.STALE_JS)
        line = grip.fresh_line(datetime(2026, 10, 5, 18, 10, tzinfo=grip.TZ))
        self.assertIn('data-run="2026-10-05T18:10:00+01:00"', line)
        self.assertIn("Updated Mon 5 Oct, 18:10 &middot; Next update within the hour", line)


class ModelsSentence(unittest.TestCase):
    def said(self, rows, day=LATER, start=9, before=True, is_today=False):
        by_day = {day: hours(day, start, rows)}
        if before:  # an earlier day on which all three models have data
            by_day[TODAY] = hours(TODAY, 9, [5, 5, 5])
        r = result("A", "S", by_day)
        return grip.models_sentence(r, day, r["daily"][day], is_today)

    def test_agree(self):
        self.assertEqual(self.said([5, 6, 7, 6, 5]), ("a", "All three models are within 2 points all day."))
        self.assertEqual(self.said([(5, 7, 6)] * 4, is_today=True), ("a", "All three models are within 2 points for the rest of the day."))

    def test_one_differs_in_the_best_window(self):
        kind, s = self.said([5, 5, (7, 3, 7), (7, 2.6, 7), (7, 3.5, 7), 5])  # best window 11:00 to 14:00
        self.assertEqual(kind, "d")
        self.assertEqual(s, "ECMWF is up to 4 points lower than the other two from 11:00 to 14:00. This touches the best window.")

    def test_one_differs_outside_the_best_window(self):
        kind, s = self.said([7, 7, 7, 5, (5, 5, 8.6)])
        self.assertEqual(kind, "w")
        self.assertEqual(s, "ICON is up to 4 points higher than the other two at 13:00. The best window is not affected.")

    def test_just_over_two(self):
        self.assertEqual(self.said([7, 7, 7, (5, 5, 7.4)])[1],
                         "ICON is just over 2 points higher than the other two at 12:00. The best window is not affected.")

    def test_all_three_apart(self):
        self.assertEqual(self.said([(3, 6, 9), (3, 6, 9), (3, 6, 9)]),
                         ("d", "The models differ by up to 6 points from 09:00 to 12:00. This touches the best window."))

    def test_one_model_only(self):
        self.assertEqual(self.said([(None, 5, None)] * 3),
                         ("o", "Only ECMWF reaches this far ahead. Treat it as a rough guide."))
        # no earlier day shows the others, so the sentence does not claim they stop short
        self.assertEqual(self.said([(None, 5, None)] * 3, before=False),
                         ("o", "Only ECMWF has a forecast for this day. Treat it as a rough guide."))

    def test_a_model_stops_short(self):
        kind, s = self.said([5, 5, 5, (None, 5, 5), (None, 5, 5)])
        self.assertEqual(kind, "a")
        self.assertEqual(s, "Met Office only reaches to 12:00. The models are within 2 points all day.")
        kind, s = self.said([(None, 5, 5)] * 3)
        self.assertEqual(s, "Met Office does not reach this far ahead. Both models are within 2 points all day.")
        kind, s = self.said([(5, 5, 5), (None, 6, None), (None, 6, None)], start=15)
        self.assertEqual(kind, "o")
        self.assertTrue(s.endswith("Only one model covers part of the best window, so treat it as a rough guide."))


def cal_row(grip_score, feel, day="2026-10-01"):
    return {"grip": grip_score, "feel": feel, "date": day, "crag": "A"}


class HowSure(unittest.TestCase):
    def test_square_classification(self):
        self.assertEqual(grip.cal_mark(cal_row(6.4, "Crisp")), "in")       # shows 6, Grippy
        self.assertEqual(grip.cal_mark(cal_row(7.6, "Crisp")), "near")     # shows 8, a point above
        self.assertEqual(grip.cal_mark(cal_row(3.5, "Crisp")), "out")      # shows 4, two below
        self.assertEqual(grip.cal_mark(cal_row(1.4, "Soaked")), "in")
        self.assertEqual(grip.cal_mark(cal_row(10, "Prime")), "in")
        self.assertEqual(grip.cal_mark(cal_row(4.5, "Greasy")), "out")      # shows 5, two above Greasy's top

    def summary(self, n, right, within, pending=0):
        rows = [cal_row(6, "Crisp")] * n
        return {"n": n, "pending": pending, "bands_right": right, "within": within, "rows": rows}

    def test_not_very_yet_under_thirty(self):
        self.assertEqual(grip.sure_lead(self.summary(12, 6, 10)),
                         "Not very, yet. 12 days have been logged. Grip's score landed in the band climbers felt on 6 of them, and within a point on 10.")
        self.assertTrue(grip.sure_lead(self.summary(29, 15, 25)).startswith("Not very, yet. 29 days"))
        self.assertEqual(grip.sure_lead(self.summary(30, 15, 25)),
                         "30 days have been logged. Grip's score landed in the band climbers felt on 15 of them, and within a point on 25.")
        self.assertTrue(grip.sure_lead(self.summary(12, 6, 10, pending=2)).endswith(" 2 more are waiting to be scored."))
        self.assertEqual(grip.sure_lead(self.summary(1, 1, 1)), "Not very, yet. 1 day has been logged. Grip's score landed in the band climbers felt.")
        self.assertTrue(grip.sure_lead({"n": 0, "pending": 3, "rows": []}).startswith("Not very, yet. No logged days"))

    def test_squares_from_the_committed_calibration(self):
        """The squares and the lead agree with the summary computed from the committed calibration.json."""
        cfg = {"crags": [], "zones": {}}
        with unittest.mock.patch.object(grip, "fetch_log", return_value=[]), \
                unittest.mock.patch.object(grip, "write_calibration_csv"), unittest.mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GRIP_FAKE", None)
            cal = grip.calibrate(cfg)
        html = grip.render_sure(cal)
        marks = re.findall(r'<i class="(in|near|out)"></i>', html.split('class="sql"')[0])
        self.assertEqual(len(marks), cal["n"])
        self.assertEqual(marks.count("in"), cal["bands_right"])
        self.assertEqual(marks.count("in") + marks.count("near"), cal["within"])
        self.assertIn(f'{cal["n"]} days have been logged', html)


class GridSub(unittest.TestCase):
    def w(self, aspect=None, typ="trad"):
        return {"crag": {"aspect": aspect, "type": typ}}

    def test_labels(self):
        self.assertEqual(grip.grid_sub([self.w("NW")]), "Faces NW")
        self.assertEqual(grip.grid_sub([self.w("E", "sport")]), "Faces E · sport")
        self.assertEqual(grip.grid_sub([self.w()]), "Aspect not known")
        self.assertEqual(grip.grid_sub([self.w("N")] * 4), "Best of 4 walls")
        self.assertEqual(grip.grid_sub([self.w("N"), self.w("S", "sport")]), "Best of 2 walls · sport")
        self.assertNotIn("trad", grip.grid_sub([self.w("N", "trad")]))


class Nav(unittest.TestCase):
    def nav(self, html):
        return re.search(r'<nav aria-label="Main">(.*?)</nav>', html).group(1)

    def test_every_page(self):
        cal = {"n": 0, "pending": 0, "rows": []}
        now = datetime(2026, 10, 5, 12, 0, tzinfo=grip.TZ)
        pages = {"log": (grip.render_log({"crags": []}), "Contribute", ""),
                 "birds": (grip.render_birds({"crags": []}, now), "Birds", ""),
                 "method": (grip.render_method(cal, now, ["ECMWF"]), "Method", ""),
                 "crag": (grip.header_bar("../"), None, "../")}
        for name, (html, current, root) in pages.items():
            with self.subTest(name):
                nav = self.nav(html)
                self.assertEqual(re.findall(r'href="([^"]+)"', nav),
                                 [root or "./", root + "log.html", root + "birds.html", root + "method.html"])
                self.assertEqual(re.findall(r'>(\w+)</a>', nav), ["Forecast", "Contribute", "Birds", "Method"])
                cur = re.findall(r'aria-current="page"[^>]*>(\w+)<', nav)
                self.assertEqual(cur, [current] if current else [])
                self.assertNotIn("Back to the forecast</a></div></header>", html)

    def test_method_page_holds_what_left_home(self):
        cal = {"n": 1, "pending": 0, "bias": 0.0, "mae": 0.0, "bands_right": 1, "within": 1, "by_model": {},
               "rows": [{"date": "2026-10-01", "crag": "A", "feel": "Crisp", "grip": 6.2, "models": {}, "era": None}]}
        html = grip.render_method(cal, datetime(2026, 10, 5, 12, 0, tzinfo=grip.TZ), ["Met Office", "ECMWF", "ICON"])
        for text in ("<h1>How Grip works</h1>", "<th>Factor</th><th>Points</th><th>Why</th>", "The index is 3 plus half the points",
                     "Models in the latest run, Mon 5 Oct, 12:00: Met Office, ECMWF, ICON.", 'id="days">Checking Grip against real days',
                     "1 logged day scored so far", "Grip is independent and not affiliated with the SMC or UKClimbing.",
                     "Open-Meteo</a> (CC BY 4.0)"):
            self.assertIn(text, html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
