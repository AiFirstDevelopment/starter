---
name: status
description: Reports where the current work item stands in the quorum pipeline - what has run, what it concluded, and what has changed since - and names the next command to run. Read-only; changes nothing.
---

# Status — where am I?

Answer two questions and stop: **what has run on this work item**, and **what is
the one command to run next.** Change nothing.

Read `${CLAUDE_PLUGIN_ROOT}/reference/contract.md` for the slug rules, the file
layout, and the `state.json` schema you are reading.

## Why this step exists

Knowing where you stand means reading five things and knowing what their
combinations mean. This skill does that reading and gives a straight answer.

`state.json` records what has run. The artifacts record what was decided. You need
both: the artifacts alone cannot distinguish *the pipeline never got that far*
from *the pipeline finished and then work landed on top* — and those are opposite
situations that demand opposite responses.

## The failure this skill exists to avoid

**Never report an unsatisfied step without first saying what completed.**

A branch whose pipeline ran, passed, and then took one follow-up commit is in
excellent shape. Reporting that as "reviews stale — run `/quorum:3-review`" is
mechanically true and badly misleading: it reads as *the pipeline did not do its
job*, and it sends people to re-run a finished forty-minute pipeline over a
five-line diff.

Lead with what ran and what it concluded. Then say precisely what has changed
since, and how big it is. A reader who knows the pipeline completed and that one
small commit landed after it can make the call themselves; a reader told only
"stale" cannot.

## One deliberate deviation from the contract

The contract says to stop and ask for a slug when the branch is the default
branch. **Do not stop here.** Sitting on `main` with no work item is a state, and
naming it is precisely this skill's job. Report it and give the fix.

The same holds for everything else you find: a missing plan, an unanswered open
question, a `blocked` verdict, a red suite. Those are things to **report**, never
things to fix. Status never writes and never runs another step.

## Procedure

1. **Read `state.json` first.** It is the index of what has run:

   ```bash
   cat docs/work/<slug>/state.json 2>/dev/null
   ```

   Missing or malformed is not an error — the work item predates it, or a step
   failed to record. Fall back to inferring from the artifacts, and say that the
   answer is inferred rather than recorded.

2. **Gather the rest** from disk and git:

   ```bash
   git branch --show-current                        # slug source; default branch = a finding
   git log --oneline -1                             # silent failure = no commits yet
   ls -1 docs/work/ 2>/dev/null                     # known work items
   sed -n '1,12p' docs/work/<slug>/plan.md          # Slug, Branch, Status
   grep -c '^- \[x\] S' docs/work/<slug>/plan.md    # ticked build steps
   ls -1 docs/work/<slug>/reviews/ 2>/dev/null      # lenses run, and which round
   sed -n '1,12p' docs/work/<slug>/verdict.md       # Outcome, Test suite
   git status --porcelain                           # uncommitted work
   ```

3. **Compute what has changed since each stage.** This is the whole point of the
   recorded `head` SHAs — ask git instead of guessing:

   ```bash
   git log --oneline <state.review.head>..HEAD      # commits no lens has seen
   git diff --stat <state.review.head>..HEAD        # and how big they are
   git log --oneline <state.verdict.head>..HEAD     # commits the judge never saw
   ```

   Empty means the reviews cover the branch. Non-empty names exactly what they do
   not — report the commit subjects and the diffstat, not the word "stale".

   **Once a verdict exists, `verdict.head..HEAD` is the number that matters.**
   The judge commits its own accepted fixes after the lenses have read the tree,
   so `review.head..HEAD` contains the judge's commit on *every* completed run,
   by design. Reporting that as unreviewed work would flag every successful
   pipeline as a problem — the same misleading answer this skill exists to avoid,
   in a different costume. Mention it only when there is no verdict yet, or when a
   lens round is genuinely owed.

   Only when no `head` was recorded, fall back to comparing file mtimes, and say
   "looks stale, inferred from timestamps" rather than asserting it.

4. **Cross-check the record against the disk.** `state.json` and the plan's
   *Status* are claims; the artifacts are evidence. When they disagree — `stage`
   `adjudicated` with no `verdict.md`, `built` over unticked steps — report both
   and believe the disk.

5. **Check the open questions.** Unanswered questions in `plan.md` matter most
   *before* the approval gate, because `/quorum:pipeline` leaves nobody to ask.
   Surface them whenever the item has not been built yet.

6. **Report** using the template below, then stop. Do not offer to run the next
   step unless the user asks.

## States

Read down the table and report the **first** row that matches. Every row from
*Built* down also reports what already completed, per the rule above.

