# Log a day, v2: components and rules

Change to the flow of `log.html`. Look, tokens and field parts are unchanged (see `spec/Grip Design Spec.md` §14 and `spec/grip-tokens.css`). Mock-ups: `Grip Log v2 Review.dc.html`.

## Rule: independent judgement

- Grip's forecast for the chosen wall and hours is **not in the page** until a band is chosen **and all seven observations are answered** (Not sure counts). The script then fetches it from the static per-crag JSON. Do not embed or pre-fetch it.
- Without JavaScript the form is replaced by the Google Form link (which has no forecast).

## Flow

1. Crag and wall (hint: "Type the start of any word in the name, then pick from the list."), Date, From, Until.
2. Feel tiles. Hint: "Most of the rock, across your session. Grip's forecast appears once you have answered this and what you saw."
3. What did you see? (new, every log).
4. Grip's view panel.
5. Birds question.
6. Anything else, Initials, Contact, Send, Google Form link. ("Anything else that made it worse?" is removed; see below.)

## New and changed components

### What did you see?
- `section` with `h2` "What did you see?" (16px 600, same as field labels) and a live counter on the right, 14px muted: "5 of 7". Hint, 14px muted: "One tap each, across your session. Not sure is fine."
- Seven rows, each `role="radiogroup"` with `aria-label`. Row: flex-wrap, gap 4/12. Label (15px 600) basis 190px; chip row basis 330px. On a phone the label sits above its chips; at 1280 they sit side by side.
- Chips: one row per question, `flex: 1 1 0` (the long "Most of the session" gets 1.8), min-height 44px, radius 8, 14px 500, text centred and allowed to wrap to two lines. Default: card bg, 1px rule. Selected: `--inv-bg`, 600. **Not sure** is always last: 1px dashed rule, muted text; selected like any other.
- Questions and options (fixed order):
  - Water on the rock: Wet patches / Damp / Dry / Not sure
  - Seepage: Yes / No / Not sure
  - Rock sweating or greasy to the touch: Yes / No / Not sure
  - Haar or fog: Yes / No / Not sure
  - Wind on the wall: None / Light / Strong / Not sure
  - Sun on the face: Most of the session / Some / None / Not sure
  - Spray reaching the routes: Yes / No / Not sure
- Height on a 375 phone: about 560px including the heading, so the whole step fits on one screen once scrolled to. No scrolling inside the step.
- Answers can be changed at any time, including after Grip's view appears; the table recomputes. Changes after reveal are recorded per factor (`changed_after_view`) but, unlike the band, are not labelled on screen.

### Grip's view placeholder
- Shown until the band and all seven rows are answered. Dashed muted border, radius 10. Overline "Grip's view"; 15px line "Grip's forecast for 11:00 to 15:00 appears here once you have chosen a band and answered what you saw. Your answers come first, so they stay your own."; 14px muted status "Band chosen. 4 of 7 answered." or "No band yet. 0 of 7 answered."

### Grip's view panel
- As before: overline, hour strip, average line, source line ("Grip's forecast as it stood that morning.").
- **Band line**, 20px display 600: "Grip agreed on the band." / "You found it worse than Grip forecast ({Band}, {n})." / "You found it better than Grip forecast ({Band}, {n})."
- **Band block and factor table side by side** (flex-wrap, gap 12). Band block: `--sunk`, radius 8, basis 170px, overline "Band", rows You (range chip) and Grip (score block). On a phone it sits above the table.
- **Factor table**: `table`, 14px. Caption (15px 600): "You and Grip agreed on {s} of {n}." where n excludes Not sure answers; "on all 7." or "on all {n} you answered." when nothing differs. Columns: What / You / Grip / mark (30px, header visually hidden "Match"). Values are the option labels.
  - Same: normal weight; mark "=" in a 24px box, 1px rule, muted.
  - Differs: whole row 600 weight on `--sunk`; mark "≠" in a filled `--inv-bg` box; `aria-label` "Differs".
  - Not sure: mark "–", muted, `aria-label` "Not compared". Never counted as a mismatch.
  - Key under the table, 12px muted: "≠ differs · = same · – not compared".
