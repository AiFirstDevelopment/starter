# Audit artifact contract

`/quorum:audit` measures a repository against a spec. It is the one quorum
command that runs on the default branch, and it is safe there because it writes
no code — so its artifacts live apart from the pipeline's, under `docs/audit/`,
and nothing that reads `docs/work/` ever sees them.

```
docs/audit/<slug>/
├── criteria.md          # written by /quorum:audit before the gate
└── report.md            # written by workflow/audit.js, only after the gate
```

Two files, and the order matters: `criteria.md` exists before anything audits
anything, and `report.md` exists only once a human has read the criteria and said
yes. A directory holding `criteria.md` and no `report.md` is not a failed run —
it is the ordinary shape of a run that stopped at the gate.

`docs/audit/` accumulates one directory per audit and never loses one, the same
way `docs/work/` does. Re-auditing the same spec overwrites that spec's two files;
auditing a different spec gets its own slug.

## Resolving `<slug>`

The pipeline derives its slug from the branch. An audit cannot: it runs on `main`
by design, and the contract for `docs/work/` explicitly refuses a slug derived
from the default branch. So an audit's slug comes from the **spec**, in this
order:

1. An explicit slug passed to the skill.
2. The spec file's basename, when the spec is a file in the repo —
   `docs/specs/billing-api.md` gives `billing-api`.
3. Two to four kebab-case words naming the spec's subject, when the spec is free
   text. `payment-retries`, not `spec` or `audit-1`.

Lowercase, non-alphanumeric runs collapsed to a single `-`, exactly as the
pipeline's contract does it.

## What may be written

**`docs/audit/<slug>/` and nothing else.** No source file, no test, no config, no
commit, no branch, no push. After a complete run, `git status --porcelain` lists
changed paths under `docs/audit/` and nothing anywhere else — that is the
property the whole design rests on, and it is what makes running on `main` safe.

The audit also never **executes** the repository under audit: not its
application, not its build, not its test suite, not a script it ships. The shell
is for searching and reading. A criterion that could only be settled by running
the software is `unverified`, never `gap`.

## The status vocabulary

Every criterion ends with exactly one of three statuses. They are not
interchangeable and none of them may be omitted.

| Status | Means | Requires |
|---|---|---|
| `met` | the code and tests show the criterion is implemented | a file and a line, or a named test |
| `gap` | the criterion is not implemented | the searches that came back empty — patterns and paths |
| `unverified` | the audit could not settle it from code and tests alone | the reason, in one sentence |

`unverified` is a real answer and the honest one for a whole class of criteria:
anything that turns on runtime behaviour, on data the repository does not
contain, or on an area the requested scope excluded. **Never round it up to
`met`, and never down to `gap`** — absence of runtime evidence is not evidence of
absence.

**Implementation beyond the spec is never a finding.** Behaviour the repository
has and the spec never mentions does not appear in the report at all: not as a
gap, not as an observation, not as a suggestion to remove it. The question this
command answers is whether the spec is implemented faithfully, not whether the
repository contains only the spec.

## `criteria.md`

Written by the skill, before the gate. Every criterion cites where in the spec it
came from — a quoted phrase, with a heading or a `file:line`. **A criterion that
cites nothing is not written**, because a criterion with no source is one the
audit invented, and the repository is about to be measured against it.

````markdown
# Audit criteria: <short title>

- **Slug:** <slug>
- **Spec:** `docs/specs/billing-api.md` — or `free text supplied to /quorum:audit`
- **Derived:** <ISO 8601 date>
- **Criteria hash:** <sha256, from bin/audit.py --hash>

## Spec

Verbatim, when the spec was supplied as free text — this file is then the only
record of what was audited against. Omit this section when the spec is a file in
the repository; the file is the record, and copying it here creates a second one
that can drift.

## Criteria

- **AC1** — when a request arrives with no bearer token, the API answers 401.
  - Source: "every endpoint requires a bearer token" — `docs/specs/billing-api.md:14`, under *Security*
- **AC2** — a failed charge is retried three times with exponential backoff.
  - Source: "retry three times, backing off exponentially" — *Retries*
````

Criteria are observable statements in the form `/quorum:1-plan` uses — "when
`<situation>`, `<observable result>`" — because a gap in the report becomes an
acceptance criterion in a plan, and rewriting it at that point loses the citation.

