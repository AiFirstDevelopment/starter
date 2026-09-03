# quorum

Plan → build → multi-lens review → adjudication, ending in a pull request.

Run the steps by hand (`/quorum:1-plan`, `/quorum:2-build`, `/quorum:3-review`,
`/quorum:4-quorum`) or approve a plan and run `/quorum:pipeline` to have the rest
happen unattended. `/quorum:status` reads the artifacts on disk and tells you
which of those you are due to run next.

`/quorum:audit` is the odd one out: point it at a spec and it measures an existing
repository against it, on the default branch, writing a report of the gaps and no
code at all — including a repository that never used any of the above.

**Pairs with the `tests` plugin.** The judge must run a regression suite before it
can reach a verdict; `/tests:run` is how it prefers to do that. Without the `tests`
plugin the pipeline still works — the judge finds and runs the suite itself — but
enabling both is the intended setup.

See the [marketplace README](../../README.md) for the full explanation.
