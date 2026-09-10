# Review 007 — fixture-run

- **Slug:** quorum-audit
- **Verdict:** findings
- **Covers:** the acceptance criteria no lens could reach — AC1, AC2, AC3, AC4,
  AC6, AC7, AC8, AC9, AC11

> **This is not a review lens.** It is a record of `/quorum:audit`'s procedure
> being operated by hand against the committed fixture, and of the result being
> compared against the answer key at `docs/fixtures/README.md`. It is filed here
> because `reviews/` is this work item's append-only evidence record and the
> judge reads it. It alters no earlier review.

## Why it was done by hand

Verdict E5 recommended running the `behavior` lens against the fixture. Two
things prevent that, and both are worth stating rather than leaving as a silent
substitution:

1. The lens did not fail to be scheduled — it was **blocked by a safety
   classifier at runtime** (`[review:behavior] blocked by safety classifier`).
   The verdict inferred it had been "dropped from the panel before this run" from
   a `state.json` log line that refers to something else entirely: the *audit
   skill's* behaviour pass, cut from the design earlier. Re-running the pipeline
   does not fix a classifier block.
2. `/quorum:audit` and `quorum:quorum-auditor` exist only in this working tree.
   The session's installed plugin is 0.22.0, and a running session loads plugins
   at startup, so neither the skill nor the agent resolves. A real end-to-end run
   needs the local plugin installed and a restart.

So this is verdict E5's option (c) — operate the command manually and record the
result as evidence — taken because (a) is unavailable.

## What it does not cover

**`workflow/audit.js` was never executed.** Its cluster deduplication, the
unclustered sweep, the gap-without-searches downgrade, and the `proposedChange`
fallback are unexercised by this run. What was exercised is the criteria
derivation, the report discipline, the hash chain, and the run-level properties.

A real run remains outstanding, and no criterion below should be read as
verified through the workflow.

## Method

`docs/fixtures/audit-demo/` copied to a scratch directory **outside this
repository**, per `docs/fixtures/README.md`, so the answer key was not in the
tree being audited. Fresh git repo, one commit. Nothing in the fixture was
executed: no `npm test`, no `node src/server.js`. Criteria derived from
`spec.md` alone before any source was read.

## Result — 15 of 15 answer-key checks passed

| Answer-key expectation | Observed |
|---|---|
| auth criterion `met` | met — `src/server.js:18-19`, tests cited |
| request-id criterion `met` | met — `src/server.js:16`, tests cited |
| retry criterion `gap` | gap — searches named, `src/upstream.js` read in full |
| `/health` latency `unverified` | unverified, framed as a runtime property |
| rate limiter absent from report | absent |
| `/metrics` absent from report | absent |
| gap names the empty searches | named, with patterns and paths |
| gap phrased as an acceptance criterion | *Proposed change* present |
| closing `/quorum:1-plan` invocation | present |
| all criteria present, one status each | 5 of 5 |
| no branch created or switched | none |
| no commit made | none |
| only `docs/audit/` changed | true |
| `audit.py --verify --expect-report` clean | exit 0 |
| criteria hash matches | `89948dd0…` in both files |

## Findings

### F1 — `git status --porcelain` cannot prove AC1 in the ordinary case [major]

- **Where:** `plugins/quorum/skills/audit/SKILL.md`, Step 6
- **What:** The skill's own verification of AC1 ran `git status --porcelain`.
  Git collapses a wholly-untracked directory to its top level, so a target that
  had no `docs/` reports exactly `?? docs/` — not the files under it.
- **Failure scenario:** An audit target is by definition a repository that never
  used this pipeline, so it usually has no `docs/`. A clean run there prints
  `?? docs/`, which is indistinguishable from a stray write into `docs/` and
  names none of the files actually created. The check that exists to prove AC1
  returns a string that cannot prove it, in the majority case. Observed directly:
  the audited fixture reported `?? docs/` under `--porcelain` and
  `?? docs/audit/widget-api/criteria.md` plus `?? .../report.md` under `-uall`.
- **Disposition:** Fixed. `-uall` is now specified in `SKILL.md` Step 6, in the
  promise bullet above it, in `reference/audit.md`, in the answer key, and in
  AC1 itself. Re-checked against the fixture: 15/15.

This is the only defect the exercise found, and it was invisible to five lenses
reading the code — it only appears when the command is operated against a
repository shaped like a real target.
