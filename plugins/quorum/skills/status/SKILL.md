---
name: status
description: Reports where the current work item stands in the quorum pipeline - what has been planned, built, reviewed, and adjudicated - and names the single next command to run. Read-only; changes nothing.
---

# Status — where am I?

Answer two questions and stop: **what state is this work item in**, and **what is
the one command to run next.** Change nothing.

Read `${CLAUDE_PLUGIN_ROOT}/reference/contract.md` for the slug rules and the file
layout you are inspecting.

## Why this step exists

The pipeline keeps no state anywhere but the filesystem and the branch. That is
deliberate — the artifacts *are* the record — but it means knowing where you are
requires reading four things and knowing what their combinations mean. This skill
does that reading and gives a straight answer.

## One deliberate deviation from the contract

The contract says to stop and ask for a slug when the branch is the default
branch. **Do not stop here.** Sitting on `main` with no work item is a state, and
naming it is precisely this skill's job. Report it and give the fix.

The same holds for everything else you find: a missing plan, an unanswered open
question, a `blocked` verdict, a red suite. Those are things to **report**, never
things to fix. Status never writes and never runs another step.

## Procedure

1. **Gather.** Everything you need is on disk and in git:

   ```bash
   git branch --show-current                        # slug source; default branch = a finding
   git log --oneline -1                             # silent failure = no commits yet
   ls -1 docs/work/ 2>/dev/null                     # known work items
   sed -n '1,12p' docs/work/<slug>/plan.md          # Slug, Branch, Status
   grep -c '^- \[ \] S' docs/work/<slug>/plan.md    # unticked build steps
   grep -c '^- \[x\] S' docs/work/<slug>/plan.md    # ticked build steps
   ls -1 docs/work/<slug>/reviews/ 2>/dev/null      # lenses run, and which round
   sed -n '1,12p' docs/work/<slug>/verdict.md       # Outcome, Test suite
   git status --porcelain                           # uncommitted work
   ```

2. **Resolve which work item.** Derive the slug from the branch per the contract.
   If that directory does not exist but others do under `docs/work/`, say which
   ones exist and that none matches the branch — a work item on the wrong branch
   is worth knowing about.

3. **Verify the plan's *Status* against the disk.** The *Status* field is a
   claim; the artifacts are evidence. When they disagree — `built` with unticked
   steps, `adjudicated` with no `verdict.md` — report both and believe the disk.

4. **Check for staleness.** Reviews and verdicts are only as current as the diff
   they were written against:

   - Commits or uncommitted changes **newer than the newest review** mean the
     reviews no longer cover the change. Another `/quorum:3-review` round is due.
   - A review file **newer than `verdict.md`** means the verdict predates the last
     review round and is stale.

   File mtimes are a heuristic, not proof — a checkout can rewrite them. Say
   "looks stale" and give the reason; do not assert it as fact.

5. **Check the open questions.** Unanswered questions in `plan.md` matter most
   *before* the approval gate, because `/quorum:pipeline` leaves nobody to ask.
   Surface them whenever the item has not been built yet.

6. **Report** using the template below, then stop. Do not offer to run the next
   step unless the user asks.

## States

Read down the table and report the **first** row that matches — it is the earliest
unsatisfied step, which makes it the real state.

| State | Looks like | Next |
|---|---|---|
| Wrong branch | Branch is `main`/`master`, or the repo has no commits | `git checkout -b feature/<name>`, then `/quorum:1-plan` |
| Not started | No `docs/work/<slug>/plan.md` | `/quorum:1-plan <what you want built>` |
| Planned | Status `planned` | Read the plan, settle open questions, then `/quorum:pipeline` (it holds the approval gate) or `/quorum:2-build` to drive by hand |
| Approved | Status `approved`, no code yet | `/quorum:pipeline`, or `/quorum:2-build` |
| Part built | Some `S` steps ticked, some not | `/quorum:2-build` — it resumes from the first unticked step |
| Built | Status `built`, no `reviews/` | `/quorum:3-review` |
| Reviewed | `reviews/` populated, no `verdict.md` | `/quorum:4-quorum` |
| Reviews stale | Commits landed after the newest review | `/quorum:3-review` again — it appends a new round, never overwrites |
| Adjudicated, blocked | `verdict.md` Outcome `blocked`, or a red suite | Fix what the verdict names, then `/quorum:3-review` and `/quorum:4-quorum` again |
| Adjudicated, escalations | `verdict.md` has an *Escalations* section | Decide those questions yourself — they were escalated because they are not the judge's to make |
| Done | Outcome `ready`, suite green, no escalations | Open the PR (`/quorum:pipeline` does this at the end), or merge |

Two footnotes worth reporting when they apply:

- **A missing lens is not a clean bill of health.** If `reviews/` has fewer than
  the five lenses, name the missing one and say its dimension is unexamined.
- **`ready` alongside escalations or unmet criteria is a contradiction** in the
  judge's own output. Report it as suspicious rather than smoothing it over.

## Report template

Keep it to this. The developer is asking a question, not requesting a document.

```markdown
**Work item:** <slug> — branch `<branch>`
**State:** <state from the table>

| Artifact | State |
|---|---|
| `plan.md` | Status `built` — 4 of 6 steps ticked |
| `reviews/` | 5 files, round 1 (001–005) |
| `verdict.md` | absent |
| working tree | 3 uncommitted files |

<One or two sentences on what that means — including anything stale,
unanswered, contradictory, or missing.>

**Next:** `/quorum:3-review`
```

## Rules

- **Read-only.** No edits, no commits, no running another step. A status command
  that fixes things is a status command nobody can trust to tell them the truth.
- **Exactly one next command.** The earliest unsatisfied step. Listing every
  possible move puts the decision back on the person who ran this to avoid making it.
- **The disk outranks the *Status* field.** A field says what a previous step
  intended; the artifacts say what actually happened.
- **Report ugly states plainly** — blocked, red, stale, missing lens. That is the
  entire value of asking.
- Say "I cannot tell" when the evidence is genuinely ambiguous, and say what would
  resolve it.
