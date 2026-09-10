# Calibration runs

Output from `/quorum:calibrate`. Each directory is one run: `report.md` and the
raw `findings.json` it was computed from.

## 2026-09-10 — the first real run

Two runs, recorded separately rather than spliced, because the fixture changed
between them and a combined table would hide that.

**`2026-09-10-run1`** — both cases, 10 lens/case pairs, 0 agent errors.

| Lens | Planted | Caught | Catch rate |
|---|---|---|---|
| `correctness` | 1 | 1 | 100% |
| `security` | 2 | 2 | 100% |
| `simplicity` | 1 | 1 | 100% |
| `spec-fidelity` | 1 | 1 | 100% |
| `test-quality` | 1 | 1 | 100% |
| `behavior` | — | — | not run |

**Do not read that as a 100% panel.** Six planted defects is a count, not a
rate, and each was planted by someone who then checked whether it was found.

The interesting results are the ones the table does not hold.

### The panel found eight defects nobody planted

Listed as *unmatched* — printed, never scored, exactly as designed. Spot-checked
by hand and they are real. The sharpest:

- `security` (blocker): `refreshSession` never rejects an **already expired**
  token, so a dead session refreshes indefinitely. Verified by execution: a
  token that expired an hour ago comes back renewed.
- `security` (major): the signing secret falls back to a hardcoded
  `'dev-secret'` when `SESSION_SECRET` is unset.
- `test-quality`: AC2, AC3 and AC4 have no test at all.

This is the case for printing unmatched findings rather than classifying them.
A scorer that had called these false positives would have been wrong eight
times and produced a number that made the panel look worse the better it did.

### The clean control was not clean

`test-quality` reported two findings against it. Both were **real**, confirmed
by mutation:

- deleting the `TypeError` guard left all 8 tests passing, because
  `null.toLowerCase()` throws a native `TypeError` and the test matched only on
  the class;
- changing `>` to `>=` at the length comparison left all 8 tests passing.

The fixture was fixed — assert the guard's own message, and pin the
`50 + 1 + 9 === 60` boundary — and both mutants now go red.

**`2026-09-10-run2-control`** is the re-run of the control after that fix.
`correctness`, `security` and `spec-fidelity` all returned clean, twice.
`test-quality` found two *more* real gaps, again mutation-verified, this time by
the lens itself.

### What that established

**`test-quality` has no achievable clean control.** Its remit is whether a test
would fail if the behaviour it guards broke, and mutation space is unbounded —
for any finite suite there is another surviving mutant. Four findings across two
runs, all four real. Counting them as false positives measures the fixture's
test exhaustiveness, not the lens's precision.

So the manifest gained `notControlFor`, with a mandatory `notControlForReason`
printed above the table. That knob is also the obvious way to make a harness
flatter its subject, which is why the reason is required and why `selftest.py`
refuses an exemption without one.

### Still unmeasured

- `behavior` — both fixtures are libraries with nothing to launch.
- Anything at production scale. These are 30–90 line fixtures.
- What nobody thought to plant, which is where the panel's value actually is.
  The eight unmatched findings are the only evidence here on that, and they are
  evidence, not a measurement.
