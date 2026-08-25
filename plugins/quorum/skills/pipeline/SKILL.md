---
name: pipeline
description: Runs the whole quorum pipeline autonomously from an approved plan - build, five independent review lenses in parallel, then adjudication - stopping only for plan approval at the start. Use when the plan is written and you want the change delivered without further supervision.
disable-model-invocation: true
---

# Run the pipeline

Take an approved plan and deliver the change without further human involvement:
**build → five independent review lenses in parallel → adjudicate → green suite or
an honest red one.**

Plan approval is the only gate. After it, nobody is watching until QA reads
`verdict.md`.

Read `${CLAUDE_PLUGIN_ROOT}/reference/contract.md` for slug and layout rules.

## When to run this

**Per branch, on demand — never per commit.** The unit of work is the whole
branch: the diff is measured from the fork point to `HEAD`, the slug comes from
the branch name, and the acceptance criteria describe a finished change, not an
intermediate state. Run it when the branch is ready for judgment, typically once
before opening a PR.

Running it per commit would review half-finished work against criteria nothing has
met yet, and burn eight agents doing it.

**Never wire this into CI, a git hook, or any automatic trigger.** The judge
writes code. A judge running on every push would commit to the branch
unsupervised, on top of its own previous output, with no approval gate in sight —
and the approval gate is the entire safety model. CI's job is to run the
regression suite (`/quorum:add-ci`); judgment stays on demand.

## Running it more than once on a branch

Normal and supported. Review work is asked for after more work lands, or after a
`blocked` run is unblocked.

- Reviews are **append-only**: a second run writes `006-correctness.md` and so on,
  leaving the first round's record intact. Never renumber or delete earlier
  reviews — a superseded review is still evidence of what was true then.
- The plan's *Status* will read `adjudicated` from the previous run, so the
  approval gate triggers again. That is correct: **every unattended run gets its
  own authorization.** Say plainly that this is a re-run, what changed since the
  last one, and what the previous verdict concluded — do not present the plan as
  though it were new.
- If the previous run ended `blocked`, lead with what blocked it and whether it
  has been addressed.

## Step 1 — Preconditions

1. Resolve the slug per the contract.
2. Confirm `docs/work/<slug>/plan.md` exists. If not, stop: the user runs
   `/quorum:1-plan` first. Never generate a plan here — the approval gate is
   meaningless if the same run wrote what it is approving.
3. Read the plan and check its *Status*.

## Step 2 — The approval gate

This is the **only** point at which the user is consulted. Treat it seriously.

If *Status* is already `approved`, proceed.

Otherwise, show the user the plan's **Intent**, **Acceptance criteria**,
**Non-goals**, and any **Open questions**, then ask plainly whether to proceed.
Make clear what they are authorizing: an unattended run that will write code,
review it, and apply fixes to the working tree with no further checkpoint.

If any *Open question* is unanswered, surface it now. After this point there is
nobody to ask, and the builder will have to guess and record the guess.

On approval, set *Status* to `approved` in `plan.md`, then continue. On anything
short of clear approval, stop.

## Step 3 — Run it

Call the **Workflow** tool:

```
Workflow({
  scriptPath: "${CLAUDE_PLUGIN_ROOT}/workflow/pipeline.js",
  args: { slug: "<slug>" }
})
```

Pass `args.skipBuild: true` only when the code is already written and the user
wants review and adjudication over the existing working tree.

Do not re-implement the orchestration by hand and do not spawn the agents
yourself — the script exists so the sequence is identical every run and so a
failed run can be resumed rather than re-paid for.

The workflow runs in the background and reports when it completes. It returns a
summary object; `verdict.md` on disk is the authoritative record.

## Step 4 — Report

Lead with whatever needs a human. In order:

1. `suiteGreen: false` — say so first and quote `suiteSummary`. **Never present a
   red suite as a qualified success.**
2. `escalations` — decisions the judge could not make alone.
3. `unmetCriteria` — acceptance criteria not satisfied.
4. `lensesMissing` — a lens that failed to run is an unexamined dimension, not a
   clean bill of health. Say which one and that its risk is uncovered.
5. Then the ordinary summary: outcome, findings, accepted vs rejected, follow-ups,
   and the path to `verdict.md`.

If `outcome` is `ready` **and** there are escalations or unmet criteria, that is a
contradiction in the judge's own output — report it as suspicious rather than
smoothing it over.

## What this pipeline will not do

Worth stating to the user when they ask why a run came back blocked:

- It will not disable, skip, or weaken a test to turn the suite green.
- It will not move acceptance criteria to make the code fit them.
- It will not mark a criterion met when it is not.
- It gives the judge at most two passes to reach a green suite, then stops and
  reports what fails.

A run that ends `blocked` with a clear reason is this pipeline working correctly.
