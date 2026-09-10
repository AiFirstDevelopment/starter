---
name: calibrate
description: Measure the review panel against fixtures whose defects are known in advance - catch rate and false-positive rate per lens. A deliberate, human-invoked evaluation, not part of any test suite. Use to decide whether the six-lens panel is worth its cost, or after changing a lens remit.
argument-hint: [optional: a case name to run just one fixture]
---

# Calibrate the review panel

One question: **is this panel any good, and which lens is carrying it?**

The pipeline cannot answer that from its own records, and no amount of care with
those records will fix it. `accepted` and `rejected` count adjudications, not
defects: a defect three lenses report counts three times, and a finding whose
diagnosis is accepted while its remedy is refused counts as an acceptance. Across
eight completed runs that arithmetic reads 138 of 144 findings accepted — a
number that looks like a flawless panel and is evidence of nothing at all.

The only way out is to know the answer before you ask. That is what this does.

## This is not a test

**Never wire it into `selftest.py`, a CI workflow, or anything required to be
green.** Two reasons, and the second is the one that matters:

- It costs real model time — six lenses across every fixture case.
- Its output legitimately varies between runs. A varying number in a suite that
  must pass gets one of two treatments: the suite goes flaky, or the thresholds
  get lowered until it passes. Both destroy the measurement, and the second does
  it silently.

It is an evaluation. A human runs it, reads it, and decides. `selftest.py` covers
the scorer's arithmetic against synthetic findings, which is deterministic — and
launches no agent.

Run it when you have changed a lens remit, changed the reviewer agent, changed
the panel's models, or want to argue about whether six lenses earn their cost.

## What it measures, and what it refuses to

| | |
|---|---|
| **Catch rate** | Of the defects planted for a lens, how many that lens found. |
| **False positives** | Findings at `minor` or above **on clean controls only**, where nothing was planted. |
| **Cross-catches** | A lens finding another lens's defect. Reported, never scored. |
| **Unmatched** | A finding on a case that matches no planted defect. **Printed, never judged.** |

That last row is the discipline that keeps the rest honest. On a fixture carrying
planted defects, an unmatched finding might be a false positive or might be a
real defect nobody planted — the fixture cannot tell you which, and a scorer that
guessed would manufacture exactly the kind of unfalsifiable number this exists to
replace. So it prints them and you read them.

Only clean controls yield a false-positive count, because only there is it known
that there was nothing to find.

`nit` findings never count against a lens. The reviewer prompt explicitly invites
them; scoring them here would punish a lens for doing as it was told.

## Procedure

1. **Validate the fixtures** before spending anything on agents:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/calibrate.py" \
     --cases "${CLAUDE_PLUGIN_ROOT}/calibration/cases" --validate
   ```

   It reports the case count, the planted-defect count and the control count, and
   fails on a manifest that could not produce a meaningful score. Fix any
   complaint before going on — a vague manifest yields a confident wrong number.

2. **Read the manifests yourself, once.** You are about to launch agents that
   must not see them. Confirm the planted defects are real defects and that the
   controls are genuinely clean; a control with an unnoticed bug in it turns a
   correct finding into a recorded false positive and makes the panel look worse
   than it is.

3. **Run the lenses.** Build the case list from the manifests — for each, its
   `case`, the absolute `root` of its `repo/` directory, the absolute path to its
   `plan.md`, and its `unrunnable` list and reason — and call the **Workflow**
   tool:

   ```
   Workflow({
     scriptPath: "${CLAUDE_PLUGIN_ROOT}/workflow/calibrate.js",
     args: { cases: [ { case, root, plan, unrunnable, unrunnableReason }, ... ] }
   })
   ```

   If the Workflow tool is not available on this client, **stop and say so**. Do
   not hand-orchestrate the lenses: a panel prompted by you in one session is not
   the panel production runs, and a score taken from it would describe something
   that does not exist. Say the command cannot run here and why.

   Pass `models` through if the user named any, in the same shape
   `/quorum:pipeline` takes.

4. **Score it.** Write the workflow's `results` array to a JSON file, then:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/calibrate.py" \
     --cases "${CLAUDE_PLUGIN_ROOT}/calibration/cases" \
     --findings <that file> --out docs/calibration/<YYYY-MM-DD-HHMM>
   ```

   The report lands at `docs/calibration/<run>/report.md`. Keep the findings JSON
   beside it — the report is a summary, and the raw findings are the evidence for
   it.

5. **Report to the user**, leading with the two numbers that decide anything: the
   worst catch rate and any false positive on a control. Then say plainly what
   the run does **not** establish — see below. Do not recommend dropping a lens
   from one run of two fixture cases.

## What a run of this does not tell you

Say these out loud rather than letting a table imply otherwise:

- **The sample is tiny.** A catch rate over one or two planted defects is a
  count, not a rate. Treat a single run as an anecdote and say so.
- **Fixtures are not production changes.** They are small, self-contained and
  written to carry a known defect. A lens that does well here may do worse on a
  4,000-line diff, and the harness cannot see that.
- **A planted defect is one somebody thought of.** The panel's real value is in
  what nobody thought to plant, which is exactly what this cannot measure.
- **`behavior` is largely unmeasured.** Both shipped fixtures are libraries with
  no runnable surface, so the lens that actually operates the software is
  declared unrunnable on both and scored on neither. That is a real hole in the
  harness, recorded honestly rather than papered over with a fixture that reads
  code and calls itself `behavior`.

## Adding a case

A case is a directory under `calibration/cases/<name>/`:

```
<name>/
├── manifest.json    # what is planted, and where
├── plan.md          # the plan the lenses judge it against
└── repo/            # the code under review
```

`manifest.json` declares `case`, `control`, `planted`, and optionally
`unrunnable` with `unrunnableReason`. Every planted defect needs `id`, `lens`,
`file`, `lines` as `[first, last]`, and `match`: the strings a finding must
contain to count as having found it.

Two rules about `match`, both learned from the alternative being worse:

- **Make it specific enough that a wrong finding cannot satisfy it.** Matching on
  `"user"` will credit a lens for any remark about users.
- **Make it general enough that a right finding does.** Matching on a whole
  sentence credits nobody. Name the symbol and the defect's noun.

If a defect needs judgment to recognise, it is declared too vaguely. Tighten the
manifest rather than loosening the matcher — the moment matching becomes a
judgment call, the harness is measuring the matcher.

A clean control declares `"control": true` and `"planted": []`, and must actually
be clean. Run its tests before trusting it.
