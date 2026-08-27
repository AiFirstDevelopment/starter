# Verdict — quorum-audit

- **Adjudicated:** `bce0432...7ea8d21` (the build commit), plus my own fixes on top
- **Reviews considered:** 001-correctness, 002-spec-fidelity, 003-security, 004-simplicity, 005-test-quality
- **Outcome:** blocked
- **Test suite:** green — 233/233, `python3 plugins/quorum/bin/selftest.py` (up from 207 as built)

## Read this first

The branch is sound and the suite is green. What is blocked is the claim that
the plan is satisfied, for two reasons a human has to settle:

1. **AC10 cannot be satisfied as written.** It requires `selftest.py` to fail
   when `audit.js` names an agent granting a file-editing tool, and the plan's
   own *Approach* requires `audit.js` to name `quorum-scribe`, which grants
   `Write`. The builder flagged this as a `PLAN DEFECT` and correctly did not
   touch the AC. Neither may I. See **E1**.
2. **Nine of the eleven acceptance criteria have no verification at all.** The
   plan's *Test strategy* assigns AC1, AC2, AC3, AC4, AC6, AC7, AC8, AC9 and
   AC11 to a `behavior` lens driving `/quorum:audit` against the committed
   fixture. That lens was dropped from the panel before this run and nothing
   replaced it. The panel I was handed lists `missing: ["behavior"]`. Nothing in
   this repository has ever operated `/quorum:audit` end to end. See **E5**.

Everything else below is ordinary adjudication: 13 findings accepted and fixed,
0 rejected, 5 escalated.

## Acceptance criteria

| AC | Met | Evidence |
|---|---|---|
| AC1 | **no** | Not verified — no run of the command exists. The evidence chain also had a hole: `slug` was interpolated into the scribe's write path unvalidated, so a slug holding `..` wrote outside `docs/audit/` while the skill's own `git status` check still reported a clean tree. Closed in `plugins/quorum/workflow/audit.js` (SEC-F2); the criterion itself remains unobserved. See E5. |
| AC2 | **no** | Not verified. `plugins/quorum/skills/audit/SKILL.md` Step 1 specifies the path-vs-free-text split and the stop-and-write-nothing branch exactly, but it is a prompt and no run exercised it. See E5. |
| AC3 | **no** | Not verified. Required by `plugins/quorum/skills/audit/SKILL.md` Step 3 and `plugins/quorum/reference/audit.md`; nothing enforces it — `plugins/quorum/workflow/audit.js` accepts a criterion with no source and prints `(none recorded)`. See E5. |
| AC4 | **no** | Not verified. The gate is `plugins/quorum/skills/audit/SKILL.md` Step 4 and is prompt-only by design; no run confirmed that a non-yes leaves `criteria.md` alone and starts no agent. See E5. |
| AC5 | yes | `plugins/quorum/bin/audit.py` hashes the criteria section and `--verify` compares it against the hash the criteria file recorded and the one the report file cites. Covered in `plugins/quorum/bin/selftest.py` by `test_audit` — a softened criterion, three separate reflows, a report citing another list, a report citing nothing. **Caveat, now written into the contract:** the hash covers the criteria file, the auditors measure the array handed to the workflow, and nothing mechanical ties the two. See E2. |
| AC6 | **no** | Not verified end to end. The deterministic half is real and I read it — `plugins/quorum/workflow/audit.js` dedupes cluster assignment, sweeps unassigned criteria into an `unclustered` cluster, and records any criterion no auditor returned as `unverified`. Whether the scribe then transcribes all of them is prompt-level and unobserved. See E5. |
| AC7 | **no** | Not verified. `NEVER_EXTRA` is repeated into the cluster, audit and refute prompts, the scribe prompt, `plugins/quorum/agents/quorum-auditor.md` and `plugins/quorum/reference/audit.md` — consistently, and entirely in prose. The fixture exists to catch a violation and was never run against. See E5. |
| AC8 | **no** | Not verified end to end. The enforcement is real: `plugins/quorum/workflow/audit.js` downgrades a `gap` carrying no `searched` value to `unverified`, preserving the original note. The report's rendering of it is unobserved. See E5. |
| AC9 | **no** | Not verified. One real hole is closed: `proposedChange` was optional and unenforced, so a gap could reach the scribe with nothing to put under *Proposed change*. `plugins/quorum/workflow/audit.js` now falls back to the criterion's own text after refutation (C-F5). The criterion itself is unobserved. See E5. |
| AC10 | **no** | Unsatisfiable as written — `plugins/quorum/workflow/audit.js` names `quorum:quorum-scribe`, and `plugins/quorum/agents/quorum-scribe.md` grants `Write`. See E1. The other two clauses hold: the suite exits 0, and an unregistered `agentType` fires exactly one FAIL (probed). The tool check itself was defeated by a reformat and is now fixed — see C-F1 below. |
| AC11 | **no** | Not met mechanically. `plugins/quorum/agents/quorum-auditor.md` grants `Bash`, which `plugins/quorum/bin/selftest.py` counts as a read tool, so nothing stops an auditor executing the repository under audit. The rule lives entirely in prompts. I made an admission durable rather than transient (SEC-F3) and corrected the comments that claimed otherwise, but the property is unenforced. See E3. |

