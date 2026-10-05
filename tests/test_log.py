"""Log a day, v2: the daily forecast snapshots, and the log page's Grip's view (observations first, then Grip's answers per factor).

The page logic is JavaScript; those tests run it under Node when it is installed and are skipped otherwise.
Nothing here sends anything to the Google Form or fetches any weather.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import datetime
from unittest import mock
from urllib.parse import parse_qsl

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import grip  # noqa: E402

NODE = shutil.which("node")
with open(os.path.join(os.path.dirname(grip.FORM_CRAGS_FILE), "..", "crags.json")) as f:
    CRAGS = json.load(f)
LABELS = ["Logie Head (Tidal Zone)", "Logie Head (Star Zone)", "Souter Head (Aitken’s Pinnacle)", "South Cove (Kettle Walls)",
          "The Red Cliff", "Earnsheugh (Right Wall)", "The Graip"]
CFG = {"zones": CRAGS["zones"], "crags": [c for c in CRAGS["crags"] if grip.label(c) in LABELS]}
OLD_ENTRIES = {"crag": "entry.769015387", "wall": "entry.1131909785", "date": "entry.2085482145", "from": "entry.764556216",
               "until": "entry.1083400377", "feel": "entry.1126435114", "problems": "entry.525175392", "initials": "entry.1772081994",
               "other": "entry.960162223", "contact": "entry.1160807926"}
NEW_ENTRIES = {"seep": "entry.1941262796", "sweat": "entry.1648574416", "haar": "entry.488966077", "spray": "entry.590821068",
               "water": "entry.2054188057", "wind": "entry.745293101", "sun": "entry.1196075429", "timing": "entry.1164703220",
               "birds": "entry.2000108507", "shown": "entry.579200590", "first": "entry.814548769"}
G7 = {"water": "Dry", "seep": "No", "sweat": "No", "haar": "No", "wind": "Light", "sun": "Some", "spray": "No"}
SCRIPT = None


def script():
    global SCRIPT
    if SCRIPT is None:
        with redirect_stderr(io.StringIO()):
            SCRIPT = grip.log_script(CFG)
    return SCRIPT


def run_js(calls, pre=""):
    """Run the log page's script under Node and return each call's result; G is GripLog. The script goes in a file: it is long."""
    body = script() + "\nvar G=GripLog;\n" + pre + "\nprocess.stdout.write(JSON.stringify([" + ",".join(calls) + "]));"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(body)
    try:
        out = subprocess.run([NODE, f.name], capture_output=True, text=True, check=True)
    finally:
        os.unlink(f.name)
    return json.loads(out.stdout)


def hrs(scores, start=11, **cols):
    """Snapshot hours as the page's objects: one per score, other columns constant or per hour."""
    out = []
    for i, s in enumerate(scores):
        h = {"h": start + i, "s": s, "water": 0.0, "seep": 0, "dew": 1, "air": 1.5, "haar": 0, "wind": 12.0, "sun": 0, "sea": 0}
        for k, v in cols.items():
            h[k] = v[i] if isinstance(v, list) else v
        out.append(h)
    return out


def snap_of(walls, run="2026-10-04 07:17"):
    """A snapshot file's content from {label: [hour objects]}."""
    return {"date": run[:10], "run": run, "model": grip.MODEL_VERSION, "cols": grip.SNAPSHOT_COLS,
            "walls": {k: [[h[c] for c in grip.SNAPSHOT_COLS] for h in v] for k, v in walls.items()}}


def wall_index(lab):
    with redirect_stderr(io.StringIO()):
        return [w[0] for w in grip.form_walls(CFG)].index(lab)


def form(**kw):
    f = {"wall": wall_index("Logie Head (Tidal Zone)"), "date": "2026-10-04", "from": "11:00", "until": "16:00",
         "feel": "Climbable: fine with care", "obs": dict(G7), "first": "Climbable: fine with care", "timing": -1, "birds": "",
         "initials": "", "other": "", "contact": ""}
    f.update(kw)
    return f


def fetch_log_from(rows):
    """grip.fetch_log on a sheet given as rows, without the network."""
    import csv
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    resp = mock.MagicMock()
    resp.__enter__.return_value.read.return_value = buf.getvalue().encode()
    with mock.patch.object(grip.urllib.request, "urlopen", return_value=resp):
        return grip.fetch_log()


