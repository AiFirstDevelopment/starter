# Security review

- **Lens:** security
- **Verdict:** findings
- **Diff range:** `bce043280170d6b26593b77d13cd591b52528e81...HEAD (plus uncommitted working-tree changes)`

## Findings

### F1 — The mechanical "nothing that audits the repo can write to it" guarantee is false: `Bash` is classified as a read tool, so `quorum-auditor` passes the new check while holding a tool that can write, commit, push, and execute the audited repository.

- **Severity:** major
- **File:** `plugins/quorum/bin/selftest.py`
- **Line:** 54

**What:**

`READ_TOOLS` at selftest.py:54 lists `Bash`, and `WRITE_TOOLS` at :53 omits it, so the assertion at :1254 (`audit.js: <agent> grants no file-editing tool`) passes for `plugins/quorum/agents/quorum-auditor.md:4` (`tools: Read, Grep, Glob, Bash`). I ran `python3 plugins/quorum/bin/selftest.py -v`: `PASS audit.js: quorum-auditor grants no file-editing tool`, 207/207. The plugin's only PreToolUse hook (`plugins/quorum/hooks/hooks.json`) matches `Edit|Write|MultiEdit` and not `Bash`, so no other mechanical control covers it. Meanwhile selftest.py:1224-1228 states the property is "of the agent definitions rather than of the prompts, so it is settled here instead of being promised in prose", and workflow/audit.js:34-37 repeats it. Both claims are untrue for any agent holding Bash; agents/quorum-auditor.md:10-12 ("You have no file-editing tools, and you must not use the shell to work around that") concedes that the shell is the workaround, i.e. the control is prose after all.

**Failure scenario:**

A user runs `/quorum:audit spec.md` on `main` of a production repo that never used this pipeline — exactly the advertised use. An auditor cluster is handed a criterion like "config is loaded from the environment at boot". Nothing mechanical stops it from running `node -e 'require("./src/config")'`, `npm test`, `./scripts/verify.sh`, `sed -i` on a file, `git commit`, or `git push`; the audited repository is also untrusted input, so a README or source comment carrying injected instructions reaches an agent that holds an unrestricted shell. The result the plan calls the whole basis of running on `main` ("the target is production code that may hold live credentials, migrate on boot, or consume from a real queue") is unprotected, and the suite still reports 207/207 green with a check whose name asserts the opposite.

**Suggested direction:**

Either drop `Bash` from `quorum-auditor` (Read/Grep/Glob already cover searching, and `git log` is the only listed use that needs a shell), or move `Bash` into `WRITE_TOOLS` and gate it explicitly; if `Bash` is kept, delete the claims at selftest.py:1224-1228 and audit.js:34-37 that the guarantee is mechanical rather than prompted.

### F2 — `slug` is interpolated straight into the write path with no validation, so a slug containing `..` or `/` makes the scribe write outside `docs/audit/` — and the skill's own post-run check then falsely reports that nothing else moved.

- **Severity:** minor
- **File:** `plugins/quorum/workflow/audit.js`
- **Line:** 22

**What:**

audit.js:12-13 validates only that `slug` is non-empty, then :22 builds `reportPath = 'docs/audit/' + slug + '/report.md'`, which is handed to the write-capable scribe at :479 ("Write only " + reportPath). The slug's format rules live only as prose for a model (reference/audit.md:36-37, skills/audit/SKILL.md:70-72), and its sources include "an explicit slug passed to the skill" and text derived from the spec — which, for a spec file inside the untrusted repository under audit, is attacker-influenced content that the skill agent reads in full at Step 1 before choosing the slug.

**Failure scenario:**

With `slug` = `../../../../tmp/pwn` (user-supplied, or steered by a line in the audited repo's spec file), the scribe is told to write `docs/audit/../../../../tmp/pwn/report.md`, which resolves outside the repository entirely. `criteria.md` lands there too. The skill's Step 6 verification (`git status --porcelain`, SKILL.md:199-204) then shows a clean tree and the command reports that every changed path is under `docs/audit/` — a false attestation of AC1, the invariant that makes running on `main` safe. A slug of `../work/quorum-audit` would instead overwrite pipeline artifacts under `docs/work/` while producing the same clean-looking report.

**Suggested direction:**

Validate the slug in audit.js before use — reject anything not matching `^[a-z0-9][a-z0-9-]*$` with a thrown error — rather than relying on a prose formatting rule addressed to a model.

### F3 — The only signal that an auditor executed the repository under audit (`ranNothing: false`) is written to the workflow log and never reaches `report.md` or the user-facing summary.

- **Severity:** minor
- **File:** `plugins/quorum/workflow/audit.js`
- **Line:** 285

**What:**

audit.js:285-291 collects auditors that returned `ranNothing === false` and emits a `log()` WARNING; the value then appears only in the workflow's return object at :505. The scribe prompt (:442-482) never mentions it, so `report.md` cannot record it, and skills/audit/SKILL.md Step 6 (:206-220) enumerates what to report — gaps, unverified, met count, path, `/quorum:1-plan` line, clusters that returned nothing — without ever mentioning `ranNothing`. `grep -rn ranNothing plugins/quorum/` confirms there is no other consumer.

**Failure scenario:**

An auditor runs the audited repo's `npm test` (which, per the plan's own reasoning, may start a service, run a migration, or consume from a real queue) and honestly returns `ranNothing: false`. The run completes normally; `report.md` reads like any other audit, and the skill's summary — following Step 6 literally — never says a violation of AC11 occurred. The operator of a production repo is told the audit was static when it was not, and the permanent artifact carries no trace of it.

**Suggested direction:**

Pass the violating cluster names into the scribe prompt so `report.md` records them, and add a line to SKILL.md Step 6 requiring `ranNothing: false` to be reported above the findings, the way a hash mismatch already is.

## Notes

Scope checked: plugins/quorum/bin/audit.py (no shell use, stdlib only, sha256 over the `## Criteria` section — path handling and the hash/verify logic hold up under the tamper cases the new selftest exercises), workflow/audit.js, skills/audit/SKILL.md, agents/quorum-auditor.md, reference/audit.md, selftest.py, README/manifest bumps, and docs/fixtures/. No new dependencies are introduced (no package.json, no new Python imports beyond stdlib). The fixture under docs/fixtures/audit-demo/ contains no real secrets — keys come from `WIDGET_API_KEYS` env and `test-key` is a test literal — and is not wired into any CI runner (.github runs selftest.py only). I did not modify the tree; the only command run was the repository's own selftest, which works in temp directories.
