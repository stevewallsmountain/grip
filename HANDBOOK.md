# Grip handbook

Grip is a dry-rock forecast for the sea cliffs of north-east Scotland, Girdle Ness to Portknockie. It scores every wall on a 0 to 10 index, hour by hour for seven days, from free weather and marine forecasts, and checks itself against days that climbers log. Steve Walls runs it; this file is the state of the project, written so a fresh conversation can pick it up in one read. Update it whenever the model version or the procedures change.

## Where everything lives

- Live page: https://stevewallsmountain.github.io/grip/ with a conditions page per crag under `detail/`, the bird register at `birds.html` and the log form at `log.html`.
- Crag pages (`detail/`, conditions only, no route or approach details): per wall the Today strip and plain-words line (the front page's own), why (factors worth 2 points or more), aspect and sun-on-face hours, tide, shelter, seepage, birds, weather point, recent rain and water on the rock, the sea against the face, the next seven days; then hours where the models differ by 3 or more, the hour-by-hour table, the days logged there, and a link to the crag's SMC routes database page.
- Front page order: Coast today panel (Coast tomorrow once today's daylight is over), crag search, Today and Tomorrow lists, seven-day grid; the band scale and the log button sit between the search and the lists.
- Tests: `tests/test_today.py` checks the plain-words line in the crag search and the Coast panel's median; `tests/test_detail.py` checks the crag pages' why sentences, sun-on-face hours, swell wording and water-on-rock words. Standard library only; run `python3 tests/test_today.py` and `python3 tests/test_detail.py` (on 3.11 and 3.12).
- Public repository: https://github.com/stevewallsmountain/grip. `grip.py` (the whole model and page, Python 3.12, standard library only), `crags.json` (generated, do not hand edit), `data/smc_coast.json` (structured facts from the SMC routes database), `data/overrides.json` (local corrections by wall label), `data/form_crags.json` (the Google Form's crag options in order, for the page log form), `tools/build_crags.py` (builds `crags.json` from the two data files), `calibration.json` and `calibration.csv` (scored logs), `.github/workflows/update.yml` (runs hourly at 17 past, builds the crag list, scores, deploys; checks out the latest main; the save step rebases and retries once if main has moved, and skips saving with a warning rather than blocking the deploy).
- `CLAUDE.md`: instructions for Claude Code sessions; points to this handbook and sets the change sequence.
- Private repository: https://github.com/stevewallsmountain/grip-private. Full scraped text: `smc_coast_full.json` (473 records, 2,627 routes) and `ukc_coast_full.json` (254 crags), and `evidence.json` (the SMC snippets behind each derived flag in `data/smc_coast.json`, by record id). Working data only, not published, SMC and UKC copyright.
- Log form: https://docs.google.com/forms/d/e/1FAIpQLSems6Y-X4CypSu96Vt8DuGh4yH1bWv05wjYPxsN8fnhKPMWBA/viewform. Entry IDs: crag 769015387, wall 1131909785, date 2085482145, from 764556216, until 1083400377, feel 1126435114, problems 525175392, initials 1772081994, anything else 960162223, follow-up contact 1160807926. The page log form submits into the Google Form by entry ID; if the form's questions or crag options change, update data/form_crags.json and the page form in the same change. Responses spreadsheet 12G-V5UOe7wDu5niXQrvsE3SEEY0z1c1QxYRTLl_E89c: raw tab is private (has the contact column), the `Public` tab mirrors columns A to J and is what the build reads, the `Log notes` tab is the analysis record (one row per logged day: follow-up detail, what it told us, what changed).
- Crag notes form: https://docs.google.com/forms/d/e/1FAIpQLSeFKYLfOJ5V7yZiKIyMd9RxH9yiBWbQ27h_CLWvUP52EbOWPg/viewform. Entry IDs: crag 1230562053, wall 763167181. Responses spreadsheet 171ELMVi8Y4tvfLVS7r5luaRnNVSU8fOF9Zj6zypIRXE.
- Calibration tracker (Steve's private sheet, imports calibration.csv): 1ccLcrGu4ZGQ_XVjk0Lx6vpKC0IcqJC3PZ87zHKGrJUg.
- Data: Open-Meteo. Met Office UKV 2 km (`ukmo_seamless`), ECMWF (`ecmwf_ifs025`), ICON (`icon_seamless`), marine API for waves, sea temperature and sea level, ERA5 archive for back-scoring finished days.

## The model, version 3.7

Each wall, each hour: points from the factors below are summed; index = 3 + points/2, held to 0 to 10. A day's score is its best three consecutive daylight hours (sun 5 degrees up or more). Bands: 0 to 1 Soaked, 2 to 3 Greasy, 4 to 5 Usable, 6 to 7 Crisp, 8 to 10 Prime. Three models are scored separately and blended: Met Office 2.5 (1 beyond 48 h), ECMWF 1, ICON 1.

| Factor | Points | Notes |
|---|---|---|
| Air moisture | +1 per 4% below 76% humidity, cap +4 at 60%; -1 per 5% above, floor -4; extra -1 at 75% and above (salt). Penalties scaled by the dew-point margin: full within 2 C, half at 4 C or more | Humid air greases rock through condensation |
| Dry rock | up to +2 when film is 0, no rain, no haar, rock 3 C or more above the dew point; full at 76% humidity and above, nothing at 60% | Dry rock on a grey day is good rock; tapered so it does not stack on dry-air days |
| Haar | fog on the 2 km model or visibility under 1 km -4; patchy or under 4 km -2. Also adds 0.1 mm/h (0.05 patchy) to the film | |
| Rock against dew point | margin at or below 0: -4, 1 C: -3, 2 C: -2, 3 C: -1, 5 C or more: +1 | Rock temperature = 0.4 T now + 0.6 T mean 24 h, pulled 30% towards the sea temperature (60% at tidal walls), +3 C sun on face (+2 low sun, +0.5 sunny off face), -1.5 C clear calm with sun under 15 degrees |
| Wind direction | -cos(angle between wind and coast-facing) scaled by speed (full at 15 km/h) | Coast faces 112.5 (ESE) on the Aberdeenshire coast, 0 (N) at Banff and Moray |
| Wind strength | under 5 km/h -1 (waived when rock dry and air under 80%), 5 to 15 +1, 15 to 35 +2, over 35 +1; onshore over 25 km/h -1, over 40 -2. Speed halved at sheltered walls (bay-back walls only when the wind is not onto the face; inlets always). Positive points halved while the rock is wet | Shelter does not slow drying |
| Sun | cloud 0, sun +1, on face +3 (+2 under 10 degrees). "On face" = within 60 degrees of aspect. Halved while the rock is wet | |
| Sea state | effective height: 5 ft+ -2, 2.5 to 5 -1, 1 to 2.5 0, under 1 +1. Waves from behind or along the face count 40% (70% if period 9 s+). Inlet walls count 1.5 times from any direction; sea-sheltered walls count half | |
| Water on the rock | raining -5; film over 0.5 mm -3, over 0.1 -2, trace -1. Film gets rain, haar, spray (sea over 2.5 m, 2 m tidal, at 0.05 mm/h), brine at 85%+ humidity up to 0.15 mm; dries at (0.05 + 0.01 wind) x VPD plus sun | The model's memory, tracked from three days back |
| Seepage | 5 mm+ rain in 24 h -2, 10 mm+ -3, further -1 for 25 mm+ in 72 h, cap -4 | Same for every crag; per-crag rule still to do |

Logged-day matching: a bare crag name maps to the crag's first listed wall, old names via `LABEL_ALIASES`, typed wall names by word overlap, and `LOG_PINS` fixes individual logs to a wall when the logger has confirmed it. Several logs of one crag on one day merge into one data point. Misses are measured from the band edge, not the centre.

Past days come from the forecast API, falling back per model to the historical-forecast API when it has no data (it keeps about 60 days), and from the archive outright beyond 80 days; unscored logs are retried up to three times.

## Crag list

165 crags, 289 walls, 16 SMC coastal sections, rebuilt on every run from `data/smc_coast.json` plus `data/overrides.json`. A crag is the first SMC node below a section with coordinates; its leaves are the walls. Fields per wall: name, wall, section, zone (one of nine weather points), aspect, rock, tidal, sheltered, inlet, sea_sheltered, seeps, birds {months, level, note, confirmed}, lat, lon, smc_id. Flags came from keyword matching on the SMC text, checked against UKC and the developers' own topos from the North East Outcrops Facebook group, and corrected in the overrides file; every override says where it came from. To change a crag fact, add or edit a line in `data/overrides.json` keyed by the wall label exactly as it appears on the page, and commit. Never hand edit `crags.json`. Public files hold facts and Grip's own wording only. Verbatim SMC or UKC text, including evidence snippets, stays in grip-private.

## Routines

Log review (whenever logs arrive):
1. The build scores new logs within the hour, five per run, from the three archived forecasts and from ERA5 (`Actual weather` column). The page's calibration table and `calibration.csv` show them.
2. Compare the felt band with the score, per model and against the actual weather. If the actual-weather column is also wrong, it is the scoring; if only the forecasts are, it is the blend.
3. Ask the logger what the rock was like: wet to look at or slick, worse near the sea, how the wind felt on the wall, change through the session. Remember that some people log the worst route, not the day.
4. Record the day in the `Log notes` tab: detail, what it told us, what changed. Pin the log to the right wall if needed (`LOG_PINS`).
5. Change the model only when more than one day points the same way, and never from a single log.

Remembered days: a day logged more than 30 days after it happened is a remembered day. Mark it '(remembered)' after the crag and wall in its Log notes row. It counts in the tally like any other day, but on its own it cannot count towards the two-day trigger for a scoring change: it counts only alongside at least one day logged within 30 days, missing the same way for the same physical reason. Days before mid-2024 score on the Met Office and ICON only, since the archive has no ECMWF before then; note that in the row as well.

Scoring change:
1. Reproduce the day locally with the hourly data (the hour-by-hour page shows the breakdown), test the change on every day with data, check the forecast grid does not go flat or run away.
2. Bump `MODEL_VERSION` so all logged days re-score, update the "How Grip works" table on the page, commit and merge as under Changing the repository below, run the workflow on `main` three times to re-score all logs, re-check correlation, write the row in `Log notes`.

Changing the repository: every change is made in Claude Code from a clone, following `CLAUDE.md`. Log reviews and the Google Sheets stay in a separate Claude chat, and Steve carries change briefs from there to Claude Code and the reports back.
1. Pull the latest `main` and edit on a branch. Nothing is pushed to `main` directly.
2. Test offline: build the crag list, then `GRIP_FAKE=1 python grip.py`, and revert any generated files the run changed. This proves the page builds, nothing more: it uses synthetic weather and skips real calibration and back-scoring.
3. Run the targeted test named in the brief for the behaviour being changed (for example, recomputing the calibration summary from the committed `calibration.json`, or a live Open-Meteo request for a past date).
4. Show Steve the diff and the targeted test's results. Nothing is committed without Steve's confirmation.
5. Commit, push the branch and open a PR whose summary says what changed, why, whether it touches scoring, and what result to check. Steve squash merges it.
6. After the merge, start the workflow on `main` and read its job log with the session's GitHub access (connector tools in a cloud session, `gh` on a clone), then check the page or `calibration.csv` for the expected result.
7. Report item by item what changed, with the merge commit hash, for the Grip chat.

Never run the workflow on any branch other than `main`: the page deploys from whichever branch it runs on. Testing on a branch is offline only, with `GRIP_FAKE=1`. The workflow runs Python 3.12 and a Claude Code session may run 3.11, so code must run on both, without 3.12-only syntax, and is tested on 3.12 where it is available.

Fallback when Claude Code is unavailable: the Grip chat edits through GitHub's web editor in Claude in Chrome (line edits checked by SHA-1 before and after), commits to a new branch with a PR using the commit dialog's pull request option, and Steve merges as usual. The same confirmation and testing rules apply, with the targeted test run in the chat's sandbox.

Google Forms and Sheets are edited through their normal pages. Facebook group files need a real click to download.

## Calibration procedure

1. Evidence. A log becomes a data point once it is pinned to the right wall and, where the logger scored the worst route rather than the day, the crag-overall reading is noted alongside it in Log notes. Both readings are kept; neither is deleted.
2. Metrics, recorded in a review row in Log notes at every review: days in band, days within a point, mean error (the sign shows bias), mean absolute miss, correlation against the logged bands and against the crag-overall readings, per-model in-band counts, and the grid shape for the next three days (share of cells at 8 or above, any flat day).
3. Diagnosis before change. For each miss, the actual-weather (ERA5) column separates the two causes: if ERA5 is also wrong it is the scoring; if only the forecasts are, it is the blend. Reproduce the day locally and name the factor responsible before touching anything.
4. Trigger for a scoring change: at least two days, from different crags or dates, missing in the same direction for the same stated physical reason. One day gets a note and a question to the logger, nothing more. A change must have a mechanism, not just a weight that fits. Remembered days count towards the trigger only as set out under Log review.
5. The smallest change that explains the misses, tested on every day we hold data for before it is committed. Regression rule: no day currently in band may leave it; if one does, the change is wrong or incomplete.
6. Overfitting guard. Under thirty logs: structural fixes with a physical story only, one scoring change per review, the grid check after every change. Over thirty: hold back every fourth log by date as a validation set and report fit and holdout separately.
7. Blend weights are adjusted on per-model in-band counts only, with at least ten scored days.
8. Cadence: review when three or more new logs are in, or fortnightly, whichever comes first. Seasonal checkpoints in November, February and May, when the dew-point and seepage mechanics get their real tests.
9. Record. Every change: version bump, the "How Grip works" table on the page, a Log notes review row, this handbook. Every reviewed day: a Log notes row.

## Where calibration stands, 4 October 2026

Twelve logged days from three people, all now scored by the build. In band and within a point count the score as shown on the page; typical miss and average error use the unrounded score. In band 6 of 12, within a point 10 of 12, typical miss 0.8, average error 0.1 above the felt band; correlation with the logged bands r = 0.47, with crag-overall readings about 0.55. In band by model: Met Office 6 of 12, ECMWF 5, ICON 5, actual weather 5; typical miss 0.8 for the Met Office against 1.0 for ECMWF and ICON. The Met Office lead is narrow on this count, so the 2.5/1/1 weights are due a fresh look at the next review.

Known misses with no mechanism yet: Brown Band Crag on a calm, grey, humid morning (felt Crisp, model Usable); Souter Head south wall in July, warm air over a cold sea in an inlet (felt Greasy, model Crisp, ERA5 also Crisp).

Open questions, in the order evidence is likely to arrive: how long inlets hold water; whether the Embankment at Logie Head should keep its sheltered flag; the per-crag seepage rule (Brown Crag, Crazy Band Cliff until May, The Fin, Little O Wall are the candidates); the rock-temperature factor in spring; bird months for the many crags still on the April to July placeholder.

## Credits and sources

Forecasts from Open-Meteo (CC BY 4.0) including Met Office data (CC BY-SA 4.0). Crag details from the SMC routes database and UKC, with local corrections. The original idea was a friend's hand-scored "NERD" table, which still runs as the baseline for comparison in the calibration data.
