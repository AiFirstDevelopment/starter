# quorum

Plan → build → multi-lens review → adjudication, ending in a pull request.

Run the steps by hand (`/quorum:1-plan`, `/quorum:2-build`, `/quorum:3-review`,
`/quorum:4-quorum`) or approve a plan and run `/quorum:pipeline` to have the rest
happen unattended. `/quorum:status` reads the artifacts on disk and tells you
which of those you are due to run next.

`/quorum:audit` is the odd one out: point it at a spec and it measures an existing
repository against it, on the default branch, writing a report of the gaps and no
code at all — including a repository that never used any of the above.

`/quorum:calibrate` measures the review panel itself. It runs the six lenses over
fixtures whose defects are planted in advance and reports a catch rate and a
false-positive rate for each one. Nothing else in the pipeline can tell you
whether the panel is worth its cost: the run records count findings and
acceptances, and a defect three lenses report counts three times. This is a
deliberate, human-invoked evaluation — never wire it into a suite that has to be
green, because a varying number inside a required check gets the check loosened
until it passes.

**Pairs with the `tests` plugin.** The judge must run a regression suite before it
can reach a verdict; `/tests:run` is how it prefers to do that. Without the `tests`
plugin the pipeline still works — the judge finds and runs the suite itself — but
enabling both is the intended setup.

See the [marketplace README](../../README.md) for the full explanation.
