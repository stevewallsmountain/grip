# Instructions for Claude sessions

Read `HANDBOOK.md` in full before doing anything else. It is the current state of the project, and its procedures take precedence over anything here except where this file is stricter.

Log reviews and the Google Sheets are handled in a separate Claude chat. Steve carries change briefs from there to this repository and carries the reports back.

## Approval

- No change to the scoring model without at least two logged days pointing the same way for the same physical reason, and Steve's explicit confirmation. If a brief asks for a scoring change and does not say the trigger has been met, stop and ask.
- Every other change (reporting, data fetching, wording) also needs Steve's confirmation before it is committed.
- Follow the handbook's change rules: bump `MODEL_VERSION` for scoring changes, update the "How Grip works" table on the page, and never hand edit generated files (`crags.json`, `state.json`, `calibration.json`, `calibration.csv`).

## Sequence for every change

1. Pull the latest `main` and work on the session's branch. Never push to `main`.
2. Edit on the branch.
3. Test offline: `python tools/build_crags.py data/smc_coast.json data/overrides.json crags.json`, then `GRIP_FAKE=1 python grip.py`. Afterwards revert any generated files the run changed and delete `site/`.
4. Run the targeted test named in the brief (see Testing).
5. Show Steve the diff and the targeted test's results.
6. Once Steve confirms, commit, push the branch and open a PR. The summary says what changed, why, whether it touches scoring, and what result to check after the run. It asks Steve to squash merge.
7. After Steve merges, start the workflow on `main` and read its job log, using the session's GitHub access (connector tools in a cloud session, `gh` on a clone). Then check the page or `calibration.csv` for the expected result.
8. Report item by item exactly what changed, with the merge commit hash, for Steve to paste into the Grip chat.

## Workflow runs

Never run the workflow on any branch other than `main`: the page deploys from whichever branch it runs on. Testing on a branch is offline only, with `GRIP_FAKE=1`.

## Testing

- A `GRIP_FAKE=1` run proves the page builds, nothing more. It uses synthetic weather and skips real calibration and back-scoring.
- Every change also needs a targeted test of the behaviour it changes, named in the brief: for example, recomputing the calibration summary from the committed `calibration.json`, or a live Open-Meteo request for a past date. Show its results with the diff before opening the PR.
- This environment may run Python 3.11; the workflow runs 3.12. Write code that runs on both and avoid 3.12-only syntax. Test on 3.12 where it is available (`python3.12`) as well as the default interpreter.

## Design

- Changes to what people see follow the handbook's Design rules and the spec and tokens in `docs/design/`.
- If a brief references the Claude Design project, check you can read it before writing any code. If you can't, stop and ask Steve to run /design-consent.
- Read the Design project for reference only. Never copy Design project files into the repository; `docs/design/` changes only when a brief asks for it.

## Writing

British English, no em dashes, in code, comments, the page, commit messages and reports.
