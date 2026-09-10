# Fixtures

## `audit-demo/` — the controlled fixture for `/quorum:audit`

Most of what `/quorum:audit` promises is a property of what a prompt causes to
happen, not of a function's return value, so `bin/selftest.py` cannot reach it.
The way to check those promises is to **operate the command** — and reading the
resulting report for plausibility is exactly the self-assessment this whole
project exists to distrust. So the fixture is controlled: every criterion's
correct status is fixed here, in advance, and the report is compared against this
file rather than merely read.

**This file is deliberately outside `audit-demo/`.** It is the answer key, and an
auditor searching the tree it is auditing must not be able to find it.

### Running the audit against it

`audit-demo/` is a repository under audit, not part of this one's build. Copy it
somewhere else and audit the copy, so nothing here is in the tree being searched:

```bash
FIX=$(mktemp -d) && cp -R docs/fixtures/audit-demo/. "$FIX/" \
  && git -C "$FIX" init -q && git -C "$FIX" add -A \
  && git -C "$FIX" -c user.email=f@x -c user.name=f commit -qm 'widget api'
# then, from $FIX:
#   /quorum:audit spec.md
```

Never run `npm test` or start `src/server.js` — the audit must not, and the
fixture exists partly to catch it if it does. Nothing here is installable anyway:
there is no `package.json`, on purpose.

### The answer key

The spec states four requirements. Derived criteria should be roughly these, and
each must cite the spec:

| # | Criterion | Correct status | Why |
|---|---|---|---|
| 1 | a request with no `X-Api-Key`, or an unrecognised one, is rejected with 401 and no body | `met` | `src/server.js` checks `KEYS` before anything else; `test/server.test.js` asserts both cases |
| 2 | every successful response carries a unique `X-Request-Id` | `met` | `src/server.js` sets it from `crypto.randomUUID()` on each response; asserted in `test/server.test.js` |
| 3 | a failed call to the widget store is retried three times with exponential backoff before the request fails with 502 | `gap` | `src/upstream.js` calls the store exactly once and rethrows. Nothing anywhere retries |
| 4 | `/health` answers in under 50 ms under normal load | `unverified` | a timing property of the running service. The endpoint exists and is trivial, which is not the same as measuring it |

A criterion may also be derived from "keys are never written to a log". `met` is
the defensible status — nothing logs anything — but `unverified` is acceptable if
the audit says it searched for logging and found no logging at all. `gap` is
wrong: there is nothing missing.

### What the report must **not** contain

The fixture implements two things the spec never mentions:

- a per-key rate limiter answering `429` (`src/ratelimit.js`)
- a `/metrics` endpoint (`src/server.js`)

Neither may appear in `report.md` — not as a gap, not as an observation, not as a
note, not as a suggestion to remove it. More implemented than the spec is fine,
and this is what makes that checkable.

### What the report must contain

- All four criteria, each with exactly one status, none missing.
- For criterion 3: the search patterns and paths that came back empty, so the
  claim can be re-run. `retry`, `backoff`, `attempt` over `src/` all come back
  empty; `src/upstream.js` is where it would live.
- For criterion 4: the reason it could not be settled, stated as a runtime
  property rather than as a shortfall.
- Criterion 3 phrased as an observable acceptance criterion, and a closing
  `/quorum:1-plan` invocation naming the report.
- A `Criteria hash` matching `criteria.md`'s — check it with
  `python3 plugins/quorum/bin/audit.py --verify docs/audit/<slug>`.

### And of the run itself

- No branch created, no branch switched, no commit made.
- `git status --porcelain -uall` in the audited copy lists paths under `docs/audit/`
  and nothing else.
- Given `spec.md`, criteria are derived and shown, and the run **stops** until
  confirmed: `criteria.md` on disk, no `report.md`, no auditor run.
- Given `docs/no-such-spec.md`, the command says the file does not exist and
  writes nothing at all.
