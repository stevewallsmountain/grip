"""Tests for the bird register (birds.html) and the bird data: the In season now line, the status filters and their counts
(Nesting on parts included), the No information rows folded per stretch, the notes without source tags, the Confirmed column,
and tools/build_crags.py taking birds only from data/birds.json (never the SMC keyword flags), with the audit's decided walls.

Standard library only. Run from the repository root or anywhere: python3 tests/test_birds.py
"""
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import grip  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime(2026, 10, 5, 16, 51, tzinfo=grip.TZ)
STOCK = "Birds reported nesting; months not confirmed"
UNSPECIFIED = "Nesting reported at this crag; the walls aren't specified"


def load():
    with open(os.path.join(ROOT, "crags.json")) as f:
        return json.load(f)


def crag(name, level=None, months=(4, 5, 6, 7), confirmed=False, wall=None, section="S"):
    b = None if level is None else {"months": list(months), "level": level, "note": STOCK, **({"confirmed": True} if confirmed else {})}
    return {"name": name, "wall": wall, "section": section, "zone": "z", "birds": b}


class Season(unittest.TestCase):
    CFG = {"crags": [crag("Bruin Cove", "affected", (4, 5, 6, 7, 8), True), crag("South Cove", "restricted", (5, 6, 7, 8), True, "Kettle Walls"),
                     crag("South Cove", "affected", (4, 5, 6, 7), False, "Main Face"), crag("Hareness", "clear", ()),
                     crag("The Red Cliff", "affected", (4, 5, 6, 7)), crag("Longhaven", "affected", (6, 7, 8)),
                     crag("Cove", "affected", (3, 4), True), crag("Souter Head")]}

    def test_out_of_season_says_so(self):
        self.assertEqual(grip.season_line(self.CFG, 10), "In season now: none. The season here runs roughly March to August.")
        self.assertEqual(grip.season_line(self.CFG, 1), "In season now: none. The season here runs roughly March to August.")

    def test_in_season_names_confirmed_and_counts_the_rest(self):
        # May: Bruin Cove and South Cove (Kettle Walls) are confirmed for May; Cove is confirmed but over by May, so neither named nor counted;
        # The Red Cliff and Longhaven have birds with the months not confirmed (South Cove is named already, so not counted again).
        self.assertEqual(grip.season_line(self.CFG, 5),
                         "In season now: 2 crags with confirmed months (Bruin Cove and South Cove); 2 more have birds reported but months not confirmed.")
        self.assertEqual(grip.season_line(self.CFG, 3),
                         "In season now: 1 crag with confirmed months (Cove); 3 more have birds reported but months not confirmed.")

    def test_placeholder_months_only(self):
        cfg = {"crags": [crag("A", "affected"), crag("B", "restricted"), crag("B", "affected", wall="North"), crag("C", "clear", ())]}
        self.assertEqual(grip.season_line(cfg, 6), "In season now: no crag with confirmed months; 2 crags have birds reported but months not confirmed.")
        self.assertEqual(grip.season_line(cfg, 9), "In season now: none. The season here runs roughly April to July.")

    def test_confirmed_only(self):
        cfg = {"crags": [crag("A", "affected", (5, 6), True), crag("C", "clear", ())]}
        self.assertEqual(grip.season_line(cfg, 6), "In season now: 1 crag with confirmed months (A).")

    def test_many_confirmed_named_in_part(self):
        cfg = {"crags": [crag(f"C{i}", "affected", (5,), True) for i in range(8)]}
        self.assertEqual(grip.season_line(cfg, 5), "In season now: 8 crags with confirmed months (C0, C1, C2, C3, C4 and 3 more).")
        self.assertEqual(grip.season_line({"crags": cfg["crags"][:6]}, 5), "In season now: 6 crags with confirmed months (C0, C1, C2, C3, C4 and 1 more).")
        self.assertEqual(grip.season_line({"crags": cfg["crags"][:5]}, 5), "In season now: 5 crags with confirmed months (C0, C1, C2, C3 and C4).")

    def test_the_crag_list_today(self):
        self.assertEqual(grip.season_line(load(), 10), "In season now: none. The season here runs roughly March to August.")
        self.assertRegex(grip.season_line(load(), 5),
                         r"^In season now: 10 crags with confirmed months \(The Red Cliff, South Cove, Bruin Cove, The Orchestra Cave, "
                         r"Crazy Band Walls and The Shag’s Hole and 5 more\); \d+ more have birds reported but months not confirmed\.$")

    def test_partly_counts_as_nesting(self):
        cfg = {"crags": [crag("A", "partly", (5, 6), True), crag("B", "partly")]}
        self.assertEqual(grip.season_line(cfg, 5), "In season now: 1 crag with confirmed months (A); 1 more has birds reported but months not confirmed.")