## Dispositions

| Finding | Lens | Severity | Disposition | Reasoning |
|---|---|---|---|---|
| F1 | correctness | major | **Accepted** | Confirmed by calling `frontmatter_tools` directly: `tools: "Read, Grep, Write"` parsed to `['"Read', 'Grep', 'Write"']` and a YAML block sequence parsed to `[]`. Both yielded `writes == []` and the read-only check reported PASS on an agent really granted `Write`. Fixed in `plugins/quorum/bin/selftest.py`. |
| F2 | correctness | major | **Escalated (E2)** | Confirmed structurally: `criteriaHash` is an opaque string, `args.criteria` is independent, nothing compares them. Closing the loop properly is a design decision about the skill/workflow contract, not a judge's edit. Documented honestly in the meantime, and the loudest variant (an omitted hash) is fixed under F4. |
| F3 | correctness | minor | **Accepted** | Reproduced: a directory with `criteria.md` and no `report.md` printed `clean` and exited 0, while `SKILL.md` told the skill exit 0 means the report cites the matching hash. Added `--expect-report` to `plugins/quorum/bin/audit.py` and passed it from Step 6. |
| F4 | correctness | minor | **Accepted** | Confirmed: `slug` and `criteria` threw, `criteriaHash` defaulted to `''`. A full multi-agent run would end in a false "measured against different criteria". `plugins/quorum/workflow/audit.js` now throws before any agent starts. |
| F5 | correctness | minor | **Accepted** | Confirmed: `proposedChange` is optional in `AUDIT_SCHEMA` and had no post-hoc enforcement, unlike `searched`. Fixed with a fallback to the criterion's own text, applied after refutation so refuted gaps do not carry one. |
| F1 | spec-fidelity | minor | **Escalated (E1)** | Correct, and correctly identified as unfixable by anyone who may not edit *Acceptance criteria*. That includes me. |
| F2 | spec-fidelity | minor | **Accepted** | Confirmed: `READ_TOOLS` contains `Bash`, `quorum-auditor` holds it, and the comment claimed the guarantee was "a property of the agent definitions, not a promise in a prompt". It is not. Corrected in the module docstring, the `READ_ONLY_WORKFLOWS` comment, the check's own comment, and `plugins/quorum/workflow/audit.js`. The remedy it suggests is E3. |
| F3 | spec-fidelity | minor | **Escalated (E2)** | Same defect as correctness F2, from the other side. Same disposition. |
| F1 | security | major | **Split: docs fixed, remedy escalated (E3)** | The overstated claim is fixed (see spec-fidelity F2). Dropping `Bash` from `quorum-auditor` contradicts the plan's *Approach*, which names the grant explicitly, and materially changes what an auditor can do. Not a judge's call. |
| F2 | security | minor | **Accepted** | Confirmed by inspection: only `if (!slug) throw`, then `'docs/audit/' + slug + '/report.md'` handed to the one write-capable agent. `plugins/quorum/workflow/audit.js` now requires `^[a-z0-9]+(-[a-z0-9]+)*$`, which accepts every slug `reference/audit.md` describes and rejects `../work/quorum-audit` and `docs/specs/billing`. |
| F3 | security | minor | **Accepted** | Confirmed: `ranNothing: false` reached only `log()` and the return object. A run log scrolls away; the artifact is what an operator still has tomorrow. The scribe is now told to write a *Ran during the audit* section, and `SKILL.md` Step 6 reports it above the findings. |
| F1 | simplicity | major | **Split: prompt fixed, remedy escalated (E4)** | Confirmed: `quorum-scribe`'s standing instruction still names `docs/work/<slug>/reviews/NNN-<lens>.md`, the one tree the audit must not touch. The scribe prompt in `audit.js` now overrides it explicitly. Generalising the agent is a **non-goal** of this plan ("the agents they use"), so I did not. |
| F2 | simplicity | minor | **Accepted** | Confirmed: `title` was read and echoed back and never reached an artifact, because the scribe's restated format omitted the `# Audit report: <title>` line `reference/audit.md` requires. The prompt now opens the file with it. |
| F3 | simplicity | nit | **Accepted** | Confirmed: `grouped.notes` was never read. Now logged beside the cluster names. |
| F1 | test-quality | major | **Accepted** | Same defect as correctness F1, found independently with a block sequence. Fixed once; both are credited. A regression test was added — reverting the parser produces 11 targeted failures. |
| F2 | test-quality | minor | **Accepted** | Confirmed: `CRITERIA` held no checkbox, and the blank line was inserted where `body.strip()` removed it. Two of three normalisation rules were uncovered. Now one reflow variant per rule; deleting either rule from `audit.py` produces exactly the two failures naming it. |
| F3 | test-quality | minor | **Accepted** | Confirmed: every report case supplied a hash value, so the `cited is None` branch was never exercised. Added; stubbing the branch now fails. |
| F4 | test-quality | minor | **Accepted** | Confirmed by running the fixture's own tests on the build commit: tests 4 and 5 failed, because `WIDGET_API_KEYS` was never set. The answer key cited one of them as evidence for criterion 2's `met`. `test/helper.js` now sets the variable before requiring the server; all four tests pass. No assertion was changed. |

