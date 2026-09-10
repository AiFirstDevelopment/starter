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

Last updated at v0.24.0, after surveying the spec-driven development field.

## The landscape

Four families overlap with what quorum does, and they are solving different
problems:

**Spec-driven development tools** — GitHub Spec Kit, Kiro, Tessl, OpenSpec, BMAD,
MoAI-ADK, GAAI, and roughly a dozen more. This is the family quorum belongs to:
all of them write intent down before code exists. They differ in what the spec is
*for*. Spec Kit and Kiro discard it after implementation; OpenSpec keeps it as a
durable delta-tracked record; Tessl goes furthest and treats code as generated
output, so the spec is the only thing anyone edits. What almost none of them do is
stop the agent from rewriting the spec mid-run. GAAI, the closest of them to this
pipeline in shape — acceptance criteria, autonomous delivery, pull requests — says
so outright in its own README: *"The framework relies on the agent following the
files. There is no programmatic enforcement."*

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

| | PR bots | Autonomous coders | SDD tools | Quorum |
|---|---|---|---|---|
| Measured against | the diff | tests passing | a written spec | **intent recorded before the code existed** |
| Reviewers | one pass | self-check | usually one QA pass, often none | 6 blind lenses, then a judge |
| Runs the software | no | sometimes | rarely | yes, a dedicated lens |
| Reviews the fixer's own edits | n/a | no | no | yes, bounded, read-only |
| Record left behind | inline comments | commit log | spec files | append-only reviews + verdict + state, queryable per change |
| Can the agent edit the spec? | n/a | n/a | **yes** | **no — the write is refused** |
| Rules enforced by | prompt | prompt | prompt (Tessl: regeneration) | **prompt, hook, and CI** |
| Survives a repo's lifetime | yes, by construction | n/a, per task | **yes — often better than here** | yes, but it had to be built |

The last two rows are the whole argument, and they cut both ways. Enforcement is
where this pipeline is alone. Durability is where it is behind: OpenSpec's delta
specs are a better long-term record than a directory of frozen per-change plans.

## What it does better

**Falsifiable intent, written first.** Acceptance criteria are pre-registered
before any code exists, in terms someone who did not write the code can check by
operating the application. This is the single most valuable idea in the system.
It is no longer a rare one — an entire tool family is built on it — but the
version here is frozen at approval and unwriteable for the duration of the run,
which is the part that is rare. It is the same move as pre-registration in
science, and it works for the same reason: it removes the option of deciding
after the fact what you were trying to do. A tool reviewing only a diff can tell
you the code is well-written. It cannot tell you it is the wrong feature.

**Nothing grades its own work.** Most systems with a critic stop there. The
exception worth knowing is `agent-review-panel`, whose 4-6 reviewers cross-examine
each other over several debate rounds before a judge arbitrates — a more elaborate
panel than this one. It reviews only: it builds nothing, has no spec to measure
against, and states plainly that it cannot evaluate runtime behaviour. Here the
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

**No durable spec of record.** `docs/work/<slug>/plan.md` is frozen per change
and then archived. There is no single evolving document describing what the system
is supposed to do, so nothing measures change N against the intent of changes 1
through N-1. OpenSpec solved this with delta specs and archives; Spec Kit has
`constitution.md`; Kiro has steering files. `/quorum:audit` is the piece that could
close it — pointed at an accumulated spec rather than one supplied by hand — but
that is not what it does today.

**The narrowest harness support in the family.** Spec Kit, OpenSpec, GAAI, and
Superpowers all span several agents; OpenSpec claims thirty-odd. This is Claude
Code only. That is a deliberate trade — the PreToolUse hook and the plugin
marketplace are exactly what buy the enforcement — but it is a real ceiling on who
can adopt it.

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

**The orchestration is reachable only through one tool, and its absence used to
be silent.** Every multi-agent claim in this document — six blind lenses, the
refute pass, the read-only recheck — routes through a Workflow tool that older
Claude Code releases do not register. When `/quorum:audit` first met a client
without one, it did not fail. It improvised: it audited the repository from the
skill's own shell-holding session and wrote a report asserting *"Refutation:
upheld — read `src/upstream.js` … found none"* for a pass that never happened, and
the hash verifier exited 0 on it. Nothing downstream could tell that report from a
real one.

It was caught by the `behavior` lens actually running the command, and only after
five lenses had read the same code and passed it — which is the argument for that
lens in one incident. Both call sites are hard stops now. But the lesson
generalises past the fix: **a pipeline whose guarantees are structural is only as
honest as its behaviour when the structure is missing**, and the failure mode to
fear is not the missing dependency, it is the plausible artifact produced in its
absence. This document's own claims about the panel are worth exactly as much as
the panel having run.

## Verdict

Having a statement of intent is not the differentiator. Twenty tools have that,
and several keep it better than this one does.

The differentiator is one row of the table: **everywhere else the spec is a
document the agent is asked to honour, and here it is one the agent cannot
edit** — refused by a hook during the run, re-checked by a script in CI where no
agent is running at all. A survey of the field puts it plainly: multi-agent
adversarial review and CI-gated spec enforcement are largely absent, because most
tools trust adherence rather than enforcing it. That combination — a frozen
pre-code spec, a blind panel measured against it, one lens that operates the
software, and machine-checked rules outside the agent's reach — is the thing that
does not appear to exist elsewhere.

Not better on cost, not better on portability, not better on the long-lived spec,
and not better on measured defect-catching — nobody in this field has measured
that, which is a gap available to whoever measures it first. Not a substitute for
a human reading the pull request. The honest claim is narrower than "better": it
is a system that makes it hard to quietly ship something other than what was asked
for, and that leaves behind enough evidence to tell when it did.
