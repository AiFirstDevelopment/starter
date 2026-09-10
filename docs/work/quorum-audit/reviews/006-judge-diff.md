# Review 006 — judge-diff

- **Lens:** judge-diff
- **Verdict:** findings
- **Diff range:** 7ea8d21..d271ce6 (review.head..verdict.head, from docs/work/quorum-audit/state.json)

> **Scope note:** This review covers the judge's own adjudication commits, which no other lens saw.

## Findings

### F1 — major

**Claim:** The judge's adjudication is not fully committed: docs/work/quorum-audit/state.json has an uncommitted local modification recording the actual 'adjudicated/blocked' outcome, while the committed HEAD (d271ce6) still shows stage 'reviewed' with no review/verdict data.

**Location:** `docs/work/quorum-audit/state.json:3`

**What:** `git show HEAD:docs/work/quorum-audit/state.json` (HEAD = d271ce6, the judge's own commit) shows `"stage": "reviewed"`, `"updated": "2026-08-27T10:05:24Z"`, and a log ending at 'panel complete, adjudication started' — with no `review` or `verdict` object at all. The working tree, however, contains an uncommitted diff on top of that (`git status --porcelain=2` reports `.M` for this exact file) that adds `stage: "adjudicated"`, a `review` block, a `verdict` block (outcome: blocked, accepted: 13, rejected: 0, unmet: 10, escalations: 5), and a final log line '4-quorum adjudicated blocked — 13 accepted...'. The file's mtime (Aug 27 06:26:31, matching the commit's own author timestamp) shows it was written by the same judge run that made commit d271ce6, but that final write to state.json was never staged/committed.

**Failure scenario:** The verdict.md file (committed) and the commit message both assert the run is adjudicated and blocked with 13 accepted / 5 escalated findings, but the machine-readable state.json that this pipeline's own tooling (bin/state.py, bin/watch.py, and any subsequent /quorum:1-plan or resume logic that reads state.json to determine pipeline stage) actually reads still says stage 'reviewed' and carries no verdict record at all. Anyone who runs `git status` on this branch sees an unexpected dirty file; anyone who does `git checkout -- .` or a clean clone loses the adjudication record from state.json entirely, leaving a permanent mismatch between verdict.md's narrative and the tracked pipeline state.

**Suggested direction:** Stage and commit the pending state.json update (or fold it into the adjudication commit) so the committed HEAD's state.json matches the stage/verdict that verdict.md and the commit message describe.

---

### F2 — major

**Claim:** The slug-validation fix (security F2) is applied only to the scribe's report.md write path inside audit.js; the criteria.md write at Step 3 of SKILL.md, which uses the identical unsanitized slug and runs earlier (before the Workflow call and before the approval gate), is left with prose-only protection — the exact 'defeated by a reformat / prose is what a model can talk itself out of' failure mode this same commit calls out and fixes elsewhere.

**Location:** `plugins/quorum/skills/audit/SKILL.md:109`

**What:** audit.js:22-28 now rejects any `slug` that isn't `^[a-z0-9]+(-[a-z0-9]+)*$` before the Workflow tool's scribe agent is ever invoked, closing the path-escape hole for `reportPath = 'docs/audit/' + slug + '/report.md'` (audit.js:48). But `criteria.md` is written earlier and separately: SKILL.md Step 2-3 has the top-level orchestrating agent itself derive `<slug>` (explicit argument, spec basename, or free-text-derived words — reference/audit.md:23-37) and then, at SKILL.md:109, 'Write `docs/audit/<slug>/criteria.md`' via its own Write tool, entirely outside audit.js/the Workflow call. Nothing in bin/audit.py's `--hash`/`--verify` (invoked right after, SKILL.md:113) validates the path either — it just opens whatever `work_dir/criteria.md` it's given (audit.py:113-114). The only constraint on this slug is the prose in reference/audit.md:36-37 ('Lowercase, non-alphanumeric runs collapsed to a single -') and SKILL.md:70-72, both addressed to a model, not enforced by code.

**Failure scenario:** If the slug resolved at Step 2 contains `..` (e.g. an explicit slug the user supplies, or one influenced by an untrusted spec file's content/name per the original security review's own attack scenario), Step 3 writes criteria.md via the orchestrator's Write tool to a path outside docs/audit/ — e.g. `../../../tmp/x/criteria.md`, landing outside the repository entirely — before Step 4's approval gate and long before Step 5's Workflow call, where the new kebab-case check lives. The skill's own 'confirm nothing outside the audit directory moved' check (SKILL.md `git status --porcelain`, run only at Step 6) cannot see a file written outside the git working tree, so it reports a clean run — the identical false-clean-tree outcome that security F2 was raised against, just via the criteria.md write instead of report.md, and reachable without the fix in audit.js ever running. verdict.md's AC1 row says this hole is 'Closed in plugins/quorum/workflow/audit.js (SEC-F2)', which is only true for the scribe's write; the criteria.md write remains open.

**Suggested direction:** Give Step 2/3 the same mechanical guard, e.g. have `bin/audit.py` (or a new flag) validate/reject a non-kebab-case slug before criteria.md is written, rather than relying on the prose rule in reference/audit.md that a model is asked to follow — mirroring the fix already applied to audit.js's report path.

---

## Notes

Range confirmed directly from docs/work/quorum-audit/state.json's review.head (7ea8d21) and verdict.head (d271ce6) fields, so no fallback was needed. The range is a single commit (d271ce6, 'Adjudicate the audit review: close the read-only guard's reformat hole') touching 14 files. I verified several of the judge's own factual claims empirically rather than taking them on faith: (1) reverting frontmatter_tools to the pre-fix inline-only parser produces exactly 11 new selftest failures, matching the commit message; (2) the fixture's test/server.test.js genuinely failed 2 of 4 tests before the helper.js WIDGET_API_KEYS fix and passes 4/4 after, confirmed by running node --test against both versions in isolated temp dirs; (3) selftest.py passes 233/233 as claimed. Both findings above are things those spot-checks did not cover and that I verified independently by reading the surrounding code paths (SKILL.md Step 2/3, audit.py's verify(), and the actual working-tree git status). I did not find evidence of the review files (001-005) or verdict.md being altered from what the lenses produced, but I also have no earlier commit to diff them against (they land as new files in this same commit), so I can't rule that out — I did not report it as a finding since I can't attach a concrete failure scenario to it, only flag it here as a limit of what this lens could check.
