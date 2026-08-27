---
name: audit
description: Measure an existing repository against a spec - free text, or a spec file already in the repo - and report where the implementation falls short, or "All clear". Runs on the default branch, writes no code, and works on a repo that never used the pipeline. Use to check that a repo faithfully implements a spec.
argument-hint: [the spec as free text, or a path to a spec file in this repo]
---

# Audit a repository against a spec

One question: **does this repository faithfully implement that spec?** The
deliverable is a file listing proposed changes, or `All clear`.

Read `${CLAUDE_PLUGIN_ROOT}/reference/audit.md` first — it defines the slug
rules, the file layout, the criteria and report formats, and the
`met` / `gap` / `unverified` vocabulary you must use.

## What makes this safe on `main`

Every other quorum command refuses to run on the default branch, and this one is
built for it. The difference is that this command **writes no code**. It
proposes; it never fixes. There is nothing for an approval gate to protect and
nothing that can damage `main`:

- It creates no branch and switches no branch.
- It makes no commit and no push.
- It writes `docs/audit/<slug>/` and nothing else. When the run is done,
  `git status --porcelain` lists changed paths under `docs/audit/` and nowhere
  else. **Check that at the end and say so.**
- It never executes the repository under audit — not its application, not its
  build, not its test suite, not a script it ships. The shell searches and reads.

That last one costs something and you say so rather than hiding it: this command
can tell you the code **appears** to implement a requirement; it cannot tell you
the software does. Criteria that turn on runtime behaviour come back
`unverified`, in those words.

The repository does not need to have used this pipeline. There is no `plan.md`
to find, no branch to be on, and nothing under `docs/work/` is read or written.

## Two things this deliberately does not do

- **More implemented than the spec is fine.** Behaviour this repo has that the
  spec never mentions is not a finding, in any form. The question is fidelity to
  the spec, not the absence of anything else.
- **General code review is out of scope.** A bug unrelated to a criterion belongs
  to `/code-review` or `/quorum:3-review`; mixing them buries the spec gaps.

## Step 1 — Resolve the spec

The argument is either a path to a file in this repository or the spec itself as
free text. Decide, and **do not guess quietly**:

- **Path-shaped** — one token, no spaces, containing `/` or ending in a document
  extension (`.md`, `.txt`, `.rst`, `.adoc`, `.pdf`, `.yaml`, `.json`).
  - The file exists → read it in full. It is the spec, and it stays the record;
    do not copy it into `criteria.md`.
  - **The file does not exist → stop, say so, and write nothing.** Name the path
    you looked for, offer to search for it (`git ls-files | grep -i <name>`), and
    offer the alternative of pasting the spec as text. Do **not** fall back to
    treating the path string as prose: auditing a repository against the sentence
    `docs/specs/billing.md` produces criteria from nothing and a report that
    looks exactly like a real one.
  - It exists but is a directory → say so and ask which file. Auditing against a
    directory is guessing which of its files was meant.
- **Anything else** — free text. It is the spec, and `criteria.md` is then the
  only record of it, so copy it verbatim into that file's *Spec* section.
- **No argument at all** — ask what to audit against. There is nothing to derive
  criteria from, and inferring a spec from the code makes the audit vacuous.

## Step 2 — Resolve the slug and check the agents

Slug, per `reference/audit.md`: an explicit argument, else the spec file's
basename, else two to four kebab-case words naming the spec's subject. It is
never derived from the branch — this runs on `main` on purpose.

If `docs/audit/<slug>/` already exists, say what is in it and that you are about
to overwrite it. A previous audit of a different spec keeps its own directory.

Then confirm the agents this needs are registered, under exactly these names:
`quorum:quorum-auditor` and `quorum:quorum-scribe`. If either is missing, stop
and say the plugin is not installed correctly. This sits above the gate for the
same reason it does in `/quorum:pipeline`: a wrong agent name does not surface
until the workflow's first agent call, which is after the user has decided.

## Step 3 — Derive the criteria

Read the spec and turn it into numbered, observable criteria.

**Derive them from the spec, not from the repository.** Do not read the code
first. Criteria shaped by what the implementation happens to do make the audit
vacuous — every criterion is met because every criterion was copied off the
thing being measured.

- **One criterion per obligation the spec states.** A "must", a "should", a
  described behaviour, a stated limit. Background, rationale, and examples are
  not obligations.
- **Observable, in the form `/quorum:1-plan` uses**: "when `<situation>`,
  `<observable result>`". A gap becomes an acceptance criterion in a plan later,
  and rewriting it at that point loses the citation.
- **Every criterion cites where it came from** — a quoted phrase, plus a heading
  or a `file:line`. **A criterion that cites nothing is not written.** A criterion
  with no source is one you invented, and the repository is about to be measured
  against it.
