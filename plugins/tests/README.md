# tests

Behavioral regression tests against the fully assembled application, proven able
to fail, and gated in CI.

- `/tests:add` — write tests for the current branch's change, each one verified to
  fail when the behavior it guards is deliberately broken
- `/tests:run` — run the whole suite and classify every failure as code-broken,
  test-broken, environment, or flake
- `/tests:ci` — make the suite a required status check so PRs cannot merge red

Stands alone. A repo can adopt this testing discipline without the `quorum`
pipeline; when both are enabled, `/tests:add` uses the plan's acceptance criteria
as its checklist.

See the [marketplace README](../../README.md) for the full explanation.
