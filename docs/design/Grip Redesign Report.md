# Grip redesign

A full design pass on the forecast, crag pages, the three forms and the bird register. Reviewed against the live site on Mon 5 Oct 2026.

Assumptions: data in the mock-ups is taken from the live site where it existed (Logie Head walls, scores, tides, calibration); counts on the birds page and the "118 of 165" style summaries are illustrative. Mock-ups use the fixed palette, Barlow and Barlow Condensed, and the supplied G2 logo. Items that depend on a group B proposal are drawn in, so each can be judged in place.

## 1. Audit

1. The first question has no first answer. Home opens with the title, the key and a long paragraph of form links. "Is anywhere good today or tomorrow?" means scrolling to ten prose cards and reading each one.
2. Two vocabularies for the bands. The home key says Usable and Crisp; crag pages and the log form say Climbable and Grippy; the calibration table mixes both. A climber cannot tell whether Crisp means Grippy.
3. Today and Tomorrow are written out, not laid out. "Prime, best 16:00 to 18:00; 4 of 7 daylight hours usable. Low water 02:40, 15:18." ten times over. Score, window and hours do not line up, so crags cannot be compared at a glance, and on an even day the top five are near-identical crags from one stretch.
4. Multi-wall crag pages repeat themselves. Logie Head states the same rain, rock, weather point, seepage rule, sea sentence and method caveat nine times, then prints nine ten-column hour tables. The few real differences between walls, the reason the page exists, are buried in the sameness.
5. No way to see which wall is best. The line of nine wall names links to anchors but carries no scores. Finding the best wall means scrolling through all nine sections.
6. How sure comes last and reads as small print. On crag pages it follows every wall. On home, disagreement is a stripe explained only in the key under a 165-row grid; calibration is a dense paragraph of statistics with no picture of the record.
7. The 7-day grid is hard to drive by touch. Cells are small, focus and selection are not shown, the filter gives no count or empty state, and the pop-up is the only route to a day's detail.
8. Freshness is unclear. Home says 11:37 while a crag page says 16:51. There is no next-update time and no warning when a run is late; the switch to tomorrow after dark happens without comment.
9. The method sits on the forecast page. The ten-row factor table weighs on every visit, though few read it, and there is no other way to reach it.
10. The forms are unequal and wordy. Log a day is on the site; crag notes and feedback are a link in a paragraph. The log page has two intro paragraphs before the first field, the Google Form link twice, and the five feel options are plain text without the band colours the climber is matching against.
11. The bird register is a wall of dashes. One five-column table of about 190 rows, mostly "No information", with wall names run into crag names ("The Long Slough Long Slough Red Rocks"), months as text and "Confirmed: No" on nearly every row.
12. Navigation is one-way. Inner pages only offer "Back to the forecast". Birds and the method can only be found by scrolling.

## 2. Principles

1. Answer first. Each page opens with the answer to the next question: where and when, then why, then how sure.
2. Colour is data. Band colours appear only on scores. The interface is ink on paper; pink and teal stay in the logo.
3. A number on every block. Scores are always numbers on their band. Stripes mean the models disagree, a dot means wet-rock risk.
4. Say it once. Facts shared by walls or crags are stated once, where they apply. Wall sections show only what differs.
5. Doubt on the surface. How sure sits next to the score, written as plainly as the forecast itself.
6. Built for the car park. One column, 44 px targets, nothing that needs hover, light on a weak signal.

## 3. Mock-ups

See the attached screenshots. Rows:

- **3a Home, above the fold**: Summary cards answer today and tomorrow first. The coast panel is now a hour-by-hour strip per stretch with numbers; popular crags line up as a table. Below: the three forms as equals.
- **3b Home, the 7-day grid**: 44 px cells, sticky crag names, section labels, today's column in ink, a fade showing the box scrolls. How sure sits right under the grid with the 12-day record.
- **3c Grid pop-up**: Filtered to "logie", Thursday selected. Stripes and dot on the score, then a plain sentence on the disagreement, the three models, and every wall that day.
- **3d Crag page, Logie Head (9 walls)**: Walls overview, How sure and shared conditions first (left column on desktop). Two walls open to show how they differ; the rest collapse. One hour-by-hour table with wall and day pickers.
- **3e Log a day**: Shared form frame: Contribute nav, band tiles for the feel, chips for problems, one fallback link under Send.
- **3f Log a day, sent**: Summary of what was sent, what Grip said that day, and when it will show.
- **3g Send a crag note**: Pre-filled from the Tidal Zone wall. Birds is ticked, so the situation and month picker appear.
- **3h Send a crag note, sent**: Same sent card as the other forms.
- **3i Give feedback**: No crag box. One required field, three optional ones, page and device, a private contact.
- **3j Give feedback, sent**: Same sent card.
- **3k Nesting birds**: Caution notice up top, filter chips, a 12-month bar per entry, ink-only status tags, a Confirmed column, and "no information" crags folded into one clearly unknown row per stretch. One sources line at the foot.

## 4. Design spec

See sections at the end of this file (component spec, then tokens CSS).

## 5. Wording

