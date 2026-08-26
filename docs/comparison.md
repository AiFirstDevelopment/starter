# How quorum compares

An honest look at where this pipeline sits against the tools it overlaps with,
and where it is still weaker than its own prose suggests.

Last updated after the guard work (v0.3.0).

## The landscape

Three families overlap with what quorum does, and they are solving different
problems:

**PR review bots** — CodeRabbit, Greptile, Qodo, Codacy. A pull request appears,
an LLM reads the diff, inline comments come back. They review; they do not build.
Their structural safety property is real and underrated: they *cannot edit your
code*, so the worst case is noise.

**Autonomous coders** — Devin, OpenAI's cloud Codex agent, Google Jules, Cursor
background agents, OpenHands, Aider. These take a task and produce a branch.
Verification is usually "the tests pass", occasionally a self-review pass.

**Orchestration frameworks** — LangGraph, CrewAI, AutoGen. Not products but
construction kits. A "critic agent" is a standard pattern in all of them; what
the critic is measured against is left to you.

## Where quorum sits

| | PR bots | Autonomous coders | Quorum |
|---|---|---|---|
| Measured against | the diff | tests passing | **intent recorded before the code existed** |
| Reviewers | one pass | self-check | 6 blind lenses, then a judge |
| Runs the software | no | sometimes | yes, a dedicated lens |
| Reviews the fixer's own edits | n/a | no | yes, bounded, read-only |
| Record left behind | inline comments | commit log | append-only reviews + verdict + state |
| Rules enforced by | prompt | prompt | **prompt, hook, and CI** |

## What it does better

**Falsifiable intent, written first.** Acceptance criteria are pre-registered
before any code exists, in terms someone who did not write the code can check by
operating the application. This is the single most valuable idea in the system
and it is close to absent elsewhere. It is the same move as pre-registration in
science, and it works for the same reason: it removes the option of deciding
after the fact what you were trying to do. A tool reviewing only a diff can tell
you the code is well-written. It cannot tell you it is the wrong feature.

**Nothing grades its own work.** Most systems with a critic stop there. Here the
builder is reviewed by six lenses, and the judge's own repair commits — written
last, under time pressure, with nobody waiting — get their own read-only pass.
The recheck is deliberately bounded: findings are recorded and can force a draft
PR, but nothing fixes them, because a fix would need its own review and the
regress never terminates.

**One lens operates the software.** Five static readers can all pass while the
app is visibly broken. The defects users hit first — a control that moves the
wrong element, a state that cannot be exited — are frequently invisible in a
diff.

**The specific cheats are named and closed.** "Be thorough" is not a control.
"Never weaken a test, never move the acceptance criteria, never mark an unmet
criterion met, never expand scope" is, because each names a real escape hatch. As
of v0.3.0, the mechanizable ones are checked by machine rather than requested in
prose.

**An audit trail rather than a chat log.** Reviews are append-only, including
reviews that later turned out to be wrong. The verdict records dispositions with
reasoning. `state.json` records what ran and against which commit, which is what
lets the system tell "never got that far" apart from "finished, then work landed
on top" — opposite situations that mtime-based staleness cannot distinguish.

## What is still weaker than it sounds

**Correlated blind spots.** Six lenses on one base model are six views from one
vantage point. The diversity is prompt-deep, not model-deep: a failure mode the
model does not recognise is one no lens will catch. Running lenses across
different model families would be genuinely more independent, and is the largest
available improvement not yet made.

**The judgment-dependent rules are still prose.** The guard settles what a
machine can settle. "Never mark an acceptance criterion met when it is not" is
only partly checkable — the guard verifies that cited evidence exists, not that
it proves anything. A confident, wrong "AC3: met" still passes.

**The last gate is a human action.** CI enforcement only becomes a gate once
`quorum guard` is a required status check in branch protection. Until a repo
admin ticks that box, the workflow reports and nothing more.

**Cost.** Up to thirteen agents per run against one pass from a PR bot. This is
appropriate for a branch you are about to merge and absurd for a typo.

**No benchmark.** SWE-bench numbers exist for the autonomous coders. Quorum has
none. Everything above is a design argument, not a measurement, and design
arguments are exactly the kind of claim this pipeline was built to distrust.

**The blast radius is a branch.** One approval authorizes an unattended run that
writes code, reviews it, and applies fixes. That is the trade being made
deliberately, but it is a real trade.

## Verdict

Better than anything I am aware of at **faithfulness to stated intent, with a
record you can audit afterwards** — the axis most tools ignore entirely, because
most tools never had a statement of intent to be faithful to.

Not better on cost, not better on measured defect-catching (nobody has measured
it), and not a substitute for a human reading the pull request. The honest claim
is narrower than "better": it is a system that makes it hard to quietly ship
something other than what was asked for, and that leaves behind enough evidence
to tell when it did.
