# Test-quality review

- **Lens:** test-quality
- **Verdict:** findings
- **Diff range:** `bce043280170d6b26593b77d13cd591b52528e81...HEAD`

## Findings

### F1 — frontmatter_tools() parses a YAML block-sequence `tools:` list as an empty tool list, so the AC10 read-only guard passes silently when quorum-auditor is granted Write/Edit

- **Severity:** major
- **File:** `plugins/quorum/bin/selftest.py`
- **Line:** 1153

**What:**

`raw = line.split(':', 1)[1].strip().strip('[]')` returns '' for a `tools:` line whose value is on following lines, so the function returns `[]` — indistinguishable from "grants nothing". The docstring one line above warns that None must not be conflated with "no tools"; the block-sequence case makes the opposite conflation and no check notices.

**Failure scenario:**

I copied plugins/quorum to a scratch dir and rewrote quorum-auditor.md's frontmatter as `tools:\n  - Read\n  - Grep\n  - Glob\n  - Bash\n  - Write\n  - Edit` — a valid YAML list granting the auditor two file-editing tools. `python3 bin/selftest.py` printed 198/198 passed, no FAIL. The same grant written inline (`tools: Read, Grep, Glob, Bash, Write`) correctly produces `FAIL audit.js: quorum-auditor grants no file-editing tool — grants ['Write']`. So AC10's stated property ("fails when workflow/audit.js ... names an agent whose definition grants a file-editing tool") holds only for one of two ordinary ways to write the field, and the single mechanical guarantee behind running on `main` is defeated by a reformat. Note the exempt scribe is safe by accident: block-style there yields writes=[] and trips the `bool(writes)` half of the exemption check.

**Suggested direction:**

Parse the frontmatter block as YAML (or handle the `tools:` + indented `- item` continuation lines), and treat an empty parsed list on a workflow-named agent as a failure rather than a pass — an agent that declares `tools:` with nothing under it is a parse the check does not understand, not a proven-safe agent.

### F2 — The reflow case in test_audit does not vary what its comment says it varies; two of criteria_hash's three normalisation rules are uncovered

- **Severity:** minor
- **File:** `plugins/quorum/bin/selftest.py`
- **Line:** 1066

**What:**

The comment reads "Same list, reflowed: trailing space, a blank line, a ticked checkbox", but the reflowed body only adds a trailing space and one blank line immediately after the `## Criteria` heading — which `body.strip()` removes, never reaching the blank-run collapse — and CRITERIA contains no checkbox at all.

**Failure scenario:**

Deleting `body = re.sub(r'^(\s*[-*]\s*)\[[ xX]\]', r'\1[ ]', body, flags=re.M)` from audit.py:86 leaves the suite green (198/198 in the scratch copy). Deleting `body = re.sub(r'\n{3,}', '\n\n', body)` from audit.py:88 also leaves it green. Only the `line.rstrip()` rule is genuinely covered (removing it produces 2 FAILs). Concretely: if the blank-run collapse were dropped in a later refactor, a user who adds a blank line between two criterion bullets after the gate — a pure reformat — gets `MISMATCH criteria.md has changed since its hash was recorded` and is told to re-run the whole audit, with no test to catch the regression.

**Suggested direction:**

Put a real `- [ ]`/`- [x]` bullet and a two-blank-line run inside the CRITERIA fixture's `## Criteria` section so the reflowed variant exercises all three rules, or drop the untrue clauses from the comment.

### F3 — No test covers a report.md that cites no Criteria hash at all, so that AC5 branch can regress unnoticed

- **Severity:** minor
- **File:** `plugins/quorum/bin/selftest.py`
- **Line:** 1015

**What:**

The REPORT template always contains `- **Criteria hash:** %s`, and every report case in test_audit supplies a value (the correct hash, or 64 zeros). The `result['cited'] is None` violation in audit.py:145-147 is therefore never exercised.

**Failure scenario:**

Replacing audit.py's `if result['cited'] is None: violations.append(...)` with a no-op leaves the suite green (198/198 in the scratch copy). The scenario that branch exists for is live: audit.js:18 defaults `criteriaHash` to `''` when the skill omits it, the scribe then writes `- **Criteria hash:** ` with an empty value, `field()` returns None, and `--verify` would report the audit clean — AC5's "report.md cites that hash" silently unenforced, with no failing test.

**Suggested direction:**

Add one case that writes a report.md with the hash line absent (or empty) and asserts `--verify` exits 1.

### F4 — The controlled fixture ships tests that cannot pass, and the answer key cites one of them as the evidence for a `met` status

- **Severity:** minor
- **File:** `docs/fixtures/audit-demo/test/server.test.js`
- **Line:** 19

**What:**

`src/server.js:8` builds KEYS from `process.env.WIDGET_API_KEYS`, and `test/helper.js` sets no environment, so KEYS is empty and every request 401s. The X-Request-Id test (which asserts a header the 401 path never sets, since `unauthorized()` writes no headers) and the rate-limiter test (which expects 429) both fail as written. docs/fixtures/README.md:41 nevertheless justifies criterion 2's `met` with "asserted in test/server.test.js".

**Failure scenario:**

The fixture is the oracle the behavior lens compares report.md against, so its answer key has to be defensible. An auditor that reads test/helper.js alongside src/server.js:8 can correctly observe that the only test asserting X-Request-Id cannot pass, and return criterion 2 as `unverified` with that reason. Measured against the answer key it is marked wrong — a false AC6 failure caused by the fixture, not by the audit. The reverse is equally bad: a reviewer who spots it may conclude the fixture is not the controlled artifact the plan requires.

**Suggested direction:**

Have test/helper.js set `process.env.WIDGET_API_KEYS = 'test-key,burst-key'` before requiring src/server.js so the shipped tests are consistent with the code, or drop the "asserted in test/server.test.js" justification from the answer key and rest criteria 1 and 2 on src/server.js alone.

## Notes

Method: the repo suite is green at 207/207 as committed. To answer \"would this test fail if the behaviour it guards broke?\" I copied plugins/quorum into the scratchpad (baseline 198/198 there — 9 checks need the repo root) and ran targeted mutations against the copy only; the repo tree is unmodified (git status shows only the pre-existing docs/work/quorum-audit/state.json edit). Mutations that the suite correctly caught, and are therefore not findings: dropping the per-line rstrip in criteria_hash; hashing the whole file instead of the ## Criteria section; removing the cited!=computed violation; quorum-auditor granted Write inline or as `[Read, ..., Write]`; quorum-auditor with no tools: field; quorum-scribe granted Read. Removing the \"criteria.md records no hash\" violation is an equivalent mutant (the adjacent recorded!=computed branch still exits 1), so it is not reported. Not reported as findings, for the record: workflow/audit.js's deterministic merge logic (cluster dedup, the unclustered sweep, the gap-without-searches downgrade at lines 189-328) has no mechanical test — but the plan's Test strategy assigns AC6/AC8 to the behavior lens and C8 records that the repo has no JS test runner, so this is a stated deferral rather than a defect. Also noted and dropped: WRITE_TOOLS classifies Bash as a read tool, so the module docstring's claim that audit.js's agents \"cannot write to the repository they are auditing\" overstates what the check establishes for an agent granted Bash — I could not construct a concrete regression scenario that is not really a prompt-behaviour question, which is the behavior lens's ground.