## The criteria hash

`criteria.md` records a hash over its own `## Criteria` section, and `report.md`
cites the same hash. The two matching is what makes "this report was audited
against these criteria" checkable rather than assumed — criteria softened between
the gate and the report change the hash, and re-hashing the file finds it.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit.py" --hash docs/audit/<slug>/criteria.md
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit.py" --verify docs/audit/<slug>
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit.py" --verify docs/audit/<slug> --expect-report
```

`--hash` prints the hash of the criteria list. `--verify` recomputes it, compares
it against the hash `criteria.md` recorded and against the one `report.md` cites,
and exits non-zero if any of the three disagree. A directory with no `report.md`
verifies clean, because that is the ordinary shape of a run that stopped at the
gate; `--expect-report` says the run was meant to produce one, and makes its
absence a violation rather than a silence that reads as a pass.

**What the hash does not cover.** It fixes what `criteria.md` says. The auditors
measure the list the skill hands to `workflow/audit.js`, and nothing mechanical
checks that the two are the same — the skill writes both, and it is required to
copy rather than restate. A clean `--verify` therefore proves the criteria were
not edited after the gate; it does not prove the auditors were given them.

The hash covers the `## Criteria` section only. Everything else in the file —
the title, the spec reference, the date, the hash line itself — is outside it, so
recording the hash does not change the thing being hashed.

## `report.md`

Written after the gate, by the scribe in `workflow/audit.js`, from findings the
auditors returned. Every criterion in `criteria.md` appears exactly once, with
exactly one status.

````markdown
# Audit report: <short title>

- **Slug:** <slug>
- **Spec:** `docs/specs/billing-api.md`
- **Criteria hash:** <sha256 — must equal the one in criteria.md>
- **Audited:** <ISO 8601 date>
- **Commit:** <short SHA the audit read>

## Outcome

All clear

— or —

2 gaps and 1 unverified, out of 9 criteria.

## Criteria

| # | Criterion | Status |
|---|---|---|
| AC1 | when a request arrives with no bearer token, the API answers 401 | met |
| AC2 | a failed charge is retried three times with exponential backoff | gap |
| AC3 | the nightly reconciliation completes within 10 minutes | unverified |

## Gaps

### AC2 — a failed charge is retried three times with exponential backoff

**Searched, no match:** `rg -n 'retry|backoff|attempt' src/ lib/`; `rg -n 'retr' tests/`;
`src/billing/charge.js` calls the gateway once and returns its error.

**Refutation:** upheld — a second pass looked for a retry in the gateway client,
in middleware, and in the queue consumer, and found none.

**Proposed change:** when a charge fails with a retryable gateway error, retry it
three times with exponential backoff before surfacing the failure.

## Unverified

### AC3 — the nightly reconciliation completes within 10 minutes

**Why:** this turns on runtime behaviour. The audit reads code and tests and runs
neither, so nothing here can time a job. `src/jobs/reconcile.js` exists and is
scheduled nightly; whether it finishes inside ten minutes is not a question the
source answers.

## Met

- **AC1** — `src/http/auth.js:22` rejects a missing `Authorization` header with
  401; `tests/auth.test.js:9` asserts it.

## Next

```
/quorum:1-plan Close the gaps in docs/audit/<slug>/report.md — AC2 and AC5,
quoted there as acceptance criteria.
```
````

Rules for the report:

- **Every criterion appears, exactly once, with exactly one status.** A criterion
  missing from the report is indistinguishable from one that passed, which is the
  quietest way an audit can lie.
- **When every criterion is `met`, the Outcome line reads `All clear`** and the
  *Gaps* section is empty. That is the deliverable in the case the user cares
  about most, and it is one line.
- **Every gap names the searches that came back empty** — the patterns and the
  paths — so a reader can re-run them and disagree. "I did not find it" without
  saying where you looked is not evidence, and negative claims are the ones this
  command gets wrong most easily.
- **Every gap is phrased as an observable criterion** in the form
  `/quorum:1-plan` can consume, and the report ends by naming the
  `/quorum:1-plan` invocation that takes the report as input. A gap is the start
  of a work item; leaving it as prose costs a translation nobody checks.
- Omit an empty section rather than writing "None" into it — except *Gaps*, which
  stays, empty, so that "All clear" has something to be empty about.
