# Grip design spec

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

- Per day: overline label "Today, Mon 5" and the plain line (17px 600) "Grippy now. Best 16:00 to 18:00." on one wrapping row. When every daylight hour of the day is Climbable or better (and none has passed), the line reads "Climbable all day." in place of "Climbable from 09:00.", then the best window as usual.
- Blocks: flex 1, 36px tall, radius 5, number 19px; hour label under each, 12px display muted.
- States as the coast panel: past, current ring, stripes, dot, not scored. **After dark:** the Today strip is all past and its line reads "Over for today. Best was 16:00 to 18:00."

## 12. Crag page sections

Layout ≥ 900px: left column (basis 320px) = Walls, How sure, Across the crag; right column (basis 560px) = wall cards, hour by hour, logged days, source. Below 900px the same order stacks, so the walls overview and How sure come before any wall detail.

- **Title block:** breadcrumb "Forecast / {stretch}" (14px), `h1` 36 to 40px display, meta line "9 walls · Weather from the Cullen and Portsoy point · Updated …", actions: "Log a day here" (primary), "Send a crag note" (secondary).
- **Walls (B8):** card with a 3-column grid (name+sub, Today, Tmrw). Rows are links to the wall card, 44px min. Current wall: `aria-current`, `--sunk` bg, 3px inset ink left rule. Single-wall crags omit this card.
- **How sure (B10):** 2px ink border, radius 10. Heading 20px. One to three sentences naming which model differs, when, and whether it touches the best window. On multi-wall crags the sentences go under a day overline ("Today", "Tomorrow"), and a sentence shared by several walls is said once, led by the walls it is true of: "Embankment One, Embankment Two and 7 more: …" (up to three walls named in full, beyond that two and a count). Empty state: "Today and tomorrow the three models agree on every wall, within 2 points."
- **Across the crag (B9):** `dl` of Rock now, Low water, Sea, Weather. Footnote naming the source model and time. The Sea line ends with the day's highest sea: "Up to 1.2 m today."; after dark, when the page leads with tomorrow, it is tomorrow's, with the day named: "Up to 1.0 m on Tuesday."
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

- `h1` "Nesting birds". Intro: "Nesting status and months for every crag Grip covers. Entries come from published crag information and climbers' reports, and most months are placeholders until someone confirms them. If you know better, send a crag note."
- **Caution notice** directly under the intro, never collapsed: `role="note"`, card bg, 2px ink border, radius 10, padding 12/14, 24px ink "!" disc, 16px 600: "Not a definitive record. Check local guidance and look before you climb in the nesting season."
- Meta line, 14px muted: "Updated Mon 5 Oct, 16:51 · In season now: …". In season (the current month is in some entry's months): the crags whose confirmed months include the current month, counted and named (at most five, then "and N more"), and how many more crags have birds reported with the months not confirmed: "In season now: 4 crags with confirmed months (A, B, C and D); 23 more have birds reported but months not confirmed." With none confirmed: "In season now: no crag with confirmed months; 58 crags have birds reported but months not confirmed." Outside every entry's months: "In season now: none. The season here runs roughly March to August." (the span of all the entries' months).
- Controls (shown by script; hidden without it): search (as §8, the shared matching code) and status filter chips (`aria-pressed`, 44px, pill, rule border; pressed `--inv-bg`) with counts of rows: All, Restricted, Nesting birds, Bird free, No information. Live line under them, `role="status"`: "165 crags in 16 stretches"; "3 crags match “logie”"; "10 crags shown" for a chip alone.
- Legend: nesting month confirmed (solid), nesting month not confirmed (hatched), clear, this month, and the No information tag with "Unknown. Not the same as bird free."
- Sections by stretch, each one card (`h2` 15px display caps muted). Row (flex-wrap, so nothing goes off-screen): crag + walls (the walls named when the crag has more than one row; links to the crag page and wall), status tag, 12-month bar, note, Confirmed. Phones: name and tag on the first line, then the bar on its own line, the note, and Confirmed with its label. From 600px: name up to 280px, tag 118px, bar, note, Confirmed 132px.
- **Status tags**, ink only, different in shape as well as fill: Restricted = `--inv-bg` fill; Nesting birds = 1.5px ink outline; Bird free = `--sunk` fill, 1px rule outline; No information = 1px dashed outline with a "?" prefix on a `--sunk` row, text always "Grip does not know whether birds nest at …". No information is never lighter than, or styled like, Bird free.
- **Confirmed** is its own 132px column: overline "Confirmed", value "Yes" (filled ink tick disc) or "No" (outlined "?" disc), 15px 600. On phones it wraps under the note with its label.
- Notes carry no source tags. The repeated stock note reads "Birds reported nesting; months not confirmed."
- Month bar: 12 squares 14px, gap 2, radius 2; confirmed nesting months solid ink, placeholder months hatched; others 1px rule outline; current month 3px inset ink underline; initials row 10px display muted; `aria-label` "Nesting April to July, months not confirmed".
- **No information folded:** each stretch's No information crags sit after its other rows, summarised in one `--sunk` row: the tag, "16 crags. Grip does not know whether birds nest at A, B, C and 13 others." (all named when there are four or fewer, joined with "or"), and a 44px "Show them" text button (`aria-expanded`) that lists them as rows and turns to "Hide them". The No information chip, and any search, list them as rows. Without script every row is listed and the summary row is not shown.
- Empty filter: "No crags match. Clear the search or pick All." with a Clear button that empties the search and picks All.
- Foot: "Sources: the SMC routes database, UKClimbing and climbers' reports, reworded by Grip." 13px muted.

## 18. Method page (How Grip works)

- Moves from home **(B)**: method in plain words, scoring factors table, full calibration (summary, by model, every logged day).
- Foot: data credits (Open-Meteo, Met Office) and one line: "Grip is independent and not affiliated with the SMC or UKClimbing."
