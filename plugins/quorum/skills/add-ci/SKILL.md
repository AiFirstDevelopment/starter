---
name: add-ci
description: Wires the regression suite into CI as a required status check so a pull request cannot merge while tests fail. Generates the workflow file and explains the branch-protection settings that must be applied in the hosting UI or API.
---

# Add CI

Make the regression suite a merge gate. A suite that does not block merges is
documentation, not a gate.

## Procedure

1. **Detect the host.** Look for `.github/`, `.gitlab-ci.yml`, `azure-pipelines.yml`,
   `.circleci/`, `Jenkinsfile`. Default to GitHub Actions when there is a
   `.github/` directory or a github.com remote. If a CI config already exists,
   **extend it rather than adding a competing one.**

2. **Establish the test recipe** the same way `/quorum:run-regression-tests` does,
   including prerequisites — services, env vars, migrations, build steps. The CI
   job must run the *whole* suite, not a subset.

3. **Write the workflow.** It must:
   - trigger on pull requests to the default branch, and on pushes to it
   - use the runtime version the repo pins (`.nvmrc`, `engines`, `go.mod`, etc.)
   - cache dependencies where the host supports it
   - run install, build, and the full regression suite as distinct steps, so a
     failure is attributable
   - upload test reports or screenshots as artifacts on failure, if the suite
     produces them
   - have a **stable job name** — branch protection references it by name, so
     renaming the job later silently disables the gate

4. **Do not invent secrets.** If tests need credentials, list exactly which
   secrets must be added and where, and leave them referenced but unset. Never
   commit a secret, and never weaken a test so it can run without one.

5. **Explain the branch protection step.** This is a repository setting, not a
   file — the workflow alone does not block anything. Tell the user to require
   the status check on the default branch, and give them the exact command:

   ```bash
   gh api -X PUT repos/:owner/:repo/branches/main/protection \
     -F required_status_checks.strict=true \
     -F 'required_status_checks.contexts[]=regression-tests' \
     -F enforce_admins=false \
     -F required_pull_request_reviews.required_approving_review_count=1 \
     -F restrictions=null
   ```

   Ask before running it — it changes repository settings, which is outside the
   working tree and affects everyone on the repo.

6. **Verify.** Confirm the workflow is valid (`gh workflow list`, or the host's
   linter) and tell the user it is unproven until it has run on a real PR.

## Rules

- The CI command and the local command must be the same recipe. A gate that runs
  something different from what developers run locally trains people to ignore it.
- Never make a job non-blocking (`continue-on-error`, `allow_failure`) to get it
  green. A gate that cannot fail is not a gate.
- No secrets in committed files.
