# Review: behavior

- Lens: behavior
- Verdict: findings
- Diff range: a22d7e7...HEAD

## Findings

### F1 — major — plugins/quorum/skills/audit/SKILL.md:170

**Claim:** When the Workflow tool is not present, /quorum:audit does not stop — it audits the repository itself from the skill's own shell-holding session and writes a report.md that asserts refutation passes that never ran.

**What:** Step 5 instructs the skill to call the Workflow tool, and nothing tells it what to do if that tool is absent. Observed: the whole audit.js pipeline (cluster / read-only auditors / refute on a different model / scribe) was silently replaced by the skill reading the repository itself and writing the report.

**Failure scenario:** Fixture repo: `cp -R docs/fixtures/audit-demo/. $FIX/`, `git init`, one commit. From $FIX: `claude -p "/quorum:audit spec.md" --plugin-dir /Users/joelstevick/starter/plugins/quorum --permission-mode bypassPermissions`, then resume with "yes, run the audit". The transcript (scratchpad/run.ndjson) shows the session say "I don't have access to a Workflow tool" and "I need to manually orchestrate the audit", then Read src/server.js, src/upstream.js, src/ratelimit.js, test/server.test.js, test/helper.js itself and Write docs/audit/spec/report.md. `grep -c '"name":"Task"' run.ndjson` = 0 — no quorum-auditor and no scribe ever ran, and no refutation pass on a second model ran. The delivered docs/audit/spec/report.md nevertheless states for AC7 "**Refutation:** upheld — read `src/server.js`, `src/upstream.js`, and `src/ratelimit.js` in full; searched for any retry pattern, middleware, or wrapper; found none." and similar for AC8 and AC9 — provenance for a pass that did not happen. `audit.py --verify docs/audit/spec --expect-report` exits 0 on it, and the skill's closing summary said "Audit complete" with no hint the pipeline was bypassed. This is not a transient: the installed Claude Code CLI 2.1.19 registers no Workflow tool at all (0 occurrences of `"Workflow"` in cli.js, versus TodoWrite/AskUserQuestion/SlashCommand which are present), so every run from that binary degrades this way. The reader of report.md cannot tell a real run from an improvised one.

**Suggested direction:** Make the Workflow call a hard gate in Step 5: if the Workflow tool is not available, stop, say the plugin cannot run the audit in this client, and write no report.md. Explicitly forbid hand-orchestrating the passes, since the report's refute/auditor provenance is otherwise fabricated. (The same hole exists in skills/pipeline/SKILL.md:144, but there the blast radius is a feature branch rather than a production main.)

### F2 — major — plugins/quorum/skills/audit/SKILL.md:96

**Claim:** Step 2's agent-registration check has no prescribed mechanism, and in a real run it launched a `general-purpose` subagent — which holds Bash and Write — that read the audited repository, contradicting the property this commit rewrote three files to assert.

**What:** "Then confirm the agents this needs are registered" names no way to do it, so the model invents one. Observed twice, differently, and both inventions involve a shell inside the audit target.

**Failure scenario:** Run: from a fixture repo with spec.md removed, `claude -p "/quorum:audit <free text spec>" --plugin-dir …/plugins/quorum --permission-mode bypassPermissions` (scratchpad/free.ndjson). At Step 2 the skill issued `Task(subagent_type: "general-purpose", …)`. That subagent — which is granted Bash, Write and Edit — then ran `Glob **/.claude/skills/**/*.md`, `Glob **/skills.json` and `Glob **/.claude/**/*`, all rooted at the audited repository, plus `Bash: ls -la /Users/joelstevick/rag-service/.claude/skills` and `Grep` over `/Users/joelstevick`. In the other run (scratchpad/gate.ndjson) the same step instead ran `Bash: claude -p "list subagent types" | grep -E "quorum:quorum-auditor|quorum:quorum-scribe"`, spawning a nested Claude Code session. So an agent that both reads the audited repository and holds a shell ran during an audit — exactly what plugins/quorum/reference/audit.md:53-57 ("a property of the tool grants rather than of the prompts — the agents that read the audited repository hold `Read`, `Grep` and `Glob` and no shell, and `selftest.py` asserts it") and SKILL.md:29-33 assert cannot happen, and what AC11 states. selftest.py's new EXEC_TOOLS check only inspects agents named in workflow/audit.js, so it cannot see a subagent the skill launches, and it passed 235/235 while this run did it.

**Suggested direction:** Replace the prose instruction with a mechanical check the skill can do from its own tools — Read or Glob `${CLAUDE_PLUGIN_ROOT}/agents/quorum-auditor.md` and `quorum-scribe.md` and compare the `name:` fields — and state in the Rules section that the skill launches no subagent of its own and shells out to nothing but `git status` and `bin/audit.py`.

## Notes

Coverage limits, stated plainly. The orchestration layer (workflow/audit.js) could not be exercised at all: the installed Claude Code CLI 2.1.19 has no Workflow tool, so audit.js never executed in any run. Everything I observed about report.md content therefore came from the improvised path in F1 and is NOT evidence about audit.js, the auditor fan-out, the refute pass, the cluster sweep, or the gap-without-searches downgrade. I did not build a stub Workflow runtime, since that would be a test harness rather than the artifact. AC6/AC7/AC8/AC9 remain unverified against the real workflow; other lenses reading audit.js are the only coverage they have.

For what it is worth, the improvised report did match docs/fixtures/README.md's answer key on substance: AC7/AC8/AC9 gap with named empty searches, AC10 unverified as a runtime property, the rest met, no mention anywhere of the rate limiter or /metrics, and a closing /quorum:1-plan invocation.

Working-tree note, unrelated to this change: at review start `git status --porcelain -uall` in /Users/joelstevick/starter listed only ` M docs/work/quorum-audit/state.json`. At 07:01 during my review, README.md and docs/comparison.md also became modified (a spec-driven-development landscape survey). I have no edit tools and did not make those changes; they are attributable to a separate concurrent session, transcript /Users/joelstevick/.claude/projects/-Users-joelstevick-starter/db7fdde9-bd42-41d1-bf46-b176e47f44bd.jsonl. I left them alone rather than reverting. Whoever commits this branch should be aware those two files are dirty for a different reason.

All my runs were confined to /private/tmp/claude-501/-Users-joelstevick-starter/022188ac-0088-497c-b985-9c4a92d47296/scratchpad/fix1, fix2, fix3 and canary. Nothing under /Users/joelstevick/starter was written by me.