Eighteen findings: 13 accepted and fixed, 0 rejected, 5 escalated. No reviewer
claim turned out to be wrong on the facts — every one I checked reproduced.

## Changes applied

- `plugins/quorum/bin/selftest.py` — `frontmatter_tools` parses the inline,
  quoted, flow-sequence and block-sequence spellings of `tools:` alike, strips
  quotes, and returns `None` for any field it cannot read as a grant, so an
  unreadable grant fails closed as inherit-everything (correctness F1,
  test-quality F1).
- `plugins/quorum/bin/selftest.py` — new `test_agent_tools()`, sixteen checks
  over every spelling plus the three unreadable cases (test-quality F1).
- `plugins/quorum/bin/selftest.py` — one reflow case per normalisation rule in
  `criteria_hash`, with an assertion that each variant actually reformats the
  fixture; `CRITERIA` gained a checkbox and a blank line so there is something to
  reformat (test-quality F2).
- `plugins/quorum/bin/selftest.py` — a report citing no hash, and the
  gate-stopped versus `--expect-report` distinction (test-quality F3,
  correctness F3).
- `plugins/quorum/bin/selftest.py` — module docstring, `READ_ONLY_WORKFLOWS`
  comment and the check's own comment now say what the check settles (declared
  grants) and what it does not (a shell) (spec-fidelity F2, security F1).
- `plugins/quorum/bin/audit.py` — `--expect-report` makes a missing `report.md`
  a violation for a run that was meant to write one (correctness F3).
- `plugins/quorum/workflow/audit.js` — `slug` must be kebab-case (security F2);
  `criteriaHash` is required (correctness F4); `proposedChange` falls back to the
  criterion text after refutation (correctness F5); the scribe is told to open
  with `# Audit report: <title>` (simplicity F2), to disregard any standing
  instruction naming `docs/work/` (simplicity F1), and to record a *Ran during
  the audit* section when a cluster did not confirm it ran nothing (security F3);
  clustering notes are logged (simplicity F3); the agent-name comment no longer
  overstates the guarantee (spec-fidelity F2).
- `plugins/quorum/skills/audit/SKILL.md` — Step 5 requires the criteria array to
  be copied from `criteria.md` word for word and says why; Step 6 passes
  `--expect-report`, states what exit 0 does not prove, and reports a
  ran-something admission above the findings.
- `plugins/quorum/reference/audit.md` — `--expect-report`, and a *What the hash
  does not cover* paragraph (correctness F2, spec-fidelity F3).
- `docs/fixtures/audit-demo/test/helper.js` — sets `WIDGET_API_KEYS` before
  requiring the server, so the shipped tests are consistent with the code
  (test-quality F4).

