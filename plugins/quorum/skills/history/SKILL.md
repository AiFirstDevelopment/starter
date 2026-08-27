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
python3 "${CLAUDE_PLUGIN_ROOT}/bin/history.py" --markdown
```

One section per work item, each with the prompt that produced it quoted in full.
**Use `--markdown` unless the user asked for the table.** The table exists for a
terminal and pays for it: every field is clipped to a column width, and a prompt
does not survive that at any width.

Useful variations:

```bash
history.py                   # the fixed-width table, for a narrow terminal
history.py --author joel     # only items planned by a matching author or email
history.py --limit 10        # the ten most recent
history.py --json            # for anything you want to compute over
```

**Present the output as it comes back and do not summarise it.** It is already
prose in sections; restating it underneath adds a second, worse copy. If the user
asked about a particular item, follow up by reading that plan's
`docs/work/<slug>/plan.md` and `verdict.md` — this listing is an index, not a
summary of what happened.

## What the fields actually mean

The output now carries its own caveats inline — an inferred request number, an
uncommitted plan, and which agents built it are printed beside the item they
apply to, rather than explained once underneath where they attach to nothing.
Three meanings it still cannot state for itself:

- **Prompt** is the plan's *Prompt* section, verbatim. It is a record, not a
  requirement: nothing downstream reads it and nothing checks it, so a plan whose
  *Intent* drifted from its *Prompt* still passes every gate. Comparing the two
  is the reason it is here, and it is a comparison only a person makes.

  It is absent on every item planned before `1-plan` began recording it, and
  cannot be recovered from the repository — the prompt was never written to disk.
  Say "not recorded", never reconstruct one from the Intent.

- **Planned / by** is the author date and author of the commit that first added
  `plan.md`, not a file mtime — a checkout rewrites those, which is the same
  reason `state.json` exists. And it is **whoever's git config made the commit**,
  not necessarily whoever decided the work should happen: in this pipeline the
  builder, judge, and publisher all commit under the repository owner's config,
  so on a solo repo it is one name repeated. Agent involvement comes from
  `Co-Authored-By` trailers and is printed separately, precisely because the
  author field cannot carry it.

- **took** is wall-clock between the first and last event `state.json` recorded,
  and appears only once a run recorded at least two. It includes any time the item
  sat waiting for a human, because that is also time the change took. These are
  what `bin/watch.py` estimates from during a live run — durations that happened
  *and* the only basis for saying how long the next one has left.

## What it will not tell you

- **Who asked for the change.** *Prompt* records **what** was asked, never who
  asked it. No plan records a requester, and the commit author is a proxy for it
  at best — say so rather than presenting it as provenance.
- **Anything about an uncommitted plan.** It is listed, sorted last, and marked
  `(uncommitted)`. Nothing records who wrote it until it is committed, and a file
  mtime is not an answer to that question.
- **A request for work that was never published.** No `pr` in `state.json` and
  nothing in the history means nothing was found, not that nothing exists — a
  change merged with a rebase and a tidy message leaves no trace to find.
- **Work on branches you do not have.** `docs/work/` is read from the current
  branch. A change item that only exists on somebody else's unmerged branch is
  not here, and its absence is not evidence it does not exist.
