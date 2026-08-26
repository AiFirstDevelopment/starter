---
name: pipeline
description: Runs the whole quorum pipeline autonomously from an approved plan - build, six independent review lenses in parallel, adjudication, then a read-only recheck of the judge's own commits - stopping only for plan approval at the start. Use when the plan is written and you want the change delivered without further supervision.
argument-hint: [slug]
disable-model-invocation: true
---

# Run the pipeline

Take an approved plan and deliver the change without further human involvement:
**build → six independent review lenses in parallel → adjudicate → recheck the
judge's own commits → green suite or an honest red one.**

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
regression suite (`/tests:ci`); judgment stays on demand.

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
3. Confirm the pipeline's agents are registered. The workflow calls five, by
   their namespaced names: `quorum:quorum-builder`, `quorum:quorum-reviewer`,
   `quorum:quorum-scribe`, `quorum:quorum-judge`, `quorum:quorum-publisher`.
   You can see which agent types you have — check all five are there under
   exactly those names. If any is missing or registers differently, stop and say
   the plugin is not installed correctly. Do not go on to the gate.

   This check sits above the gate deliberately. A wrong agent name does not
   surface until the workflow reaches its first agent call, long after the user
   has authorized the run — and an approval spent on a run that cannot start is
   worse than no approval, because it leaves the plan sitting at `approved`,
   where the next run reads it as consent nobody gave.

4. Read the plan and check its *Status*.

## Step 2 — The approval gate

This is the **only** point at which the user is consulted. Treat it seriously.

If *Status* is already `approved`, check `state.json` before trusting it. Two
histories put it there and they are opposites:

- **`stage` is `approved`, or `planned`, or there is no `state.json`** — an
  authorization nobody has spent. Either bare `/quorum:1-plan` held the gate and
  the user said yes, or they approved the plan by hand. **Proceed without asking
  again.** Asking twice for one decision is not twice the safety; it teaches
  people to click through the only checkpoint in the system.
- **`stage` is `building` and no `build` was ever recorded** — a run was
  authorized, launched, and died before the builder did anything. That
  authorization is **stale**: it bought nothing, and nobody has looked at this
  plan since. Treat the plan as unapproved and ask below, saying plainly that the
  last run never got past launch and what went wrong with it.

The distinction is only available because Step 4 records `building` at launch. An
approval that has been spent and an approval that has not look identical on disk
otherwise, and assuming the worse one costs a real decision every time a plan
waits.

Otherwise — a stale authorization included — show the user the plan's **Intent**,
**Acceptance criteria**, **Non-goals**, and any **Open questions**, then ask
plainly whether to proceed.
Make clear what they are authorizing: an unattended run that will write code,
review it, and apply fixes to the working tree with no further checkpoint.

If any *Open question* is unanswered, surface it now. After this point there is
nobody to ask, and the builder will have to guess and record the guess.

On approval, set *Status* to `approved` in `plan.md`, record it, then continue:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/state.py" docs/work/<slug> \
  '{"stage":"approved","log":"pipeline approved by user, starting unattended run"}'
```

That line is the audit trail for the one human decision in the whole run. On
anything short of clear approval, stop.

## Step 3 — Determine the diff, once

**Resolve the range here and pass it down.** The workflow script cannot run git —
it has no shell — so if you do not supply a range, every lens works one out
independently. Six agents then repeat the same archaeology and each self-reports a
range that nothing cross-checks, which quietly allows two lenses to review two
different things.

Compute it per the contract:

```bash
BASE=$(git symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null | sed 's@.*/@@')
BASE=${BASE:-main}
git merge-base HEAD "origin/$BASE" 2>/dev/null   # the fork point, if there is one
```

Pass `<fork-point>...HEAD`. If there is no remote, no base branch, or no fork
point — a fresh repo, a branch off nothing — say which, and pass the widest range
that is actually true, down to the root commit. **An honest wide range beats a
confident wrong one**, and stating it once means all six lenses are demonstrably
looking at the same change.

Uncommitted working-tree changes are reviewed too; the range names the committed
part.

## Step 4 — Run it

Call the **Workflow** tool:

```
Workflow({
  scriptPath: "${CLAUDE_PLUGIN_ROOT}/workflow/pipeline.js",
  args: { slug: "<slug>", diffRange: "<fork-point>...HEAD" }
})
```

Record the launch first. This is what separates an authorization that has been
spent from one that has not, and it is the only moment either is knowable:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/state.py" docs/work/<slug> \
  '{"stage":"building","log":"pipeline launched"}'
```

