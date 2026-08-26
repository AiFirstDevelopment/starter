# How quorum compares

Quorum makes an AI write down what it's going to build — in terms you can actually
check — before it writes any code, then holds it to that plan mechanically instead
of asking nicely. There's no new tool to learn and no dashboard to log into: it's
slash commands in the editor you already use, and every plan, review, and verdict
is a markdown file in your own repository. All you do is approve the plan and read
the pull request, both things you already know how to do — you never have to
supervise an agent or decide when to trust one, which is the part most developers
don't understand and are right to be wary of.

That is the claim. What follows is an honest look at where this pipeline actually
sits against the tools it overlaps with, and where it is still weaker than its own
prose suggests.

Last updated after the history work (v0.10.0).

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
| Record left behind | inline comments | commit log | append-only reviews + verdict + state, queryable per change |
| Rules enforced by | prompt | prompt | **prompt, hook, and CI** |
| Survives a repo's lifetime | yes, by construction | n/a, per task | yes, but it had to be built |

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

**The enforcement checks itself.** The CI half runs a *copy* of the checker,
because a CI runner has no plugin installed — and a copy is the kind of thing
that rots quietly. So the guard has rules about its own installation: a vendored
copy that no longer matches the plugin it came from is a violation, and so is one
that has been deleted, or left without the workflow that runs it. This closes a
gap most tools do not have because most tools do not have this shape: a PR bot is
a hosted service that cannot go stale on your machine, while a vendored script
silently can. It is worth being precise about what this buys — it makes removing
the enforcement a visible act rather than a quiet one. It does not stop anyone
with commit access from removing it deliberately and saying so.

**An audit trail rather than a chat log.** Reviews are append-only, including
reviews that later turned out to be wrong. The verdict records dispositions with
reasoning. `state.json` records what ran and against which commit, which is what
lets the system tell "never got that far" apart from "finished, then work landed
on top" — opposite situations that mtime-based staleness cannot distinguish.

## What is still weaker than it sounds

**Correlated blind spots — reduced, not removed.** The judge and the recheck now
run on different models by default, which is the case that matters most: one
agent checking another's work, where shared weights mean shared blind spots. The
six lenses can be spread across model tiers too, but that is offered rather than
assumed, because diversity there is bought with per-lens capability and there is
no evidence here on which way that trades.

What remains is the harder half. Every option is a Claude model, so the panel
is less correlated than it was and nowhere near independent. Genuine
independence would mean spanning providers, which this harness cannot do. Treat
six agreeing lenses as one careful opinion, not six.

**The judgment-dependent rules are still prose, but less of them.** The guard
now catches the structural half of "never mark a criterion met when it is not":
a criterion **omitted** from the verdict is a violation, since silence about AC4
reads exactly like success; a criterion the verdict invented is too; and cited
evidence must name a file that exists and a line inside it.

What no checker settles is whether the cited test proves the criterion. A
confident, wrong "AC3: met, see `foo.test.js:31`" — with a real file and a real
line — still passes. That is a judgment, and judgment is what this system spends
six lenses and a judge on precisely because it cannot be checked.

**The last gate is still a human action, but no longer an invisible or
unasked one.** CI enforcement becomes a gate only when `quorum guard` is a
required status check. `guard.py --check-gate` reports whether it actually is —
`LIVE`, `NOT LIVE`, or `cannot tell` — and the pipeline now runs it on every
publish, puts the answer in the pull request body, and records it in
`state.json`. The three answers stay distinct: `cannot tell` is never rounded up
to a pass. That turns "is the gate live" from a question somebody had to think to
ask into one that gets answered every run. Nobody here can tick the box; a repo
admin must, and a run does not fail because they have not.

**The orchestrator is barely tested.** `selftest.py` covers the enforcement layer
thoroughly and covers exactly one thing about `pipeline.js`: that it calls agents
by names that actually resolve. It knows nothing about whether the prompts say
what they should, whether the schemas match what the agents return, or whether
the phases run in the right order — all of which need live agents to exercise and
none of which a static check reaches. The script that invokes every agent in the
system has the thinnest coverage in it. That is not hypothetical: a wrong agent
name shipped in that file twice, and both times it was found by a run failing
rather than by a test.

**The installation rules only see one diff.** `enforcement` catches the CI checker
being deleted in the change under review. It cannot see a deletion that landed on
the base branch before this work item started, and a repo where both the checker
and its workflow went months ago is indistinguishable from one that never adopted
them. Closing that needs a memory of what was once installed — which would be one
more file that could itself be quietly deleted.

**Cost.** Up to thirteen agents per run against one pass from a PR bot. This is
appropriate for a branch you are about to merge and absurd for a typo.

**No benchmark for the part that needs one.** The enforcement layer is now
tested: `selftest.py` builds throwaway repositories, breaks each rule
deliberately, and asserts it fires — and the suite itself was checked by
disabling each rule and confirming the tests go red. That is a real measurement
of the mechanical half.

The half that matters more is still unmeasured. There is no benchmark for
whether six lenses catch more real defects than one careful pass, and no
SWE-bench-style number to compare against the autonomous coders. Everything
about review quality here is a design argument, not a measurement — and design
arguments are exactly the kind of claim this pipeline was built to distrust.
Applying its own standard: this system asks you to take its review quality on
faith.

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
