---
name: 2-build
description: Step 2 of the quorum pipeline. Implements the plan at docs/work/<slug>/plan.md, ticking off steps as it goes and recording any deviation from the plan.
argument-hint: [slug]
disable-model-invocation: true
---

# Step 2 — Build

Implement the plan. Nothing more, nothing less.

Read `${CLAUDE_PLUGIN_ROOT}/reference/contract.md` for slug and layout rules.

## Procedure

1. **Read `docs/work/<slug>/plan.md` in full** before writing anything. If it does
   not exist, stop and tell the user to run `/quorum:1-plan` first. Do not
   improvise a plan.

2. **Resolve open questions.** If the plan has unanswered *Open questions* whose
   answers would change what you build, ask now rather than after the code exists.

3. **Work step by step.** After completing each step in the *Steps* list, tick its
   checkbox in `plan.md`. This is what makes an interrupted session resumable —
   a later session reads the plan and knows exactly where work stopped.

4. **Match the surrounding code.** Follow the naming, structure, error handling,
   and comment density already in the repo. New code should be indistinguishable
   in style from the code next to it.

5. **Record deviations as they happen.** Any time reality differs from the plan,
   append to the *Build notes* section of `plan.md`:

   ```markdown
   - **S3 deviation:** plan assumed the repository exposed `findByEmail`; it does
     not. Used `findOne({ email })` instead. No behavior change.
   ```

   Step 4 reads these. An unrecorded deviation reads as a defect later.

6. **Stop when the plan is done.** Do not add unrequested features, do not fix
   unrelated issues you notice, do not refactor adjacent code. Note them for the
   user instead.

7. **Run whatever tests exist** (`/tests:run`, or the repo's own command if the
   `tests` plugin is not enabled) and report the result honestly. Do not report the build complete with failing tests.

8. **Update *Status*** in `plan.md` to `built` and record the state per the
   contract. If you committed, take `head` afterwards so it names the tree you
   actually built:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/state.py" docs/work/<slug> \
     '{"stage":"built","build":{"stepsDone":6,"deviations":2,"suite":"green",
       "head":"'"$(git rev-parse --short HEAD)"'"},
       "log":"2-build built 6/6, 2 deviations, suite green"}'
   ```

   `suite` is `green`, `red`, or `none`. Record `red` honestly — the next step
   needs to know, and a suite recorded green over failing tests is the one lie
   that makes every later report worthless.

9. **Report**: what was built, which steps are ticked, what deviated, test
   results, and anything you deliberately left out.

## When the plan is wrong

If implementing reveals that the plan itself is flawed — an acceptance criterion
is impossible, the approach cannot work, the change is much larger than scoped —
**stop and say so.** Do not quietly redesign around it.

Small, obviously-correct corrections you may make directly, provided you record
them in *Build notes*. Anything that changes intent, acceptance criteria, or
non-goals is the user's decision, not yours.

## Rules

- The plan bounds the work. Scope changes are escalated, never absorbed.
- Never edit *Intent*, *Acceptance criteria*, or *Non-goals*. Those are step 1's
  output and step 4's yardstick. You may tick *Steps* checkboxes and append to
  *Build notes* — nothing else.
- Never weaken or delete an existing test to make your change pass.