| State | Looks like | Next |
|---|---|---|
| On the base branch | Branch is `main`/`master`, or the repo has no commits | `/quorum:1-plan <what you want built>` — it names the branch with you and creates it |
| Not started | No `docs/work/<slug>/` | `/quorum:1-plan <what you want built>` |
| Planned | `stage` `planned` | Settle open questions, then `/quorum:pipeline` (it holds the approval gate) or `/quorum:2-build` to drive by hand |
| Approved | `stage` `approved` | `/quorum:pipeline`, or `/quorum:2-build` |
| Part built | Some `S` steps ticked, some not | `/quorum:2-build` — it resumes from the first unticked step |
| Built | `stage` `built`, no `reviews/` | `/quorum:3-review` |
| Reviewed | `reviews/` populated, no `verdict.md` | `/quorum:4-quorum` |
| Reviews stale | Commits after `review.head`, not yet adjudicated | `/quorum:3-review` — it appends a new round, never overwrites |
| Adjudicated, blocked | Outcome `blocked`, or a red suite | Fix what the verdict names, then `/quorum:3-review` and `/quorum:4-quorum` |
| Adjudicated, escalations | Verdict has open *Escalations* | Decide those yourself — they were escalated because they are not the judge's to make |
| **Adjudicated, then changed** | Verdict exists **and** commits landed after `verdict.head` | Say the pipeline completed and what it concluded, then size the delta — see below |
| Published | `pr.url` recorded, nothing changed since | Nothing here — the PR is the deliverable. When you want the next change, `/quorum:1-plan` branches off the base rather than stacking on this one |
| Done | Outcome `ready`, suite green, no escalations, nothing since | Open the PR (`/quorum:pipeline` does this), or merge. Then `/quorum:1-plan <the next change>` |

### Adjudicated, then changed

The most commonly misread state. It means commits landed after `verdict.head` —
not merely after `review.head`, which every finished run has by design.

Report, in this order: the pipeline completed and what it concluded; the commits
since the verdict, by subject and diffstat; and that those commits alone are
unreviewed.

Then size the call rather than making it for them:

- **A small, well-guarded delta** — a few lines, covered by tests that were shown
  failing first. Opening the PR is defensible. Say so.
- **Anything larger, or anything self-assessed** — code written and graded by the
  same session is exactly what the lenses exist to not take at face value.
  `/quorum:3-review` appends a round without re-adjudicating.

Never recommend re-running the whole `/quorum:pipeline` over a small follow-up
commit. It re-pays for build, six lenses, and adjudication to look at a diff a
single review round covers.

Two footnotes worth reporting when they apply:

- **A missing lens is not a clean bill of health.** If `review.missing` is
  non-empty or `reviews/` has fewer than six lenses, name the missing one and say
  its dimension is unexamined. `behavior` missing means nobody ran the software.
- **No `recheck` means the judge's own commits were never reviewed.** Absent is
  not clean. Say so, and that `/quorum:pipeline` is what covers them.
- **`guard` violations outrank everything else you report.** A broken rule is not
  a finding to weigh; say what broke and that `/quorum:guard` names it. Absent
  `guard` means the check never ran, which is not a pass.
- **`ready` alongside escalations or unmet criteria is a contradiction** in the
  judge's own output. Report it as suspicious rather than smoothing it over.

## Report template

Terse. The developer is asking a question, not requesting a document. Rows for
stages that have not run are omitted, not written as "absent".

```markdown
**retry-failed-webhooks** · `feature/retry-failed-webhooks` · **adjudicated, 1 commit since**

| | |
|---|---|
| plan | 6/6 steps · 4 ACs · 0 open |
| reviews | round 1 · 5 lenses · 7 findings (1 blocker) |
| verdict | ready with follow-ups · suite green · 2 escalations |
| since review | `ea84c9d` fix retry gating — 3 files, +18 −4 |
| tree | clean |

The pipeline ran and completed. `ea84c9d` landed afterwards — the escalation
fixes — so it is the only part of the branch no lens has seen.

**Next:** `/quorum:3-review` for one round over that commit, or open the PR if you
are satisfied five lines guarded by two tests do not need it.
```

## Rules

- **Read-only.** No edits, no commits, no writing `state.json`, no running another
  step. A status command that fixes things is one nobody can trust to report
  honestly.
- **Say what completed before what is missing.** Every time.
- **One next command.** The earliest unsatisfied step. Offer a second only in
  *Adjudicated, then changed*, where the delta's size genuinely decides it — and
  then state the size so the reader can judge.
- **The disk outranks `state.json`, which outranks the *Status* field.** The
  artifacts are what happened; the index is what a step reported; the field is
  what a step intended.
- **Report ugly states plainly** — blocked, red, missing lens, contradictory. That
  is the entire value of asking.
- Say "I cannot tell" when the evidence is genuinely ambiguous, and say what would
  resolve it.
