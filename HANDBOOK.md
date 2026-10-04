# Grip handbook

Grip is a dry-rock forecast for the sea cliffs of north-east Scotland, Girdle Ness to Portknockie. It scores every wall on a 0 to 10 index, hour by hour for seven days, from free weather and marine forecasts, and checks itself against days that climbers log. Steve Walls runs it; this file is the state of the project, written so a fresh conversation can pick it up in one read. Update it whenever the model version or the procedures change.

## Where everything lives

- Live page: https://stevewallsmountain.github.io/grip/ with a hour-by-hour page per crag under `detail/` and the bird register at `birds.html`.
- Public repository: https://github.com/stevewallsmountain/grip. `grip.py` (the whole model and page, Python 3.12, standard library only), `crags.json` (generated, do not hand edit), `data/smc_coast.json` (structured facts from the SMC routes database), `data/overrides.json` (local corrections by wall label), `tools/build_crags.py` (builds `crags.json` from the two data files), `calibration.json` and `calibration.csv` (scored logs), `.github/workflows/update.yml` (runs hourly at 17 past, builds the crag list, scores, deploys).
- Private repository: https://github.com/stevewallsmountain/grip-private. Full scraped text: `smc_coast_full.json` (473 records, 2,627 routes) and `ukc_coast_full.json` (254 crags). Working data only, not published, SMC and UKC copyright.
- Log form: https://docs.google.com/forms/d/e/1FAIpQLSems6Y-X4CypSu96Vt8DuGh4yH1bWv05wjYPxsN8fnhKPMWBA/viewform. Entry IDs: crag 769015387, wall 1131909785, date 2085482145, from 764556216, until 1083400377, feel 1126435114, problems 525175392, initials 1772081994. Responses spreadsheet 12G-V5UOe7wDu5niXQrvsE3SEEY0z1c1QxYRTLl_E89c: raw tab is private (has the contact column), the `Public` tab mirrors columns A to J and is what the build reads, the `Log notes` tab is the analysis record (one row per logged day: follow-up detail, what it told us, what changed).
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

## Crag list

165 crags, 289 walls, 16 SMC coastal sections, rebuilt on every run from `data/smc_coast.json` plus `data/overrides.json`. A crag is the first SMC node below a section with coordinates; its leaves are the walls. Fields per wall: name, wall, section, zone (one of nine weather points), aspect, rock, tidal, sheltered, inlet, sea_sheltered, seeps, birds {months, level, note, confirmed}, lat, lon, smc_id. Flags came from keyword matching on the SMC text, checked against UKC and the developers' own topos from the North East Outcrops Facebook group, and corrected in the overrides file; every override says where it came from. To change a crag fact, add or edit a line in `data/overrides.json` keyed by the wall label exactly as it appears on the page, and commit. Never hand edit `crags.json`.

## Routines

Log review (whenever logs arrive):
1. The build scores new logs within the hour, five per run, from the three archived forecasts and from ERA5 (`Actual weather` column). The page's calibration table and `calibration.csv` show them.
2. Compare the felt band with the score, per model and against the actual weather. If the actual-weather column is also wrong, it is the scoring; if only the forecasts are, it is the blend.
3. Ask the logger what the rock was like: wet to look at or slick, worse near the sea, how the wind felt on the wall, change through the session. Remember that some people log the worst route, not the day.
4. Record the day in the `Log notes` tab: detail, what it told us, what changed. Pin the log to the right wall if needed (`LOG_PINS`).
5. Change the model only when more than one day points the same way, and never from a single log.

Scoring change:
1. Reproduce the day locally with the hourly data (the hour-by-hour page shows the breakdown), test the change on every day with data, check the forecast grid does not go flat or run away.
2. Bump `MODEL_VERSION` so all logged days re-score, update the "How Grip works" table on the page, commit, run the workflow three times to re-score all logs, re-check correlation, write the row in `Log notes`.

Committing from a chat: the Claude in Chrome extension edits files through GitHub's web editor (a script applies line edits to the CodeMirror document, checked by SHA-1 before and after) and runs the workflow from the Actions page. Google Forms and Sheets are edited through their normal pages. Facebook group files need a real click to download.

## Where calibration stands, 4 October 2026

Twelve logged days from three people. In band 6 of 12, within a point 10 of 12. Correlation with the logged bands r = 0.58, with crag-overall readings 0.69; average error 0.1 below the felt band. Met Office in band 6 of 11 against 3 of 11 for ECMWF and ICON, hence its weight.

Known misses with no mechanism yet: Brown Band Crag on a calm, grey, humid morning (felt Crisp, model Usable); Souter Head south wall in July, warm air over a cold sea in an inlet (felt Greasy, model Usable).

Open questions, in the order evidence is likely to arrive: how long inlets hold water; whether the Embankment at Logie Head should keep its sheltered flag; the per-crag seepage rule (Brown Crag, Crazy Band Cliff until May, The Fin, Little O Wall are the candidates); the rock-temperature factor in spring; bird months for the many crags still on the April to July placeholder.

## Credits and sources

Forecasts from Open-Meteo (CC BY 4.0) including Met Office data (CC BY-SA 4.0). Crag details from the SMC routes database and UKC, with local corrections. The original idea was a friend's hand-scored "NERD" table, which still runs as the baseline for comparison in the calibration data.
