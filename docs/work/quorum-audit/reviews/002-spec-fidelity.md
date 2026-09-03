# Spec-fidelity review

- **Lens:** spec-fidelity
- **Verdict:** findings
- **Diff range:** `bce043280170d6b26593b77d13cd591b52528e81...HEAD (plus uncommitted docs/work/quorum-audit/state.json)`

## Findings

### F1 — AC10 is not met as written: selftest.py exits 0 while workflow/audit.js names quorum-scribe, whose definition grants Write. The PLAN DEFECT note is correct and must be escalated, because AC10 sits in the requirements-locked section that the builder may not edit.

- **Severity:** minor
- **File:** `plugins/quorum/bin/selftest.py`
- **Line:** 1247

**What:**

AC10 requires selftest to fail when audit.js "names an agent whose definition grants a file-editing tool". audit.js:481 names `quorum:quorum-scribe`; agents/quorum-scribe.md:4 declares `tools: Write`, which selftest itself classifies as a WRITE_TOOL at line 52. Lines 1247-1253 exempt it by name via WRITE_ONLY_EXEMPT.

**Failure scenario:**

Run `python3 plugins/quorum/bin/selftest.py` on HEAD with audit.js naming quorum-scribe (a Write-granting agent): it prints 207/207 passed and exits 0. AC10's second condition therefore does not hold on the shipped tree. I confirmed the exemption is the only reason: granting quorum-auditor Write on a scratch copy produces `FAIL audit.js: quorum-auditor grants no file-editing tool — grants ['Write']`, while the scribe's identical Write grant is silently accepted. AC10 as worded is unsatisfiable alongside Approach ("Reuse quorum-scribe for the report") and S5 ("then have the scribe write report.md"), so it cannot be closed by code — it needs an AC wording decision, and Acceptance criteria is one of guard.py's REQUIREMENT_SECTIONS (guard.py:85), so the builder could not make it.

**Suggested direction:**

Judge should settle AC10's wording explicitly rather than leaving the plan contradicting the shipped check — e.g. reword to "names an agent that can both read the repository under audit and edit it", or record the write-only-scribe carve-out in the AC itself. The mechanically-constrained exemption in the code is a reasonable resolution; what is missing is the recorded decision.

### F2 — The comment justifying the new selftest check claims a mechanical guarantee the agent definitions do not provide: quorum-auditor grants Bash, which selftest classifies as a READ tool, so writing to the audited repository is prevented only by prose.

- **Severity:** minor
- **File:** `plugins/quorum/bin/selftest.py`
- **Line:** 1229

**What:**

Lines 1227-1231 assert "nothing the script starts can write to that repository. That is a property of the agent definitions rather than of the prompts, so it is settled here instead of being promised in prose." READ_TOOLS at line 53 includes `Bash`, and agents/quorum-auditor.md:4 grants `Read, Grep, Glob, Bash`.

**Failure scenario:**

An auditor agent launched by audit.js runs `sed -i '' 's/x/y/' src/app.js` or `echo >> config.yml` in the repository under audit. Nothing in any agent definition blocks it — only prose (quorum-auditor.md:10-11 and the NEVER_RUN string in audit.js:41). The run then violates AC1 (`git status --porcelain` lists a path outside `docs/audit/`), and the check the comment says "settles" this still passes, because Bash is counted as a read tool. The build note's PLAN DEFECT resolution rests on the same overstated property ("nothing which can read the audited repository can write to it").

**Suggested direction:**

Either soften the comment (and the build-note rationale) to say what the check actually settles — no declarative file-editing tool — or state explicitly that Bash write-capability is accepted and mitigated by prompt, so a later reader does not trust a guarantee that is not there.

### F3 — Nothing ties the criteria the auditors actually measure to the criteria.md the hash covers, so AC5's stated consequence — that criteria softened mid-run are detectable by re-hashing the file — does not hold for the skill-to-workflow hand-off.

- **Severity:** minor
- **File:** `plugins/quorum/workflow/audit.js`
- **Line:** 18

