---
name: add-regression-tests
description: Writes behavioral regression tests for the current change, exercising the fully assembled application through its outermost user-facing surface. Verifies each new test actually fails when the behavior it guards is broken. Use when asked to add tests, harden a change, or close test gaps.
---

# Add regression tests

Write tests that fail when a user-visible behavior regresses, and prove that they
do.

## The objective

**Not** a coverage number. The objective is:

> Every behavior introduced or changed by this diff has a test that fails if that
> behavior regresses.

Coverage is a **diagnostic for finding gaps**, never the target. Chasing a
percentage reliably produces assertion-free tests that execute lines without
checking anything — a merge gate you trust and shouldn't. If a coverage tool is
configured, use its report to *find behaviors you missed*, then write a
behavioral test for each. If no coverage tooling exists, say so and work from the
diff and the acceptance criteria instead. Do not install coverage tooling
uninvited.

## Scope

Default to the diff between this branch and its base — see
`${CLAUDE_PLUGIN_ROOT}/reference/contract.md`. Include uncommitted changes. Report
the range you used. If `docs/work/<slug>/plan.md` exists, its acceptance criteria
are the primary checklist: **every acceptance criterion gets a test.**

## What kind of test

**Behavioral tests against the fully assembled application, driven through its
outermost surface.** Not unit tests. Wire the real application together — real
routing, real state management, real dependency graph — and exercise it the way a
user does.

Reserve **unit tests** for pure logic that genuinely needs hardening on its own:
parsers, date math, pricing rules, state machines, validation predicates —
things with many input cases and no I/O. Do not unit test a component or handler
just because it exists.

### The principles to carry across stacks

These come from the Angular/DOM Testing Library philosophy, but they are
stack-independent. Apply them wherever the code lives:

1. **Query the way the user perceives.** Find things by their accessible role,
   visible label, or text — never by CSS class, internal id, test-only hooks, or
   position in a tree. If something is hard to query this way, that is usually an
   accessibility defect worth reporting.
2. **Assert observable outcomes**, not internal state. What appeared, what
   changed, what was sent, what the exit code was — not which function ran or
   what a private field holds.
3. **Never reach into internals.** No touching private members, no asserting on
   implementation structure, no mocking the unit under test's own collaborators
   just to observe a call. A test that knows how the code works will break on a
   refactor that changed nothing a user can see.
4. **Mock only at the true system boundary** — the network, the clock, the
   filesystem, third-party services. Everything inside the boundary runs for real.
5. **One user-meaningful behavior per test**, and name the test after that
   behavior in plain language: `shows a validation error when email is empty`,
   not `test handleSubmit case 2`.

### Mapping "the UI surface" to other stacks

The surface is whatever the consumer actually touches:

| Stack | Assemble | Drive through | Assert on |
|---|---|---|---|
| Web app (Angular, React, Vue, Svelte) | Full component tree with real router and stores | Testing Library queries and user-event interactions; Playwright/Cypress for full-browser cases | Rendered output, accessible state, navigation, outbound requests |
| HTTP API / backend service | Boot the real app with a real (test) database | Actual HTTP requests to routes | Status, response body, persisted state, emitted events |
| CLI | Build/execute the real binary or entrypoint | Argv, stdin, env vars | stdout, stderr, exit code, files written |
| Library / SDK | Import the built public entrypoint | Only the public API | Return values, thrown errors, callbacks fired |
| Mobile | Full app under the platform test harness | Taps, gestures, accessibility identifiers | Visible screen state, navigation, persistence |
| Event/queue worker | Real consumer wired to a test broker | Publish a real message | Side effects, acks, dead-letter behavior |

If the repo already has an integration test setup, **follow its patterns exactly**
rather than introducing a second style.

## Fail-first verification — the rule that makes this worth doing

**A test that passes against broken code is worse than no test**, because it is a
merge gate that will wave regressions through.

For every test you write, prove it can fail:

1. Deliberately break the behavior it guards — invert a condition, return a wrong
   value, delete the line that renders the message.
2. Run the test. **Confirm it fails, and fails for the expected reason** — not on
   a setup error, a timeout, or a crash somewhere unrelated.
3. Restore the code exactly. Re-run and confirm the test passes again.

Any test that does not fail in step 2 is not testing what you think. Rewrite it
or delete it — never keep it. Report at the end that every new test was
fail-verified, and name any you could not verify and why.

Work in small batches so a broken restore is obvious immediately, and confirm the
working tree is clean of your deliberate breakage before finishing.

## Determinism

Flaky tests are what kill a suite used as a merge gate — a suite people re-run
until it goes green is not a gate. Every test must be independent and repeatable:

- **Time:** freeze or inject the clock. Never assert against the real current time.
- **Network:** stub at the boundary. No test touches a live external service.
- **Randomness and IDs:** seed them, or assert on shape rather than exact value.
- **Waiting:** wait for a condition, never a fixed sleep.
- **Isolation:** no shared mutable state between tests; each sets up and tears
  down its own data. Tests must pass in any order and in parallel.
- **Selectors:** no dependence on incidental ordering or layout.

## Procedure

1. Determine the scope and read the diff and any plan.
2. Inventory the behaviors it introduces or changes; map each acceptance
   criterion to at least one behavior.
3. Find the existing test setup and follow it. If there is none, propose the
   minimal setup and confirm before adding dependencies.
4. Write behavioral tests, then unit tests for pure logic that warrants it.
5. Fail-verify every new test as above.
6. Run the whole suite (`/quorum:run-regression-tests`) and confirm green.
7. Report: behaviors covered, acceptance criteria mapped, tests fail-verified,
   gaps you could not close and why. **Name the gaps** — silence reads as
   complete coverage when it isn't.

## Rules

- Never weaken or delete an existing test to make the suite pass.
- Never add a test-only hook to production code where an accessible query would
  work. If you must, say so explicitly in your report.
- No assertion-free tests. No test whose only assertion is "did not throw", unless
  not throwing is the actual behavior under test.
- Adding a dependency or a new test framework needs the user's agreement first.
