"""Tests for the bird register (birds.html): the In season now line, the status filters and their counts, the No information
rows folded per stretch, the notes without source tags and the stock note's wording.

Standard library only. Run from the repository root or anywhere: python3 tests/test_birds.py
"""
import html
import json
import os
import re
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import grip  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime(2026, 10, 5, 16, 51, tzinfo=grip.TZ)
STOCK = "Birds reported nesting; months not confirmed"


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
                         r"^In season now: no crag with confirmed months; \d+ crags have birds reported but months not confirmed\.$")


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
        self.assertIn('<p class="foot">Sources: the SMC routes database, UKClimbing and climbers’ reports, reworded by Grip.</p>', h)
        self.assertNotIn("\u2014", h)  # no em dashes

    def test_no_source_tags_and_the_stock_note(self):
        self.assertNotRegex(self.html, r"\((?:SMC|UKC|developers)")
        self.assertNotIn("Nesting birds noted in the SMC database", self.html)
        self.assertIn(f'<span class="bnote">{STOCK}.</span>', self.html)

    def test_chips_and_counts(self):
        chips = re.findall(r'<button type="button" data-k="(\w+)" aria-pressed="(true|false)">([^<]+) <span>(\d+)</span></button>', self.html)
        self.assertEqual([(k, t) for k, _p, t, _n in chips],
                         [("all", "All"), ("restricted", "Restricted"), ("nesting", "Nesting birds"), ("clear", "Bird free"), ("unknown", "No information")])
        self.assertEqual([p for _k, p, _t, _n in chips], ["true", "false", "false", "false", "false"])
        n = {k: int(x) for k, _p, _t, x in chips}
        rows = self.rows()
        kinds = [k for _u, k, _c, _f, _b in rows]
        self.assertEqual(n["all"], len(rows))
        self.assertEqual(n["restricted"], kinds.count("restricted"))
        self.assertEqual(n["nesting"], kinds.count("nesting") + kinds.count("possible"))
        self.assertEqual(n["clear"], kinds.count("clear"))
        self.assertEqual(n["unknown"], kinds.count("unknown"))
        self.assertEqual(n["restricted"] + n["nesting"] + n["clear"] + n["unknown"], n["all"])
        self.assertEqual((n["all"], n["restricted"], n["nesting"], n["clear"], n["unknown"]), (178, 10, 51, 24, 93))  # crags.json today

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
        self.assertEqual(grip.bird_kind({"level": "possible", "months": []}), "possible")

    def test_unknown_never_looks_bird_free(self):
        for unk, k, _c, _f, body in self.rows():
            if k == "unknown":
                self.assertEqual(unk, " unk")
                self.assertIn('class="tag t-unk"', body)
                self.assertNotIn("t-free", body)
                self.assertNotIn("Bird free", body)
                self.assertNotIn("mbar", body)
                self.assertRegex(body, r'<span class="bnote">Grip does not know whether birds nest at [^<]+\.</span>$')
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

    def test_stock_note_in_the_build(self):
        with open(os.path.join(ROOT, "tools", "build_crags.py")) as f:
            src = f.read()
        self.assertIn(f'"note": "{STOCK}"', src)
        self.assertNotIn("Nesting birds noted in the SMC database", src)
        notes = [(c.get("birds") or {}).get("note") for c in load()["crags"]]
        self.assertEqual(notes.count(STOCK), 61)


if __name__ == "__main__":
    unittest.main(verbosity=2)