Pass `args.skipBuild: true` only when the code is already written and the user
wants review and adjudication over the existing working tree.

### Which model runs what

The judge and the recheck run on **different models by default**, because the
recheck exists to catch what the judge could not see in its own work, and the
same weights reviewing themselves see the same things. That decorrelation costs
no capability, so it is not optional.

The six lenses inherit the session model. Spreading them across tiers buys
diversity and spends per-lens capability, and there is no evidence here on which
way that trades — so it is offered rather than assumed:

```
args: { models: { correctness: "opus", simplicity: "sonnet", recheck: "haiku" } }
```

Every option is a Claude model, so this **reduces** correlated blind spots rather
than removing them. A genuinely independent panel would span providers, which
this harness cannot do — worth saying plainly rather than implying the panel is
more independent than it is.

Do not re-implement the orchestration by hand and do not spawn the agents
yourself — the script exists so the sequence is identical every run and so a
failed run can be resumed rather than re-paid for.

The workflow runs in the background and reports when it completes. It returns a
summary object; `verdict.md` on disk is the authoritative record.

## Covering an escalation after the fact

The one loop this pipeline cannot close by itself. It escalates a decision, the
run finishes, a human makes that decision and writes the code — and that new code
has never been reviewed by anything.

There is **no new approval gate for this**; the plan was approved once and this is
the same work item. Run the pipeline over just the delta:

```
Workflow({
  scriptPath: "${CLAUDE_PLUGIN_ROOT}/workflow/pipeline.js",
  args: { slug: "<slug>", skipBuild: true, diffRange: "<verdict.head>...HEAD" }
})
```

`verdict.head` is in `docs/work/<slug>/state.json` — it is the commit the judge
last saw, so that range is exactly the uncovered work and nothing else. Reviews
append a new round, and the judge adjudicates only what is new.

Do **not** re-run the whole branch through build, six lenses, and adjudication to
cover a small follow-up commit. It re-pays for the entire run to look at a diff
one round covers.

## Step 5 — Report

### If the run never started

A workflow that dies before the builder does anything — no commits, `state.json`
still at `building`, no `verdict.md` — spent the user's authorization on nothing.
Put the gate back before reporting:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/state.py" docs/work/<slug> \
  '{"stage":"planned","log":"run died before build; approval reset, gate re-armed"}'
```

and set *Status* back to `planned` in `plan.md`. Then say what failed. Do not
relaunch on the same approval — the user authorized one run, and they should see
why the first one died before deciding to spend another.

### What the run concluded

Lead with whatever needs a human. In order:

1. `suiteGreen: false` — say so first and quote `suiteSummary`. **Never present a
   red suite as a qualified success.**
2. `escalations` — decisions the judge could not make alone.
3. `unmetCriteria` — acceptance criteria not satisfied.
4. `lensesMissing` — a lens that failed to run is an unexamined dimension, not a
   clean bill of health. Say which one and that its risk is uncovered. `behavior`
   missing means nobody ran the software.
5. **Guard violations** — a rule was broken, not a finding to weigh. Report these
   above everything else the run concluded; a verdict cannot vouch for a run that
   broke one of the rules the verdict is written under.
6. `judgeDiffBlockers` — blockers found in the judge's own adjudication commits.
   These are deliberately left unfixed: the pipeline will not let the judge grade
   its own repairs. Name them and say they need a human.
7. Then the ordinary summary: outcome, findings, accepted vs rejected, follow-ups,
   and the path to `verdict.md`.

If `outcome` is `ready` **and** there are escalations or unmet criteria, that is a
contradiction in the judge's own output — report it as suspicious rather than
smoothing it over.

## What this pipeline will not do

Worth stating to the user when they ask why a run came back blocked:

- It will not disable, skip, or weaken a test to turn the suite green — and since
  that promise is only a sentence in a prompt, `/quorum:guard` checks it
  mechanically and CI checks it where no agent can reach.
- It will not move acceptance criteria to make the code fit them.
- It will not mark a criterion met when it is not.
- It gives the judge at most two passes to reach a green suite, then stops and
  reports what fails.

A run that ends `blocked` with a clear reason is this pipeline working correctly.
