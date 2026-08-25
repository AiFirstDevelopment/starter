# Determining the change under test

Unless the user names an explicit range, "the change" means the diff between the
current branch and the base branch it will merge into — the whole branch, not the
last commit:

```bash
BASE=$(git symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null | sed 's@.*/@@')
BASE=${BASE:-main}
git diff "$(git merge-base HEAD origin/$BASE)"...HEAD   # committed changes
git diff HEAD                                            # plus uncommitted work
```

Include uncommitted working-tree changes, and report which ranges you used.

## If the repo uses the quorum pipeline

A repo that also has the `quorum` plugin enabled keeps a plan at
`docs/work/<slug>/plan.md`, where `<slug>` derives from the branch name. When that
file exists, **its acceptance criteria are the primary checklist** — every
criterion gets a test — and its *Test strategy* section says which criteria were
meant to be covered behaviorally and which pure logic warrants unit tests.

When it does not exist, work from the diff and from what the change appears
intended to do, and say so in your report.