Verification of my own changes: every fix was mutation-tested. Reverting the
parser fails 11 new checks; deleting either normalisation rule from `audit.py`
fails the two checks naming it; stubbing the `cited is None` branch or the
`expect_report` branch fails the check for each. The five read-only probes each
still produce exactly one targeted FAIL — an unregistered `agentType`, the
auditor granted `Write` inline, the auditor granted `Edit` as a block sequence
(this one passed silently before), the scribe granted `Read`, and `audit.js`
deleted (two FAILs, both correct). `audit.js` and `pipeline.js` both parse.
`claude plugin validate` passes on both manifests. `guard.py --work-dir
docs/work/quorum-audit` is clean.

## Escalations

### E1 — AC10 contradicts the plan's own *Approach*, and only you can reword it

AC10 requires `selftest.py` to fail when `workflow/audit.js` "names an agent
whose definition grants a file-editing tool". *Approach* ("Reuse `quorum-scribe`
for the report") and S5 require `audit.js` to name `quorum:quorum-scribe`, which
grants `Write`. Both cannot hold. Something must write `report.md`, `audit.js`
has no file tools of its own, and every candidate agent grants a write tool by
definition.

The builder implemented the check with exactly one exemption, `quorum-scribe`,
named in a constant and itself constrained: the scribe must be write-only, so
granting it `Read`, `Grep`, `Glob` or `Bash` makes it stop qualifying and the
check fires. I verified that — the probe produces exactly one FAIL. This is a
good resolution of the engineering problem. What is missing is the recorded
decision, and *Acceptance criteria* is a section neither the builder nor I may
edit.

**Options.** (a) Reword AC10 to the property actually worth protecting: "names an
agent that can both read the repository under audit and edit it." (b) Keep the
wording and record the write-only-scribe carve-out in the AC itself. (c) Give the
audit its own write-only agent so `quorum-scribe` is never named here — more
surface for no behavioural gain.

**Recommendation: (a).** It is what the code already enforces, it states the real
invariant, and it does not need a named exemption to be true.

### E2 — The criteria hash does not cover the seam it is assumed to cover

`criteria.md` is hashed and `report.md` cites the hash, so criteria edited
*in the file* after the gate are detectable. But the auditors never read
`criteria.md`: they measure `args.criteria`, which the skill assembles separately
for the `Workflow` call. Nothing mechanical checks the two are the same list. A
criterion paraphrased on its way into that call is audited in its weakened form,
and `audit.py --verify` still exits 0 and prints `clean`.

AC5 as literally worded is met, which is why I marked it `yes` — the mechanism it
names exists and is tested. The finding is that the mechanism's *purpose* has a
hole one step to the side of where it looks, and two independent lenses found it.

I have documented it rather than papered over it: `reference/audit.md` now has a
*What the hash does not cover* paragraph, `SKILL.md` Step 5 requires the array to
be copied word for word and says what paraphrasing costs, and Step 6 states what
exit 0 does not prove.

**Options.** (a) Accept the documented limit — the skill writes both sides, and
it is now told plainly to copy rather than restate. (b) Add a mode to `audit.py`
that hashes a structured list, have the skill run it over the exact `args.criteria`
before launching, and have `audit.js` refuse to run on a mismatch. Real closure;
one more helper mode and one more step in the skill. (c) Have `audit.js` re-render
the criteria as markdown and hash them in JS — fragile, because the hash is over
markdown text and the two renderings must agree byte for byte forever.

**Recommendation: (b)**, as a follow-up work item rather than here. It is the only
option that makes the guarantee mechanical, and (c) makes the hash's definition
travel, which `audit.py`'s own comments argue against at length.

### E3 — `quorum-auditor` holds `Bash`, so nothing mechanical keeps the audit read-only

This is the property the whole command rests on. `/quorum:audit` is designed to
run on the default branch of a production repository that never asked for this
pipeline, and the stated reason that is safe is that nothing it starts can write
to that repository or execute it. `plugins/quorum/agents/quorum-auditor.md`
grants `Read, Grep, Glob, Bash`; `selftest.py` counts `Bash` as a read tool; the
plugin's only `PreToolUse` hook matches `Edit|Write|MultiEdit` and not `Bash`. A
shell can `sed -i`, `git commit`, `git push`, and `npm test`.

So AC11 and the write-side of AC1 are enforced by prompt text alone. The
repository under audit is also untrusted input — a README or comment carrying
injected instructions reaches an agent holding an unrestricted shell.

I fixed the claims that said otherwise, in four places, and made an auditor's own
admission durable in `report.md` instead of transient in the run log. I did not
change the grant: the plan's *Approach* names `Read, Grep, Glob, Bash`
explicitly, and removing `Bash` changes what an auditor can do.