class Register(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = load()
        cls.html = grip.render_birds(cls.cfg, NOW)
        cls.sections = grip.bird_sections(cls.cfg)

    def rows(self, html=None):
        return re.findall(r'<li class="brow( unk)?" data-k="(\w+)" data-crag="([^"]*)" data-find="([^"]*)">(.*?)</li>', html or self.html)

    def test_heading_intro_caution_and_foot(self):
        h = self.html
        self.assertIn("<h1>Nesting birds</h1>", h)
        self.assertIn("<title>Grip: nesting birds</title>", h)
        intro = ('<p class="intro">Nesting status and months for every crag Grip covers. Entries come from published crag information and '
                 "climbers’ reports, and most months are placeholders until someone confirms them. If you know better, "
                 '<a href="note.html">send a crag note</a>.</p>')
        caution = ('<div class="caution" role="note"><i aria-hidden="true">!</i><p>Not a definitive record. Check local guidance and look '
                   "before you climb in the nesting season.</p></div>")
        self.assertIn(intro + caution, h)  # directly under the intro, and never in a <details>
        self.assertIn("Updated Mon 5 Oct, 16:51 &middot; In season now: none. The season here runs roughly March to August.", h)
        self.assertEqual(h.count("<details"), 0)
        foot = ('<div class="sf-src"><p>Sources: the SMC routes database, UKClimbing and climbers’ reports, reworded by Grip.</p>'
                '</div></div></footer>')  # in the footer
        self.assertIn(foot, h)
        self.assertNotRegex(h.replace(foot, ""), r"\b(?:SMC|UKC|UKClimbing)\b")  # sources named only in the foot line
        self.assertNotIn("\u2014", h)  # no em dashes

    def test_no_source_tags_and_the_notes(self):
        self.assertNotRegex(self.html, r"\((?:SMC|UKC|developers)")
        self.assertNotIn("Nesting birds noted in the SMC database", self.html)
        self.assertNotIn(STOCK, self.html)  # the old keyword-flag note is gone
        self.assertIn(f'<span class="bnote">{html.escape(UNSPECIFIED)}.</span>', self.html)
        self.assertIn('<span class="bnote">No nesting birds reported on this wall by a local climber.</span>', self.html)
        for k, b in data("birds.json")["walls"].items():
            self.assertNotRegex(b["note"] or "", r"\b(?:SMC|UKC|UKClimbing)\b", k)  # notes never name a source

    def test_partly_tag_legend_and_rows(self):
        self.assertIn('.t-part{border-left:6px solid var(--ink);padding-left:7px;box-shadow:inset 0 0 0 1.5px var(--ink)}', self.html)
        self.assertIn('<span><span class="tag t-part">Nesting on parts</span> Some walls, routes or ledges only.</span>', self.html)
        rows = {(c, f): b for _u, k, c, f, b in self.rows() if k == "partly"}
        self.assertTrue(rows)
        for b in rows.values():
            self.assertIn('<span class="tag t-part">Nesting on parts</span>', b)
            self.assertNotIn("t-free", b)
        right = rows[("Earnsheugh", "Earnsheugh Right Wall")]
        self.assertIn("Fulmars hold some ledges, notably at the foot of the Thug Wall pitches", right)
        self.assertEqual(len({grip.BIRD_TAG[k][0] for k in grip.BIRD_TAG} | {"t-unk"}), len(grip.BIRD_TAG) + 1)  # every tag its own shape

    def test_confirmed_column(self):
        """"Yes" where the months are documented, otherwise a dash; never a source label."""
        rows = {(c, f): b for _u, _k, c, f, b in self.rows()}
        yes = '<span class="conf"><i class="yes" aria-hidden="true"></i>Yes</span>'
        dash = '<span class="conf"><span aria-hidden="true">–</span><span class="vh">No</span></span>'
        self.assertIn(yes, rows[("The Red Cliff", "The Red Cliff")])  # months from the guidebook
        self.assertIn('aria-label="Nesting April to August"', rows[("The Red Cliff", "The Red Cliff")])
        self.assertIn(yes, rows[("Johnsheugh", "Johnsheugh")])  # months from the access notes
        self.assertIn('aria-label="Nesting March to August"', rows[("The Red Wall", "The Red Wall")])
        for key in (("Logie Head", "Logie Head Star Zone"), ("Logie Head", "Logie Head Embankment One"), ("Hareness", "Hareness")):
            self.assertIn(dash, rows[key], key)  # months not confirmed, or bird free
        for label in ("From the guidebook", "Climber report", "guidebook", "access notes"):
            self.assertNotIn(label, self.html)
        self.assertNotIn('<i class="no"', self.html)
        b = {"level": "affected", "months": [5, 6], "confirmed": True, "months_source": "climber", "note": "x"}
        self.assertEqual(grip.confirmed_cell(b), yes)
        self.assertEqual(grip.confirmed_cell(dict(b, confirmed=False)), dash)
        self.assertEqual(grip.confirmed_cell({"level": "clear", "months": [], "source": "climber report"}), dash)
        self.assertEqual(grip.confirmed_cell(None), dash)

    def test_chips_and_counts(self):
        chips = re.findall(r'<button type="button" data-k="(\w+)" aria-pressed="(true|false)">([^<]+) <span>(\d+)</span></button>', self.html)
        self.assertEqual([(k, t) for k, _p, t, _n in chips],
                         [("all", "All"), ("restricted", "Restricted"), ("nesting", "Nesting birds"), ("partly", "Nesting on parts"),
                          ("clear", "Bird free"), ("unknown", "No information")])
        self.assertEqual([p for _k, p, _t, _n in chips], ["true", "false", "false", "false", "false", "false"])
        n = {k: int(x) for k, _p, _t, x in chips}
        rows = self.rows()
        kinds = [k for _u, k, _c, _f, _b in rows]
        self.assertEqual(n["all"], len(rows))
        self.assertEqual(n["restricted"], kinds.count("restricted"))
        self.assertEqual(n["nesting"], kinds.count("nesting") + kinds.count("possible"))
        self.assertEqual(n["partly"], kinds.count("partly"))
        self.assertEqual(n["clear"], kinds.count("clear"))
        self.assertEqual(n["unknown"], kinds.count("unknown"))
        self.assertEqual(n["restricted"] + n["nesting"] + n["partly"] + n["clear"] + n["unknown"], n["all"])
        self.assertEqual((n["all"], n["restricted"], n["nesting"], n["partly"], n["clear"], n["unknown"]),
                         (192, 12, 41, 48, 17, 74))  # crags.json today: rows, walls sharing an entry counted once

    def test_every_wall_is_in_one_row_of_its_status(self):
        seen = {}
        for _s, rs in self.sections:
            for r in rs:
                for c in r["walls"]:
                    seen[grip.label(c)] = seen.get(grip.label(c), 0) + 1
                    self.assertEqual(grip.bird_kind(c.get("birds")), r["kind"])
        self.assertEqual(sorted(seen), sorted(grip.label(c) for c in self.cfg["crags"]))
        self.assertEqual(set(seen.values()), {1})

    def test_kinds(self):
        self.assertEqual(grip.bird_kind(None), "unknown")
        self.assertEqual(grip.bird_kind({"level": "clear", "months": []}), "clear")
        self.assertEqual(grip.bird_kind({"level": "restricted", "months": [4]}), "restricted")
        self.assertEqual(grip.bird_kind({"level": "affected", "months": [4]}), "nesting")
        self.assertEqual(grip.bird_kind({"level": "partly", "months": [4]}), "partly")
        self.assertEqual(grip.bird_kind({"level": "possible", "months": []}), "possible")

    def test_unknown_never_looks_bird_free(self):
        for unk, k, _c, _f, body in self.rows():
            if k == "unknown":
                self.assertEqual(unk, " unk")
                self.assertIn('class="tag t-unk"', body)
                self.assertNotIn("t-free", body)
                self.assertNotIn("Bird free", body)
                self.assertNotIn("mbar", body)
                self.assertRegex(body, r'<span class="bnote">Grip does not know whether birds nest at [^<]+\.</span>'
                                       r'<span class="bc"><span class="ovl">Confirmed</span><span class="conf"><span aria-hidden="true">–</span>'
                                       r'<span class="vh">No</span></span></span>$')  # a dash, never a tick
            else:
                self.assertEqual(unk, "")
                self.assertNotIn("t-unk", body)
                self.assertIn('class="mbar"', body)
                self.assertIn('<span class="ovl">Confirmed</span>', body)  # its own column

    def test_folded_rows_one_per_stretch(self):
        parts = self.html.split('<section class="bsec"')[1:]
        self.assertEqual(len(parts), len(self.sections))
        for (sec, rs), part in zip(self.sections, parts):
            unk = [r for r in rs if r["kind"] == "unknown"]
            folds = re.findall(r'<div class="fold" hidden>.*?<span class="ft">([^<]+)</span><button type="button" aria-expanded="false" '
                               r'aria-controls="(bu-\d+)">Show them</button></div>', part)
            self.assertEqual(len(folds), 1 if unk else 0, sec)
            if not unk:
                continue
            text, ctl = folds[0]
            self.assertIn(f'<ul class="unks" id="{ctl}">', part)
            names = [r["name"] + (f" ({r['sub']})" if r["sub"] else "") for r in unk]
            self.assertEqual(html.unescape(text), grip.unknown_text(list(dict.fromkeys(names))))
            listed = part[part.index(f'id="{ctl}"'):]
            self.assertEqual(listed.count('data-k="unknown"'), len(unk))  # every one is there, behind Show them
            self.assertEqual(part.count('data-k="unknown"'), len(unk))
            self.assertEqual(part[:part.index('class="fold"')].count('data-k="unknown"'), 0)  # folded after the known rows

    def test_unknown_text(self):
        self.assertEqual(grip.unknown_text(["Crathie Point", "Crathie Point East"]),
                         "2 crags. Grip does not know whether birds nest at Crathie Point or Crathie Point East.")
        self.assertEqual(grip.unknown_text(["A"]), "Grip does not know whether birds nest at A.")
        self.assertEqual(grip.unknown_text(["A", "B", "C", "D"]), "4 crags. Grip does not know whether birds nest at A, B, C or D.")
        self.assertEqual(grip.unknown_text([f"C{i}" for i in range(16)]),
                         "16 crags. Grip does not know whether birds nest at C0, C1, C2 and 13 others.")

    def test_rows_name_their_walls_and_link_the_crag_page(self):
        rows = {(c, f): b for _u, _k, c, f, b in self.rows()}
        logie = [(f, b) for (c, f), b in rows.items() if c == "Logie Head"]
        self.assertGreater(len(logie), 1)
        for f, b in logie:
            self.assertRegex(b, r'^<a class="bn" href="detail/logie-head\.html#[a-z0-9-]+">Logie Head<small>[^<]+</small></a>')
        single = [b for (c, f), b in rows.items() if c == "Hareness"]
        self.assertEqual(len(single), 1)
        self.assertTrue(single[0].startswith('<a class="bn" href="detail/hareness.html">Hareness</a>'))

    def test_month_bar(self):
        bar = grip.month_bar({4, 5, 6, 7}, False, 10)
        self.assertIn('aria-label="Nesting April to July, months not confirmed"', bar)
        self.assertEqual(bar.count('<i class="p"></i>'), 4)  # hatched while a placeholder
        self.assertEqual(bar.count('<i class="now"></i>'), 1)
        bar = grip.month_bar({5, 6}, True, 5)
        self.assertIn('aria-label="Nesting May to June"', bar)
        self.assertIn('<i class="n now"></i><i class="n"></i>', bar)  # solid once confirmed
        self.assertIn('aria-label="No nesting months"', grip.month_bar(set(), False, 5))

    def test_no_script_shows_everything(self):
        self.assertIn('<div class="bctl" id="bctl" hidden>', self.html)  # search and chips need the script
        self.assertNotRegex(self.html, r'<li class="brow[^"]*"[^>]* hidden')
        self.assertNotIn('<ul class="unks" id="bu-0" hidden', self.html)
        self.assertIn("GripMatch", self.html)  # the shared matching code

    def test_the_build_no_longer_writes_a_stock_note(self):
        with open(os.path.join(ROOT, "tools", "build_crags.py")) as f:
            src = f.read()
        self.assertNotIn(STOCK, src)
        self.assertNotIn('f.get("birds")', src)  # the SMC keyword flag is never read
        notes = [(c.get("birds") or {}).get("note") for c in load()["crags"]]
        self.assertEqual(notes.count(STOCK), 0)
        self.assertEqual(notes.count(UNSPECIFIED), 27)


def build(tmp, smc=None, overrides=None, birds=None):
    """Run tools/build_crags.py on copies of the data files (any of them replaced) and return its crags by label."""
    for name, alt in (("smc_coast.json", smc), ("overrides.json", overrides), ("birds.json", birds)):
        path = os.path.join(tmp, name)
        if alt is None:
            shutil.copy(os.path.join(ROOT, "data", name), path)
        else:
            with open(path, "w") as f:
                json.dump(alt, f, ensure_ascii=False)
    out = os.path.join(tmp, "crags.json")
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "build_crags.py"), os.path.join(tmp, "smc_coast.json"),
                    os.path.join(tmp, "overrides.json"), out], check=True, capture_output=True, cwd=tmp)
    with open(out) as f:
        return {grip.label(c): c for c in json.load(f)["crags"]}