class SnapshotSelection(unittest.TestCase):
    def at(self, s):
        return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=grip.TZ)

    def test_nearest_seven(self):
        self.assertTrue(grip.snapshot_due(None, self.at("2026-10-05 03:17")))  # nothing yet: any run saves
        self.assertTrue(grip.snapshot_due("2026-10-05 05:17", self.at("2026-10-05 06:17")))
        self.assertTrue(grip.snapshot_due("2026-10-05 06:17", self.at("2026-10-05 07:17")))  # 17 minutes beats 43
        self.assertFalse(grip.snapshot_due("2026-10-05 07:17", self.at("2026-10-05 08:17")))
        self.assertFalse(grip.snapshot_due("2026-10-05 06:30", self.at("2026-10-05 07:30")))  # a tie keeps the saved one
        self.assertTrue(grip.snapshot_due("2026-10-05 06:20", self.at("2026-10-05 07:10")))

    def test_late_runs_count(self):
        self.assertTrue(grip.snapshot_due("2026-10-04 07:17", self.at("2026-10-05 11:40")))  # the first run of a day, however late
        self.assertFalse(grip.snapshot_due("2026-10-05 11:40", self.at("2026-10-05 12:40")))
        self.assertTrue(grip.snapshot_due("2026-10-05 23:17", self.at("2026-10-06 00:17")))  # a new day starts afresh

    def test_clock_change_days(self):
        self.assertTrue(grip.snapshot_due("2026-03-29 06:17", self.at("2026-03-29 07:17")))  # by the clock on the wall
        self.assertFalse(grip.snapshot_due("2026-10-25 07:17", self.at("2026-10-25 08:17")))


class SnapshotFile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        models, marine = grip.fake_data(CFG["zones"])
        cls.results, _tides, cls.now = grip.build(CFG, models, marine)

    def test_offline_build_writes_snapshot_and_history(self):
        now = self.now.replace(hour=12, minute=17, second=30, microsecond=0)  # a fixed clock: after 07:00 the saved run stays nearer
        with tempfile.TemporaryDirectory() as tmp:
            folder, site = os.path.join(tmp, "history"), os.path.join(tmp, "site")
            with redirect_stderr(io.StringIO()):
                path = grip.save_snapshot(self.results, now, folder)
                again = grip.save_snapshot(self.results, now, folder)  # the same run is not nearer
            self.assertEqual(os.path.basename(path), now.date().isoformat() + ".json")
            self.assertIsNone(again)
            with open(path) as f:
                snap = json.load(f)
            self.assertEqual(snap["cols"], ["h", "s", "water", "seep", "dew", "air", "haar", "wind", "sun", "sea"])
            self.assertEqual(snap["run"], now.strftime("%Y-%m-%d %H:%M"))
            self.assertEqual(sorted(snap["walls"]), sorted(LABELS))
            for r in self.results:
                day = grip.day_hours(r, self.now.date().isoformat())
                rows = snap["walls"][grip.label(r["crag"])]
                self.assertEqual([x[0] for x in rows], [grip.hour_of(h) for h in day])  # every daylight hour of the day
                self.assertEqual([x[1] for x in rows], [grip.rnd(h["index"]) for h in day])  # the blended score as shown
            with redirect_stderr(io.StringIO()):  # before 07:00 a later run is nearer, so it replaces the saved one
                night = os.path.join(tmp, "night")
                self.assertTrue(grip.save_snapshot(self.results, now.replace(hour=5, minute=10, second=0), night))
                self.assertTrue(grip.save_snapshot(self.results, now.replace(hour=6, minute=20, second=0), night))
                self.assertIsNone(grip.save_snapshot(self.results, now.replace(hour=5, minute=40, second=0), night))
            open(os.path.join(folder, "notes.txt"), "w").close()
            self.assertEqual(grip.publish_history(site, folder), 1)
            self.assertEqual(os.listdir(os.path.join(site, "history")), [os.path.basename(path)])

    def test_row(self):
        crag = {"aspect": "E", "sheltered": True}
        hr = {"t": "2026-10-04T13:00", "index": 6.5, "d": {"film": 0.12345, "ws": 30.0, "wd": 270, "sun": "low sun on the face",
              "f": {"seep": -2, "dew": -1, "air": -0.75, "fog": -2, "sea": -1}}}
        self.assertEqual(grip.snapshot_row(hr, crag), [13, 7, 0.123, 1, -1, -0.75, 1, 15.0, 1, -1])  # wind from behind a sheltered wall: halved
        hr["d"].update(wd=90, sun="sun", f={"seep": 0, "dew": None, "air": 2.0, "fog": 0, "sea": None})
        self.assertEqual(grip.snapshot_row(hr, crag), [13, 7, 0.123, 0, None, 2.0, 0, 30.0, 0, None])  # onto the face: in full