**Options.** (a) Drop `Bash` from `quorum-auditor`. `Read`, `Grep` and `Glob`
cover searching; `git log` is the only listed use that needs a shell, and it is
rarely load-bearing for a spec audit. This makes the mechanical claim true. (b)
Keep `Bash` and add a `PreToolUse` hook that allows only a read-only command
allowlist for this agent. Strongest, and the most work. (c) Keep `Bash` and
accept that the guarantee is prompted — now stated honestly everywhere.

**Recommendation: (a) now, (b) later.** A spec audit that cannot run `git log` is
a small loss; a spec audit that can `git push` to a production `main` is not a
small risk, and the command's entire selling point is that it is safe there.

### E4 — `quorum-scribe` still tells itself to write into `docs/work/<slug>/reviews/`

`audit.js` reuses `quorum-scribe`, exactly as the plan's *Approach* directs. But
the agent's standing instruction was never generalised: its `description` and
body both name `docs/work/<slug>/reviews/NNN-<lens>.md` — the one tree an audit
must not touch — and a scribe that follows it writes a file that breaks AC1. The
`tools:` line is all `selftest.py` checks, so the drift is invisible to the suite.

I added an explicit override to the scribe's task prompt in `audit.js`, which is
the strongest fix available inside this change's scope. I did not touch the agent
definition: *Non-goals* excludes "the agents they use", and `quorum-scribe` is
used by all four numbered steps.

**Options.** (a) Generalise the agent — "transcribe verbatim into whichever path
the task names" — and move the review-file naming rule into the `pipeline.js`
prompts. I verified this is lossless: `pipeline.js` already spells the full path
out at both call sites. (b) Give the audit its own write-only scribe. Duplicates
an agent to avoid editing one. (c) Leave it at the prompt override.

**Recommendation: (a)**, as its own small work item, since it needs a non-goal
lifted. The agent's `description` is already false today — it writes audit
reports too.

### E5 — Nine acceptance criteria have no verification, because the lens assigned to them was dropped

The plan's *Test strategy* is explicit and honest: AC5 and AC10 are mechanically
covered, and AC1, AC2, AC3, AC4, AC6, AC7, AC8, AC9 and AC11 "are properties of
what a prompt causes to happen", to be checked by "the `behavior` lens driving
`/quorum:audit` against a **fixture repository**". The builder committed that
fixture and wrote its answer key precisely so the lens would have something
controlled to compare against, and recorded under *Deliberately left out* that
"the run itself belongs to `/quorum:3-review`".

That lens was dropped from the panel before this run — `state.json` records
"behavior pass dropped, AC11 added" — and the panel handed to me lists
`missing: ["behavior"]`. So the verification the plan designed never happened,
and the fixture built for it has never been used. Five lenses read the code
carefully; none of them ran the command, and none could.

This is why nine criteria are marked `no` rather than `yes`. They are not known
to be broken. They are unobserved, which is a different thing from met, and the
plan says so in its own words.

**Options.** (a) Run the behavior lens against `docs/fixtures/audit-demo/` before
merging, per `docs/fixtures/README.md`, and re-adjudicate those nine on what it
finds. (b) Merge on the code review alone and accept that `/quorum:audit` ships
never having been executed. (c) Operate the command manually once against the
fixture and record the result as evidence.

**Recommendation: (a).** The fixture is committed, the answer key is written and
I checked it against the fixture code myself; the remaining work is to run it.
Shipping a command that has never been run, whose safety story is prompt-level
(E3), is the combination this plugin exists to prevent.

## Follow-ups

Real, and out of scope for this change.

- `plugins/quorum/workflow/audit.js`'s deterministic merge logic — cluster
  dedup, the unclustered sweep, the gap-without-searches downgrade, the
  `proposedChange` fallback I added — has no mechanical test, because the
  repository has no JavaScript test runner (claim C8). It is the part of this
  change most amenable to unit testing and the part with none.
- The report format now lives in two places that must agree: `reference/audit.md`
  and the restated format in the scribe prompt. They had already drifted once —
  the missing `# Audit report:` heading was simplicity F2. Nothing checks them.
- `plugins/quorum/bin/selftest.py` nits noted by the simplicity lens and left
  alone: an unused `code` in `write_audit`, an unreachable `or ''`, and two
  passes over `scripts` where one would do.
