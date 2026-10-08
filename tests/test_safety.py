"""Tests for the safety wording: the footer notice on every page, the Method page's "What Grip does not tell you" section and
its foot, the crag pages' big-sea notice and the Sea line's daylight high, and the contrast of the footer's muted lines.

Standard library only. Run from the repository root or anywhere: python3 tests/test_safety.py
"""
import json
import os
import re
import sys
import unittest
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import grip  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTICE = ("Grip forecasts how dry the rock is likely to be. It does not tell you whether a crag, route or sea is safe. "
          "Climbing is dangerous: check the rock, the sea and the tide yourself, and climb at your own risk.")
TAIL = "A big sea can reach walls that are not marked tidal. Check the sea and the weather on the day before you commit to a route."
INDEPENDENT = "Grip is independent and not affiliated with the SMC or UKClimbing."
DAY_TIME, NIGHT_TIME = "2026-10-05T11:37", "2026-10-05T20:10"  # a Monday: today and tomorrow, then after dark tomorrow and Wednesday


def load_cfg(names):
    with open(os.path.join(ROOT, "crags.json")) as f:
        cfg = json.load(f)
    cfg["crags"] = [c for c in cfg["crags"] if c["name"] in names]
    return cfg


def at(when, fn):
    """Run fn with the build's clock fixed at when (local time)."""
    fixed = datetime.fromisoformat(when).replace(tzinfo=grip.TZ)

    class Fixed(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    real, grip.datetime = grip.datetime, Fixed
    try:
        return fn()
    finally:
        grip.datetime = real


def build(when, sea=None, names=("Logie Head",)):
    """The synthetic weather (GRIP_FAKE's) at a fixed time; sea(day, is_daylight) gives every wave height when set, by date.
    Returns (cfg, results, tides, now, models, marine)."""
    cfg = load_cfg(set(names))

    def run():
        models, marine = grip.fake_data(cfg["zones"])
        if sea:
            for zk, m in marine.items():
                m["wave_height"] = [sea(t[:10], grip.daylight(t, cfg["zones"][zk])) for t in m["time"]]
        results, tides, now = grip.build(cfg, models, marine)
        return cfg, results, tides, now, models, marine
    return at(when, run)


def crag_pages(when, sea=None, names=("Logie Head",)):
    """{crag name: page} built at when, with the sea as build() takes it."""
    cfg, results, tides, now, models, marine = build(when, sea, names)

    def run():
        view = grip.coast_view(results, now, cfg)
        nxt = grip.next_view(results, view)
        here = grip.zone_now(cfg, models, marine, now)
        return {g: grip.render_detail(g, w, tides, now, now.date(), cfg, view, here, [], nxt) for g, w in grip.groups_of(results)}
    return at(when, run)


def by_day(heights, night=0.5):
    """A sea that is heights[date] in daylight and night (default 0.5 m) after dark; dates not given are 1.0 m."""
    return lambda d, is_day: heights.get(d, 1.0) if is_day else night


def text(fragment):
    return re.sub(r"<[^>]+>", "", fragment)


def notice_of(html):
    m = re.search(r'<div class="caution sea" role="note"><i aria-hidden="true">!</i><p>([^<]*)</p></div>', html)
    return m.group(1) if m else None


def sea_line(html):
    return re.search(r"<dt>Sea</dt><dd>([^<]+)</dd>", html).group(1)


class Footer(unittest.TestCase):
    """The notice on every page the build generates, forms included, exactly once; sources lines in the footer."""

    @classmethod
    def setUpClass(cls):
        cfg, results, tides, now, models, marine = build(DAY_TIME, names=("Logie Head", "Souter Head", "Buchan Walls"))
        cal = {"n": 0, "pending": 0, "rows": []}
        cls.pages = at(DAY_TIME, lambda: {
            "index.html": grip.render(results, tides, now, cfg, ["Met Office", "ECMWF", "ICON"], None),
            "method.html": grip.render_method(cal, now, ["Met Office"]),
            "birds.html": grip.render_birds(cfg, now),
            "log.html": grip.render_log(cfg, cal),
            "note.html": grip.render_note(cfg),
            "feedback.html": grip.render_feedback()})
        cls.pages.update({f"detail/{grip.slug(g)}.html": p for g, p in crag_pages(DAY_TIME, names=("Logie Head", "Souter Head", "Buchan Walls")).items()})

    def test_notice_once_on_every_page(self):
        self.assertEqual(len(self.pages), 9)
        for name, html in self.pages.items():
            with self.subTest(name):
                self.assertEqual(html.count(NOTICE), 1)
                self.assertIn(f'<footer class="sitefoot"><div class="sf"><p class="sf-m"><a href="{"../" if "/" in name else ""}method.html">'
                              f'Method</a></p><p class="sf-note">{NOTICE}</p>', html)  # the Method link below 340 px stays
                self.assertTrue(html.endswith("</footer></body></html>"))
                self.assertLess(html.index("</main>"), html.index('<footer class="sitefoot">'))

    def test_sources_lines_in_the_footer(self):
        foot = {n: h[h.index('<footer class="sitefoot">'):] for n, h in self.pages.items()}
        for name in ("index.html", "log.html", "note.html", "feedback.html"):
            self.assertNotIn("sf-src", foot[name], name)  # no sources line: the notice stands alone
        self.assertIn(f'<div class="sf-src"><p>{grip.BIRD_SOURCES}</p></div>', foot["birds.html"])
        self.assertRegex(foot["detail/logie-head.html"], r'<div class="sf-src"><p>Crag facts from the <a href="https://routes\.smc\.org\.uk/crag/\d+">'
                                                          r"SMC routes database</a>, climbers' reports and local developers' notes, reworded by Grip\.</p></div>")
        for name, html in self.pages.items():
            main = html[:html.index('<footer class="sitefoot">')]
            self.assertNotIn("reworded by Grip", main, name)  # moved out of the main content
            self.assertNotIn('class="foot"><p>Forecast data', main, name)
            self.assertEqual(INDEPENDENT in html, name == "method.html", name)


class Method(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = grip.render_method({"n": 0, "pending": 0, "rows": []}, datetime(2026, 10, 5, 12, 0, tzinfo=grip.TZ), ["ECMWF"])

    def test_second_section_with_exact_text(self):
        h = self.html
        m = re.search(r'<main><h1>How Grip works</h1><div class="method"><p>Grip estimates the state of the rock[^<]*</p></div>'
                      r'(<section class="notell" aria-labelledby="not-h">.*?</section>)<h2 id="factors">Scoring factors</h2>'
                      r'<div class="method"><table class="factors">', h)
        self.assertIsNotNone(m)  # straight after the opening explanation, before Scoring factors
        sec = m.group(1)
        self.assertEqual(re.findall(r"<h2[^>]*>([^<]+)</h2>", sec), ["What Grip does not tell you"])
        parts = [(tag, text(body)) for tag, body in re.findall(r"<(p|div class=\"caution\" role=\"note\")>(.*?)</(?:p|div)>", sec)]
        self.assertEqual([t for _tag, t in parts], [
            "Grip scores friction: how dry and grippy the rock is likely to be, from weather and sea forecasts. It is a guide, not a guarantee, and it can be wrong.",
            "It does not tell you whether the sea is safe, and it does not cover freak waves, tide times, loose rock or rockfall, access, how hard a route is, "
            "or your own ability. Nesting birds are covered only as far as the bird register goes, and it is not a definitive record.",
            "Crag facts such as aspect, tide, shelter and birds come from guidebooks and climbers’ reports. They may be out of date or wrong. "
            "If you find one that is, send a crag note.",
            "!Climbing and moving around sea cliffs carry a risk of serious injury or death. You are responsible for your own decisions: look at the rock "
            "and the sea when you arrive, check the tide times, and turn back if in doubt.",
            "Grip is a free, non-commercial project, provided as is, with no promise that it is accurate or always available. Use it at your own risk."])
        self.assertEqual([tag for tag, _t in parts], ["p", "p", "p", 'div class="caution" role="note"', "p"])
        self.assertIn('<div class="caution" role="note"><i aria-hidden="true">!</i><p>Climbing and moving', sec)
        self.assertNotIn("tidal or low wall", h)
        self.assertNotIn("as it is", h)
        self.assertNotRegex(sec, "\u2014|!</p>|'")  # no em dashes or exclamation marks; the curly apostrophe

    def test_links_resolve(self):
        sec = re.search(r'<section class="notell".*?</section>', self.html).group(0)
        links = re.findall(r'<a href="([^"]+)">([^<]+)</a>', sec)
        self.assertEqual(links, [("birds.html", "bird register"), ("note.html", "send a crag note")])  # no wall prefilled
        written = {page for _k, page, _t in grip.FORM_PAGES} | {"birds.html"}  # the pages main() writes beside method.html
        for href, _t in links:
            self.assertIn(href, written)

    def test_independence_line_last_in_the_footer(self):
        foot = self.html[self.html.index('<footer class="sitefoot">'):]
        self.assertTrue(foot.endswith(f"<p>{INDEPENDENT}</p></div></div></footer></body></html>"))
        self.assertRegex(foot, r'<div class="sf-src"><p>Forecast data: <a href="https://open-meteo.com/">Open-Meteo</a> \(CC BY 4\.0\).*?'
                               r"climbers' reports\.</p><p>" + re.escape(INDEPENDENT))
        self.assertEqual(self.html.count(INDEPENDENT), 1)


class BigSea(unittest.TestCase):
    """The crag-level notice from synthetic marine data at Logie Head; Today is 5 Oct, Tomorrow 6 Oct, the day after 7 Oct."""

    def test_threshold_and_night(self):
        self.assertEqual(grip.BIG_SEA_M, 1.5)
        cases = [({"2026-10-05": 1.4, "2026-10-06": 1.4}, 0.5, None),
                 ({"2026-10-05": 1.5, "2026-10-06": 1.0}, 0.5, f"Big sea: up to 1.5 m today. {TAIL}"),
                 ({"2026-10-05": 1.0, "2026-10-06": 1.0}, 3.0, None)]  # 3 m, but only at night
        for heights, night, want in cases:
            with self.subTest(heights=heights, night=night):
                html = crag_pages(DAY_TIME, by_day(heights, night))["Logie Head"]
                self.assertEqual(notice_of(html), want)
                if want is None:
                    self.assertNotIn("Big sea", html)  # no "sea OK" state either
                    self.assertNotIn("caution sea", html)

    def test_wordings(self):
        cases = [(DAY_TIME, {"2026-10-05": 2.1, "2026-10-06": 1.0}, f"Big sea: up to 2.1 m today. {TAIL}"),
                 (DAY_TIME, {"2026-10-05": 1.0, "2026-10-06": 1.9}, f"Big sea: up to 1.9 m tomorrow. {TAIL}"),
                 (DAY_TIME, {"2026-10-05": 2.1, "2026-10-06": 2.4}, f"Big sea: up to 2.1 m today and 2.4 m tomorrow. {TAIL}"),
                 (NIGHT_TIME, {"2026-10-05": 3.0, "2026-10-06": 2.4, "2026-10-07": 2.6},
                  f"Big sea: up to 2.4 m tomorrow and 2.6 m on Wednesday. {TAIL}"),
                 (NIGHT_TIME, {"2026-10-05": 3.0, "2026-10-06": 1.0, "2026-10-07": 2.6}, f"Big sea: up to 2.6 m on Wednesday. {TAIL}"),
                 (NIGHT_TIME, {"2026-10-05": 3.0, "2026-10-06": 1.0, "2026-10-07": 1.0}, None)]  # today is over: its sea drops out
        for when, heights, want in cases:
            with self.subTest(when=when, heights=heights):
                self.assertEqual(notice_of(crag_pages(when, by_day(heights))["Logie Head"]), want)

    def test_one_decimal_place(self):
        sea = {"maxes": {"2026-10-05": 2.06, "2026-10-06": 1.449}}
        days = [date(2026, 10, 5), date(2026, 10, 6)]
        self.assertEqual(grip.big_sea_text(sea, days, False), f"Big sea: up to 2.1 m today. {TAIL}")
        self.assertIsNone(grip.big_sea_text({"maxes": {}}, days, False))
        self.assertIsNone(grip.big_sea_text(None, days, False))

    def test_crag_level_only(self):
        heights = {"2026-10-05": 2.1, "2026-10-06": 2.4}
        for gname, html in crag_pages(DAY_TIME, by_day(heights), ("Logie Head", "Buchan Walls")).items():
            with self.subTest(gname):
                self.assertEqual(html.count("Big sea"), 1)  # no wall card, Walls row or summary carries it
                self.assertRegex(html, r'Send a crag note</a></p></div><div class="caution sea" role="note">.*?</div><div class="cols">')  # between the title block and the columns
                self.assertNotIn("Big sea", html[html.index('<div class="cols">'):])

    def test_the_same_for_every_wall_whatever_its_tags(self):
        cfg, results, *_ = build(DAY_TIME, by_day({"2026-10-05": 2.1}))
        walls = [r["crag"] for r in results]
        self.assertTrue(any(c.get("tidal") for c in walls) and any(not c.get("tidal") for c in walls))
        self.assertEqual(notice_of(crag_pages(DAY_TIME, by_day({"2026-10-05": 2.1}))["Logie Head"]), f"Big sea: up to 2.1 m today. {TAIL}")

    def test_home_and_popular_unchanged(self):
        cfg, results, tides, now, _m, _mar = build(DAY_TIME, by_day({"2026-10-05": 2.1, "2026-10-06": 2.4}), ("Logie Head", "Souter Head"))
        html = at(DAY_TIME, lambda: grip.render(results, tides, now, cfg, ["Met Office", "ECMWF", "ICON"], None))
        self.assertNotIn("Big sea", html)
        self.assertNotIn('class="caution', html)
        popular = at(DAY_TIME, lambda: grip.render_popular(results, tides, now, cfg))
        self.assertNotIn("Big sea", popular)


class SeaLine(unittest.TestCase):
    def test_up_to_is_the_daylight_high(self):
        """A 3.0 m sea at night and 1.2 m by day: the Sea line and the notice both go by the daylight 1.2 m."""
        html = crag_pages(DAY_TIME, by_day({"2026-10-05": 1.2, "2026-10-06": 1.0}, night=3.0))["Logie Head"]
        self.assertTrue(sea_line(html).endswith(" Up to 1.2 m today."), sea_line(html))
        self.assertIsNone(notice_of(html))
        html = crag_pages(NIGHT_TIME, by_day({"2026-10-06": 1.3}, night=3.0))["Logie Head"]
        self.assertTrue(sea_line(html).endswith(" Up to 1.3 m on Tuesday."), sea_line(html))

    def test_notice_and_sea_line_agree(self):
        html = crag_pages(DAY_TIME, by_day({"2026-10-05": 2.1, "2026-10-06": 2.4}, night=3.0))["Logie Head"]
        self.assertTrue(sea_line(html).endswith(" Up to 2.1 m today."))
        self.assertTrue(notice_of(html).startswith("Big sea: up to 2.1 m today and 2.4 m tomorrow."))


class Snapshot(unittest.TestCase):
    """The daily grip-history snapshot records, per weather point, each shown day's daylight high as shown and whether the
    big-sea notice showed, so the BIG_SEA_M review can count notice days per crag from the snapshots."""

    def snap(self, when, heights, night=0.5):
        cfg, results, tides, now, models, marine = build(when, by_day(heights, night))
        here = grip.zone_now(cfg, models, marine, now)
        zone = results[0]["crag"]["zone"]
        return cfg, results, now, here, zone, grip.snapshot(results, now, here)

    def test_day_run(self):
        cfg, _r, _n, _h, zone, snap = self.snap(DAY_TIME, {"2026-10-05": 2.1, "2026-10-06": 1.0}, night=3.0)
        self.assertEqual(set(snap["sea"]), set(cfg["zones"]))  # every weather point
        self.assertEqual(snap["sea"][zone], {"notice": True, "days": {"2026-10-05": {"high": 2.1, "big": True},
                                                                      "2026-10-06": {"high": 1.0, "big": False}}})  # daylight, not the 3 m night
        self.assertEqual(snap["walls"].keys(), grip.snapshot(_r, _n)["walls"].keys())  # the walls are as before
        self.assertNotIn("sea", grip.snapshot(_r, _n))

    def test_after_dark_run_records_the_days_the_page_shows(self):
        *_x, zone, snap = self.snap(NIGHT_TIME, {"2026-10-05": 3.0, "2026-10-06": 1.0, "2026-10-07": 1.4})
        self.assertEqual(snap["sea"][zone], {"notice": False, "days": {"2026-10-06": {"high": 1.0, "big": False},
                                                                       "2026-10-07": {"high": 1.4, "big": False}}})

    def test_high_as_shown_and_the_page_agree(self):
        cfg, results, now, here, zone, snap = self.snap(DAY_TIME, {"2026-10-05": 1.0, "2026-10-06": 1.46})
        self.assertEqual(snap["sea"][zone]["days"]["2026-10-06"], {"high": 1.5, "big": True})
        self.assertTrue(snap["sea"][zone]["notice"])
        html = crag_pages(DAY_TIME, by_day({"2026-10-05": 1.0, "2026-10-06": 1.46}))["Logie Head"]
        self.assertEqual(notice_of(html), f"Big sea: up to 1.5 m tomorrow. {TAIL}")

    def test_saved_to_the_history_file(self):
        import tempfile
        cfg, results, now, here, zone, _s = self.snap(DAY_TIME, {"2026-10-05": 2.1})
        with tempfile.TemporaryDirectory() as folder:
            path = grip.save_snapshot(results, now, folder, here=here)
            with open(path) as f:
                saved = json.load(f)
        self.assertEqual(saved["sea"][zone]["days"]["2026-10-05"], {"high": 2.1, "big": True})
        self.assertEqual(saved["cols"], grip.SNAPSHOT_COLS)


def contrast(a, b):
    def lum(hexc):
        rgb = [int(hexc[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class Contrast(unittest.TestCase):
    def test_footer_lines_meet_wcag_aa(self):
        """The 13 px muted sources and independence lines, and their ink links, on the footer's paper, light and dark."""
        light, dark = grip.TOKENS_CSS.split("@media (prefers-color-scheme:dark)")
        for mode, css in (("light", light), ("dark", dark)):
            tok = dict(re.findall(r"--(paper|muted|ink):(#[0-9a-f]{6})", css))
            for fg in ("muted", "ink"):
                with self.subTest(mode=mode, fg=fg):
                    self.assertGreaterEqual(contrast(tok[fg], tok["paper"]), 4.5)
        self.assertIn(".sitefoot{background:var(--paper)", grip.CSS)
        self.assertIn("font-size:var(--t-small);line-height:1.45;color:var(--muted)}", grip.CSS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
