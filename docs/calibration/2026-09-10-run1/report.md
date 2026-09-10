# Review panel calibration

2 fixture case(s), 1 clean control(s).

Catch rate counts only defects planted for that lens. False positives
are counted only on clean controls, where nothing was planted and there
is nothing a finding could have legitimately found. Everything else is
listed below unscored, because the fixtures cannot settle it.

**Lenses exempt from the false-positive count**, and why. Read these
before the table: an exemption is the harness declining to measure the
one thing that can count against a lens.

- `test-quality` on control `clean-control` — test-quality has no achievable clean control. Its remit is whether a test would fail if the behaviour it guards broke, and mutation space is unbounded - for any finite suite there is always another surviving mutant. Two runs of this fixture produced four such findings and all four were confirmed real by mutation, including two the lens mutation-tested itself. Counting them would measure this fixture's test exhaustiveness, not the lens's precision.

| Lens | Planted | Caught | Catch rate | False pos. (controls) | Cross-catches | Unmatched | Findings |
|---|---|---|---|---|---|---|---|
| `behavior` | 0 | 0 | — | 0 | 0 | 0 | 0 |
| `correctness` | 1 | 1 | 100% | 0 | 4 | 1 | 7 |
| `security` | 2 | 2 | 100% | 0 | 0 | 3 | 5 |
| `simplicity` | 1 | 1 | 100% | 0 | 0 | 1 | 2 |
| `spec-fidelity` | 1 | 1 | 100% | 0 | 3 | 2 | 6 |
| `test-quality` | 1 | 1 | 100% | 0 | 0 | 6 | 9 |

## Planted and not found

None. Every planted defect was found by the lens it was planted for.

## False positives on clean controls

None at `minor` or above.

## Cross-catches

A lens finding a defect planted for another. Not scored either way —
recorded because it is the panel overlapping, which is the argument for
having several lenses and the argument against paying for all of them.

- `correctness` found `SEC1`, planted for `security` (case `token-refresh`)
- `correctness` found `SEC2`, planted for `security` (case `token-refresh`)
- `correctness` found `TST1`, planted for `test-quality` (case `token-refresh`)
- `correctness` found `SPC1`, planted for `spec-fidelity` (case `token-refresh`)
- `spec-fidelity` found `SEC1`, planted for `security` (case `token-refresh`)
- `spec-fidelity` found `SEC2`, planted for `security` (case `token-refresh`)
- `spec-fidelity` found `TST1`, planted for `test-quality` (case `token-refresh`)

## Unmatched findings

Findings on cases that carry planted defects, matching none of them.
**Not scored, in either direction.** Each is either a false positive or
a real defect nobody planted, and the fixture cannot tell you which.
Read them.

- `correctness` — major `src/session.js:20` — Intent: refresh a token that is "close to expiring"; "leave it alone" otherwise. (case `token-refresh`)
- `security` — blocker `src/session.js:20` — `refreshSession` never rejects an already-expired token, so any expired session can be renewed indefinitely. (case `token-refresh`)
- `security` — major `src/tokens.js:5` — The signing secret silently falls back to the hardcoded literal `'dev-secret'` when `SESSION_SECRET` is unset. (case `token-refresh`)
- `security` — minor `src/session.js:25` — The newly minted session token is persisted in plaintext on the in-memory user record. (case `token-refresh`)
- `simplicity` — nit `src/slug.js:15` — The `.trim()` on src/slug.js:15 is an inert call, and the four-step tokenising chain (lines 13-17) is equivalent to a single regex split. (case `clean-control`)
- `spec-fidelity` — major `src/users.js:9` — Claim C2 ('findUser returns a user for every id that reaches it') is false; findUser returns undefined for any unknown id and refreshSession dereferences it unguarded. (case `token-refresh`)
- `spec-fidelity` — minor `src/session.js:25` — refreshSession writes the login record on every refresh, behavior the plan's Approach never describes and which corrupts the login audit trail the non-goal fenced off. (case `token-refresh`)
- `test-quality` — minor `test/slug.test.js:33` — The AC5 test cannot fail if the behavior it guards is removed: it passes identically with the explicit TypeError guard deleted, because the chosen input (null) throws a native TypeError anyway. (case `clean-control`)
- `test-quality` — minor `test/slug.test.js:22` — AC3's fit-exactly boundary is untested, so an off-by-one at the length comparison in slugify passes the whole suite. (case `clean-control`)
- `test-quality` — major `test/session.test.js:20` — AC2 ('when the token expires further out than that, the same token comes back with refreshed: false') has no test. No test in the file constructs a token expiring beyond the refresh window, and the string 'refreshed' does not appear anywhere in test/session.test.js. (case `token-refresh`)
- `test-quality` — major `test/session.test.js:20` — AC3 ('when the account is disabled, refreshing fails and no new token is minted') has no test. The disabled fixture `u2` in src/users.js:5 is never referenced by any test. (case `token-refresh`)
- `test-quality` — blocker `test/session.test.js:20` — AC4 ('when a token's signature does not match its body, refreshing fails and nothing is looked up') and plan claim C1 ('verify rejects a token whose MAC does not match its body') have no test. No test constructs a token with a mismatched MAC. (case `token-refresh`)
- `test-quality` — minor `test/session.test.js:20` — Plan claim C2 ('findUser returns a user for every id that reaches it') is untested and false. No test passes a `sub` that is absent from the USERS map in src/users.js:3-6. (case `token-refresh`)

## Not run

Excluded from every rate above rather than scored as a miss.

- `behavior` on case `clean-control` — the fixture is a library with no runnable surface; the behavior lens has nothing to launch
- `behavior` on case `token-refresh` — the fixture is a library with no runnable surface; the behavior lens has nothing to launch

