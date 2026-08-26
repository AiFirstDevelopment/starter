---
name: history
description: Lists every change this repository has planned through the quorum pipeline, oldest first - what it was, who planned it, when, and where it got to. Reads docs/work/ and git history. Read-only; changes nothing.
argument-hint: [author or slug]
---

# What this repo has been asked to do

`docs/work/` accumulates one directory per change and never loses one, so the
repository already holds a record of every change anyone has planned through the
pipeline. This reads it back.

Read `${CLAUDE_PLUGIN_ROOT}/reference/contract.md` for the artifact layout.

## Run it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/history.py"
```

Useful variations:

```bash
history.py --full            # include each plan's Intent
history.py --author joel     # only items planned by a matching author or email
history.py --limit 10        # the ten most recent
history.py --json            # for anything you want to compute over
```

Present the table as it comes back. If the user asked about a particular item,
follow up by reading that plan's `docs/work/<slug>/plan.md` and `verdict.md` —
this listing is an index, not a summary of what happened.

## What the columns actually mean

Worth being precise, because two of them are easy to misread:

- **PLANNED** is the author date of the commit that first added `plan.md`, not a
  file mtime. A checkout rewrites mtimes, which is the same reason `state.json`
  exists; a plan written today on a branch checked out yesterday would otherwise
  read as yesterday's work.

- **BY** is that commit's git author — meaning **whoever's git config made the
  commit**, not necessarily whoever decided the work should happen. In this
  pipeline the builder, judge, and publisher all commit under the repository
  owner's config, so on a solo repo this column is one name repeated. It earns
  its place on a shared repo.

  Agent involvement is a separate line, taken from `Co-Authored-By` trailers, and
  it is separate precisely because the author field cannot carry it.

- **PR** is where to find the pull or merge request. It comes from
  `state.json`'s `pr` object when the publisher recorded one — that case also
  prints the full URL, and `*` marks a draft. Failing that it is **inferred from
  the history**, which is why the listing says so: a squash merge collapses the
  branch into one commit carrying `(#12)`, and a real merge commit or a GitLab
  merge says `Merge pull request #12 from …` / `See merge request grp/proj!12`.
  Both are read, because neither finds the other's case.

  An inferred reference can be wrong. Any commit touching the work item that ends
  in `(#12)` matches, and that might be a later fix rather than the change itself.
  Treat a recorded URL as fact and an inferred number as a lead.

- **STAGE** prefers `state.json`'s stage and falls back to the plan's *Status*.
  Work items planned before the state recorder existed have only the latter, so
  both are read rather than assuming the newer one is there.

## What it will not tell you

- **Who asked for the change.** No plan records a requester. The author is the
  best available proxy and is not the same thing — say so rather than presenting
  it as provenance.
- **Anything about an uncommitted plan.** It is listed, sorted last, and marked
  `(uncommitted)`. Nothing records who wrote it until it is committed, and a file
  mtime is not an answer to that question.
- **A request for work that was never published.** No `pr` in `state.json` and
  nothing in the history means nothing was found, not that nothing exists — a
  change merged with a rebase and a tidy message leaves no trace to find.
- **Work on branches you do not have.** `docs/work/` is read from the current
  branch. A change item that only exists on somebody else's unmerged branch is
  not here, and its absence is not evidence it does not exist.
