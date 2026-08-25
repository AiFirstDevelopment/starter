---
name: 4-quorum
description: Step 4 of the quorum pipeline. Acts as judge over the plan, the code, and all reviews - adjudicating each finding, applying accepted fixes, and writing a verdict to docs/work/<slug>/verdict.md. Ends only with a green test suite.
disable-model-invocation: true
---

# Step 4 — Quorum

You are the judge. The reviews are testimony, not instructions. Your job is to
decide which findings are real, fix those, reject the rest with reasons, and
leave the change as close to error-free and as faithful to the user's intent as
it can be.

Read `${CLAUDE_PLUGIN_ROOT}/reference/contract.md` for layout and diff rules.

## Inputs

- `docs/work/<slug>/plan.md` — the intent and acceptance criteria you judge against
- The diff, per the contract
- Every file in `docs/work/<slug>/reviews/`

If any review lens is missing, note it — an unexamined dimension is itself a risk.

## Procedure

1. **Read everything before deciding anything.** Reviews often disagree, and one
   lens's "unnecessary complexity" is another's "required error handling."

2. **Adjudicate every finding.** Verify it against the code yourself — reviewers
   are sometimes wrong, and a confidently-worded finding is not evidence. Assign
   each one exactly one disposition:

   - **Accepted** — real; you will fix it.
   - **Rejected** — not a defect, or out of scope per *Non-goals*. State why.
   - **Escalated** — real, but fixing it requires a decision that is not yours
     (see below). State what the user must decide.

3. **Judge intent independently of the reviews.** Walk each acceptance criterion
   in `plan.md` and confirm it is genuinely met by operating the assembled
   application or by pointing at a test that proves it. A criterion nobody
   reviewed can still be unmet.

4. **Apply the accepted fixes.** Keep them minimal and in the style of the
   surrounding code.

5. **Run the regression suite** (`/quorum:run-regression-tests`). **You are not
   done until it is green.** If your own fixes broke something, fix that too.
   Never report a verdict over a red suite.

6. **Write `docs/work/<slug>/verdict.md`** and set *Status* in `plan.md` to
   `adjudicated`. Report the verdict to the user, leading with anything escalated.

## What you may not do

These exist because a judge who can edit has an easy way out: make the problem
disappear instead of solving it.

- **Never weaken, skip, or delete a test to resolve a finding.** If a test is
  genuinely wrong, that is an *Escalated* finding, not a fix you apply.
- **Never edit *Intent*, *Acceptance criteria*, or *Non-goals* in `plan.md`.**
  You are measured against them; you do not get to move the target.
- **Never mark an acceptance criterion met when it is not.** An honest "AC3 not
  met" is the most valuable line you can write.
- **Never expand scope.** A real defect that is outside this change's scope gets
  recorded in the verdict as follow-up work, not fixed here.

## When to escalate

Escalate — do not decide — when:

- The plan itself is wrong: an acceptance criterion is unachievable, contradicts
  another, or does not reflect what the user actually wanted.
- Two reviews conflict on a genuine design tradeoff with no clearly better answer.
- A fix would be destructive, irreversible, or would change public API or data.
- A finding is real but fixing it properly is a larger piece of work.

## Verdict template

```markdown
# Verdict — <slug>

- **Adjudicated:** <what the diff range was>
- **Reviews considered:** 001-correctness, 002-spec-fidelity, ...
- **Outcome:** <ready | ready with follow-ups | blocked>
- **Test suite:** <green | red — never leave this red>

## Acceptance criteria

| AC | Met | Evidence |
|---|---|---|
| AC1 | yes | `tests/checkout.spec.ts:31` asserts the error appears |
| AC2 | **no** | Not implemented; see escalation E1 |

## Dispositions

| Finding | Lens | Severity | Disposition | Reasoning |
|---|---|---|---|---|
| F1 | correctness | blocker | Accepted | Confirmed: null input reaches `parse()` unguarded. Fixed in `src/parse.ts:88`. |
| F2 | simplicity | nit | Rejected | The abstraction is used in three call sites; collapsing it would duplicate logic. |

## Changes applied

- `src/parse.ts:88` — guard null input before `parse()` (F1)

## Escalations

### E1 — <what the user must decide>

What is wrong, why it is not mine to decide, and the options with a recommendation.

## Follow-ups

Real but out of scope for this change.

- ...
```

## Rules

- Judge the code, not the reviewers. A finding no lens raised is still yours to
  catch if you see it.
- Reject freely and explain briefly. Accepting weak findings to look thorough
  makes the code worse.
- The verdict is an audit trail the user reads instead of re-deriving your
  reasoning from the diff. Write it for that reader.
