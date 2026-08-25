---
name: 1-plan
description: Step 1 of the quorum pipeline. Investigates a requested change and writes a planning document capturing intent, acceptance criteria, and non-goals to docs/work/<slug>/plan.md. Writes no code.
disable-model-invocation: true
---

# Step 1 — Plan

Turn a change request into a written plan that the rest of the pipeline can be
measured against. **You write no production code in this step.**

Read `${CLAUDE_PLUGIN_ROOT}/reference/contract.md` first — it defines the slug
rules and file layout you must follow.

## Why this step exists

Step 4 (`/quorum:4-quorum`) has to judge whether the delivered code fulfills the
user's intent. It can only do that if the intent was written down, in testable
terms, before the code existed. A plan that is only a task list makes step 4
impossible. **Acceptance criteria are the load-bearing part of this document —
everything else is supporting material.**

## Procedure

1. **Resolve the slug** per the contract. If `docs/work/<slug>/plan.md` already
   exists, do not silently overwrite it. Report it and ask whether to revise the
   existing plan or start a new work item under a different slug.

2. **Investigate before planning.** Read the code the change touches. Identify
   the existing patterns, the test setup, the build and run commands. A plan
   written without reading the repo will propose things that do not fit it.

3. **Surface unknowns as questions, not assumptions.** If the request is
   ambiguous in a way that would change the shape of the work, put it in *Open
   questions* and ask the user directly before finishing. Make routine judgment
   calls yourself; escalate only forks that lead to materially different work.

4. **Write `docs/work/<slug>/plan.md`** using the template below.

5. **Stop.** Report the path and summarize the acceptance criteria and any open
   questions. Do not begin building. The user runs `/quorum:2-build` when ready.

## Template

```markdown
# Plan: <short title>

- **Slug:** <slug>
- **Branch:** <branch>
- **Status:** planned

## Intent

What the user is actually trying to achieve, in their terms — the outcome, not
the implementation. Two to five sentences. If the user gave a reason or a
constraint, capture it here verbatim rather than paraphrasing it away.

## Acceptance criteria

Observable, testable statements. Each one must be checkable by someone who did
not write the code, by operating the assembled application. Prefer the form
"when <situation>, <observable result>".

- [ ] AC1: ...
- [ ] AC2: ...

Bad: "the service layer is refactored cleanly."
Good: "when a user submits the form with an empty email, the form stays open and
shows 'Email is required' next to the email field."

## Non-goals

Explicitly out of scope. This section prevents step 2 from expanding the work and
step 4 from penalizing the absence of things nobody asked for.

- ...

## Open questions

Anything unresolved, with the assumption being made in the meantime so work is
not blocked. Empty is fine — but only if it is genuinely empty.

- **Q:** ... **Assumption:** ...

## Approach

The intended implementation, at the level of files and responsibilities. Name the
existing patterns being followed. Call out anything risky or irreversible.

## Steps

Ordered and small enough to verify individually. `/quorum:2-build` ticks these
off as it goes, so a dead session can be resumed by reading this list.

- [ ] S1: ...
- [ ] S2: ...

## Test strategy

Which acceptance criteria get behavioral tests through the assembled application,
and which pure logic (if any) warrants unit tests. See `/quorum:add-regression-tests`.

## Build notes

Left empty by this step. `/quorum:2-build` appends deviations here.
```

## Rules

- No production code, no test code, no dependency changes in this step.
- Every acceptance criterion must be falsifiable. If you cannot describe how it
  would be observed failing, it is not an acceptance criterion — rewrite it.
- Do not pad the plan. A three-line change gets a short plan.
