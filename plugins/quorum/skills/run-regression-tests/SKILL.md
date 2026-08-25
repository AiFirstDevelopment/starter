---
name: run-regression-tests
description: Runs the full regression suite, discovering and recording how this repo runs its tests, and reports failures in a structured form the rest of the quorum pipeline can consume. Distinguishes broken code from broken tests from flakes.
---

# Run regression tests

Run the whole suite and report the result honestly and in a form other steps can
act on.

## Use a recorded recipe if one exists

Do not rediscover how to run tests every session. In order:

1. A repo-local recipe: `.claude/skills/run-*/SKILL.md` or
   `.claude/skills/verify/SKILL.md` — Claude Code's own `/run-skill-generator`
   and `/verify` record these. **Follow it if present.**
2. `docs/work/<slug>/plan.md` *Test strategy*, and the repo's README or
   CONTRIBUTING.
3. Otherwise discover from the manifest — `package.json` scripts, `Makefile`,
   `pyproject.toml`, `go.mod`, `Cargo.toml`, `*.csproj`, CI workflow files. The CI
   workflow is the most reliable source: it is what actually gates merges.

**After discovering, record it** so the next run is deterministic: write the exact
commands, prerequisites (services, env vars, migrations, build steps), and
expected runtime to `.claude/skills/run-regression-tests/SKILL.md` in the repo.

## Procedure

1. Establish the recipe as above; state which source you used.
2. Run any prerequisites: install, build, start dependent services, migrate.
3. **Run the whole suite** — not a filtered subset. If a subset was requested,
   say prominently that this was a partial run.
4. On failure, classify each one (below) before reporting.
5. Report in the structured form below.

## Classify every failure

Step 4 (`/quorum:4-quorum`) makes different decisions for each of these, so the
classification is the valuable part of this skill:

- **Code broken** — the test is right, the behavior is wrong. Fix the code.
- **Test broken** — the behavior is right, the test's expectation is wrong or
  outdated. This needs a human decision; never silently "fix" the test to match
  current behavior, because that erases the regression the test was guarding.
- **Environment** — missing service, missing env var, failed install, wrong
  runtime version. Not a code defect; say what is missing.
- **Flake** — passes on re-run with no code change. **Re-run a failing test once**
  to detect this. A flake is a real defect in the suite: report it with the
  suspected nondeterminism (time, network, ordering, shared state, fixed sleep).

Do not guess a classification. If you cannot tell, say so and give the evidence.

## Report format

```markdown
## Regression suite

- **Recipe source:** recorded | discovered from CI workflow | ...
- **Command:** `npm run test:integration`
- **Result:** 148 passed, 3 failed, 2 skipped (2m14s)
- **Scope:** full suite

### Failures

| Test | Class | Evidence |
|---|---|---|
| `checkout > applies promo code` | code broken | Expected total 90, got 100. `src/pricing.ts:44` skips the discount when quantity is 1. |
| `auth > session expiry` | flake | Failed once, passed on re-run. Asserts against real `Date.now()`. |

### Skipped

- `payments > refund flow` — skipped via `.skip` at `tests/payments.spec.ts:12`.
  Skipped tests are silent gaps; flag them.
```

## Rules

- **Never modify code or tests in this skill.** It runs and reports; that is all.
  Fixing belongs to `/quorum:2-build` or `/quorum:4-quorum`.
- Never report success on a partial run without saying it was partial.
- Always surface skipped and filtered-out tests — a suite that quietly skips is
  indistinguishable from one that passes.
- Report the failure output verbatim where it is short enough to be useful.
