"""Tests for the crag pages' layout logic: the wall opened by default, what goes to Across the crag and what stays on the wall cards,
source tags left out of notes, the birds line, the Why sentence's figures, the hour-by-hour points and wet-risk columns, and the
page itself built from synthetic weather (no source tags, every hour table present without script).

Standard library only. Run from the repository root or anywhere: python3 tests/test_crag.py
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
TODAY = "2026-10-05"
TOMORROW = "2026-10-06"


def wall(name, daily=None, **c):
    return {"crag": {"name": "Crag", "wall": name, "zone": "z", **c}, "daily": daily or {}, "hours": [], "earlier": []}


def day(index, usable, spread=0, n=3, wet=0):
    return {"index": index, "usable": usable, "hours": 10, "start": "11:00", "end": "14:00", "spread": spread, "n": n, "wet": wet}


class OpenWall(unittest.TestCase):
    def test_best_score_as_shown(self):
        walls = [wall("A", {TODAY: day(5.2, 6)}), wall("B", {TODAY: day(6.6, 2)}), wall("C", {TODAY: day(6.4, 9)})]
        self.assertEqual(grip.open_wall(walls, TODAY), 1)  # 7 beats 6, whatever the hours

    def test_tie_goes_to_most_climbable_hours(self):
        walls = [wall("A", {TODAY: day(6.6, 4)}), wall("B", {TODAY: day(7.4, 8)}), wall("C", {TODAY: day(6.5, 8)})]
        self.assertEqual(grip.open_wall(walls, TODAY), 1)  # all show 7; B and C have 8 hours; B comes first

    def test_tie_on_everything_goes_to_the_first(self):
        walls = [wall("A", {TODAY: day(3, 0)}), wall("B", {TODAY: day(3.2, 0)})]
        self.assertEqual(grip.open_wall(walls, TODAY), 0)

    def test_not_simply_the_first(self):
        walls = [wall("A", {TODAY: day(1, 0)}), wall("B", {TODAY: day(2, 0)})]
        self.assertEqual(grip.open_wall(walls, TODAY), 1)

    def test_after_dark_uses_tomorrow(self):
        walls = [wall("A", {TODAY: day(9, 9), TOMORROW: day(2, 0)}), wall("B", {TOMORROW: day(5, 3)})]
        self.assertEqual(grip.open_wall(walls, TOMORROW), 1)

    def test_unscored_wall_never_wins(self):
        walls = [wall("A"), wall("B", {TODAY: day(0, 0)})]
        self.assertEqual(grip.open_wall(walls, TODAY), 1)

    def test_ids_unique(self):
        walls = [wall("Main Face"), wall(None), wall("Main face"), wall("Walls")]
        self.assertEqual(grip.wall_ids(walls), ["main-face", "main-face-2", "main-face-3", "walls"])


ZONE = {"name": "Cullen and Portsoy", "lat": 57.695, "lon": -2.76, "coast_faces": 0}
ZN = {"rain": ("Met Office", 0.6, 1.4), "sea": {"h": 1.1, "dir": 135, "period": 9.2, "max": 1.2}}
TIDES = {"z": {TODAY: ["05:44", "18:08"], TOMORROW: ["06:34"]}}
DAYS = [date(2026, 10, 5), date(2026, 10, 6)]


class Across(unittest.TestCase):
    def facts(self, films):
        walls = [wall(f"W{i}") for i in range(len(films))]
        for r, f in zip(walls, films):
            r["film_now"] = ("Met Office", f) if f is not None else None
        return grip.across_facts(walls, ZONE, ZN, TIDES, DAYS, ["Today", "Tomorrow"])

    def test_crag_wide_facts_stated_once(self):
        across, per_wall = self.facts([0, 0, 0])
        self.assertEqual([h for h, _t in across], ["Rock now", "Low water", "Sea", "Weather"])
        a = dict(across)
        self.assertEqual(a["Rock now"], "Dry. 0.6 mm of rain in 24 hours, 1.4 mm in 72.")
        self.assertEqual(a["Low water"], "Today 05:44, 18:08. Tomorrow 06:34.")
        self.assertEqual(a["Sea"], "1.1 m from the SE, 9 s swell. Up to 1.2 m today.")
        self.assertEqual(a["Weather"], "Cullen and Portsoy point, shared along this stretch. Coast counted as facing N.")
        self.assertEqual(per_wall, [[], [], []])  # nothing differs, so no wall card repeats it

    def test_sea_after_dark_names_the_day(self):
        """After dark the page leads with tomorrow, so the sea's high point is tomorrow's, named by its day, never "today"."""
        walls = [wall("W0")]
        walls[0]["film_now"] = ("Met Office", 0)
        zn = {**ZN, "sea": {**ZN["sea"], "maxes": {TODAY: 1.2, TOMORROW: 1.0}}}
        across, _pw = grip.across_facts(walls, ZONE, zn, TIDES, DAYS[1:] + [date(2026, 10, 7)], ["Tomorrow", "Day after"])
        self.assertEqual(dict(across)["Sea"], "1.1 m from the SE, 9 s swell. Up to 1.0 m on Tuesday.")
        across, _pw = grip.across_facts(walls, ZONE, zn, TIDES, DAYS, ["Today", "Tomorrow"])
        self.assertEqual(dict(across)["Sea"], "1.1 m from the SE, 9 s swell. Up to 1.2 m today.")
        across, _pw = grip.across_facts(walls, ZONE, ZN, TIDES, DAYS[1:] + [date(2026, 10, 7)], ["Tomorrow", "Day after"])
        self.assertEqual(dict(across)["Sea"], "1.1 m from the SE, 9 s swell.")  # no forecast for that day: no high point

    def test_sea_highs_by_day(self):
        times = [f"{TODAY}T{h:02d}:00" for h in range(24)] + [f"{TOMORROW}T{h:02d}:00" for h in range(24)]
        heights = [0.5] * 20 + [1.4, None, 0.6, 0.6] + [0.8] * 12 + [1.04] + [0.2] * 11
        marine = {"z": {"time": times, "wave_height": heights, "wave_direction": [90] * 48, "wave_period": [7] * 48}}
        now = datetime(2026, 10, 5, 20, 10, tzinfo=grip.TZ)
        sea = grip.zone_now({"zones": {"z": ZONE}}, {}, marine, now)["z"]["sea"]
        self.assertEqual((sea["h"], sea["max"]), (1.4, 0.5))  # 1.4 m at 20:00 is the sea now, but after dark: never the day's high
        self.assertEqual(sea["maxes"], {TODAY: 0.5, TOMORROW: 1.04})

    def test_a_differing_wall_carries_its_own_rock(self):
        across, per_wall = self.facts([0, 0.3, 0])
        self.assertTrue(dict(across)["Rock now"].startswith("Dry on 2 of 3 walls."))
        self.assertEqual(per_wall, [[], [("Rock now", "Damp (0.30 mm on the rock).")], []])

    def test_wall_facts_stay_on_the_card(self):
        c = {"aspect": "SE", "tidal": True, "tidal_note": "Partially Tidal", "inlet": True, "sheltered": True,
             "birds": {"months": [], "level": "clear", "note": "Free of nesting birds (SMC database)"}}
        heads = [h for h, _t in grip.shapes_items(c, ZONE, DAYS[0], "today", ZN["sea"])]
        self.assertEqual(heads, ["Sun", "Shelter", "Sea", "Tide", "Seepage", "Birds"])
        for h in ("Rock now", "Low water", "Weather"):
            self.assertNotIn(h, heads)  # stated once, in Across the crag
        plain = {"aspect": "N", "tidal_note": "Non Tidal"}
        items = grip.shapes_items(plain, ZONE, DAYS[0], "today", ZN["sea"])
        self.assertEqual([h for h, _t in items], ["Sun", "Sea", "Seepage", "Birds"])
        self.assertEqual(dict(items)["Seepage"], "None noted.")
        self.assertEqual(dict(items)["Sun"], "Does not reach the face today.")
        self.assertRegex(dict(grip.shapes_items({"aspect": "SE"}, ZONE, DAYS[0], "today", ZN["sea"]))["Sun"],
                         r"^On the face \d\d:00 to \d\d:00, when it shines\.$")
        self.assertIn("Tide", [h for h, _t in grip.shapes_items({"aspect": "N"}, ZONE, DAYS[0], "today", ZN["sea"])])  # status unknown

    def test_sea_depends_on_the_wall(self):
        sea = {"h": 1.0, "dir": 0, "period": 6}
        self.assertEqual(grip.wall_sea_text(sea, {"aspect": "N"}), "Onto the face, counted in full: 1.0 m at the wall.")
        self.assertEqual(grip.wall_sea_text(sea, {"aspect": "S"}), "Comes from behind the face, counted at 40%: 0.4 m at the wall.")
        self.assertEqual(grip.wall_sea_text({**sea, "period": 10}, {"aspect": "SE"}),
                         "Runs along the face, counted at 70%, as long swell wraps round: 0.7 m at the wall.")
        self.assertEqual(grip.wall_sea_text(sea, {"aspect": "S", "inlet": True}), "Comes from behind the face, funnels in the inlet, counted at 1.5 times: 1.5 m at the wall.")
        self.assertEqual(grip.wall_sea_text(sea, {"aspect": "N", "sea_sheltered": True}), "Onto the face, broken by offshore rock, counted at half: 0.5 m at the wall.")
        self.assertEqual(grip.wall_sea_text(sea, {}), "Aspect not known, counted in full: 1.0 m at the wall.")
        for c in ({"aspect": "N"}, {"aspect": "S", "tidal": True}, {"aspect": "N", "inlet": True}):
            said = grip.wall_sea_text({"h": 3.0, "dir": 0, "period": 6}, c)
            self.assertNotIn("point", said)  # no points and no spray threshold
            self.assertNotIn("spray", said)

    def test_wall_sub_and_tags(self):
        self.assertEqual(grip.wall_sub({"aspect": "SE", "tidal": True, "tidal_note": "Partially Tidal", "seeps": True}), "Faces SE · part tidal · seeps")
        self.assertEqual(grip.wall_sub({"aspect": "NW", "tidal_note": "Non Tidal"}), "Faces NW")
        self.assertEqual(grip.wall_tags({"aspect": "SE", "sheltered": True, "tidal_note": "Non Tidal"}, DAYS), ["Faces SE", "Sheltered bay", "Not tidal"])
        self.assertEqual(grip.wall_tags({"aspect": "NW", "tidal_note": "Non Tidal"}, DAYS), ["Faces NW", "Open", "Not tidal"])
        self.assertEqual(grip.wall_tags({"tidal": True, "tidal_note": "Partially Tidal", "inlet": True}, DAYS), ["Aspect not known", "Inlet", "Part tidal"])

    def test_shelter_wording(self):
        """Inlet wording only for inlet walls; a sheltered wall without the inlet flag reads as the back of a bay."""
        shelter = lambda c: dict(grip.shapes_items(c, ZONE, DAYS[0], "today", ZN["sea"])).get("Shelter", "")
        self.assertTrue(shelter({"aspect": "E", "sheltered": True, "inlet": True}).startswith("Narrow inlet."))
        self.assertTrue(shelter({"aspect": "E", "sheltered": True}).startswith("Back of a bay."))
        self.assertNotIn("inlet", shelter({"aspect": "E", "sheltered": True}).lower())

    def test_override_aspect_drops_the_inherited_list(self):
        """A wall whose aspect comes from data/overrides.json carries no inherited aspect_note, so its sun line names only that
        aspect, unless the override gives its own aspect_note."""
        with open(os.path.join(ROOT, "data", "overrides.json")) as f:
            ov = json.load(f)["walls"]
        with open(os.path.join(ROOT, "crags.json")) as f:
            walls = {grip.label(c): c for c in json.load(f)["crags"]}
        checked = 0
        for lab, o in ov.items():
            if "aspect" in o and lab in walls:
                checked += 1
                self.assertEqual(walls[lab].get("aspect_note"), o.get("aspect_note"), lab)
        self.assertGreater(checked, 10)
        for lab, asp in (("Alligator Ridge (North Wall)", "N"), ("Logie Head (Pinnacle)", "NW")):
            c = walls[lab]
            self.assertEqual(c["aspect"], asp)
            self.assertEqual(grip.wall_tags(c, DAYS)[0], f"Faces {asp}")
            self.assertNotIn("in places", dict(grip.shapes_items(c, ZONE, DAYS[0], "today", ZN["sea"]))["Sun"])


def data_notes():
    """Every note text in data/overrides.json and every note string in tools/build_crags.py (data/birds.json's notes are
    Grip's own words without tags; Birds.test_bird_notes_have_no_tags checks them)."""
    with open(os.path.join(ROOT, "data", "overrides.json")) as f:
        ov = json.load(f)
    out = []

    def walk(x, key=""):
        if isinstance(x, dict):
            for k, v in x.items():
                walk(v, k)
        elif isinstance(x, list):
            for v in x:
                walk(v, key)
        elif isinstance(x, str) and key in ("note", "seep_note", "aspect_note", "tidal_note"):
            out.append(x)
    walk(ov)
    with open(os.path.join(ROOT, "tools", "build_crags.py")) as f:
        out += re.findall(r'"note": "([^"]+)"', f.read())
    return out


class Sources(unittest.TestCase):
    def test_every_tag_form(self):
        for raw, clean in [("Birds in summer (SMC)", "Birds in summer"), ("Generally bird free (UKC)", "Generally bird free"),
                           ("Free of nesting birds (SMC database)", "Free of nesting birds"), ("Bird free (UKC and SMC)", "Bird free"),
                           ("Bad seepage; usually wet until May (developers' notes, 2020)", "Bad seepage; usually wet until May"),
                           ("One corner sometimes carries a wet streak (developers' notes, 2024)", "One corner sometimes carries a wet streak"),
                           ("Large guano ledge in the centre (UKC); months not confirmed", "Large guano ledge in the centre; months not confirmed")]:
            self.assertEqual(grip.strip_sources(raw), clean)

    def test_data_notes_lose_only_their_tags(self):
        """Every note in the data files: only the known tag forms come out, and the rest of the text is unchanged."""
        forms = {"(SMC)", "(UKC)", "(SMC database)", "(UKC and SMC)", "(developers' notes, 2020)", "(developers' notes, 2024)"}
        notes = data_notes()
        self.assertGreater(len(notes), 2)
        tagged = 0
        for n in notes:
            removed = [t.strip() for t in grip.SOURCE_TAG.findall(n)]
            self.assertLessEqual(set(removed), forms, n)
            tagged += bool(removed)
            expect = n
            for t in removed:
                expect = expect.replace(" " + t, "").replace(t, "")
            self.assertEqual(grip.strip_sources(n), expect.strip())
            self.assertNotRegex(grip.strip_sources(n), r"\((?:SMC|UKC|developers)")
        self.assertGreater(tagged, 2)

    def test_other_brackets_and_names_untouched(self):
        for text in ("Logie Head (Embankment One)", "Grassy Pinnacle (North Wall)", "Faces SE (south-east and north-west)",
                     "Noted in the SMC routes database", "UKC logbooks say so", "Nesting birds noted in the SMC database; months not confirmed"):
            self.assertEqual(grip.strip_sources(text), text)


class HowSure(unittest.TestCase):
    def test_walls_named(self):
        self.assertEqual(grip.walls_named(["Embankment One"]), "Embankment One")
        self.assertEqual(grip.walls_named(["A", "B", "C"]), "A, B and C")
        names = ["Embankment One", "Embankment Two"] + [f"W{i}" for i in range(7)]
        self.assertEqual(grip.walls_named(names), "Embankment One, Embankment Two and 7 more")

    def test_shared_sentences_grouped_by_day(self):
        a, b, c = wall("A"), wall("B"), wall("C")
        s1, s2 = "ECMWF is up to 4 points lower than the other two from 09:00 to 12:00. This touches the best window.", "Other."
        sure = [(a, DAYS[0], s1), (a, DAYS[1], s2), (b, DAYS[0], s1), (c, DAYS[0], s2), (c, DAYS[1], s2)]
        self.assertEqual(grip.sure_groups(sure, DAYS), [(DAYS[0], [(["A", "B"], s1), (["C"], s2)]), (DAYS[1], [(["A", "C"], s2)])])
        self.assertEqual(grip.sure_groups([], DAYS), [])
        self.assertEqual(grip.sure_groups([(b, DAYS[1], s2)], DAYS), [(DAYS[1], [(["B"], s2)])])  # a day with nothing is left out


class Birds(unittest.TestCase):
    def test_no_information(self):
        self.assertEqual(grip.bird_status(None), "unknown")
        line = grip.birds_line(None)
        self.assertTrue(line.startswith("No information."))
        self.assertNotIn("None reported", line)

    def test_bird_free(self):
        self.assertEqual(grip.birds_line({"months": [], "level": "clear", "note": "Free of nesting birds (SMC database)"}), "None reported.")
        self.assertEqual(grip.birds_line({"months": [], "level": "clear", "note": "Almost no nesting birds, even in season (SMC database)"}),
                         "None reported. Almost no nesting birds, even in season.")
        self.assertNotIn("No information", grip.birds_line({"months": [], "level": "clear", "note": ""}))

    def test_nesting_placeholder(self):
        b = {"months": [4, 5, 6, 7], "level": "affected", "note": "Birds reported nesting; months not confirmed"}
        self.assertEqual(grip.birds_line(b), "Reported nesting, April to July, months not confirmed.")
        b = {"months": [4, 5, 6, 7], "level": "affected", "note": "Nesting birds can trouble the routes at the ridge's seaward tip (UKC); months not confirmed"}
        self.assertEqual(grip.birds_line(b), "Reported nesting, April to July, months not confirmed. "
                                             "Nesting birds can trouble the routes at the ridge's seaward tip.")

    def test_nesting_confirmed_and_restricted(self):
        b = {"months": [5, 6, 7, 8], "level": "restricted", "note": "Nesting kittiwakes April to August (SMC)", "confirmed": True}
        self.assertEqual(grip.birds_line(b), "Reported nesting, May to August. Climbing is restricted while they nest. Nesting kittiwakes April to August.")

    def test_possible_and_no_months(self):
        self.assertEqual(grip.birds_line({"months": [], "level": "possible", "note": ""}), "Reported nesting, months not known.")

    def test_every_wall_in_the_crag_list(self):
        with open(os.path.join(ROOT, "crags.json")) as f:
            crags = json.load(f)["crags"]
        for c in crags:
            b = c.get("birds")
            line = grip.birds_line(b)
            st = grip.bird_status(b)
            self.assertEqual(line.startswith("None reported"), st == "clear", c["name"])
            partly = (b or {}).get("level") == "partly"
            self.assertEqual(line.startswith("Reported nesting"), st == "nesting" and not partly, c["name"])
            self.assertEqual(line.startswith("Nesting on parts: "), partly, c["name"])
            self.assertEqual(line.startswith("No information"), st == "unknown", c["name"])
            self.assertNotRegex(line, r"\((?:SMC|UKC|developers)")

    def test_partly(self):
        b = {"months": [4, 5, 6, 7], "level": "partly", "note": "Kittiwakes nest on the left side; routes right of New Horizons are clear"}
        self.assertEqual(grip.birds_line(b), "Nesting on parts: kittiwakes nest on the left side; routes right of New Horizons are clear. "
                                             "April to July, months not confirmed.")
        b = {"months": [4, 5, 6, 7, 8], "level": "partly", "note": "Some nests on top", "confirmed": True, "months_source": "guidebook"}
        self.assertEqual(grip.birds_line(b), "Nesting on parts: some nests on top. April to August.")
        self.assertEqual(grip.bird_status(b), "nesting")
        self.assertIn("Nesting on parts now", grip.wall_tags({"birds": b}, [date(2026, 5, 3)]))
        self.assertNotIn("Birds nesting now", grip.wall_tags({"birds": b}, [date(2026, 5, 3)]))
        self.assertEqual(grip.wall_tags({"birds": b}, [date(2026, 10, 5)])[-1], "Tide not known")

    def test_clear_notes_read_on(self):
        self.assertEqual(grip.birds_line({"months": [], "level": "clear", "note": "No nesting birds reported"}), "None reported.")
        self.assertEqual(grip.birds_line({"months": [], "level": "clear", "note": "No nesting birds reported; the neighbouring Storm Wall can be nested"}),
                         "None reported. The neighbouring Storm Wall can be nested.")

    def test_bird_notes_have_no_tags(self):
        with open(os.path.join(ROOT, "data", "birds.json")) as f:
            for k, b in json.load(f)["walls"].items():
                self.assertEqual(grip.strip_sources(b["note"] or ""), b["note"] or "", k)

    def test_grid_names_the_most_severe(self):
        days = [date(2026, 5, 3).isoformat()]
        walls = [{"crag": {"birds": {"level": "partly", "months": [5], "note": "p"}}},
                 {"crag": {"birds": {"level": "restricted", "months": [5], "note": "r"}}},
                 {"crag": {"birds": {"level": "clear", "months": [], "note": "c"}}}]
        self.assertEqual(grip.birds_in(walls, days)["note"], "r")
        self.assertEqual(grip.birds_in(walls[:1], days)["note"], "p")
        self.assertIsNone(grip.birds_in(walls[2:], days))

    def test_in_season_tag(self):
        b = {"months": [4, 5, 6, 7], "level": "affected", "note": ""}
        self.assertIn("Birds nesting now", grip.wall_tags({"birds": b}, [date(2026, 5, 3)]))
        self.assertNotIn("Birds nesting now", grip.wall_tags({"birds": b}, [date(2026, 10, 5)]))
        self.assertNotIn("Birds nesting now", grip.wall_tags({}, [date(2026, 5, 3)]))


QUIET = {"air": 0.5, "fog": 0, "dew": 1, "wdir": 0.3, "wind": 1, "sun": 1, "sea": 0, "wet": 0, "dry": 1, "seep": 0}


def hours(start, rows, day=TODAY):
    """Hours with factor points and the first model's figures: (score, {factor: points}, {figure: value})."""
    return [{"t": f"{day}T{start + i:02d}:00", "index": v, "d": {"f": {**QUIET, **f}, **x}} for i, (v, f, x) in enumerate(rows)]


class WhyFigures(unittest.TestCase):
    def test_figures_from_the_hours(self):
        damp = ({"air": -3, "dew": -2}, {"rh": 89, "margin": 1.2, "ws": 6, "wd": 90, "sun": "cloud"})
        good = ({"air": 3, "sun": 3}, {"rh": 66, "margin": 7.4, "ws": 6, "wd": 200, "sun": "on the face"})
        hs = hours(8, [(2, *damp)] * 4 + [(7, *good)] * 3 + [(5, {}, {"rh": 70, "sun": "cloud"})] * 3)
        self.assertEqual(grip.why_text(hs, 8),
                         "Held back this morning by humid air (89% humidity) and rock only 1°C above the dew point. "
                         "The best window comes from dry air (66% humidity) and sun on the face (12:00 to 15:00).")

    def test_only_factors_worth_two_points_are_named(self):
        """A strong wind in the figures is not named when the wind's points are small: the data does not show it as a cause."""
        hs = hours(9, [(6, {"air": 2.5, "wind": 1}, {"rh": 70, "ws": 30, "wd": 200, "sun": "cloud"})] * 4)
        said = grip.why_text(hs, 9)
        self.assertEqual(said, "The best window comes from dry air (70% humidity).")
        self.assertNotIn("km/h", said)
        self.assertNotIn("sun", said)

    def test_wind_sea_rain_and_sunshine(self):
        hs = hours(9, [(1, {"wet": -5, "wind": -2, "sea": -2}, {"ws": 45, "wd": 90, "ft": 5.5, "note": "raining", "sun": "cloud"})] * 3
                   + [(6, {"sun": 2, "wdir": 2}, {"ws": 20, "wd": 250, "sun": "sun"})] * 3)
        self.assertEqual(grip.why_text(hs, 9),
                         "Held back this morning by rain and a strong onshore wind (45 km/h). "
                         "The best window comes from an offshore wind from the W and sunshine.")

    def test_water_and_calm_sea(self):
        hs = hours(9, [(4, {"wet": -2, "sea": 2}, {"film": 0.3, "ft": 0.6})] * 3)
        self.assertEqual(grip.why_text(hs, 9), "The best window comes from a calm sea (0.2 m at the wall), though damp rock still holds it back.")

    def test_without_figures_the_plain_words(self):
        hs = hours(9, [(6, {"air": 3}, {})] * 3)
        self.assertEqual(grip.why_text(hs, 9), "The best window comes from dry air.")


def hour(f, wet=0.0, n=3, note=""):
    return {"t": "2026-10-05T10:00", "index": 5, "wet": wet, "n": n, "spread": 0, "models": [("Met Office", 5.0), ("ICON", 4.5)],
            "d": {"f": f, "wd": 90, "ws": 10, "ft": 2.0, "rh": 70, "margin": 4, "sun": "cloud", "note": note}}


class HourTable(unittest.TestCase):
    def test_points_leave_out_zero_factors(self):
        f = {"air": 4, "fog": 0, "dew": 1, "wdir": -0.3, "wind": 0.4, "sun": 3, "sea": 0, "wet": 0, "dry": 1.6, "seep": None}
        self.assertEqual(grip.points_text({"f": f, "note": ""}), "air +4 · dew +1 · sun +3 · dry rock +2")
        self.assertEqual(grip.points_text({"f": {**f, "wet": -2}, "note": "damp, 0.3 mm on the rock"}),
                         "air +4 · dew +1 · sun +3 · wet -2 · dry rock +2 (damp, 0.3 mm on the rock)")
        self.assertEqual(grip.points_text({"f": {k: 0 for k in f}, "note": ""}), "all factors 0")

    def test_model_blocks_round_as_grip(self):
        for v, shown in ((4.5, "5"), (5.5, "6"), (6.49, "6"), (0.5, "1"), (7.5, "8")):
            hr = {**hour({"air": 0}), "index": v, "models": [("Met Office", v), ("ECMWF", v), ("ICON", v)]}
            x = grip.hour_cells(hr)
            self.assertEqual(x["grip"], shown)
            self.assertEqual([s for _l, s in x["models"]], [shown] * 3)

    def test_wet_risk_words(self):
        self.assertEqual(grip.wet_words({"wet": 0, "n": 3}), "None")
        self.assertEqual(grip.wet_words({"wet": 1 / 3, "n": 3}), "1 in 3")
        self.assertEqual(grip.wet_words({"wet": 2 / 3, "n": 3}), "2 in 3")
        self.assertEqual(grip.wet_words({"wet": 0.5, "n": 2}), "1 in 2")

    def test_cells_and_models_in_fixed_order(self):
        x = grip.hour_cells(hour({"air": 1, "fog": 0, "dew": 0, "wdir": 0, "wind": 0, "sun": 0, "sea": 0, "wet": 0, "dry": 0, "seep": 0}))
        self.assertEqual(x["models"], [("Met Office", "5"), ("ECMWF", None), ("ICON", "5")])  # 4.5 shows 5, as Grip's own score
        self.assertEqual((x["time"], x["grip"], x["humidity"], x["margin"], x["wind"], x["sea"], x["points"]),
                         ("10:00", "5", "70%", "+4.0°C", "E 10 km/h", "0.6 m", "air +1"))
        table = grip.hours_table([hour({"air": 1})], "Monday 5 October")
        self.assertIn("<caption>Monday 5 October</caption>", table)
        self.assertIn('class="num sz-xs b3" role="img" aria-label="ICON 5"', table)  # coloured by the number shown
        self.assertIn('aria-label="ECMWF: no forecast"', table)


class Page(unittest.TestCase):
    """A crag page built from the synthetic weather (GRIP_FAKE's), for Logie Head and a crag with source-tagged notes."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "crags.json")) as f:
            cfg = json.load(f)
        names = {"Logie Head", "Crazy Band Walls and The Shag’s Hole", "Buchan Walls"}
        cfg["crags"] = [c for c in cfg["crags"] if c["name"] in names]
        cls.pages = {}
        for when in ("2026-10-05T11:37", "2026-10-05T20:10"):
            fixed = datetime.fromisoformat(when).replace(tzinfo=grip.TZ)

            class Fixed(datetime):
                @classmethod
                def now(cls, tz=None):
                    return fixed

            real, grip.datetime = grip.datetime, Fixed
            try:
                models, marine = grip.fake_data(cfg["zones"])
                results, tides, now = grip.build(cfg, models, marine)
                view = grip.coast_view(results, now, cfg)
                nxt = grip.next_view(results, view)
                for gname, walls in grip.groups_of(results):
                    html = grip.render_detail(gname, walls, tides, now, now.date(), cfg, view, grip.zone_now(cfg, models, marine, now), [], nxt)
                    cls.pages[(when[11:13], gname)] = (html, walls, view)
            finally:
                grip.datetime = real

    def test_no_source_tags_and_one_sources_line(self):
        for (_t, gname), (html, _w, _v) in self.pages.items():
            self.assertNotRegex(html, r"\((?:SMC|UKC|developers)", gname)
            self.assertEqual(html.count("Crag facts from the "), 1)
            self.assertIn("reworded by Grip.", html)
            foot = re.search(r'<div class="sf-src"><p>Crag facts from the .*?</p></div></div></footer>', html).group(0)  # in the footer
            self.assertNotRegex(html.replace(foot, ""), r"\b(?:SMC|UKC|UKClimbing)\b", gname)  # sources named only in the foot line

    def test_best_wall_open_by_default(self):
        for t in ("11", "20"):
            html, walls, view = self.pages[(t, "Logie Head")]
            i = grip.open_wall(walls, view[0].isoformat())
            self.assertIn(f'data-open="{grip.wall_ids(walls)[i]}"', html)
            self.assertEqual(view[1], t == "20")  # after dark the page shows tomorrow first
            self.assertEqual(html.count('<details class="wall"'), len(walls))
            self.assertEqual(html.count('<details class="wall" id='), html.count("open><summary><h2>"))  # all open without script

    def test_every_hour_table_present(self):
        html, walls, _v = self.pages[("11", "Logie Head")]
        days = sorted({hr["t"][:10] for r in walls for hr in r["hours"] if hr["t"][:10] <= "2026-10-07"})
        self.assertEqual(len(days), 3)
        self.assertEqual(html.count('<details class="hb"'), len(walls) * len(days))
        self.assertEqual(html.count("<table class=\"hours\">"), len(walls) * len(days))

    def test_after_dark_columns(self):
        html, _w, _v = self.pages[("20", "Logie Head")]
        self.assertIn('<span class="ovl" aria-hidden="true">Tmrw</span><span class="ovl" aria-hidden="true">Day after</span>', html)
        self.assertIn("<h3>Tomorrow, Tue 6</h3>", html)
        self.assertIn("<h3>Day after, Wed 7</h3>", html)
        self.assertNotIn("<h3>Today,", html)

    def test_how_sure_empty_state(self):
        self.assertEqual(grip.sure_items([wall("A", {})], DAYS, DAYS[0]), [])
        html, walls, view = self.pages[("11", "Logie Head")]
        sure = grip.sure_items(walls, [view[0], view[0] + grip.timedelta(days=1)], view[0])
        if sure:
            self.assertNotIn("the three models agree", html)
            for r, _d, said in sure:
                self.assertIn(grip.escape(said), html)

    def test_how_sure_says_each_sentence_once(self):
        html, walls, view = self.pages[("11", "Logie Head")]
        days = [view[0], view[0] + grip.timedelta(days=1)]
        sure = grip.sure_items(walls, days, view[0])
        for _d, groups in grip.sure_groups(sure, days):
            for names, said in groups:
                self.assertEqual(html.count(f"<b>{grip.escape(grip.walls_named(names))}:</b> {grip.escape(said)}</p>"), 1)
        for t in ("11", "20"):
            html, _w, _v = self.pages[(t, "Logie Head")]
            box = html[html.index('id="sure-h"'):html.index('id="across-h"')]
            for part in box.split("<h3>")[1:]:
                lines = re.findall(r"</b> ([^<]+)</p>", part)
                self.assertEqual(len(lines), len(set(lines)), part)  # within a day, no sentence twice

    def test_sea_line_after_dark(self):
        html, _w, _v = self.pages[("20", "Logie Head")]
        sea = re.search(r"<dt>Sea</dt><dd>([^<]+)</dd>", html).group(1)
        self.assertNotIn("today", sea)
        self.assertRegex(sea, r"Up to \d\.\d m on Tuesday\.$")
        html, _w, _v = self.pages[("11", "Logie Head")]
        self.assertRegex(re.search(r"<dt>Sea</dt><dd>([^<]+)</dd>", html).group(1), r"Up to \d\.\d m today\.$")

    def test_single_wall_has_no_walls_list(self):
        html, walls, _v = self.pages[("11", "Buchan Walls")]
        self.assertEqual(len(walls), 1)
        self.assertNotIn('class="box wlist"', html)
        self.assertNotIn("<details class=\"wall\"", html)
        self.assertIn('<article class="wall"', html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