- **Do not invent, extend, or tighten.** If the spec is silent on something
  important, that is the spec's problem and not a criterion.
- A spec statement too vague to observe is not a criterion either. Say so at the
  gate — the user can sharpen it or accept its absence — rather than writing one
  nothing can settle.

Write `docs/audit/<slug>/criteria.md` in the format `reference/audit.md` gives,
then record the hash of the criteria list into its `Criteria hash` field:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit.py" --hash docs/audit/<slug>/criteria.md
```

That hash is what lets a reader prove the report was measured against the list
you are about to show — criteria softened between the gate and the report change
it, and `--verify` finds that.

## Step 4 — The gate

**Show the derived criteria in full and stop.** Not a count, not a paraphrase:
the criteria and their sources, which is the only thing the decision can honestly
be taken from. Say that `criteria.md` is already on disk and give its path, so
the user can read the whole file while the question waits.

Make plain what they are deciding: whether this list is what the repository
should be measured against. Say what is not in it — anything you could not derive
observably, and any part of the spec you judged not to be an obligation.

Then ask whether to run the audit.

**On anything short of a clear yes, stop.** `criteria.md` stays on disk — it is
the work product of everything above, and the user may want to edit it and come
back — and nothing else happens: no `report.md`, and no auditing agent has run.
That is an ordinary outcome, not a failed run.

If the user amends the criteria, rewrite `criteria.md`, re-record the hash, and
show the amended list again. The hash must always match what was approved.

## Step 5 — Run it

Resolve the commit being audited, so the report names the tree it read:

```bash
git rev-parse --short HEAD
```

Then call the **Workflow** tool:

```
Workflow({
  scriptPath: "${CLAUDE_PLUGIN_ROOT}/workflow/audit.js",
  args: {
    slug: "<slug>",
    title: "<short title>",
    specSource: "docs/specs/billing-api.md",   // or "free text supplied to /quorum:audit"
    criteriaHash: "<the recorded hash>",
    commit: "<short SHA>",
    criteria: [ { id: "AC1", text: "...", source: "\"...\" — docs/specs/billing-api.md:14" } ]
  }
})
```

Hand the criteria down rather than letting each auditor read `criteria.md` for
itself. Resolving them once here is what makes "every auditor measured the same
list" a fact rather than a hope — the same reason `/quorum:pipeline` resolves the
diff range once for its six lenses.

The script clusters the criteria, fans out one read-only auditor per cluster,
puts every claimed gap to a refutation pass on a different model, and has the
scribe write `report.md`. It launches nothing belonging to the repository under
audit at any point.

Pass `args.models: { refute: "opus" }` to change the model that tries to prove
the gaps wrong. It defaults to a different model from the auditors, because the
findings here are mostly **absences** and the same weights that missed a file the
first time miss it the second.

There is no watcher for this. `bin/watch.py` reads `docs/work/` and knows nothing
about `docs/audit/`, which is deliberate — say that, and point at `/workflows`
for the live progress tree.

## Step 6 — Report

First, prove the report was measured against the approved list:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit.py" --verify docs/audit/<slug>
```

Exit 0 means `criteria.md` still hashes to what it recorded and `report.md` cites
that same hash. **Non-zero means the report and the criteria are not the same
list** — report that above everything else and do not summarise the findings as
though they stood; re-run the audit rather than reconciling the two by hand.

Then confirm nothing outside the audit directory moved:

```bash
git status --porcelain
```

Every listed path must be under `docs/audit/`. If anything else changed, say so
plainly — it is a defect in this command, not a detail.

Then report, leading with what the user asked for:

1. **`All clear`**, when every criterion is `met` — one line, and the path to the
   report.
2. Otherwise the **gaps**, in the report's own words, each one already phrased as
   an acceptance criterion.
3. Then the **`unverified`** criteria and why. These are the honest edge of the
   command and they are easy to skim past — a criterion nothing could settle is
   not a criterion that passed.
4. Then the count met, and the path to `report.md`.
5. Finally, the `/quorum:1-plan` invocation that turns the report into a work
   item. That is where the fixing happens; it does not happen here.

Name any cluster that returned nothing, and say its criteria came back
`unverified` for that reason rather than because the code was ambiguous.

## Rules

- **Write nothing outside `docs/audit/<slug>/`.** No source file, no test, no
  config, no `docs/work/` artifact.
- **No branch, no commit, no push, no pull request.** Not even to tidy up.
- **Never run the repository under audit**, and never ask an agent to.
- **Never fix anything you find.** The report proposes; `/quorum:1-plan` plans;
  the pipeline builds. Offer that path rather than taking it.
- **Never report extra implementation as a problem**, in any form.
- **Never mark a criterion `met` you could not evidence**, and never round
  `unverified` up to `met` to make the report read better.