| Where | Before | After |
|---|---|---|
| Band names | Usable / Crisp (home key, calibration) | Climbable / Grippy everywhere |
| Home subtitle | Dry-rock forecast for the sea cliffs of north-east Scotland. Updated Mon 5 Oct, 11:37. Models: Met Office, ECMWF, ICON. | Updated Mon 5 Oct, 11:37 · Next update about 17:30 |
| Summary (new) | none | Today, Mon 5 Oct · Prime late on, 16:00 to 18:00 · Best from Cove to Newtonhill. 118 of 165 crags reach Grippy. |
| Coast panel | Coast today / Coast tomorrow | Along the coast [Today / Tomorrow] · Best wall on each stretch, hour by hour. Earlier hours are greyed. |
| Popular cell | Prime, best 16:00 to 18:00; 4 of 7 daylight hours usable. Low water 02:40, 15:18. | [8] 16:00 to 18:00 · 4 h · LW 15:18 |
| Hours | usable hours | climbable hours |
| Grid intro | Crags with several walls show their best wall. Tap a crag name for its hour-by-hour page; tap any score for the other walls, what each weather model gives it, usable hours and wet-rock risk. | Each crag shows its best wall. Tap a score for that day's detail, or a name for the crag page. |
| Grid sub-labels | NW, trad · 4 walls, best shown · aspect unknown, trad | Faces NW · Best of 4 walls · Aspect not known (sport marked only where it applies) |
| Key, stripes | Striped: models differ by more than 2, or only one model | Stripes: the models differ by more than 2, or only one model runs that far ahead. |
| Key, dot | Dot: at least one model in three has the rock wet, foggy or raining in the best window | Dot: at least one model in three has the rock wet in the best window. |
| Search | Find a crag (no count, no empty state) | Find a crag · Start typing a name, such as Logie · 3 crags match "logie" · No crag matches "xyz". Try part of a name, such as Souter or Cove. |
| Calibration heading | Checking Grip against real days | How sure is Grip? |
| Calibration lead | 12 logged days scored so far. Taking the score as shown, Grip landed in the felt band 6 times, and within a point of it 10 times. Misses are measured on the unrounded score… | Not very, yet. 12 days have been logged. Grip's score landed in the band climbers felt on 6 of them, and within a point on 10. The typical miss is 0.8 of a point. (Detail moves to Method.) |
| Form links | Log a day on the rock (button), "Climbed on the coast? Say how the rock felt…" Know a crag better than the list does? Send a crag note… | Help Grip get better: three equal cards. Log a day on the rock / Send a crag note / Give feedback, each with one line. |
| Crag subtitle | Conditions at this crag: the score, why, how sure, and what shapes the rock. | 9 walls · Weather from the Cullen and Portsoy point · Updated Mon 5 Oct, 16:51 |
| Wall list | 9 walls: Embankment One · Embankment Two · … | Walls (table: name, aspect, Today, Tmrw) |
| Strip line | Grippy now, best 16:00 to 18:00. | Grippy now. Best 16:00 to 18:00. |
| Why | The best window comes from dry air. From the hourly factor points (the first model's figures…). Only factors worth 2 points or more either way are named. | Dry air. Humidity falls below 60% by late morning, and the sun is on the face from 09:00 to 14:00. |
| Recent weather | Rain in the last 24 hours 0.1 mm, last 72 hours 0.4 mm (Met Office figures…). Water on the rock now: dry (0.00 mm…) | Rock now: Dry. 0.1 mm of rain in 24 hours, 0.4 mm in 72. (Once per crag.) |
| Sea | Waves now 1.0 m, up to 1.0 m today. Coming from the W, from behind the face, period 4.1 s (short wind sea). Grip counts it at 40%… | Sea: comes from behind the face, counted at 40%: 0.4 m at the wall. |
| Birds, per wall | Climbing is not affected. Free of nesting birds (SMC database). | Birds: None reported. |
| How sure, empty | The models agree today and tomorrow on every wall. | Today and tomorrow the three models agree on every wall, within 2 points. |
| Hour table | Wet risk 0% / 33% · Breakdown (points) air +4, fog +0, dew +1, wind -0/+0… · Models Met 6, ECM 6, ICO 6 | Wet risk None / 1 in 3 · Points air +4 · dew +1 · sun +3 (zeros left out) · Models as three score blocks |
| Log intro | How did the rock actually feel? Your answers calibrate the Grip forecast. Anonymous, no account needed. One entry per crag per visit. Score the crag as a whole… | How did the rock feel? Each day logged tests Grip against real rock. It takes about a minute and needs no account. (Per-visit rule moves to the aside.) |
| Log times | On the rock from / On the rock until | From / Until (beside Date) |
| Log problems | If it was poor, what was the problem? Tick any that apply. | Anything that made it worse? Optional. Tick any that apply. |
| Log contact | Happy to answer a follow-up question about this day? Leave a name and a way to reach you, WhatsApp number or email. Kept private, never published. | Contact for a follow-up (Optional) · Kept private. Never published. |
| Fallback link | Prefer the Google form? Use it here. (twice, plus a no-JS notice) | Prefer the Google form? Use it here. (once, under Send, same on all three forms) |
| Sent states | (none on site for notes and feedback) | Thank you. Your day is logged. / Thank you. Your note is in. / Thank you. Feedback sent. Each with a summary and what happens next. |
| Birds title | Nesting birds by crag | Nesting birds · In season now: none. The season here runs roughly March to August. |
| Birds rows | No information · - · - · - | ? No information · 16 crags. Grip does not know whether birds nest at Girdle Ness Point, The Black Dyke… (one row per stretch) |
| Birds confirmed | Confirmed: No | Confirmed: No, with an outlined ? mark, kept as its own column |
| Crag sources | Source: SMC routes database | Crag facts from the SMC routes database, climbers’ reports and local developers’ notes, reworded by Grip. (One line at the foot; no per-fact tags.) |
| Method foot (new) | none | Grip is independent and not affiliated with the SMC or UKClimbing. |
| Birds intro | Status, months and source for every crag Grip covers… Most entries come from keyword matching on the SMC routes database and UKC… | Nesting status and months for every crag Grip covers. Entries come from published crag information and climbers’ reports, and most months are placeholders until someone confirms them. If you know better, send a crag note. |
| Birds caution (new) | none | Not a definitive record. Check local guidance and look before you climb in the nesting season. |
| Birds stock note | Nesting birds noted in the SMC database; months not confirmed | Birds reported nesting; months not confirmed |
| Birds sources | (SMC) / (UKC) after each note | Sources: the SMC routes database, UKClimbing and climbers’ reports, reworded by Grip. |
| Back links | Back to the forecast | Header nav: Forecast · Contribute · Birds · Method |
| Stale (new) | none | This forecast is 11 hours old. The next run is late, so treat it with care. |
| After dark (new) | Coast today silently becomes Coast tomorrow | Tomorrow selected by default; the summary cards show Tomorrow and the day after. |

## 6. Change list

### A. Look only

Changes appearance. The site does and shows the same things.

- A1 Ink-on-paper interface: band colours only on scores, so the data is the only colour on the page.
- A2 One band vocabulary: Climbable and Grippy everywhere, matching the fixed names.
- A3 Score blocks at five fixed sizes: 56, 44, 36, 28, 24 px, so a score reads the same on every page.
- A4 Type scale and spacing tokens: fewer sizes and steadier rhythm make the hierarchy obvious.
- A5 Popular crags as an aligned table: same data as now, but scores, windows and hours line up for comparison.
- A6 Coast blocks carry numbers; past greyed, current ringed: same behaviour, marked clearly and without relying on colour.
- A7 Grid cells at 44 px with focus and selected rings, sticky names, a scroll fade: easier to tap and to see where you are.
- A8 Compact key with ranges on band chips and samples of dot and stripes: teaches the scale in one line.
- A9 Pop-up as a bottom sheet on phones, a centred dialog on desktop: same content, within thumb reach.
- A10 Hour table: score and model blocks, tabular numbers: the same columns, easier to scan.
- A11 Log feel options as band tiles, problems as chips: same options, matched to the scale climbers are judging against.
- A12 Birds: status tags in ink and a 12-month bar; No information drawn unlike Bird free: same data, scannable, and unknown never reads as safe.
- A13 Focus rings, 44 px targets and hover states throughout: keyboard and touch use.
- A14 Tuned dark tokens for sunk, past and scrim: keeps contrast at AA in dark mode.

### B. Changes how it works

Proposals, to be decided one by one.

- B1 Header nav on every page: Forecast, Contribute, Birds, Method: every page reachable from every other.
- B2 Best today and best tomorrow cards at the top of home: answers the first question before any scrolling.
- B3 Today | Tomorrow switch on the coast panel, Tomorrow by default after dark: plan tomorrow during the day; says plainly what after dark does.
- B4 Freshness line with next update, and a stale banner after 9 hours: tells you when not to trust the page.
- B5 "Help Grip get better": three equal cards on home: presents logging, notes and feedback as equals, as asked.
- B6 On-site Send a crag note and Give feedback pages, sharing one form design and sent state with Log a day: three forms that look and behave alike, with the Google Forms as fallback.
- B7 Crag note pre-filled from the crag page, with a Birds section and month picker when Birds is ticked: fewer steps, and bird notes arrive in a usable shape.
- B8 Method page holds How Grip works and the full calibration table; home keeps a How sure summary: lighter home without hiding the honesty.
- B9 Calibration as a 12-square record: shows how often Grip has been right at a glance.
- B10 Search count and empty state: says what the filter did.
- B11 Pop-up adds a plain sentence on model disagreement: answers how sure where the score is.
- B12 Crag page: Walls overview with Today and Tomorrow scores: finds the best wall in one look.
- B13 Crag page: "Across the crag" states shared facts once; walls list only what differs: cuts most of the repetition.
- B14 Crag page: How sure moves up beside the walls and names which model differs and when: doubt sits next to the score.
- B15 Crag page: walls after the first collapse to summary rows (details, no JS): a 9-wall page shrinks to a screen or two.
- B16 Hour by hour: one table with a wall picker and day tabs, zero factors left out: far less to scroll and download; all tables still render without JS.
- B17 Log sent state shows what Grip said for that wall and day: closes the loop for the person logging; needs a small JSON of recent scores.
- B18 One Google Form link per form, under Send: removes duplicates.
- B19 Birds: filter chips, search, "In season now" line, a caution notice, no-information crags collapsed per stretch: the register becomes a lookup, and its limits are stated up front.
- B21 Sources as one line at the foot of crag and bird pages; independence line on Method: credit stays visible without a tag on every note.
- B20 Grid sub-labels drop "trad", keep aspect and "sport": less noise on 165 rows.

---

# Appendix A: Grip design spec

For building the redesign in the existing Python site generator. Hand-written HTML and CSS, a little vanilla JS, no frameworks. Tokens are in `grip-tokens.css`; this file covers layout, components and states. Mock-ups: `Grip Redesign.dc.html`.

Items marked **(B)** depend on a proposal in group B of the change list. Build the rest without them.

## 0. Global rules

- **Colour is data.** Band colours only on score blocks, key chips and the log page's band tiles. Brand pink and teal only inside the logo image. Every other surface uses paper, card, sunk, ink, muted, rule.
- **Every score block carries its number.** Disagreement adds stripes, wet-rock risk adds a dot. Each block gets an `aria-label` such as "Thu 8: 5 Climbable, wet-rock risk, models disagree".
- **Page frame:** `max-width: var(--page-max)`, side padding 16px (header 12px). One column below 900px. No horizontal page scroll at 360px; wide tables scroll inside their own box (`overflow-x: auto`, `tabindex="0"`, `aria-label`).
- **Breakpoints:** 600px (form rows go side by side), 900px (two-column home and crag layouts), 1200px (max width).
- **Fonts:** self-host Barlow 400/500/600 and Barlow Condensed 500/600, latin subset, woff2, `font-display: swap`. About 90 KB total. Numbers use `font-variant-numeric: tabular-nums` in tables.
- **Focus:** every interactive element shows `box-shadow: var(--focus-ring)` on `:focus-visible`. Never remove outlines without this.
- **Hover** (pointer devices only, `@media (hover:hover)`): links thicken underline to 2px; buttons darken by swapping to `--sunk` (secondary) or 90% opacity (primary); score buttons gain `--now-ring` at 50% opacity.
- **Motion:** none needed. Sheet and dialog may fade 120ms; respect `prefers-reduced-motion`.
- **Headings:** one `h1` per page (visually hidden on home: "Grip, dry-rock forecast for the north-east sea cliffs"). `h2` per section, `h3` inside cards.

## 1. Header

- `<header>` full-bleed, background exactly `--paper` (#eef1f2 / #141d23), 1px `--rule` bottom border. Height 56px; inner flex, space-between.
- Logo: the hand stays thrift pink (#c2457e, dark #ec8bb6). Never recolour it to a skin tone. Any other hand icon is pink or plain ink.
- Logo link: `<a href="/" aria-label="Grip, forecast home">` holding the header logo at 36px tall (89 × 36). Use `<picture>` with `grip-logo-dark.svg` for `prefers-color-scheme: dark`.
- **(B1)** Nav: `<nav aria-label="Main">` with Forecast, Contribute (the three forms), Birds, Method. Barlow Condensed 500, 17px, each link 44px tall, 7px side padding, `white-space: nowrap`. Current page: `aria-current="page"`, 2px underline offset 6px. Fits at 360px; below 340px drop "Method" into the footer.
- States: default, hover (underline), focus (ring), current.

## 2. Freshness line (home and crag)

- 14px muted: "Updated Mon 5 Oct, 11:37" and "Next update about 17:30", flex-wrap, gap 12px.
- **Stale (B17):** if the newest run is over 9 hours old (JS compares the embedded ISO timestamp with now), insert above it a `--sunk` box with a 1px ink border, radius 8, 12px padding: "This forecast is 11 hours old. The next run is late, so treat it with care." No colour beyond ink.
- **Loading:** the page is static, so there is no loading state for data. Fonts swap in; layout must not jump (reserve block sizes).

## 3. Summary cards (B2)

- Two cards in a flex row (wrap, basis 300px, gap 12). Card: `--card`, 1px rule, radius 10, padding 14/16, flex with 14px gap.
- Left: score block XL (56px, number 34px). Right: overline (13px display caps, muted) "Today, Mon 5 Oct"; line (21px display 600) "Prime late on, 16:00 to 18:00"; meta (14px muted) "Best from Cove to Newtonhill. 118 of 165 crags reach Grippy."
- Generator picks the best stretch by its best wall's score, ties broken by longest window.
- **After dark:** once today's daylight is over the cards show Tomorrow ("Tomorrow, Tue 6 Oct") and the day after, headed by its date alone ("Wed 7 Oct"), both in the same format as by day: score block, line with the band and best window, best stretch and Grippy count. There is no "Today is over" card. These are the same two days as the Popular crags table and the crag pages.
- **No good day:** if nothing reaches 4, the line reads "Nowhere climbable. Best is Greasy, 3, at …".

## 4. Coast panel

- `h2` "Along the coast" + segmented control (B3) Today | Tomorrow (`role="radiogroup"`, buttons 40px tall inside a 44px control, selected = `--inv-bg`).
- Hint line 14px muted: "Best wall on each stretch, hour by hour. Earlier hours are greyed."
- Rows: name (link to the first crag in that stretch, 15px 500) and a strip. Name column basis 170px; strip basis 240px; the row wraps so on phones the name sits above the strip.
- Hour header row: 12px display, muted, centred over each block.
- Blocks: `flex: 1`, height 30px, gap 3px, radius 4, number 15px display 600.
- States:
  - **Past hour:** background `--past`, number `--past-ink`, no stripes or dot.
  - **Current hour:** `--now-ring`.
  - **Disagreement:** stripes. **Wet-rock risk:** 6px dot, top right, in the block's text colour.
  - **After dark:** switch defaults to Tomorrow; Today is still selectable and shows every block as past.
  - **Hour not scored** (sun under 5°): no block; leave the slot empty with a 1px dashed rule outline.

## 5. Key

- Inline flex-wrap, gap 6/14, 13px. Each band: chip (min 34 × 22, radius 4, 13px display 600) showing the range "6–7" on the band colour, then the name. Then two samples on `--sunk` with rule border: dot ("Wet-rock risk") and stripes ("Models disagree").
- Appears once under the coast panel and once as a footnote under the grid (sentence form). Not repeated on crag pages; the crag page links to Method.

## 6. Help Grip get better (the three forms, as equals)

- Section after popular crags. `h2` 24px "Help Grip get better"; one muted line.
- Three cards in a flex row (wrap, basis 240px, gap 8), identical in size and weight: card bg, 1px rule, radius 10, padding 14/16. Each card is one link: title (20px display 600), one line (14px muted), call to action (15px 600, underlined).
- Order: Log a day on the rock, Send a crag note, Give feedback. None is primary.
- States: hover = `--sunk` background; focus = focus ring on the whole card.

## 7. Popular crags

- `h2` "Popular crags". Box: card, rule border, radius 10.
- Column header row: Today | Tomorrow, 13px display caps, muted; from 1100px a Crag heading over the names as well.
- Rows: the crags in `data/popular.json`, ranked by the first day's score as shown, then climbable hours, then list order. The top 5 show (`POPULAR_TOP`: of 5 to 8, the number that brings the column closest to the coast panel at 1280px).
- Each crag row, under 1100px: name (16px 600 link) on its own line, then a two-column grid. Each cell: score block 40px (number 22px) + two lines at 13px: window "16:00 to 18:00" (600, ink) and "4 h · LW 15:18" (muted). LW only for tidal walls.
- From 1100px each crag row is one line: name on the left, then the two cells, same content, in columns 1fr / 1.2fr / 1.2fr, centred vertically.
- Show-all button under the rows: full width, 44px, 1px rule above, 16px 600 ink, left aligned, with a chevron pointing down. "Show all 15 popular crags" shows the rest in place and becomes "Show fewer" (chevron up); `aria-expanded` and `aria-controls` point at the rows. Hover `--sunk`; the focus ring is drawn inside the box. Without JavaScript every row shows and there is no button.
- Footer link "All 165 crags, next 7 days" (jumps to grid), below the button.
- Desktop: in the right column, beside the coast panel.
- States: **after dark** the columns are Tomorrow | Day after, ranked by tomorrow; **no window** (score under 4): window line reads "No climbable hours".

## 8. Search box

- `<label>` "Find a crag" (15px 600) wraps an `<input type="search">`: 48px tall, radius 8, 1px rule border, card bg, 16px text, placeholder "Start typing a name, such as Logie".
- Live result line, `role="status"`, 14px muted: default "165 crags in 16 stretches"; filtered "3 crags match “logie”".
- Filtering hides non-matching rows and any section left empty; matches any word start, ignores apostrophes.
- States: focus = 2px ink border + focus ring; **empty result**: grid hidden, message in the grid box: "No crag matches “xyz”. Try part of a name, such as Souter or Cove." plus a "Clear" text button (44px).
- No JS: input hidden (`hidden` attribute removed by script), grid shows in full.

## 9. Seven-day grid and cells

- `h2` "Next 7 days", one-line hint, search, then the box: card bg, rule border, radius 10; inner `overflow-x: auto`.
- `<table>`: `thead` day columns "Mon / 5", 14px display; today's column in ink, others muted. First column `th scope="row"`, `position: sticky; left: 0`, card bg, 1px right rule (box-shadow). Width 132px phone, 260px desktop.
- Crag name 15px 600 link; sub-label 12px muted: "Faces NW", "Best of 4 walls", "Faces E · sport", "Aspect not known".
- Section rows: `th colspan scope="rowgroup"`, 15px display caps muted, inner span sticky left so it stays visible while scrolling.
- Cells: `<button>` 44 × 44, radius 6, number 21px display 600, gap 2px. Phone total width ≈ 460px, so it scrolls; a 28px fade on the right edge shows there is more.
- States: default; hover (pointer) half-opacity now-ring; **focus** focus ring; **selected** (its pop-up open) `--now-ring`; stripes; dot; **filtered out** (`hidden`).
- Footnote 13px muted explains dot and stripes.
- Weight: keep each cell as `<button data-c="logie-head" data-d="3">5</button>` with the band as a class (`.b4`); pop-up detail lives in one JSON blob loaded on first tap (or inline at the page end), not in each cell.

## 10. Pop-up (day detail)

- `<dialog>` opened with `showModal()`; scrim `--scrim`; Esc and the close button close it; focus returns to the cell.
- Phone (< 600px): bottom sheet, full width, top radius 16, max-height 85vh, scrolls inside; 40 × 4 grab bar (decorative). Desktop: centred, 480px wide, radius 12, `--shadow-overlay`.
- Contents in order:
  1. Overline day "Thu 8 Oct", `h2` crag name (26 to 28px display), close button 44 × 44.
  2. Score block XL + line (19 to 20px display) "Climbable, best 15:00 to 18:00" + meta "5 climbable hours. Low water 05:02 and 17:21."
  3. How sure panel (`--sunk`, radius 8, padding 10/12): heading "The models agree" or "The models disagree" (15px 600), one plain sentence, then three model results (32px blocks + name) in a row: Met Office, ECMWF, ICON.
  4. `h3` overline "9 walls on Thursday", grid of walls (2 columns phone, 3 desktop), each a 28px block + name.
  5. Actions: primary "Hour by hour" (to the crag page, that day), secondary "Log this day" (log page with wall and date prefilled). 48px phone, 44px desktop.
- Single-wall crags skip part 4.
- States: **models agree** heading and sentence "All three models are within 2 points."; **one model only** (days 5 to 7): "Only ECMWF reaches this far ahead. Treat it as a rough guide."

## 11. Strips (crag page)

- Per day: overline label "Today, Mon 5" and the plain line (17px 600) "Grippy now. Best 16:00 to 18:00." on one wrapping row.
- Blocks: flex 1, 36px tall, radius 5, number 19px; hour label under each, 12px display muted.
- States as the coast panel: past, current ring, stripes, dot, not scored. **After dark:** the Today strip is all past and its line reads "Over for today. Best was 16:00 to 18:00."

## 12. Crag page sections

Layout ≥ 900px: left column (basis 320px) = Walls, How sure, Across the crag; right column (basis 560px) = wall cards, hour by hour, logged days, source. Below 900px the same order stacks, so the walls overview and How sure come before any wall detail.

- **Title block:** breadcrumb "Forecast / {stretch}" (14px), `h1` 36 to 40px display, meta line "9 walls · Weather from the Cullen and Portsoy point · Updated …", actions: "Log a day here" (primary), "Send a crag note" (secondary).
- **Walls (B8):** card with a 3-column grid (name+sub, Today, Tmrw). Rows are links to the wall card, 44px min. Current wall: `aria-current`, `--sunk` bg, 3px inset ink left rule. Single-wall crags omit this card.
- **How sure (B10):** 2px ink border, radius 10. Heading 20px. One to three sentences naming which model differs, when, and whether it touches the best window. Empty state: "Today and tomorrow the three models agree on every wall, within 2 points."
- **Across the crag (B9):** `dl` of Rock now, Low water, Sea, Weather. Footnote naming the source model and time.
- **Wall card:** `article`, card bg, radius 10, padding 14/16. `h2` 28px display + "Log a day on this wall" link; tags (pills, 13px, rule border) for aspect, shelter, tide, birds-in-season. Then strips (Today, Tomorrow), Why (`h3` overline + one or two sentences), What shapes this wall (`dl`, only facts that differ from "Across the crag"), Next 7 days (7-column grid: day, 38px block, window "11–14", hours "9 h").
- **Collapsed walls (B11):** `<details>` per wall; `<summary>` 48px min with name, aspect, today and tomorrow blocks, "+" marker that turns to "−" when open. First wall (or the one in the URL hash) opens by default.
- **Logged days here:** table: Date, Wall, Felt, Grip said, Actual weather. Empty: "No days logged here yet. Climbed here? Log a day." with the link.
- **Sources:** one line at the foot, 13px muted, 1px rule above: "Crag facts from the SMC routes database, climbers' reports and local developers' notes, reworded by Grip." "SMC routes database" links to the crag's own SMC page. No per-fact or per-note source tags anywhere.

## 13. Hour-by-hour table

- `h2` + 14px hint naming whose figures the points column uses.
- **(B12)** Controls: Wall `<select>` (44px), day tabs (`role="tablist"`, Mon 5 / Tue 6 / Wed 7). Without JS, render every wall and day as stacked tables (current behaviour) under `<details>`.
- Box: card, rule, radius 10, `overflow-x: auto`, `tabindex="0"`. Table min-width 820px; `caption` with the day and low water.
- Columns: Time (sticky), Grip (34px block, stripes when models differ by over 2), Models (three 24px blocks, fixed order, named in the footnote), Wet risk ("None" / "1 in 3" in 600 weight), Humidity, Rock over dew point, Wind, Sun ("on the face" / "sun" / "cloud"), Sea at wall, Points ("air +4 · dew +1 · sun +3", zero factors left out, muted).
- Rows 40px min; 1px rule between; past hours on today use `--past-ink` text and past block.

## 14. Forms: Log a day, Send a crag note, Give feedback

All three are on-site pages (`log.html`, `note.html`, `feedback.html`) built from one set of parts. They post to the same Google Forms back ends; the Google Forms stay as a fallback.

- **Shared frame:** header with "Contribute" current; under it a segmented nav `<nav aria-label="Contribute">` linking the three pages (42px options, current = `--inv-bg`, `aria-current="page"`), max 460px wide. Then `h1`, one-line intro, the form (max 680px), and an aside (basis 280px) with one or two short cards.
- **Shared ending:** Send (primary, 52px, full width up to 320px), then 14px muted "Prefer the Google form? Use it here." Same sent card on all three: overline "Sent", `h1` "Thank you. …", a `dl` summary, one sentence on what happens next, "Send another …" (primary) and "Back to the forecast" (secondary).
- **Log a day:** crag and wall, date / from / until, feel (band tiles), problems (chips), notes, initials, contact.
- **Send a crag note:** crag and wall (prefilled from `?wall=` when opened from a crag page, hint "Filled in from the crag page. Change it if needed."), "What is the note about?" chips (Aspect, Tidal, Seepage, Shelter, Birds, Other), the note (textarea, 120px), initials. When Birds is ticked, a Birds fieldset appears (card bg, rule border, radius 10): situation radios (Restricted, Nesting birds, Bird free, Not sure) as 48px tiles, and a 12-month picker (`role="checkbox"` buttons, 44px tall, `repeat(auto-fill,minmax(48px,1fr))`, selected = `--inv-bg`). Without JS the Birds fieldset is always shown.
- **Give feedback:** "What were you trying to do?" (required, 72px), "What worked?", "What did not?", "Anything missing, or ideas?" (optional, 72px), Which page (select) and Device (segmented Phone / Tablet / Computer), a way to reach you (optional, kept private). No crag box, no initials.
- Page and device are prefilled from the referring page and screen width where possible.

### Field parts

- Label 16px 600 above; hint 14px muted under the label; optional fields say "Optional" in 400 muted after the label. Required fields are not starred; the few required ones (crag, date, feel) are validated on Send.
- Text, date, time inputs: 48px tall, radius 8, 1px rule, card bg, 16px text. Focus: 2px ink border + focus ring. Error: 2px ink border plus a message under the field in 14px 600 ink starting "Pick a crag from the list" etc. (no red: red is Soaked).
- Crag combobox: `role="combobox"`, listbox of up to 8 options, 44px rows, matches word starts; Esc closes; the chosen value reads "Logie Head (Embankment One)".
- Date, From, Until on one row ≥ 600px (date basis 150, times 90).
- **Feel:** `fieldset` + `legend`. Five tiles, one per band: 52px min, card bg, 1px rule; 44px band chip with the range; name (17px 600) and description (14px muted); radio circle on the right. Selected: 2px ink border, filled dot.
- **Problems:** checkbox chips, pill, 44px tall, 1px rule; checked = `--inv-bg` with tick.
- Notes `textarea` 96px min.
- Send: primary button 52px, up to 320px wide; "Use the Google Form instead" link beside it.
- **No JS:** the form is replaced by the Google Form link (current behaviour) with the sentence "This form needs JavaScript. Use the Google Form instead."
- **Sending:** button text "Sending…", `aria-disabled`, fields locked.
- **Failed:** message above Send: "That did not go through. Check your signal and send again, or use the Google Form." Fields keep their values.
- **Sent:** the form is replaced by a status card (`role="status"`, focus moves to its `h1`): "Thank you. Your day is logged.", a `dl` summary (crag, when, felt, and **(B13)** Grip said), a sentence on when it appears, and buttons "Log another day", "Back to the forecast".

## 15. Buttons

- Primary: `--inv-bg` / `--inv-fg`, 600 16px, radius 8, 44px min (48 to 52 for the main action on phones).
- Secondary: card bg, 1px rule, ink text, 500.
- Segmented: 1px rule container radius 8, 2px padding; options 38 to 40px; selected `--inv-bg`.
- Icon button (close): 44 × 44, 1px rule, transparent.
- States: hover (see global), focus ring, active (translateY 1px), disabled (`--past` bg, `--past-ink` text, no pointer).

## 16. Links

- Body links: ink, underline 1px, offset 3px; hover 2px; visited unchanged. Crag names in tables and lists: no underline, 600 weight, underline on hover and focus.
- External links (Google Forms, SMC, UKC, Open-Meteo): no icon; the link text says where it goes ("Use the Google Form").

## 17. Birds page

- `h1` "Nesting birds". Intro: "Nesting status and months for every crag Grip covers. Entries come from published crag information and climbers' reports, and most months are placeholders until someone confirms them. If you know better, send a crag note." Meta line with "In season now: …".
- **Caution notice** directly under the intro, never collapsed: `role="note"`, card bg, 2px ink border, radius 10, padding 12/14, 24px ink "!" disc, 16px 600: "Not a definitive record. Check local guidance and look before you climb in the nesting season."
- Controls: search (as §8) and status filter chips (`aria-pressed`) with counts: All, Restricted, Nesting birds, Bird free, No information.
- Legend: nest month, clear month, this month, and the No information tag with "Unknown. Not the same as bird free."
- Sections by stretch, each a card. Row (flex-wrap): crag + wall, status tag, 12-month bar, note, Confirmed.
- **Status tags**, ink only, different in shape as well as fill: Restricted = `--inv-bg` fill; Nesting birds = 1.5px ink outline; Bird free = `--sunk` fill, 1px rule outline; No information = 1px dashed outline with a "?" prefix on a `--sunk` row, text always "Grip does not know whether birds nest at …". No information is never lighter than, or styled like, Bird free.
- **Confirmed** is its own 132px column: overline "Confirmed", value "Yes" (filled ink tick disc) or "No" (outlined "?" disc), 15px 600. On phones it wraps under the note with its label.
- Notes carry no source tags. The repeated stock note reads "Birds reported nesting; months not confirmed."
- Month bar: 12 squares 14px, gap 2, radius 2; nesting months ink; others 1px rule outline; current month 3px inset ink underline; initials row 10px display muted; `aria-label` "Nesting April to July".
- **(B)** No-information crags summarised in one row per section with "Show them"; the No information chip expands them as rows.
- Foot: "Sources: the SMC routes database, UKClimbing and climbers' reports, reworded by Grip." 13px muted.
- Empty filter: "No crags match. Clear the search or pick All."

## 18. Method page (How Grip works)

- Moves from home **(B)**: method in plain words, scoring factors table, full calibration (summary, by model, every logged day).
- Foot: data credits (Open-Meteo, Met Office) and one line: "Grip is independent and not affiliated with the SMC or UKClimbing."


---

# Appendix B: grip-tokens.css

```css
/* Grip design tokens. Drop into the generated site's main stylesheet. */
:root {
  color-scheme: light dark;

  /* Surface and ink (light) */
  --paper: #eef1f2;      /* page and header background. Header MUST be exactly this (logo nails). */
  --card: #f8fafa;       /* cards, tables, inputs */
  --sunk: #e4e9eb;       /* inset panels inside cards, selected rows */
  --ink: #1d2b34;        /* text, primary buttons, focus ring, selected states */
  --muted: #5b6b75;      /* secondary text: 5.0:1 on paper, 5.3:1 on card */
  --rule: #c9d1d5;       /* hairlines, input borders, unselected outlines */
  --past: #dbe1e4;       /* blocks for hours already gone */
  --past-ink: #4f5e67;   /* numbers on past blocks: 5.0:1 */
  --inv-bg: var(--ink);  /* primary button, selected segment, Restricted tag */
  --inv-fg: var(--paper);
  --scrim: rgb(20 29 35 / .5);
  --shadow-overlay: 0 2px 4px rgb(29 43 52 / .08), 0 12px 32px rgb(29 43 52 / .16);

  /* Data: the five bands. Nothing else on the site may use these colours. */
  --soaked: #b3261e;    --on-soaked: #ffffff;   /* 0 to 1 */
  --greasy: #ee8a3a;    --on-greasy: #1d2b34;   /* 2 to 3 */
  --climbable: #f2cd4f; --on-climbable: #1d2b34;/* 4 to 5 */
  --grippy: #8fc66b;    --on-grippy: #1d2b34;   /* 6 to 7 */
  --prime: #2e8b3e;     --on-prime: #ffffff;    /* 8 to 10 */
  /* Model-disagreement stripes, laid over the band colour */
  --stripe-on-dark-text: repeating-linear-gradient(135deg, rgb(255 255 255 / .45) 0 4px, transparent 4px 10px);
  --stripe-on-light-text: repeating-linear-gradient(135deg, rgb(0 0 0 / .22) 0 4px, transparent 4px 10px);

  /* Brand: logo only. Never in data, never next to the band scale. */
  --brand-thrift: #c2457e;
  --brand-sea: #2a9d8f;

  /* Type */
  --font-body: "Barlow", system-ui, sans-serif;            /* 400, 500, 600 */
  --font-display: "Barlow Condensed", "Barlow", sans-serif; /* 500, 600: headings, labels, scores */
  --t-micro: 0.75rem;   /* 12  hour labels, axis ticks */
  --t-small: 0.8125rem; /* 13  key, footnotes, captions, overlines */
  --t-meta: 0.875rem;   /* 14  meta lines, hints, table body */
  --t-body: 1rem;       /* 16  body, inputs (never below 16 in inputs: stops iOS zoom) */
  --t-lead: 1.0625rem;  /* 17  plain-words strip lines, nav */
  --t-h3: 1.25rem;      /* 20  card headings (display) */
  --t-h2: 1.5rem;       /* 24  section headings (display) */
  --t-wall: 1.75rem;    /* 28  wall name on crag page (display) */
  --t-h1: 2.25rem;      /* 36  page title; 40 on crag pages at >= 900px */
  --lh-tight: 1.1;
  --lh-body: 1.45;
  --overline-tracking: 0.06em; /* uppercase display labels */

  /* Score blocks: block size / number size */
  --score-xl: 56px;  --score-xl-num: 2.125rem; /* 34  summary cards, pop-up */
  --score-l: 44px;   --score-l-num: 1.3125rem; /* 21  grid cells, tap targets */
  --score-m: 36px;   --score-m-num: 1.1875rem; /* 19  strips, wall list, hour table */
  --score-s: 28px;   --score-s-num: 1rem;      /* 16  pop-up walls, log summary */
  --score-xs: 24px;  --score-xs-num: 0.875rem; /* 14  model values in hour table */

  /* Spacing (4px base, plus 2 and 6 for tight data) */
  --s-2: 2px; --s-3: 3px; --s-4: 4px; --s-6: 6px; --s-8: 8px; --s-12: 12px;
  --s-16: 16px; --s-20: 20px; --s-24: 24px; --s-32: 32px; --s-48: 48px;
  --page-pad: 16px;          /* 12px header side padding at <= 400px */
  --page-max: 1200px;

  /* Radii */
  --r-xs: 4px;   /* coast blocks, small score blocks, checkboxes */
  --r-s: 6px;    /* score blocks 36 to 44 */
  --r-m: 8px;    /* buttons, inputs, 56 blocks, segmented control */
  --r-l: 10px;   /* cards, table boxes */
  --r-xl: 16px;  /* bottom sheet top corners */
  --r-pill: 999px;

  /* Borders and focus */
  --bw: 1px;
  --bw-strong: 2px;  /* How sure card, selected tile, focused input */
  --focus-ring: 0 0 0 2px var(--paper), 0 0 0 4px var(--ink);
  --now-ring: 0 0 0 2px var(--card), 0 0 0 4px var(--ink); /* current hour, selected cell */

  --tap: 44px; /* minimum target */
}

@media (prefers-color-scheme: dark) {
  :root {
    --paper: #141d23;    /* header MUST be exactly this in dark */
    --card: #1b262d;
    --sunk: #10181d;
    --ink: #e3e8ea;
    --muted: #93a3ad;    /* 7.1:1 on paper */
    --rule: #2c3a43;
    --past: #26333c;
    --past-ink: #9aa9b2;
    --scrim: rgb(0 0 0 / .6);
    --shadow-overlay: 0 12px 40px rgb(0 0 0 / .55);
    --brand-thrift: #ec8bb6;
    --brand-sea: #7dd3c4;
    /* Bands and their text colours do not change in dark mode. */
  }
}

```