class LogParsing(unittest.TestCase):
    HEAD = ["Timestamp", "Crag", "Date", "On the rock from", "On the rock until", "How did the rock feel overall?",
            "If it was poor, what was the problem?", "Initials", "Anything else", "Wall or sector"]
    ROW = ["", "Logie Head", "2026-10-04", "10:30:00", "14:45:00", "Grippy: good friction", "Seepage", "SW", "x", "Tidal Zone"]
    NEW = ["Seepage", "Rock sweating or greasy to the touch", "Haar or fog", "Spray reaching the routes", "Water on the rock",
           "Wind on the wall", "Sun on the face", "Did it?", "Any nesting birds?", "Grip's forecast shown", "First answer"]
    VALS = ["Yes", "No", "Not sure", "No", "Damp", "Strong", "Some", "Yes", "None that I saw", "avg 6.8 shown 7 Grippy", "Greasy"]

    def test_new_columns_change_nothing(self):
        before = fetch_log_from([self.HEAD, self.ROW])
        after = fetch_log_from([self.HEAD + self.NEW, self.ROW + self.VALS])
        self.assertEqual(before, after)
        self.assertEqual(before, [{"crag": "Logie Head", "wall": "Tidal Zone", "date": "2026-10-04", "from": 10, "to": 14, "feel": "Crisp",
                                   "problems": "Seepage"}])

    def test_existing_entries_unchanged(self):
        self.assertEqual({k: grip.FORM_ENTRIES[k] for k in OLD_ENTRIES}, OLD_ENTRIES)
        self.assertEqual({k: v for k, v in grip.FORM_ENTRIES.items() if k not in OLD_ENTRIES}, NEW_ENTRIES)
        self.assertEqual(grip.MODEL_VERSION, "3.7")


class Page(unittest.TestCase):
    def setUp(self):
        with redirect_stderr(io.StringIO()):
            self.html = grip.render_log(CFG)

    def test_observation_rows(self):
        import re
        rows = re.findall(r'<span class="ol" id="obs-(\w+)-l">([^<]+)</span>', self.html)
        self.assertEqual(rows, [("water", "Water on the rock"), ("seep", "Seepage"), ("sweat", "Rock sweating or greasy to the touch"),
                                ("haar", "Haar or fog"), ("wind", "Wind on the wall"), ("sun", "Sun on the face"), ("spray", "Spray reaching the routes")])
        for k, _q, _s, opts in grip.LOG_OBS:
            self.assertEqual(re.findall(rf'name="obs-{k}" id="obs-{k}-\d" value="([^"]+)"', self.html), opts + ["Not sure"])
        self.assertIn("One tap each, across your session. Not sure is fine.", self.html)

    def test_flow_order(self):
        marks = ['id="f-wall"', 'id="f-date"', 'id="f-feel"', 'id="f-obs"', 'id="gv-hold"', 'id="gv"', 'id="other"', 'id="f-birds"',
                 'id="initials"', 'id="contact"', 'id="send"']
        at = [self.html.index(m) for m in marks]
        self.assertEqual(at, sorted(at))

    def test_nothing_from_grip_in_the_page(self):
        self.assertNotIn("Anything that made it worse", self.html)
        self.assertNotIn('"cols"', self.html)
        self.assertNotIn('"walls"', self.html)
        self.assertIn("fetch('history/'+date+'.json'", self.html)  # fetched by the script, once the answers are in
        self.assertIn("It keeps Grip’s forecast hidden until you have said how the rock felt and what you saw", self.html)
        self.assertNotIn("\u2014", self.html)

    def test_bird_view(self):
        self.assertEqual(grip.bird_view(None), ["noinfo", []])
        self.assertEqual(grip.bird_view({"level": "clear"}), ["free", []])
        self.assertEqual(grip.bird_view({"level": "affected", "months": [7, 4, 5, 6]}), ["placeholder", [4, 5, 6, 7], False])
        self.assertEqual(grip.bird_view({"level": "affected", "months": [4, 5], "confirmed": True}), ["confirmed", [4, 5], True])
        self.assertEqual(grip.bird_view({"level": "affected", "months": [4, 5], "confirmed": True, "months_source": "guidebook"}),
                         ["confirmed", [4, 5], True])  # where the months come from is never shown
        self.assertEqual(grip.bird_view({"level": "restricted", "months": [4, 8]}), ["restricted", [4, 8], False])
        self.assertEqual(grip.bird_view({"level": "partly", "months": [4, 5, 6, 7]}), ["partly", [4, 5, 6, 7], False])
        self.assertEqual(grip.bird_view({"level": "possible", "months": []}), ["placeholder", [], False])


