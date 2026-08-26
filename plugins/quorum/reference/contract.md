# Quorum artifact contract

Every skill in the pipeline reads and writes files under a single per-work-item
directory. This is the contract between steps. Do not invent other locations.

```
docs/work/<slug>/
├── plan.md              # written by /quorum:1-plan, checkboxes ticked by /quorum:2-build
├── state.json           # terse index of what has run; every step appends to it
├── reviews/
│   ├── 001-correctness.md
│   ├── 002-spec-fidelity.md
│   └── ...              # written by /quorum:3-review, one file per lens
└── verdict.md           # written by /quorum:4-quorum
```

## Resolving `<slug>`

In order of precedence:

1. An explicit slug passed as an argument to the skill.
2. The current git branch name, lowercased, with any `feature/`, `fix/`, `chore/`
   prefix stripped and non-alphanumeric runs collapsed to a single `-`.
   `feature/PROJ-12_Add-Login` becomes `proj-12-add-login`.
3. If the branch is the default branch (`main`/`master`) or the slug would be
   empty, stop and ask the user for a slug. Never write pipeline artifacts to a
   slug derived from the default branch — that is a sign work is happening on the
   wrong branch.

   `/quorum:1-plan` is the one exception: rather than stopping, it names and
   creates the work branch, then resolves the slug from it. Every other step
   stops. See that skill for the naming rules.

Once a step has resolved a slug, later steps in the same session reuse it.

## Pipeline state — `state.json`

The prose artifacts say what was decided. They do not say **what has run**, and
reconstructing that from file mtimes gives wrong answers: a checkout rewrites
mtimes, and a commit landing after a finished pipeline is indistinguishable from
a pipeline that never got that far. Those two are the opposite of each other, so
guessing between them is worse than not answering.

`state.json` is a terse index of what has run, written as it runs. Keep it small —
counts, outcomes, and commit SHAs. Never prose, never a copy of the artifacts.

```json
{
  "slug": "retry-failed-webhooks",
  "branch": "feature/retry-failed-webhooks",
  "stage": "adjudicated",
  "updated": "2026-08-25T21:14:03Z",
  "plan":    { "acs": 4, "steps": 6, "open": 1, "requirementsHash": "3f9a1c…" },
  "build":   { "stepsDone": 6, "deviations": 2, "suite": "green", "head": "a1b2c3d" },
  "review":  { "round": 1, "lenses": ["correctness", "spec-fidelity", "security",
               "simplicity", "test-quality"], "missing": [], "findings": 7,
               "blockers": 1, "head": "a1b2c3d" },
  "verdict": { "outcome": "ready with follow-ups", "suite": "green", "accepted": 3,
               "rejected": 4, "unmet": 0, "escalations": 2, "head": "e4f5g6h" },
  "recheck": { "findings": 1, "blockers": 0 },
  "pr":      { "url": "https://github.com/o/r/pull/12", "draft": false },
  "log": [
    "2026-08-25T20:40:02Z 2-build built 6/6, 2 deviations, suite green",
    "2026-08-25T21:14:03Z 4-quorum adjudicated ready with follow-ups, 2 escalations"
  ]
}
```

`stage` is one of `planned`, `approved`, `building`, `built`, `reviewed`,
`adjudicated`, `published`. Absent sections mean that step has not run.

`recheck` is the read-only pass over the judge's own adjudication commits — the
one part of the branch no lens saw. Absent means it did not run, which is not the
same as clean.

`plan.requirementsHash` fingerprints *Intent*, *Acceptance criteria*, and
*Non-goals* as they stood when the plan was written, so `/quorum:guard` can prove
nobody moved the target. `/quorum:1-plan` records it once. **No later step may
re-record it** — a step that rewrites the baseline to match what it changed has
defeated the check entirely.

`guard` is the result of the mechanical rule check at publish time: `clean` and a
violation count.

### `head` is the load-bearing field

Every stage that inspects code records the commit it inspected, taken **after**
that stage's own commits land:

```bash
git rev-parse --short HEAD
```

That turns "are the reviews stale?" from a guess into a question git answers
exactly:

```bash
git log --oneline <review.head>..HEAD    # commits no lens has seen
git diff --stat <review.head>..HEAD      # and how big they are
```

An empty result means the reviews cover the tree. A non-empty one names precisely
what they do not, which is a different and far more useful statement than "stale".

`head` describes committed work only. A stage that ran over a dirty working tree
inspected more than its `head` names, which is why `/quorum:status` reads
`git status --porcelain` alongside it.

### Writing to it

Use the helper — it deep-merges your patch, stamps `updated`, appends one log
line, and caps the log. Record only your own section:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/state.py" docs/work/<slug> \
  '{"stage":"built","build":{"stepsDone":6,"deviations":2,"suite":"green","head":"a1b2c3d"},
    "log":"2-build built 6/6, 2 deviations, suite green"}'
```

If `python3` is unavailable, write the same shape by hand with the Write tool,
preserving every key you did not set. Do not skip the record because the helper
did not run.

Rules:

- **Record after the work, not before.** The file says what happened, not what was
  intended.
- **Never hand-edit it to change what a step reported.** Re-run the step instead.
- **It is an index, not the record.** `plan.md`, `reviews/`, and `verdict.md`
  remain authoritative. When the two disagree, the artifacts win and the
  disagreement is itself worth reporting.
- Missing or malformed is not an error — it means the work item predates this
  file or a write failed. Fall back to reading the artifacts.
- `/quorum:status` **never writes to it.**

## Review numbering

Review files are `NNN-<lens>.md`, where `NNN` is zero-padded to three digits.
To pick the next number, list `docs/work/<slug>/reviews/`, take the highest
existing numeric prefix, and add one. Start at `001`. Numbering is per work item,
not global. Never renumber or overwrite an existing review — reviews are an
append-only record, including reviews that later turned out to be wrong.

## Determining the diff under consideration

Unless the user names an explicit range, "the change" means the diff between the
current branch and the base branch it will merge into:

```bash
BASE=$(git symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null | sed 's@.*/@@')
BASE=${BASE:-main}
git merge-base HEAD "origin/$BASE"          # the fork point
git diff "$(git merge-base HEAD origin/$BASE)"...HEAD   # committed changes
git diff HEAD                                # plus uncommitted working-tree changes
```

Include uncommitted working-tree changes. Report which ranges were used.
