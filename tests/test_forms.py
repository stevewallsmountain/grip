"""The three on-site forms (log, crag note, feedback): their crag lists, links, pages and the payloads they send.

The payload builders are JavaScript; those tests run them under Node when it is installed and are skipped otherwise.
Nothing here sends anything to the Google Forms.
"""
import html as htmlmod
import io
import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from contextlib import redirect_stderr
from urllib.parse import parse_qsl

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import grip  # noqa: E402

with open(grip.FORM_CRAGS_FILE) as f:
    FORM_CRAGS = json.load(f)
NODE = shutil.which("node")
CFG = {"crags": [{"name": "Bridge of One Hair", "wall": "East Wall"}, {"name": "Bridge of One Hair", "wall": "West Wall"},
                 {"name": "Logie Head", "wall": "Embankment One"}, {"name": "Souter Head", "wall": ""}]}


def run_js(script, export, calls):
    """Run a form script under Node and return the result of each call, given as a JavaScript expression on `G`."""
    body = script + f"\nvar G={export};\nprocess.stdout.write(JSON.stringify([" + ",".join(calls) + "]));"
    out = subprocess.run([NODE, "-e", body], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def pairs(js_params):
    return f"[...{js_params}.entries()]"


class CragLists(unittest.TestCase):
    def test_both_forms_match_form_crags(self):
        names = FORM_CRAGS[:-1]
        self.assertEqual(len(names), 165)
        self.assertEqual(FORM_CRAGS[-1], grip.FORM_ELSEWHERE)
        self.assertEqual(grip.form_crag_options(grip.FORM_ELSEWHERE), FORM_CRAGS)
        self.assertEqual(grip.form_crag_options(grip.NOTES_ELSEWHERE), names + ["A crag that is not on the list yet"])

    def test_every_crag_in_crags_json_is_an_option(self):
        with open(os.path.join(os.path.dirname(grip.FORM_CRAGS_FILE), "..", "crags.json")) as f:
            cfg = json.load(f)
        buf = io.StringIO()
        with redirect_stderr(buf):
            log_walls = grip.form_walls(cfg)
            note_walls = grip.form_walls(cfg, grip.NOTES_ELSEWHERE, "notes form")
        self.assertNotIn("Warning", buf.getvalue())
        self.assertEqual(log_walls[-1], [grip.FORM_ELSEWHERE, grip.FORM_ELSEWHERE, ""])
        self.assertEqual(note_walls[-1], [grip.NOTES_ELSEWHERE, grip.NOTES_ELSEWHERE, ""])
        self.assertEqual([w[0] for w in log_walls[:-1]], [w[0] for w in note_walls[:-1]])
        self.assertTrue(all(w[1] in FORM_CRAGS for w in note_walls[:-1]))

    def test_missing_crag_warns_for_each_form(self):
        cfg = {"crags": [{"name": "Nowhere Crag", "wall": "Main"}]}
        for elsewhere, form in ((grip.FORM_ELSEWHERE, "log form"), (grip.NOTES_ELSEWHERE, "notes form")):
            buf = io.StringIO()
            with redirect_stderr(buf):
                walls = grip.form_walls(cfg, elsewhere, form)
            with self.subTest(form):
                self.assertIn(f"not options on the {form}", buf.getvalue())
                self.assertIn("Nowhere Crag", buf.getvalue())
                self.assertEqual(walls[0], ["Nowhere Crag (Main)", elsewhere, "Nowhere Crag (Main)"])


class Links(unittest.TestCase):
    def test_note_and_feedback_links(self):
        self.assertEqual(grip.note_link({"name": "Logie Head", "wall": "Embankment One"}, "../"),
                         "../note.html?wall=Logie%20Head%20%28Embankment%20One%29")
        self.assertEqual(grip.note_link({"name": "Souter Head"}), "note.html?wall=Souter%20Head")
        self.assertEqual(grip.feedback_link("home"), "feedback.html?from=home")
        self.assertTrue(set(k for k in grip.FEEDBACK_PAGES if k) >= {"home", "crag", "log", "note", "feedback", "birds", "method"})

    def test_home_cards_stay_on_site(self):
        html = grip.render_help()
        self.assertEqual(re.findall(r'class="hc" href="([^"]+)"', html), ["log.html", "note.html", "feedback.html?from=home"])
        self.assertNotIn("docs.google.com", html)
        self.assertNotIn("_blank", html)

    def test_contribute_nav(self):
        pages = {"log": grip.render_log(CFG), "note": grip.render_note(CFG), "feedback": grip.render_feedback()}
        for key, html in pages.items():
            with self.subTest(key):
                nav = re.search(r'<nav class="seg" aria-label="Contribute">(.*?)</nav>', html).group(1)
                want = ["log.html", "note.html", "feedback.html" if key == "feedback" else f"feedback.html?from={key}"]
                self.assertEqual(re.findall(r'href="([^"]+)"', nav), want)
                self.assertEqual(re.findall(r'aria-current="page">([^<]+)<', nav), [dict(log="Log a day", note="Crag note", feedback="Feedback")[key]])
                self.assertIn('<a href="log.html" aria-current="page">Contribute</a>', html)


class Pages(unittest.TestCase):
    def test_shared_frame(self):
        for html, google, sent in ((grip.render_log(CFG), grip.FORM_URL, "Thank you. Your day is logged."),
                                   (grip.render_note(CFG), grip.NOTES_URL, "Thank you. Your note is in."),
                                   (grip.render_feedback(), grip.FEEDBACK_URL, "Thank you. Feedback sent.")):
            with self.subTest(sent):
                self.assertEqual(html.count(google), 2)  # under Send, and the no-JavaScript notice
                self.assertEqual(html.count("Prefer the Google form? <a"), 1)
                self.assertIn(f'Prefer the Google form? <a id="alt-google" href="{google}">Use it here</a>.', html)
                self.assertIn(f'This form needs JavaScript. <a href="{google}">Use the Google Form instead.</a>', html)
                self.assertIn("<noscript><style>.gform{display:none}</style>", html)
                self.assertIn(f'<h1 id="done-h" tabindex="-1">{sent}</h1>', html)
                self.assertIn('role="status"', html)
                self.assertNotIn("\u2014", html)

    def test_note_page(self):
        html = grip.render_note(CFG)
        chips = re.findall(r'name="about"[^>]*value="([^"]+)"><span>([^<]+)<', html)
        self.assertEqual([(c, htmlmod.unescape(v)) for v, c in chips], grip.NOTE_ABOUT)
        self.assertEqual([c for c, _v in grip.NOTE_ABOUT], ["Aspect", "Tidal", "Seepage", "Shelter", "Birds", "Missing crag or wall", "Other"])
        self.assertIn('id="about-birds" value="Birds: nesting, restrictions, or best avoided in season"', html)
        self.assertIn('<fieldset class="birds" id="f-birds">', html)  # not hidden in the markup: only the script hides it
        self.assertEqual(re.findall(r'name="months" value="(\w+)"', html), grip.MONTHS[1:])
        self.assertIn("Filled in from the crag page. Change it if needed.", html)

    def test_log_aside_tally(self):
        self.assertIn("12 days logged so far; Grip landed in the felt band on 6.", grip.render_log(CFG, {"n": 12, "bands_right": 6}))
        self.assertNotIn("logged so far", grip.render_log(CFG))

    def test_feedback_page(self):
        html = grip.render_feedback()
        opts = re.findall(r"<option>([^<]+)</option>", html)
        self.assertEqual(opts, ["Home page", "A crag page", "Log a day", "Send a crag note", "Give feedback", "Nesting birds",
                                "How Grip works", "Somewhere else"])
        self.assertEqual(re.findall(r'name="device" value="(\w+)"', html), ["Phone", "Tablet", "Computer"])
        self.assertNotIn('id="wall"', html)


@unittest.skipUnless(NODE, "needs Node to run the forms' JavaScript")
class LogPayload(unittest.TestCase):
    def test_body_unchanged(self):
        """The body main sent before the redesign, for the same inputs, byte for byte."""
        f = ('{wall:0,date:"2026-10-04",from:"10:00",until:"12:30",feel:"Grippy: good friction",'
             'problems:["Wet from rain","Seepage"],initials:"SW",other:"Fine",contact:""}')
        body, = run_js(grip.log_script(CFG), "GripLog", [f"G.payload({f}).toString()"])
        self.assertEqual(body, "entry.769015387=Bridge+of+One+Hair&entry.1131909785=East+Wall&entry.2085482145_year=2026"
                               "&entry.2085482145_month=10&entry.2085482145_day=04&entry.764556216_hour=10&entry.764556216_minute=00"
                               "&entry.1083400377_hour=12&entry.1083400377_minute=30&entry.1126435114=Grippy%3A+good+friction"
                               "&entry.525175392=Wet+from+rain&entry.525175392=Seepage&entry.1772081994=SW&entry.960162223=Fine"
                               "&entry.1160807926=&fvv=1&pageHistory=0")

    def test_summary(self):
        rows, = run_js(grip.log_script(CFG), "GripLog", ['G.summary({wall:2,date:"2026-10-04",from:"11:00",until:"15:00",feel:"Grippy: good friction"})'])
        self.assertEqual(rows, [["Crag", "Logie Head (Embankment One)"], ["When", "Sun 4 Oct, 11:00 to 15:00"], ["Felt", "Grippy", ["b4", "6 to 7"]]])

    def test_required(self):
        bad, = run_js(grip.log_script(CFG), "GripLog", ['G.validate({wall:-1,date:"",from:"",until:"",feel:""},"2026-10-05").map(function(b){return b[0];})'])
        self.assertEqual(bad, ["wall", "date", "from", "until", "feel"])


@unittest.skipUnless(NODE, "needs Node to run the forms' JavaScript")
class NotePayload(unittest.TestCase):
    E = grip.NOTES_ENTRIES

    def run_note(self, *calls):
        return run_js(grip.note_script(CFG), "GripNote", list(calls))

    def test_birds_ticked(self):
        f = ('{wall:2,about:["Which way the wall faces","Birds: nesting, restrictions, or best avoided in season","Something else"],'
             'situation:["Formal restriction or ban in place","Birds have finished for the season, crag clear"],'
             'months:["July","April","May"],note:"  Fulmars on the left arete.  ",initials:" SW "}')
        got, = self.run_note(pairs(f"G.payload({f})"))
        E = self.E
        self.assertEqual([tuple(x) for x in got], [
            (E["crag"], "Logie Head"), (E["wall"], "Embankment One"),
            (E["about"], "Which way the wall faces"), (E["about"], "Birds: nesting, restrictions, or best avoided in season"),
            (E["about"], "Something else"),
            (E["situation"], "Formal restriction or ban in place"), (E["situation"], "Birds have finished for the season, crag clear"),
            (E["months"], "April"), (E["months"], "May"), (E["months"], "July"),
            (E["note"], "Fulmars on the left arete."), (E["initials"], "SW"), ("fvv", "1"), ("pageHistory", "0")])
        self.assertEqual(E, {"crag": "entry.1230562053", "wall": "entry.763167181", "about": "entry.1812259591",
                             "situation": "entry.1835765743", "months": "entry.193272001", "note": "entry.408400775",
                             "initials": "entry.1715627746"})

    def test_birds_not_ticked(self):
        f = ('{wall:4,about:["Seepage after rain"],situation:["Formal restriction or ban in place"],months:["May"],'
             'note:"Seeps for days",initials:""}')
        got, = self.run_note(pairs(f"G.payload({f})"))
        keys = [k for k, _v in got]
        self.assertNotIn(self.E["situation"], keys)
        self.assertNotIn(self.E["months"], keys)
        self.assertEqual(got[:3], [[self.E["crag"], "A crag that is not on the list yet"], [self.E["wall"], ""],
                                   [self.E["about"], "Seepage after rain"]])

    def test_every_option_exact(self):
        chips = [v for _c, v in grip.NOTE_ABOUT]
        sits = [v for _t, v, _d in grip.BIRD_SITUATIONS]
        f = json.dumps({"wall": 0, "about": chips, "situation": sits, "months": grip.MONTHS[1:], "note": "x", "initials": ""})
        got, = self.run_note(pairs(f"G.payload({f})"))
        self.assertEqual([v for k, v in got if k == self.E["about"]], [
            "Which way the wall faces", "Whether it is tidal", "Seepage after rain", "Shelter from wind",
            "Birds: nesting, restrictions, or best avoided in season", "A wall or crag that should be added", "Something else"])
        self.assertEqual([v for k, v in got if k == self.E["situation"]], [
            "Formal restriction or ban in place",
            "Birds nesting and the climbing is affected: noise, mess, dive-bombing, routes to avoid",
            "Birds nesting but climbing not really affected", "Birds have finished for the season, crag clear",
            "No birds here that I know of"])
        self.assertEqual([v for k, v in got if k == self.E["months"]], ["January", "February", "March", "April", "May", "June", "July",
                                                                         "August", "September", "October", "November", "December"])

    def test_required(self):
        a, b, c = self.run_note('G.validate({wall:-1,note:"  "}).map(function(b){return b[0];})',
                                'G.validate({wall:0,note:"x"})', 'G.validate({wall:99,note:"x"}).map(function(b){return b[0];})')
        self.assertEqual(a, ["wall", "note"])
        self.assertEqual(b, [])
        self.assertEqual(c, ["wall"])

    def test_google_fallback_filled_with_the_wall(self):
        base = grip.NOTES_URL
        got = self.run_note(f'G.google({json.dumps(base)},"?wall=Logie%20Head%20%28Embankment%20One%29")',
                            f'G.google({json.dumps(base)},"?wall=Souter%20Head")',
                            f'G.google({json.dumps(base)},"?wall=Bridge%20of%20One%20Hair")',
                            f'G.google({json.dumps(base)},"?wall=Nowhere")', f'G.google({json.dumps(base)},"")')
        self.assertEqual(got, [base + "?usp=pp_url&entry.1230562053=Logie%20Head&entry.763167181=Embankment%20One",
                               base + "?usp=pp_url&entry.1230562053=Souter%20Head",
                               base + "?usp=pp_url&entry.1230562053=Bridge%20of%20One%20Hair",  # a crag of several walls: the crag only
                               base, base])

    def test_summary(self):
        f = ('{wall:2,about:["Whether it is tidal","Birds: nesting, restrictions, or best avoided in season"],'
             'situation:["Birds nesting but climbing not really affected"],months:["December","April","May","June","August"],note:"x"}')
        rows, words = self.run_note(f"G.summary({f})", 'G.monthWords(["January","March","April"])')
        self.assertEqual(rows, [["Crag", "Logie Head (Embankment One)"], ["About", "Tidal, Birds"],
                                ["Birds", "Nesting, not really affected; Apr to Jun, Aug, Dec"]])
        self.assertEqual(words, "Jan, Mar to Apr")

    def test_wall_prefill(self):
        got = self.run_note('GripForms.prefill(GripForms.walls(G.WALLS),"?wall=Logie%20Head%20%28Embankment%20One%29")',
                            'GripForms.prefill(GripForms.walls(G.WALLS),"?wall=logie+head+embankment+one")',
                            'GripForms.prefill(GripForms.walls(G.WALLS),"?wall=Bridge%20of%20One%20Hair")',
                            'GripForms.prefill(GripForms.walls(G.WALLS),"")')
        self.assertEqual(got, [{"i": 2, "text": "Logie Head (Embankment One)"}, {"i": 2, "text": "Logie Head (Embankment One)"},
                               {"i": -1, "text": "Bridge of One Hair"}, None])

    def test_crag_list(self):
        walls, = self.run_note("G.WALLS")
        self.assertEqual(walls[-1], [grip.NOTES_ELSEWHERE, grip.NOTES_ELSEWHERE, ""])
        self.assertEqual(walls[0], ["Bridge of One Hair (East Wall)", "Bridge of One Hair", "East Wall"])


@unittest.skipUnless(NODE, "needs Node to run the forms' JavaScript")
class FeedbackPayload(unittest.TestCase):
    E = grip.FEEDBACK_ENTRIES

    def run_fb(self, *calls):
        return run_js(grip.feedback_script(), "GripFeedback", list(calls))

    def test_payload(self):
        f = ('{trying:" Find a dry crag ",worked:"The grid",failed:"",ideas:"Tide times",page:"A crag page",device:"Phone",'
             'contact:"sw@example.com"}')
        got, = self.run_fb(pairs(f"G.payload({f})"))
        E = self.E
        self.assertEqual([tuple(x) for x in got], [
            (E["trying"], "Find a dry crag"), (E["worked"], "The grid"), (E["failed"], ""), (E["ideas"], "Tide times"),
            (E["page"], "A crag page"), (E["device"], "Phone"), (E["contact"], "sw@example.com"), ("fvv", "1"), ("pageHistory", "0")])
        self.assertEqual(E, {"trying": "entry.1944115557", "worked": "entry.2066085876", "failed": "entry.247873462",
                             "ideas": "entry.368810859", "page": "entry.1335516550", "device": "entry.285027101",
                             "contact": "entry.901330593"})

    def test_summary(self):
        self.assertEqual(self.run_fb('G.summary({trying:"x",page:"A crag page",device:"Phone"})', 'G.summary({trying:"x",page:"",device:"Tablet"})'),
                         [[["Page", "A crag page"], ["Device", "Phone"]], [["Page", "Not given"], ["Device", "Tablet"]]])

    def test_page_left_out_when_not_chosen(self):
        got, = self.run_fb(pairs('G.payload({trying:"x",page:"",device:"Tablet"})'))
        self.assertNotIn(self.E["page"], [k for k, _v in got])

    def test_required(self):
        self.assertEqual(self.run_fb('G.validate({trying:" "})', 'G.validate({trying:"x"})'),
                         [[["trying", "Say what you were trying to do."]], []])

    def test_device_from_screen_width(self):
        got, = self.run_fb("[320,599,600,768,1023,1024,1920].map(G.device)")
        self.assertEqual(got, ["Phone", "Phone", "Tablet", "Tablet", "Tablet", "Computer", "Computer"])

    def test_page_from(self):
        here = "https://stevewallsmountain.github.io/grip/feedback.html?from=x"
        site = "https://stevewallsmountain.github.io/grip/"
        cases = [("home", "", "Home page"), ("crag", "", "A crag page"), ("log", "", "Log a day"), ("note", "", "Send a crag note"),
                 ("feedback", "", "Give feedback"), ("birds", "", "Nesting birds"), ("method", "", "How Grip works"),
                 ("method", site + "birds.html", "How Grip works"),  # ?from= wins over the referrer
                 ("", site, "Home page"), ("", site + "index.html", "Home page"), ("", site + "detail/logie-head.html#w2", "A crag page"),
                 ("", site + "log.html?wall=x", "Log a day"), ("", site + "note.html", "Send a crag note"),
                 ("", site + "birds.html", "Nesting birds"), ("", site + "method.html", "How Grip works"),
                 ("", site + "feedback.html", ""), ("toString", "", ""), ("", "https://www.google.com/", ""),
                 ("", "https://stevewallsmountain.github.io/other/", ""), ("", "", "")]
        got, = self.run_fb("[" + ",".join(f"G.pageFrom({json.dumps(a)},{json.dumps(b)},{json.dumps(here)})" for a, b, _w in cases) + "]")
        self.assertEqual(got, [w for _a, _b, w in cases])
        self.assertTrue(all(w in grip.FEEDBACK_PAGES.values() for _a, _b, w in cases if w))

    def test_payload_for_every_page_option(self):
        pages = list(grip.FEEDBACK_PAGES.values())
        got, = self.run_fb("[" + ",".join(f'G.payload({{trying:"x",page:{json.dumps(p)}}}).get({json.dumps(self.E["page"])})' for p in pages) + "]")
        self.assertEqual(got, pages)


class Helpers(unittest.TestCase):
    def test_query_strings_decode(self):
        self.assertEqual(dict(parse_qsl(grip.note_link({"name": "Crabs’ Lair", "wall": ""}).split("?", 1)[1])), {"wall": "Crabs’ Lair"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