@unittest.skipUnless(NODE, "needs Node to run the log page's JavaScript")
class Window(unittest.TestCase):
    """The page averages exactly the hours the build back-scores a log over (grip.log_window), rounded half up."""

    def test_page_and_build_agree(self):
        models, marine = grip.fake_data(CFG["zones"])
        results, _t, now = grip.build(CFG, models, marine)
        day = now.date().isoformat()
        snap = grip.snapshot(results, now)
        times = [("11:00", "15:00"), ("10:30", "14:45"), ("06:00", "21:00"), ("12:15", "12:45"), ("13:59", "14:01"), ("09:00", "10:00")]
        head = LogParsing.HEAD
        sheet = [head] + [["", "Logie Head", day, a + ":00", b + ":00", "Grippy: good friction", "", "", "", "Tidal Zone"] for a, b in times]
        entries = fetch_log_from(sheet)  # read back as the build reads the sheet
        self.assertEqual(len(entries), len(times))
        calls, want = [], []
        for r in results:
            lab = grip.label(r["crag"])
            for (a, b), e in zip(times, entries):
                win = grip.log_window(grip.day_hours(r, day), e)
                shown = [grip.rnd(h["index"]) for h in win]
                want.append([[grip.hour_of(h) for h in win], sum(shown), len(shown), grip.rnd(sum(shown) / len(shown)) if shown else None])
                calls.append(f"(function(){{var v=G.view({{wall:{wall_index(lab)},from:'{a}',until:'{b}',feel:'Grippy: good friction',obs:{{}}}},S);"
                             "return v.state==='scored'?[v.win.map(function(h){return h.h;}),v.avg.sum,v.avg.n,v.avg.shown]:[[],0,0,null];})()")
        got = run_js(calls, "var S=" + json.dumps(snap) + ";")
        self.assertEqual(got, want)
        self.assertTrue(any(w[2] for w in want))

    def test_rounding_half_up(self):
        got = run_js(["G.average(" + json.dumps(hrs(s)) + ")" for s in ([6, 7], [6, 6, 7], [5, 6, 7, 8, 8], [3, 4], [1, 2, 2, 2])])
        self.assertEqual([[a["tenths"], a["shown"]] for a in got], [[65, 7], [63, 6], [68, 7], [35, 4], [18, 2]])


