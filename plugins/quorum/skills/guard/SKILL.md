---
name: guard
description: Runs the mechanical checks on the current work item - requirements unchanged, no test weakened, reviews append-only, verdict self-consistent, evidence real - and can install them as a CI gate. Reports violations; fixes nothing.
---

# Guard — the rules that are not opinions

Every other rule in this pipeline is a sentence in a prompt, which is a rule an
agent can talk itself out of at 2am with a red suite and no human awake. These
are the ones a machine can settle, so a machine settles them.

## What it checks

| Rule | Violation |
|---|---|
| `requirements` | *Intent*, *Acceptance criteria*, or *Non-goals* changed since the plan was written |
| `tests` | a test file deleted, test cases removed, or a new `skip` / `only` marker |
| `reviews` | an existing review file modified or deleted — the record is append-only |
| `verdict` | `ready` over a red suite, alongside open escalations, or with an unmet criterion |
| `coverage` | a criterion in the plan is missing from the verdict, or the verdict invented one |
| `evidence` | a criterion marked met cites a file, or a line, that does not exist |
| `branch` | work item artifacts sitting on the default branch |

`coverage` closes the quietest way to pass: an unmet criterion **omitted** from
the verdict reads exactly like success. Silence about AC4 is not evidence about
AC4.

`only` deserves its own mention: one `it.only(...)` disables every other test in
the file while the suite still reports green. It is the quietest way to buy a
passing run, and it is invisible in a summary line that says "42 passed".

## Running it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/guard.py"                    # this work item
python3 "${CLAUDE_PLUGIN_ROOT}/bin/guard.py" --base origin/main # explicit base
python3 "${CLAUDE_PLUGIN_ROOT}/bin/guard.py" --json             # for a script
```

Exit `0` clean, `1` violations, `2` could not run. Report what it says and stop.

**A violation is not a finding.** Findings are claims a judge weighs and may
reasonably reject. These are rules the pipeline states it does not break, so the
only correct responses are to undo the change or to tell the user plainly that a
rule was broken and why. Never adjudicate one away.

## Installing the CI gate

Everything above still runs *inside* the session, which means an agent could
skip it. The version that cannot be skipped runs on a CI runner where no agent
exists:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/guard.py" --install-ci
```

That vendors `guard.py` to `.quorum/guard.py` and writes
`.github/workflows/quorum-guard.yml`. It vendors rather than referencing the
plugin because CI runners have no plugin installed.

**Re-run it whenever the plugin updates.** The vendored copy is frozen at the
rules it was written with, so a repo that adopted a year ago is still enforcing
that year-old set — and reporting green while it does. The guard raises a
`vendored` violation as soon as `.quorum/guard.py` stops matching the checker it
came from, which is the only signal you get; nothing about a stale copy looks
wrong from the outside. `guard.py --version` says which rule set a copy carries.

Commit both, then **make `quorum guard` a required status check** in the
repository's branch protection settings. Until that box is ticked the workflow
reports and nothing more; after it, a violation blocks the merge no matter what
any verdict claims. That last step is in the hosting UI and nobody but a repo
admin can do it — say so rather than implying the gate is live.

Whether it is live is checkable rather than assumed:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/guard.py" --check-gate
```

`/quorum:pipeline` runs this on every publish and puts the answer in the pull
request body, so the question gets asked on its own rather than only when someone
remembers to. It reports LIVE, NOT LIVE, or that it could not tell — and
**`could not tell` is never rounded up to a pass**. It does not draft the pull
request over a missing gate: protecting the branch is the repository owner's
decision, not a defect in the change under review.

Deleting the vendored checker is itself a violation. `enforcement` watches for
either `.quorum/guard.py` or its workflow disappearing — including both at once,
which is what switching the gate off actually looks like — and for the
half-installed states where one exists without the other. A repo that never
vendored has neither and hears nothing.

It reports `LIVE`, `NOT LIVE`, or `cannot tell` — and `cannot tell` (no `gh`, or
no admin rights to read branch protection) is reported as its own answer rather
than rounded up to a pass.

## Testing the checker itself

The guard is now what the pipeline's promises rest on, so it has its own suite:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/selftest.py" -v
```

It builds throwaway repositories, breaks each rule deliberately, and asserts the
rule fires — and that legitimate edits (ticking a checkbox, appending a review,
editing *Approach*) are still allowed. A checker that cannot be shown to fail is
exactly the merge gate this project tells everyone else not to trust.

## The one rule enforced before the fact

The plan's requirements are also protected by a `PreToolUse` hook that refuses
any edit changing *Intent*, *Acceptance criteria*, or *Non-goals*, at the moment
it is attempted. Ticking checkboxes and editing *Approach*, *Steps*, or *Build
notes* are all allowed. It fails open: a broken hook must not wedge every edit in
the repo.

If an agent reports being blocked by it, that is the system working. The answer
is to escalate the plan defect, not to find another way to write the file.
