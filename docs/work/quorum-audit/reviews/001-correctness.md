# Correctness review

- **Lens:** correctness
- **Verdict:** findings
- **Diff range:** `bce043280170d6b26593b77d13cd591b52528e81...HEAD`

## Findings

### F1 — The AC10 read-only guard silently passes an audit agent granted a write tool, because frontmatter_tools mis-parses valid YAML `tools:` forms

- **Severity:** major
- **File:** `plugins/quorum/bin/selftest.py`
- **Line:** 1153

**What:**

`frontmatter_tools` takes the text after `tools:`, strips only `[]`, and splits on commas. A quoted scalar (`tools: "Read, Grep, Write"`) yields ['"Read', 'Grep', 'Write"'] and a YAML block sequence yields []. Neither result intersects WRITE_TOOLS, so the check at line 1254 sees `writes == []` and reports PASS. The function returns None (which fails loudly) only when there is no `tools:` line at all.

**Failure scenario:**

Change plugins/quorum/agents/quorum-auditor.md frontmatter to `tools: "Read, Grep, Glob, Bash, Write"` — semantically identical YAML to today's line, and the agent really does gain Write at runtime. `python3 plugins/quorum/bin/selftest.py` still prints 207/207 and the check 'audit.js: quorum-auditor grants no file-editing tool' passes. The one mechanical guarantee that makes /quorum:audit safe on a default branch (plan AC10, and the comment at selftest.py:1220-1224 that says this is 'a property of the agent definitions, not a promise in a prompt') is defeated by quoting a string. I confirmed this by calling frontmatter_tools on scratch files: comma form -> writes=['Write'] (FAIL, correct); quoted form -> writes=[] (PASS); block-sequence form -> writes=[] (PASS); bracketed-and-quoted form -> writes=[] (PASS). Note the failure is asymmetric: the same mis-parse makes the quorum-scribe exemption check fail loudly, so only the dangerous direction fails open.

**Suggested direction:**

Parse the frontmatter block with a real YAML load (or at minimum strip quotes and handle the `-` block-sequence continuation lines), and treat an unparseable `tools:` value as None — inherit-everything — so the check fails closed rather than open.

### F2 — The criteria hash is computed over criteria.md but the auditors measure args.criteria; nothing links the two, so a clean `--verify` does not prove what the skill and README say it proves

- **Severity:** major
- **File:** `plugins/quorum/workflow/audit.js`
- **Line:** 18

**What:**

`criteriaHash` is accepted as an opaque string and stamped into report.md's header (line 449), while the criteria actually audited come from `args.criteria` (line 15). bin/audit.py hashes only the `## Criteria` section of criteria.md and compares it to the string report.md cites. Nothing anywhere checks that args.criteria is the same list criteria.md holds.

**Failure scenario:**

criteria.md records AC2 as 'when a charge fails with a retryable gateway error, it is retried three times with exponential backoff', hashes to H, and the user approves that list at the gate. When the skill builds the Workflow args it paraphrases AC2 as 'charge failures are handled' (a prompt-driven step with no mechanical check). The auditors measure the paraphrase, return `met`, and the scribe writes report.md citing H. `python3 plugins/quorum/bin/audit.py --verify docs/audit/<slug>` exits 0 and prints 'clean', and SKILL.md:192 instructs the skill to tell the user this means the report was measured against the approved list. It was not. This is precisely the softened-mid-run case AC5 exists to detect, moved one hop to the side of where the hash looks.

**Suggested direction:**

Close the loop over the list that is actually audited: have the skill derive criteria.md from the same structured list it passes as args.criteria (or add an `audit.py --hash-list` mode the skill runs over the args before launching), and have audit.js refuse to run when the two disagree.

### F3 — `audit.py --verify` exits 0 when report.md does not exist, but SKILL.md documents exit 0 as meaning report.md cites the matching hash

- **Severity:** minor
- **File:** `plugins/quorum/bin/audit.py`
- **Line:** 141

**What:**

`verify()` returns 0 as soon as report.md is absent, provided criteria.md's own recorded hash matches. The distinction survives only in `result['notes']` (human output) and `result['reported']` (--json); the exit code cannot tell 'the report cites the right hash' apart from 'there is no report'.