- **Mismatch lines**, only if any factor differs: a list above the notes box, each with a 20px filled ≠ mark and a plain sentence from the factor's template, e.g. "Seepage: you saw it, Grip expected none." "Wind on the wall: you found it strong, Grip expected light."
- **Notes box** (one only, optional, 72px, paper bg), label:
  - "Why do you think that was?" when the band or any factor differs;
  - "Anything worth noting?" when everything agrees;
  - "Anything that made it better or worse than you expected?" when the day is not scored.
- **Timing question** unchanged (only when Grip's hours range by 2 or more).
- The "What made the difference?" cause tick lists are removed.
- **Not scored yet:** no strip, band line, band block or table; the `--sunk` message "Grip hasn't scored this day yet. It will on its next run, within the hour, and the comparison will appear under Logged days here on the crag page."; then the notes box. Observations are still required before the panel appears.

### Grip's expected value per factor
Taken from Grip's own factor terms for the user's hours (the blend shown on the crag page), not from new thresholds:
- **Water on the rock:** Grip's water-on-rock figure at the wettest hour of the session, in the crag pages' words: "wet" = Wet patches; "damp" or "a trace" = Damp; "dry" = Dry.
- **Seepage:** Yes if the seepage term was active at any hour.
- **Sweating or greasy:** Yes if the dew-point or air-moisture term was negative at any hour.
- **Haar or fog:** Yes if the haar term was active at any hour.
- **Wind on the wall:** Grip's wind at the wall (after shelter) for the majority of hours: None under 8 km/h, Light 8 to 20, Strong over 20.
- **Sun on the face:** Most of the session if two thirds or more of the hours have sun on the face; Some if any; None if none.
- **Spray:** Yes if the sea term was negative at any hour.

### Band changed after Grip's view
Unchanged. Earlier tile dashed with "First answer"; one muted line: "Changed from {Band} after seeing Grip's view. Both answers are kept, and both are useful."

### Birds question
Unchanged.

### Sent card
- Headline: "You and Grip agreed on the band: {Band}." / "You found it worse than Grip, by {one band|n bands}." / "…better…" / "Grip will score this day on its next run."
- **Factor line** (15px, under the headline): the caption plus fragments for each mismatch, joined with "; " and a final "and": "You and Grip agreed on 4 of 6; you saw seepage that Grip did not expect and you found the wind strong where Grip expected light." All agree: "You and Grip agreed on all 7." Not scored: "You answered all 7 questions on what you saw. Grip will compare them with its forecast on its next run."
- Rows: Crag, When, You felt, Grip forecast, Timing (if asked), Birds. The Why row is removed.

### No JavaScript
"This form needs JavaScript." · "It keeps Grip's forecast hidden until you have said how the rock felt and what you saw, and that takes a script. The Google Form asks the same questions, without the forecast." · Open the Google Form.

## Data recorded (additions)
`first_band`, `final_band`, `changed_after_view`, `obs.{water,seep,sweat,haar,wind,sun,spray}` (value or "not_sure"), `obs_changed_after_view[]`, `grip_obs.{…}`, `obs_mismatches[]`, `grip_avg`, `grip_band`, `grip_run`, `comparison` (agree|worse|better|unscored), `notes`, `timing_asked`, `timing_direction`, `timing_answer`, `birds_grip_status`, `birds_answer`.

## Problems list removed
"Anything else that made it worse?" is no longer on the page. The page fills the Google Form's problems column from the observations, so the sheet keeps its existing columns:
- Water on the rock = Wet patches → "Wet from rain"
- Seepage = Yes → "Seepage"
- Rock sweating or greasy = Yes → "Greasy or sweating"
- Haar or fog = Yes → "Haar or fog"
- Spray reaching the routes = Yes → "Spray from the sea"
Not sure and No map to nothing. "Still wet from the night" and "Fine until the sun left" are no longer sent; the observations (water, sun) and the notes box cover them.

## Wording
See the table at the end of `Grip Log v2 Review.dc.html`.