def data(name):
    with open(os.path.join(ROOT, "data", name)) as f:
        return json.load(f)


class Build(unittest.TestCase):
    """tools/build_crags.py takes birds from data/birds.json only; overrides.json may still override."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.walls = build(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_matches_the_committed_crag_list(self):
        self.assertEqual(self.walls, {grip.label(c): c for c in load()["crags"]})

    def test_ignores_the_smc_birds_flag(self):
        for flag in (None, "restricted", "clear", "affected"):
            smc = data("smc_coast.json")
            for r in smc["records"]:
                r.setdefault("flags", {})
                if flag is None:
                    r["flags"].pop("birds", None)
                else:
                    r["flags"]["birds"] = flag
            got = build(tempfile.mkdtemp(dir=self.tmp), smc=smc)
            self.assertEqual({k: c.get("birds") for k, c in got.items()}, {k: c.get("birds") for k, c in self.walls.items()}, flag)

    def test_no_birds_file_means_no_information(self):
        got = build(tempfile.mkdtemp(dir=self.tmp), birds={"walls": {}})
        self.assertFalse([k for k, c in got.items() if c.get("birds")])
        self.assertEqual({k: {x: y for x, y in c.items() if x != "birds"} for k, c in got.items()},
                         {k: {x: y for x, y in c.items() if x != "birds"} for k, c in self.walls.items()})  # nothing else moves

    def test_an_override_still_wins(self):
        ov = data("overrides.json")
        mine = {"months": [], "level": "clear", "note": "Override"}
        ov["walls"]["Hareness"] = {"birds": mine}
        ov["walls"]["South Cove (Main Face – Main Face - West)"]["birds"] = mine  # a wall the overrides also rename
        got = build(tempfile.mkdtemp(dir=self.tmp), overrides=ov)
        self.assertEqual(got["Hareness"]["birds"], mine)
        self.assertEqual(got["South Cove (Main Face)"]["birds"], mine)

    def test_every_wall_has_one_entry(self):
        birds = data("birds.json")["walls"]
        self.assertEqual(sorted(birds), sorted(self.walls))
        for k, b in birds.items():
            self.assertIn(b["level"], ("restricted", "affected", "partly", "clear", "none"), k)
            self.assertIn(b["months_source"], ("guidebook", "access notes", "climber", None), k)
            self.assertEqual(bool(b["months"]), bool(b["months_source"]), k)  # months only from an explicit source
            if b["level"] != "none":
                self.assertTrue(b["note"], k)
                self.assertIn(b["source"], ("SMC", "UKC", "SMC and UKC", "access notes", "climber report"), k)
                self.assertNotRegex(b["note"], r"\((?:SMC|UKC|developers)|\u2014", k)
            self.assertEqual(bool(self.walls[k].get("birds")), b["level"] != "none", k)

    def test_decided_after_review(self):
        w = self.walls
        for k in ("Findon Ness South (Grey Wall)", "Findon Ness South (Recess Wall)", "Findon Ness South (South Buttress)"):
            self.assertEqual(w[k]["birds"]["level"], "partly", k)  # crag text says parts, not which wall
        for k, months in (("Johnsheugh", [4, 5, 6, 7, 8]), ("The Red Wall", [3, 4, 5, 6, 7, 8])):
            b = w[k]["birds"]
            self.assertEqual((b["level"], b["months"], b["confirmed"], b["months_source"]), ("affected", months, True, "access notes"), k)
        self.assertIn("Jaded headwall", w["Johnsheugh"]["birds"]["note"])
        self.assertEqual(grip.birds_line(w["The Red Wall"]["birds"])[:41], "Reported nesting, March to August. Seabir")
        for k in ("Grey Mare Slabs", "Grey Mare Slabs (Pocket Wall)"):  # where Airegin, Ostrichism and the Aiguille are
            b = w[k]["birds"]
            self.assertEqual((b["level"], b["confirmed"]), ("partly", False), k)
            self.assertIn("Airegin", b["note"])
            self.assertIn("Groovin' High is clear", b["note"])
        for k in ("Grey Mare Slabs (Southern Rocks)", "Grey Mare Slabs (Northern Rocks)"):
            b = w[k]["birds"]
            self.assertEqual((b["level"], b["note"]), ("clear", "No nesting birds reported on these walls"), k)
            self.assertEqual(grip.birds_line(b), "None reported on these walls.")
        self.assertEqual((w["Little O Wall"]["birds"]["level"], w["Little O Wall"]["birds"]["note"]),
                         ("partly", "Some routes are out of bounds in the nesting season"))
        self.assertEqual(w["Tangerine Point"]["birds"]["level"], "restricted")
        for k in ("Castle Wall", "Castle Rock of Muchalls", "Brown Jewel Stack", "Poor Man of Harrol", "South Cove (Kettle Walls)",
                  "South Cove (Red Hole – Cave Walls)", "Doonie Point", "Tilly Tennent", "Redhythe Point Eastern Area"):
            self.assertEqual(w[k]["birds"]["level"], "restricted", k)  # the SMC access field reads "Bird"

    def test_earnsheugh(self):
        w = self.walls
        self.assertEqual(w["Earnsheugh"]["birds"]["level"], "partly")
        self.assertEqual(w["Earnsheugh (Left Wall)"]["birds"]["level"], "affected")
        self.assertEqual(w["Earnsheugh (Right Wall)"]["birds"]["level"], "partly")
        self.assertIn("Thug Wall", w["Earnsheugh (Right Wall)"]["birds"]["note"])
        self.assertNotIn("birds", w["Earnsheugh (Far Wall)"])  # no information, never bird free
        for k in ("Earnsheugh", "Earnsheugh (Left Wall)", "Earnsheugh (Right Wall)"):
            b = w[k]["birds"]
            self.assertEqual((b["months"], b["confirmed"], b.get("months_source"), b["source"]), ([4, 5, 6, 7], False, None, "SMC"), k)
        self.assertEqual(grip.birds_line(w["Earnsheugh (Far Wall)"].get("birds")), "No information. Grip does not know whether birds nest here.")
        self.assertTrue(grip.birds_line(w["Earnsheugh (Right Wall)"]["birds"]).startswith("Nesting on parts: fulmars hold some ledges"))

    def test_logie_head_climber_reports(self):
        star = self.walls["Logie Head (Star Zone)"]["birds"]
        self.assertEqual((star["level"], star["confirmed"], star.get("months_source"), star["source"], star["note"]),
                         ("affected", False, None, "climber report", "Nesting birds in season, reported by a local climber"))
        one = self.walls["Logie Head (Embankment One)"]["birds"]
        self.assertEqual((one["level"], one["months"], one["source"], one["note"]),
                         ("clear", [], "climber report", "No nesting birds reported on this wall by a local climber"))
        self.assertEqual(grip.birds_line(one), "None reported on this wall by a local climber.")
        self.assertEqual(grip.birds_line(star), "Reported nesting, April to July, months not confirmed. "
                                                "Nesting birds in season, reported by a local climber.")

    def test_months_source(self):
        """months_source is kept in the data for the record and never shown: confirmed months read without a source."""
        w = self.walls
        confirmed = sorted(k for k, c in w.items() if (c.get("birds") or {}).get("confirmed"))
        guide = ["Arthur Fowlie", "Bruin Cove", "Crazy Band Walls and The Shag’s Hole (North Wall)", "Saviours Wall",
                 "South Cove (Kettle Walls)", "The Graip", "The Orchestra Cave", "The Orchestra Cave (Back Wall)",
                 "The Orchestra Cave (Left Wall)", "The Orchestra Cave (Right Wall)", "The Red Cliff"]
        self.assertEqual(confirmed, sorted(guide + ["Johnsheugh", "The Red Wall"]))
        for k in guide:
            self.assertEqual((w[k]["birds"]["months"], w[k]["birds"]["months_source"]), ([4, 5, 6, 7, 8], "guidebook"), k)
        self.assertEqual(w["Johnsheugh"]["birds"]["months_source"], "access notes")
        self.assertTrue(grip.birds_line(w["The Red Cliff"]["birds"]).startswith("Reported nesting, April to August. Gulls"))
        self.assertEqual(grip.birds_line(w["The Graip"]["birds"]), "Nesting on parts: some nests on top and on some routes. April to August.")
        self.assertTrue(grip.birds_line(w["Arthur Fowlie"]["birds"]).startswith(
            "Reported nesting, April to August. Climbing is restricted while they nest."))
        b = dict(w["The Red Cliff"]["birds"], months_source="climber")
        self.assertTrue(grip.birds_line(b).startswith("Reported nesting, April to August. Gulls"))
        for k, c in w.items():
            b = c.get("birds")
            self.assertNotRegex(grip.birds_line(b), r"guidebook|climber report|access note|\b(?:SMC|UKC)\b", k)
            if b and b["level"] != "clear" and k not in confirmed:  # every other nesting wall keeps the placeholder, marked not confirmed
                self.assertEqual((b["months"], b["confirmed"], "months_source" in b), ([4, 5, 6, 7], False, False), k)
                self.assertIn("months not confirmed", grip.birds_line(b), k)

if __name__ == "__main__":
    unittest.main(verbosity=2)
