---
name: 3-review
description: Step 3 of the quorum pipeline. Reviews the built change from several independent lenses in fresh context, writing one review file per lens to docs/work/<slug>/reviews/. Finds problems; fixes nothing.
disable-model-invocation: true
---

# Step 3 — Review

Produce **several independent reviews from different lenses**, so that step 4 has
a real panel to adjudicate rather than a single opinion.

Read `${CLAUDE_PLUGIN_ROOT}/reference/contract.md` for the file layout, review
numbering, and how to determine the diff.

## The two rules that make this step worth running

**1. Review from the diff, not from the build narrative.** If this session also
built the code, you are the worst possible reviewer of it: you already believe
your choices were correct, and you will rationalize rather than investigate. Read
the diff as if a stranger wrote it. Never treat "I remember why I did that" as
evidence that it is right. Verify claims against the code.

**2. Each lens is genuinely independent.** Run each lens in **fresh context** —
spawn a separate subagent per lens with the Agent tool where it is available, so
no lens is anchored by another's conclusions. Diverse lenses find what redundant
ones cannot. If subagents are unavailable, run the lenses sequentially and
deliberately re-read the diff at the start of each, reasoning only within that
lens's remit.

## Lenses

Run these five by default. Drop a lens only if it is genuinely inapplicable, and
say in your summary that you dropped it and why.

| Lens | Remit |
|---|---|
| `correctness` | Logic errors, unhandled cases, off-by-one, null/undefined, race conditions, incorrect error handling, broken edge cases. Does the code do what it says? |
| `spec-fidelity` | Compare the diff against `plan.md`. Is every acceptance criterion actually met? Was anything from *Non-goals* built anyway? Do the *Build notes* deviations hold up? |
| `security` | Injection, authz/authn gaps, secret handling, unsafe deserialization, dependency risk, data exposure in logs or errors. |
| `simplicity` | Duplication, needless abstraction, dead code, and code that could be meaningfully shorter or clearer without losing behavior. Reuse of what already exists in the repo. |
| `test-quality` | Do the tests fail if the behavior breaks? Assertion-free tests, tests coupled to implementation detail, missing coverage of stated acceptance criteria, flakiness risk (time, network, randomness, ordering). |

## Procedure

1. Resolve the slug; read `docs/work/<slug>/plan.md`.
2. Determine the diff per the contract. Report the range you used.
3. Run each lens. Each produces its own file at
   `docs/work/<slug>/reviews/NNN-<lens>.md`, numbered per the contract.
4. Report a summary to the user: counts by severity per lens, and the single most
   serious finding overall. Then stop — the user runs `/quorum:4-quorum`.

## Review file template

```markdown
# Review NNN — <lens>

- **Slug:** <slug>
- **Diff reviewed:** <range>
- **Verdict:** <clean | findings>

## Findings

### F1 — <one-line claim> [blocker|major|minor|nit]

- **Where:** `path/to/file.ts:42`
- **What:** One or two sentences stating the defect.
- **Failure scenario:** Concrete inputs or state, and the wrong output, crash, or
  violated criterion that results. If you cannot write this, the finding is
  speculation — either verify it or drop it.
- **Suggested direction:** Optional, one sentence. Do not write the patch.
```

## Rules

- **Change no code in this step** — not even an obvious typo fix. Reviews are
  evidence for step 4; a reviewer who edits contaminates the record.
- Every finding needs a file:line and a concrete failure scenario. "This could be
  cleaner" without a specific claim is noise — leave it out.
- Severity means: `blocker` (must fix before merge), `major` (fix now, does not
  block), `minor` (worth fixing), `nit` (preference; step 4 will likely reject it).
- A clean lens writes a file saying so. Silence is not a review.
- Do not inflate. Ten weak findings are worse than two real ones, because step 4
  spends its judgment filtering instead of fixing.
