# Review: test-quality

- Lens: test-quality
- Verdict: findings
- Diff range: a22d7e7...HEAD (plus uncommitted working-tree changes)

## Findings

### F1 — major — plugins/quorum/bin/audit.py:196

**Claim:** The new `audit.py --check-slug` path-escape validator has zero coverage in the repository's only test suite; neutering it leaves the suite fully green.

**What:** `SLUG` (line 46) and the `--check-slug` branch (lines 182, 196-206) are added in this delta and made mandatory by `skills/audit/SKILL.md` ("Non-zero means stop and pick another slug"). `selftest.py` never invokes `--check-slug`: `grep -n 'check-slug\|check_slug\|SLUG' plugins/quorum/bin/selftest.py` returns nothing, and `test_audit()` (selftest.py:1065-1169) exercises only `--hash` and `--verify`.

**Failure scenario:** Probed directly: I copied the plugin to a scratch directory and replaced `SLUG = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')` with `re.compile(r'.*')`. `python3 audit.py --check-slug "../../../etc"` then exits 0 — the skill would proceed to write `docs/audit/../../../etc/criteria.md`, outside the working tree, which is exactly the escape the comment at audit.py:39-45 says the check exists to stop and which the Step 6 `git status` check cannot see. `python3 selftest.py` still printed `235/235 passed`, exit 0. The same silence covers a regression from `if opts.check_slug is not None:` to a truthy test, or a return of 0 instead of 2 on rejection. The untested code already diverges from its JS twin: `python3 audit.py --check-slug $'ok\n'` exits 0 (Python `$` matches before a trailing newline), while `audit.js:22`'s `/^[a-z0-9]+(-[a-z0-9]+)*$/` rejects the same string — so a slug the skill blesses and writes `criteria.md` under can still throw `audit requires a kebab-case args.slug` after the human has spent the gate.

**Suggested direction:** Add a `--check-slug` block to `test_audit()` in the same break-the-rule style as the rest of the file: assert exit 0 for `widget-api`, exit 2 for `..`, `../../etc`, `a/b`, `Foo`, `-x`, `x-`, `a--b`, the empty string, and a trailing-newline slug, and assert nothing is written on rejection. Anchoring with `re.fullmatch` (or `\Z`) would make the Python and JS copies agree.

### F2 — minor — plugins/quorum/bin/selftest.py:16

**Claim:** `selftest.py`'s module docstring still tells the reader the suite does not prove the read-only guarantee and that `quorum-auditor` holds `Bash` — both false after this delta.

**What:** Lines 16-19 read: "Note what the second check settles and what it does not: it settles the declared grants, not what a shell can do with them. quorum-auditor holds Bash, so 'cannot write to the repository it audits' is a rule the prompts state, not one this file proves." This delta removed `Bash` from `agents/quorum-auditor.md:4` and added the `EXEC_TOOLS` assertion at lines 1393-1397; the equivalent comments at selftest.py:48-53, selftest.py:1367-1376, and audit.js:63-74 were all rewritten, and this one was not.

**Failure scenario:** AC11 now states that the no-shell property "is a property of the tool grants rather than of the prompts, and `selftest.py` asserts it". A maintainer or an adopting repo opening `selftest.py` to confirm that claim reads the file's own header saying the opposite — that the auditor holds a shell and the guarantee is prompt-only — and concludes the mechanical assertion does not exist. The most likely consequence is re-granting `Bash` to `quorum-auditor` on the belief that the design permits it, then being surprised by a FAIL the header said could not happen; the least likely-but-worse consequence is trusting the header and reporting AC11 as unverified when it is in fact covered.

**Suggested direction:** Rewrite lines 16-19 to match what the file now asserts: the agents `audit.js` names are granted neither a file-editing tool nor a shell, and both are settled here rather than promised in the prompts.

## Notes

Scope note: I stayed inside the delta. `workflow/audit.js`'s cluster-dedup, unclustered sweep, gap-downgrade and `proposedChange` fallback remain unexercised by any automated test — `docs/work/quorum-audit/reviews/007-fixture-run.md:118` says so explicitly — but that logic predates a22d7e7 and only its comments changed here, so I did not raise it as a finding against this range. Positive result worth recording: the new EXEC_TOOLS check is not decorative. I copied the plugin to a scratch directory, restored `tools: Read, Grep, Glob, Bash` on `quorum-auditor`, and `selftest.py` produced exactly one targeted FAIL (234/235). On the tree as it stands the suite is 235/235, exit 0, and `guard.py --work-dir docs/work/quorum-audit` is clean. No flakiness risk introduced by this delta: the new assertions read committed files, add no time, network, randomness, or ordering dependency, and the existing tempdir-per-test discipline is unchanged. I made no edits to the repository; all probes were on copies under the scratchpad directory.