**Failure scenario:**

The scribe agent in audit.js fails to write docs/audit/<slug>/report.md (it returns without writing, or writes to a different path). The skill reaches Step 6, runs `audit.py --verify docs/audit/<slug>` without --json, gets exit 0, and follows SKILL.md:192 — 'Exit 0 means criteria.md still hashes to what it recorded and report.md cites that same hash' — so it reports the run as verified and summarises the workflow's returned gap counts as though a checked report backed them. The verification step passes on a run that produced no report at all.

**Suggested direction:**

Either add a flag (e.g. `--expect-report`) that the skill passes after a completed run so a missing report.md is a violation, or have Step 6 check `--json`'s `reported` field rather than the exit code alone.

### F4 — audit.js validates slug and criteria but not criteriaHash, so a missing hash costs a full multi-agent run and ends in a false 'measured against different criteria' verdict

- **Severity:** minor
- **File:** `plugins/quorum/workflow/audit.js`
- **Line:** 18

**What:**

`slug` (line 13) and `criteria` (line 16) throw immediately when absent; `criteriaHash` silently defaults to ''. AC5 makes the hash as load-bearing as the other two.

**Failure scenario:**

The skill launches the Workflow without `criteriaHash` (a prompt-assembled arg list; the script's author already anticipated this class of omission for two other args). Clustering, N parallel auditors, the refutation pass and the scribe all run to completion. The scribe is told 'Header fields, exactly these: ... - **Criteria hash:** ' with an empty value, so report.md's header line carries no value and `field()` in audit.py returns None. `--verify` then raises the violation 'report.md cites no "Criteria hash", so which criteria it measured is unknowable' and exits 1, and SKILL.md:193-195 tells the user the report and the criteria are not the same list and to re-run the whole audit — when in fact the criteria never changed. The failure is detectable for free before any agent runs.

**Suggested direction:**

Throw at the top of audit.js when args.criteriaHash is empty, matching the guards already there for slug and criteria.

### F5 — `proposedChange` is optional and unenforced, so a gap can reach report.md without the observable restatement AC9 and the report format require

- **Severity:** minor
- **File:** `plugins/quorum/workflow/audit.js`
- **Line:** 121

**What:**

AUDIT_SCHEMA marks `proposedChange` optional (only id/status/evidence are required). `searched` is equally optional in the schema but is enforced after the fact at lines 319-328 (a gap with no searches is downgraded to unverified); no equivalent check exists for `proposedChange`, even though reference/audit.md:169 makes '**Proposed change:**' a required element of every gap section and AC9 requires every gap to be phrased as a criterion /quorum:1-plan can consume.

**Failure scenario:**

An auditor returns {id: 'AC3', status: 'gap', evidence: '...', searched: 'rg -n retry src/ — no match'} and omits proposedChange. The gap survives the searched check and the refutation pass, and the scribe is told at line 459 to head the section '<id> — <the proposed change, as an observable criterion>' and to include 'the proposed change', while also being told at line 472 'Do not merge, reword, reorder, drop, add, or soften anything' — so it has nothing to write there and no licence to invent it. The resulting Gaps section is missing the required Proposed change, and the closing /quorum:1-plan invocation points at a report whose gap is not stated as an acceptance criterion.

**Suggested direction:**

Give proposedChange the same post-hoc treatment as searched: when a gap has none, fall back to the criterion's own text (the skill already requires criteria to be in the 'when <situation>, <observable result>' form) and say so, rather than leaving the scribe with a blank.

## Notes

Verified by running `python3 plugins/quorum/bin/selftest.py` (207/207 green; working tree unchanged) and by exercising `selftest.frontmatter_tools` against scratch agent files in the scratchpad — no repository file was modified. The fixture under docs/fixtures/audit-demo/ was read and cross-checked against its answer key in docs/fixtures/README.md; the four statuses in the key match the fixture code (upstream.js calls the store once, server.js checks KEYS first and sets X-Request-Id, /health timing is a runtime property). Note in passing that test/server.test.js's third and fourth tests cannot pass as written because WIDGET_API_KEYS is never set, but the fixture is documented as never being executed, so I did not raise it as a finding.
