# Quorum artifact contract

Every skill in the pipeline reads and writes files under a single per-work-item
directory. This is the contract between steps. Do not invent other locations.

```
docs/work/<slug>/
├── plan.md              # written by /quorum:1-plan, checkboxes ticked by /quorum:2-build
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

Once a step has resolved a slug, later steps in the same session reuse it.

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
