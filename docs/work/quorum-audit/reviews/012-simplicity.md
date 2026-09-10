# Review: simplicity

- Lens: simplicity
- Verdict: findings
- Diff range: a22d7e7...HEAD (plus uncommitted working-tree changes)

## Findings

### F1 — minor — plugins/quorum/workflow/audit.js:133

**Claim:** Removing Bash from quorum-auditor makes the whole ranNothing self-report path dead — it can no longer detect anything true, and its only remaining output is a false alarm printed into the report.

**What:** AUDIT_SCHEMA still requires a `ranNothing` boolean (audit.js:129,133-136), the audit prompt still asks for it (audit.js:307), audit.js still computes `ranSomething` and logs a WARNING (323-329), builds a verbatim `## Ran during the audit` block for the scribe (500-506, injected at 517), returns `ranNothing` (577), and SKILL.md:238-241 still tells the operator to surface it above the findings. quorum-auditor.md:4 now grants `Read, Grep, Glob` only, so no agent audit.js names can execute anything — selftest.py's new EXEC_TOOLS check (selftest.py:1393-1397) enforces exactly that. The condition this ~25 lines of machinery watches for is now impossible by tool grant, and the diff's own comment at audit.js:71-74 reasons about keeping NEVER_RUN while leaving this path untouched.

**Failure scenario:** An auditor holding only Read/Grep/Glob is asked to "confirm you executed nothing belonging to the repository under audit" and returns `ranNothing: false` — a plausible model answer given it did invoke Grep against that repository, and given the field is required so it must answer. audit.js then logs a WARNING and instructs the scribe to write, verbatim and above the Outcome section, "These clusters did not confirm that they executed nothing: <cluster>. Treat every finding below as coming from a run that may have started this software." The operator of a production repo reads a claim that their software may have been started, when the tool grant makes that impossible; SKILL.md:238-241 then requires the skill to repeat it above every finding. Every firing of this path is now necessarily a false positive.

**Suggested direction:** Either drop `ranNothing` from AUDIT_SCHEMA and remove the ranSomething/ranWarning/return-field/SKILL.md-step-6 chain that hangs off it, now that selftest.py asserts the grant mechanically; or, if it is being kept as defence in depth against someone re-granting a shell, say so in a comment beside the schema field and state what it is expected to catch given the check at selftest.py:1393.

## Notes

Most of the diff is prose restating one fact (the auditor holds Read/Grep/Glob and no shell) across audit.js, quorum-auditor.md, reference/audit.md, SKILL.md and selftest.py. That repetition is the repo's stated convention for prompt files (see the NEVER_RUN comment at audit.js:76) and each restatement has a different audience, so I did not file it. The SLUG regex duplicated between audit.py:46 and audit.js:22 is forced by a language boundary and documented as deliberate; not filed. audit.py's copied sections() is pre-existing and outside the range. Out of lens, so not filed as a finding: the uncommitted state.json deletes the log line "2026-08-27T09:26:58Z 1-plan planned 10 ACs..." and appends three entries out of chronological order.