@unittest.skipUnless(NODE, "needs Node to run the log page's JavaScript")
class FactorRules(unittest.TestCase):
    def saw(self, *wins):
        return run_js(["G.gripSaw(" + json.dumps(w) + ")" for w in wins])

    def test_water_words_are_the_crag_pages(self):
        films = [i / 1000 for i in range(0, 2001)]
        got, = run_js([f"{json.dumps(films)}.map(G.waterWord)"])
        self.assertEqual(got, [grip.water_words(x) for x in films])

    def test_water_at_the_wettest_hour(self):
        cases = [(0.02, "Dry"), (0.021, "Damp"), (0.1, "Damp"), (0.5, "Damp"), (0.51, "Wet patches")]
        got = self.saw(*[hrs([5, 5, 5], water=[0, x, 0.01]) for x, _w in cases])
        self.assertEqual([g["water"] for g in got], [w for _x, w in cases])

    def test_yes_no_terms(self):
        got = self.saw(hrs([5, 5]), hrs([5, 5], seep=[0, 1]), hrs([5, 5], dew=[1, -1]), hrs([5, 5], air=[0, -0.5]),
                       hrs([5, 5], haar=[0, 1]), hrs([5, 5], sea=[None, -1]), hrs([5, 5], dew=0, air=0, sea=[1, 0]))
        keys = ["seep", "sweat", "haar", "spray"]
        self.assertEqual([[g[k] for k in keys] for g in got],
                         [["No"] * 4, ["Yes", "No", "No", "No"], ["No", "Yes", "No", "No"], ["No", "Yes", "No", "No"],
                          ["No", "No", "Yes", "No"], ["No", "No", "No", "Yes"], ["No"] * 4])

    def test_wind_thresholds_and_majority(self):
        cases = [([7.9], "None"), ([8], "Light"), ([20], "Light"), ([20.1], "Strong"), ([5, 5, 12], "None"), ([5, 12, 25], "Light"),
                 ([5, 5, 25, 25], "None"), ([12, 25, 25, 25], "Strong"), ([None, 21, 3, 30], "Strong")]
        got = self.saw(*[hrs([5] * len(w), wind=w) for w, _a in cases])
        self.assertEqual([g["wind"] for g in got], [a for _w, a in cases])
        self.assertIsNone(self.saw(hrs([5], wind=None))[0]["wind"])

    def test_sun_two_thirds(self):
        cases = [([1, 1, 0], "Most of the session"), ([1, 0, 0], "Some"), ([0, 0, 0], "None"), ([1, 1, 1, 0, 0], "Some"),
                 ([1, 1, 1, 1, 0, 0], "Most of the session"), ([1], "Most of the session")]
        got = self.saw(*[hrs([5] * len(s), sun=s) for s, _a in cases])
        self.assertEqual([g["sun"] for g in got], [a for _s, a in cases])

    def test_mismatch_steps(self):
        cases = [("seep", "Yes", "No", "diff"), ("seep", "No", "No", "same"), ("seep", "Not sure", "Yes", "ns"),
                 ("water", "Damp", "Dry", "near"), ("water", "Wet patches", "Dry", "diff"), ("water", "Damp", "Wet patches", "near"),
                 ("wind", "Strong", "Light", "near"), ("wind", "Strong", "None", "diff"), ("wind", "None", None, "ns"),
                 ("sun", "Most of the session", "Some", "near"), ("sun", "None", "Most of the session", "diff"), ("sun", "Not sure", "None", "ns")]
        got = run_js([f"G.verdict({json.dumps(k)},{json.dumps(u)},{json.dumps(g)})" for k, u, g, _v in cases])
        self.assertEqual(got, [v for *_x, v in cases])

    def test_one_step_is_shown_not_marked(self):
        pre = "var S=" + json.dumps(snap_of({"Logie Head (Tidal Zone)": hrs([5, 5, 5, 6, 5], sun=[0, 0, 1, 0, 0])})) + ";"
        one = form(obs=dict(G7, water="Damp", wind="Strong", haar="Not sure"))
        two = form(obs=dict(G7, water="Wet patches"))
        a, b = run_js([f"G.view({json.dumps(one)},S)", f"G.view({json.dumps(two)},S)"], pre)
        self.assertEqual([r["v"] for r in a["rows"]], ["near", "same", "same", "ns", "near", "same", "same"])
        self.assertFalse(a["mismatch"])
        self.assertEqual(a["caption"], "You and Grip agreed on 4 of 6.")
        self.assertEqual(a["lines"], [])
        self.assertTrue(b["mismatch"])
        self.assertEqual(b["lines"], ["Water on the rock: you found it wet in patches, Grip expected it dry."])

    def test_timing(self):
        cases = [([5, 5, 6, 5], None), ([5, 6, 7, 8, 8], ["up", 13]), ([5, 4, 3, 2, 2], ["down", 13]), ([6, 4, 8], ["down", 12]),
                 ([5, 8, 5], ["up", 12]), ([7, 5], ["down", 12]), ([5], None)]
        got = run_js([f"G.timing({json.dumps(hrs(s))})" for s, _w in cases])
        self.assertEqual([[g["dir"], g["hour"]] if g else None for g in got], [w for _s, w in cases])

    def test_shape(self):
        cases = [([5, 5, 5, 6, 5], "steady all session"), ([7, 7, 7, 7, 6], "Grippy all session"),
                 ([5, 6, 7, 8, 8], "Climbable early, Prime by 14:00"), ([3, 4, 5, 6, 7], "Greasy early, Grippy by 14:00"),
                 ([5, 4, 3, 2, 2], "Climbable early, Greasy by 13:00"), ([5, 8, 5], "Climbable early and late, Prime around 12:00")]
        got = run_js([f"G.shape({json.dumps(hrs(s))})" for s, _w in cases])
        self.assertEqual(got, [w for _s, w in cases])


