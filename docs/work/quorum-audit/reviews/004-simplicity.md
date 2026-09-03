# Simplicity review

- **Lens:** simplicity
- **Verdict:** findings
- **Diff range:** `bce043280170d6b26593b77d13cd591b52528e81...HEAD (plus uncommitted working-tree changes)`

## Findings

### F1 — quorum-scribe is reused for the audit report but its definition was never generalised — it still hard-codes writing into docs/work/<slug>/reviews/NNN-<lens>.md, the one tree the audit must not touch.

- **Severity:** major
- **File:** `plugins/quorum/agents/quorum-scribe.md`
- **Line:** 10

**What:**

The plan's *Decisions worth stating* says "Reuse `quorum-scribe` for the report", and `workflow/audit.js:481` does exactly that. But the agent's standing instructions were left review-only: its `description` says it "Transcribes structured review findings into review files under docs/work/<slug>/reviews/", and its body says "Write each lens's findings **verbatim** into `docs/work/<slug>/reviews/NNN-<lens>.md`, using the numbering and template from the quorum artifact contract." In `pipeline.js` the task prompts agree with that (`pipeline.js:290`, `:438`). In `audit.js` the task prompt contradicts it outright — "Write only docs/audit/<slug>/report.md. Write no other file." — and the reused agent is left carrying a directive to write somewhere else. Nothing in `selftest.py` covers the body of an agent definition; `test_agents()` only checks the `tools:` line, so this drift is invisible to the suite.

**Failure scenario:**

Run `/quorum:audit spec.md` against the committed fixture (`docs/fixtures/audit-demo/`, copied out per `docs/fixtures/README.md:22`). The Report phase invokes `quorum:quorum-scribe`, whose system prompt tells it to write `docs/work/<slug>/reviews/NNN-<lens>.md` "using the numbering and template from the quorum artifact contract" — a file it has no Read tool to consult. A scribe that follows its standing instruction creates a file under `docs/work/`, and the `git status --porcelain` check the skill runs at SKILL.md:200 then lists a path outside `docs/audit/`. That violates AC1 and the property reference/audit.md:44 calls "the property the whole design rests on". Even when the task prompt wins, the agent's own `description` is now false: it writes audit reports too.

**Suggested direction:**

Generalise the scribe's description and body to state its actual job — transcribe structured findings verbatim into whichever path the task names — and move the `docs/work/<slug>/reviews/NNN-<lens>.md` naming rule into the pipeline.js prompts that already restate it (pipeline.js:290 and :438 both spell the path out in full, so nothing is lost).

### F2 — `args.title` is a dead parameter: accepted, documented in the skill, echoed back, and never reaching any artifact — because the scribe prompt's restated report format omits the `# Audit report: <short title>` heading the contract requires.

- **Severity:** minor
- **File:** `plugins/quorum/workflow/audit.js`
- **Line:** 21

**What:**

`const title = (args && args.title) || slug` is read at line 21 and used at exactly one place, line 488, where it is echoed straight back in the return object. `SKILL.md:156` instructs the caller to pass it. But the scribe cannot read `reference/audit.md` (it is Write-only), so `audit.js:443-451` restates the format inline — and that restatement begins at "Header fields, exactly these:" with `- **Slug:**`. The `# Audit report: <short title>` line that `reference/audit.md:135` puts at the top of every report is not in the restatement, and `title` is never interpolated into the prompt. The skill's Step 6 (SKILL.md:206-220) never uses the returned `title` either. This is duplication-drift: the report format now lives in two places and the copies already disagree.

**Failure scenario:**

Call the workflow with `slug: "billing-api"`, `title: "Billing API"`. The scribe receives a prompt whose first structural instruction is "Header fields, exactly these:" followed by `- **Slug:** billing-api`. `docs/audit/billing-api/report.md` therefore opens with a bullet list and no `# Audit report: Billing API` heading, diverging from the format `reference/audit.md:135` documents, while the `title` the skill was told to supply is discarded. `audit.py --verify` only inspects the `Criteria hash` field, so nothing catches it.

**Suggested direction:**

Either interpolate the title into the scribe prompt as the leading `# Audit report: ' + title` line, restoring agreement with reference/audit.md:135, or drop `args.title` from audit.js:21 and SKILL.md:156 and delete `title` from the return object.

### F3 — `CLUSTER_SCHEMA.notes` is a dead output field — the clustering agent is asked to produce it and nothing ever reads it.

- **Severity:** nit
- **File:** `plugins/quorum/workflow/audit.js`
- **Line:** 86

**What:**

`notes: { type: 'string' }` is declared on the cluster schema. The only consumer of the clustering result is `grouped.clusters` at line 181; `grouped.notes` appears nowhere in the file, in `SKILL.md`, or in the returned object. Unlike `proposedChange` and `searched` — which are dead-looking but genuinely reach the scribe through the `rows` JSON at line 480 — `notes` reaches nothing.

**Failure scenario:**

The Cluster phase runs; the model fills in `notes` with its reasoning about how it grouped the criteria (it is a plain unconstrained string with no description telling it otherwise), that text is generated and then silently dropped. A reader of the schema reasonably assumes clustering notes surface somewhere in `criteria.md` or `report.md`; they do not appear in either.

**Suggested direction:**

Delete the property, or read it and `log()` it alongside the cluster names at line 211 so the choice is visible in the run.

## Notes

Checked and deliberately not reported: the duplicated `sections()`/normalisation in plugins/quorum/bin/audit.py:41 (the hash-stability rationale for not importing from the vendored, drift-checked guard.py is sound, and the source states it at the function); the near-verbatim `announce()` in audit.js:219 vs pipeline.js:212 (workflow scripts appear to have no shared-module mechanism); the repeated NEVER_RUN/NEVER_EXTRA prompt constants (a defended prompt-reinforcement choice, applied consistently); the status-vocabulary table appearing in README.md, reference/audit.md and quorum-auditor.md (checked all three for drift — they agree); several selftest.py nits (unused `code` in write_audit, the unreachable `or ''` at the `--hash prints a sha256` check, two passes over `scripts` where one would do) that are too small to spend judge attention on. The frontmatter_tools YAML block-sequence parsing hole at selftest.py:1139 and the refute-model default at audit.js:30 are correctness questions, left to that lens.