**What:**

`criteriaHash` is accepted as an opaque string (defaulting to `''`) and echoed verbatim into the report header at line 449. `args.criteria` (line 15) is an independent value that is never checked against it. audit.py --verify only compares criteria.md's own text, criteria.md's recorded field, and report.md's cited field.

**Failure scenario:**

SKILL.md:138 explicitly supports amendment at the gate: "If the user amends the criteria, rewrite criteria.md, re-record the hash, and show the amended list again." Suppose the skill rewrites criteria.md with the amended list and re-records hash H', but at Step 5 hands `criteria:` the pre-amendment array (built separately in the Workflow call). The auditors measure the superseded list; the scribe writes report.md citing H'; `python3 plugins/quorum/bin/audit.py --verify docs/audit/<slug>` recomputes H' from criteria.md, sees report.md citing H', and prints "clean", exit 0. Step 6 then reports to the user that the report was measured against the approved list. It was not, and re-hashing the file cannot show it — contradicting AC5's "so a report audited against criteria that were softened mid-run is detectable by re-hashing the file" and reference/audit.md:111-113 ("makes 'this report was audited against these criteria' checkable rather than assumed"). A related, louder variant: if `criteriaHash` is omitted, audit.js writes an empty `- **Criteria hash:**` line and --verify exits 1 with "report.md cites no Criteria hash", which SKILL.md:193 tells the user means the report and criteria are different lists.

**Suggested direction:**

Make audit.js derive (or at minimum re-render and hash) the criteria it was handed and compare against `args.criteriaHash`, failing loudly on mismatch; and require `criteriaHash` the way `slug` and `criteria` are required at lines 13 and 16, rather than defaulting to empty.

## Notes

Verified and found sound, so not reported as findings: (1) All eight Approach claims — C1 (skills discovered from skills/<name>/SKILL.md, README:1070, plugin.json has no skills list), C2 (pipeline.js uses quorum:<agent> at 8 sites), C3 (base selftest.py:1050-1053 is exactly the "wired into the pipeline" assertion), C4 (substance holds; plan-lock-hook.py matches at line 25 not 35 — build note records this correctly), C5 (no docs/audit reference in plugins/ at base), C6 (pipeline.js contains no `pipeline(` call — build note records this correctly), C7 (both manifests were 0.23.0 and are both now 0.24.0), C8 (.github/workflows/selftest.yml:27 runs selftest.py, no other runner). (2) All four recorded Deviations hold against the code: the no-searches downgrade (audit.js:319-328), cluster dedup + unclustered sweep + missing-criterion sweep (audit.js:189-208, 304-314), the committed fixture, and the extra README edits. (3) I independently checked the fixture answer key against the fixture: criterion 1 met (server.js:18-19 + both tests), criterion 2 met (server.js:16 + test), criterion 3 genuinely a gap (`grep -rniE 'retry|retri|backoff|attempt'` over audit-demo matches only spec.md:21-22; upstream.js:6-10 calls once), criterion 4 runtime-only, extras present (ratelimit.js, /metrics at server.js:31), and nothing logs. The answer key is outside audit-demo/ as claimed. (4) Non-goals were respected: no source edits, no branch/commit/push logic, no behaviour pass in audit.js (four phases only), no changes to guard.py/history.py/watch.py/plan-lock-hook.py/status skill/pipeline.js/the four numbered steps/reference/contract.md, no .github changes, no CI gate wiring, extra-implementation prohibition repeated in the agent, both prompts, and the reference. (5) PLAN DEFECT #2 (the stale "run one behaviour pass" line at plan.md:154) holds up and is correctly resolved by following AC11/Non-goals; note that Approach is not in guard.py's REQUIREMENT_SECTIONS, so that stale line could simply be struck without a lock override. (6) The four probes the build note claims all reproduce on a scratch copy: bogus agentType, auditor granted Write, scribe granted Read, audit.js deleted — plus an agent with no `tools:` field. The working tree was not modified.
