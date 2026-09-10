# Review panel calibration

1 fixture case(s), 1 clean control(s).

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
| `correctness` | 0 | 0 | — | 0 | 0 | 0 | 0 |
| `security` | 0 | 0 | — | 0 | 0 | 0 | 0 |
| `simplicity` | 0 | 0 | — | 0 | 0 | 1 | 1 |
| `spec-fidelity` | 0 | 0 | — | 0 | 0 | 0 | 0 |
| `test-quality` | 0 | 0 | — | 0 | 0 | 2 | 2 |

## Planted and not found

None. Every planted defect was found by the lens it was planted for.

## False positives on clean controls

None at `minor` or above.

## Cross-catches

A lens finding a defect planted for another. Not scored either way —
recorded because it is the panel overlapping, which is the argument for
having several lenses and the argument against paying for all of them.

None.

## Unmatched findings

Findings on cases that carry planted defects, matching none of them.
**Not scored, in either direction.** Each is either a false positive or
a real defect nobody planted, and the fixture cannot tell you which.
Read them.

- `simplicity` — nit `src/slug.js:17` — `.filter(Boolean)` on the word list is unreachable-effect code: the preceding regex collapse plus trim guarantees `split(' ')` never yields a falsy element that changes the result. (case `clean-control`)
- `test-quality` — minor `test/slug.test.js:29` — The only test for AC4 asserts the slug's length but not its content, using an input where every possible 60-character result is identical, so it cannot detect truncation from the wrong end of the word. (case `clean-control`)
- `test-quality` — minor `test/slug.test.js:52` — No test exercises a too-long word followed by a shorter word that would still fit, so the `break` that implements AC3's 'stops at the last whole word that fits' is unguarded; replacing it with `continue` passes the entire suite. (case `clean-control`)

## Not run

Excluded from every rate above rather than scored as a miss.

- `behavior` on case `clean-control` — the fixture is a library with no runnable surface; the behavior lens has nothing to launch