@unittest.skipUnless(NODE, "needs Node to run the log page's JavaScript")
class ViewAndPayload(unittest.TestCase):
    E = grip.FORM_ENTRIES
    WALLS = {"Logie Head (Tidal Zone)": hrs([5, 6, 7, 8, 8], dew=[1, 1, -1, 1, 1], sun=[0, 0, 1, 0, 0]),
             "Logie Head (Star Zone)": hrs([5, 5, 5, 6, 5], sun=[0, 0, 1, 0, 0])}
    PRE = "var S=" + json.dumps(snap_of(WALLS)) + ";"

    def run_v(self, *calls):
        return run_js(list(calls), self.PRE)

    def body(self, f, snap="S"):
        out, = self.run_v(f"[...G.payload({json.dumps(f)},G.view({json.dumps(f)},{snap})).entries()]")
        return out

    def test_shown_line_as_in_the_brief(self):
        line, = self.run_v(f"G.shownLine(G.view({json.dumps(form())},S))")
        self.assertEqual(line, "avg 6.8 shown 7 Grippy; 11:5 12:6 13:7 14:8 15:8; factors Grip: water Dry, seepage No, sweating Yes, "
                               "haar No, spray No, wind Light, sun Some; snapshot 2026-10-04 07:17")
        self.assertEqual(self.run_v("G.shownLine(G.view(" + json.dumps(form(date="2026-10-03")) + ",null))"), ["not scored yet"])

    def test_existing_fields_byte_identical(self):
        """For the same inputs, the old fields go out byte for byte as main sent them (problems now come from the observations)."""
        f = form(wall=0, date="2026-10-04", **{"from": "10:00", "until": "12:30"}, feel="Grippy: good friction",
                 obs=dict(G7, water="Wet patches", seep="Yes"), initials="SW", other="Fine", contact="")
        f["first"] = f["feel"]
        keep = "[...p.entries()].filter(function(e){return NEW.indexOf(e[0])<0;})"
        body, = self.run_v(f"(function(){{var NEW={json.dumps(list(NEW_ENTRIES.values()))},f={json.dumps(f)},p=G.payload(f,G.view(f,null));"
                           f"return new URLSearchParams({keep}).toString();}})()")
        self.assertEqual(body,
                         "entry.769015387=Souter+Head&entry.1131909785=Aitken%E2%80%99s+Pinnacle&entry.2085482145_year=2026"
                         "&entry.2085482145_month=10&entry.2085482145_day=04&entry.764556216_hour=10&entry.764556216_minute=00"
                         "&entry.1083400377_hour=12&entry.1083400377_minute=30&entry.1126435114=Grippy%3A+good+friction"
                         "&entry.525175392=Wet+from+rain&entry.525175392=Seepage&entry.1772081994=SW&entry.960162223=Fine"
                         "&entry.1160807926=&fvv=1&pageHistory=0")

    def test_every_observation_option_exact(self):
        for k, _q, _s, opts in grip.LOG_OBS:
            for o in opts + ["Not sure"]:
                with self.subTest(k=k, o=o):
                    pairs = self.body(form(obs=dict(G7, **{k: o})))
                    self.assertIn([self.E[k], o], pairs)
        pairs = self.body(form())
        self.assertEqual([p[0] for p in pairs if p[0] in NEW_ENTRIES.values()],
                         [self.E[k] for k in ("seep", "sweat", "haar", "spray", "water", "wind", "sun", "shown")])

    def test_problems_from_the_observations(self):
        cases = [(dict(G7), []), (dict(G7, water="Wet patches"), ["Wet from rain"]), (dict(G7, water="Damp"), []),
                 (dict(G7, seep="Yes"), ["Seepage"]), (dict(G7, sweat="Yes"), ["Greasy or sweating"]), (dict(G7, haar="Yes"), ["Haar or fog"]),
                 (dict(G7, spray="Yes"), ["Spray from the sea"]), ({k: "Not sure" for k in G7}, []),
                 ({"water": "Wet patches", "seep": "Yes", "sweat": "Yes", "haar": "Yes", "wind": "Strong", "sun": "None", "spray": "Yes"},
                  ["Wet from rain", "Greasy or sweating", "Seepage", "Haar or fog", "Spray from the sea"])]
        for obs, want in cases:
            with self.subTest(obs=obs):
                self.assertEqual([v for k, v in self.body(form(obs=obs)) if k == self.E["problems"]], want)

    def test_timing_only_when_asked(self):
        asked = form(timing=2)  # Tidal Zone rises 5 to 8: asked
        self.assertIn([self.E["timing"], "It changed the other way"], self.body(asked))
        for i, o in enumerate(grip.TIMING_OPTIONS):
            self.assertIn([self.E["timing"], o], self.body(form(timing=i)))
        self.assertNotIn(self.E["timing"], [k for k, _v in self.body(form(timing=-1))])  # asked, not answered
        flat = form(wall=wall_index("Logie Head (Star Zone)"), timing=0)  # moves by 1: not asked
        self.assertNotIn(self.E["timing"], [k for k, _v in self.body(flat)])
        q, = self.run_v(f"G.timingQ(G.view({json.dumps(form())},S).timing)")
        self.assertEqual(q, "Grip expected it to improve from about 13:00. Did it?")
        self.assertEqual(self.run_v("G.timingShown({dir:'up',hour:13})", "G.timingShown({dir:'down',hour:13})"),
                         [["Yes", "No, it stayed the same", "It got worse", "Not sure"], ["Yes", "No, it stayed the same", "It got better", "Not sure"]])

    def test_birds_only_when_answered(self):
        self.assertNotIn(self.E["birds"], [k for k, _v in self.body(form())])
        for o in grip.BIRD_ANSWERS:
            self.assertIn([self.E["birds"], o], self.body(form(birds=o)))
        self.assertEqual(grip.BIRD_ANSWERS, ["On most of the wall", "On some routes", "None that I saw", "Didn't notice"])

    def test_first_answer_only_when_changed(self):
        self.assertNotIn(self.E["first"], [k for k, _v in self.body(form())])
        changed = form(first="Greasy: damp and slippery, training at best")
        self.assertIn([self.E["first"], "Greasy"], self.body(changed))

    def test_ready_needs_the_band_and_all_seven(self):
        """Grip's view is fetched and shown only when both are in, whichever comes last."""
        six = {k: v for k, v in G7.items() if k != "spray"}
        cases = [(form(), True), (form(feel=""), False), (form(obs=six), False), (form(feel="", obs={}), False),
                 (form(obs={k: "Not sure" for k in G7}), True), (form(wall=-1), False), (form(date="2026-10-06"), False)]
        got = self.run_v(*[f"G.ready({json.dumps(f)},'2026-10-05')" for f, _w in cases])
        self.assertEqual(got, [w for _f, w in cases])

    def test_required(self):
        bad, = self.run_v('G.validate({wall:-1,date:"",from:"",until:"",feel:"",obs:{}},"2026-10-05").map(function(b){return b[0];})')
        self.assertEqual(bad, ["wall", "date", "from", "until", "feel", "obs"])
        six = {k: v for k, v in G7.items() if k != "spray"}
        self.assertEqual(self.run_v(f"G.validate({json.dumps(form(obs=six))},'2026-10-05')"), [[["obs", "Answer all seven. Not sure is fine."]]])
        self.assertEqual(self.run_v(f"G.validate({json.dumps(form(obs={k: 'Not sure' for k in G7}))},'2026-10-05')"), [[]])

    def test_band_lines_and_notes_labels(self):
        agree = form(wall=wall_index("Logie Head (Star Zone)"))
        worse = form(feel="Greasy: damp and slippery, training at best")
        factor = form(wall=wall_index("Logie Head (Star Zone)"), obs=dict(G7, seep="Yes"))
        got = self.run_v(*[f"(function(){{var v=G.view({json.dumps(f)},S);return [G.bandLine(v),G.notesLabel(v),v.caption];}})()"
                           for f in (agree, worse, factor)])
        self.assertEqual(got, [["Grip agreed on the band.", "Anything worth noting?", "You and Grip agreed on all 7."],
                               ["You found it worse than Grip forecast (Grippy, 7).", "Why do you think that was?", "You and Grip agreed on 6 of 7."],
                               ["Grip agreed on the band.", "Why do you think that was?", "You and Grip agreed on 6 of 7."]])
        better = form(feel="Prime: as dry as this coast gets")
        self.assertEqual(self.run_v(f"G.bandLine(G.view({json.dumps(better)},S))"), ["You found it better than Grip forecast (Grippy, 7)."])
        self.assertEqual(self.run_v(f"G.notesLabel(G.view({json.dumps(form())},null))", "G.notesLabel(null)"),
                         ["Anything else about the day?", "Anything else about the day?"])
        some = form(wall=wall_index("Logie Head (Star Zone)"), obs=dict(G7, haar="Not sure"))
        self.assertEqual(self.run_v(f"G.view({json.dumps(some)},S).caption"), ["You and Grip agreed on all 6 you answered."])

    def test_states(self):
        dark = form(**{"from": "05:00", "until": "06:00"})
        missing = form(wall=wall_index("South Cove (Kettle Walls)"))
        got = self.run_v(f"G.view({json.dumps(dark)},S).state", f"G.view({json.dumps(missing)},S).state",
                         f"G.view({json.dumps(form())},null).state", f"G.view({json.dumps(form())},'error').state",
                         "G.view({wall:G.ELSEWHERE},S).state")
        self.assertEqual(got, ["dark", "unscored", "unscored", "error", "nowall"])

    def test_sent_card(self):
        worse = form(feel="Greasy: damp and slippery, training at best", obs=dict(G7, seep="Yes", wind="Strong", haar="Not sure"),
                     timing=0, birds="None that I saw")
        s, = self.run_v(f"G.summary({json.dumps(worse)},G.view({json.dumps(worse)},S))")
        self.assertEqual(s["lead"], ["You found it worse than Grip, by 2 bands.",
                                     "You and Grip agreed on 3 of 6; you saw seepage that Grip did not expect and the rock did not sweat when Grip expected it."])
        self.assertEqual([r[0] for r in s["rows"]], ["Crag", "When", "You felt", "Grip forecast", "Timing", "Birds"])
        self.assertEqual(s["rows"][3], ["Grip forecast", "Grippy, average for your hours", ["b4", "7"]])
        self.assertEqual(s["rows"][4][1], "Grip expected it to improve from about 13:00. You said: Yes")
        self.assertEqual(s["link"], ["detail/logie-head.html", "Logie Head page"])
        changed = form(feel="Grippy: good friction", first="Greasy: damp and slippery, training at best")
        c, = self.run_v(f"G.summary({json.dumps(changed)},G.view({json.dumps(changed)},S))")
        self.assertEqual(c["rows"][2][1], "Grippy (first answer Greasy)")
        self.assertEqual(c["lead"][0], "You and Grip agreed on the band: Grippy.")
        u, = self.run_v(f"G.summary({json.dumps(form())},G.view({json.dumps(form())},null))")
        self.assertEqual(u["lead"], ["Grip will score this day on its next run.",
                                     "You answered all 7 questions on what you saw. Grip will compare them with its forecast on its next run."])
        self.assertEqual(u["rows"][3], ["Grip forecast", "Not scored yet"])

    def test_birds_have(self):
        pre = self.PRE
        got = run_js([f"G.birdsHave({wall_index(lab)},'2026-05-10')" for lab in (
            "Souter Head (Aitken’s Pinnacle)", "Logie Head (Tidal Zone)", "South Cove (Kettle Walls)", "The Red Cliff",
            "Earnsheugh (Right Wall)", "The Graip")] + ["G.birdsHave(G.ELSEWHERE,'2026-05-10')"], pre)
        self.assertEqual([(g["status"], g["tag"], g["text"]) for g in got], [
            ("free", "Bird free", "Grip has: bird free at this wall."),
            ("partly", "Nesting on parts", "Grip has: birds nesting on parts of this wall, April to July, months not confirmed."),
            ("restricted", "Restricted", "Grip has: climbing restricted while birds nest, April to August."),
            ("confirmed", "Nesting birds", "Grip has: birds nesting, April to August, months confirmed."),
            ("partly", "Nesting on parts", "Grip has: birds nesting on parts of this wall, April to July, months not confirmed."),
            ("partly", "Nesting on parts", "Grip has: birds nesting on parts of this wall, April to August, months confirmed."),
            ("noinfo", "No information", "Grip has no information on birds at this wall. Anything you saw helps.")])
        self.assertEqual(got[1]["now"], 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
