export const meta = {
  name: 'quorum-pipeline',
  description: 'Autonomous build, multi-lens review, and adjudication for an approved quorum plan',
  phases: [
    { title: 'Build', detail: 'implement the approved plan' },
    { title: 'Review', detail: 'six independent lenses in parallel, read-only' },
    { title: 'Record', detail: 'transcribe findings to docs/work/<slug>/reviews/' },
    { title: 'Adjudicate', detail: 'judge the panel, apply fixes, end green or blocked' },
    { title: 'Recheck', detail: "one read-only pass over the judge's own commits" },
    { title: 'Publish', detail: 'push the branch and open or update the PR/MR' },
  ],
}

const slug = (args && args.slug) || ''
if (!slug) throw new Error('pipeline requires args.slug')

const planPath = 'docs/work/' + slug + '/plan.md'
const skipBuild = !!(args && args.skipBuild)
const skipPublish = !!(args && args.skipPublish)
const skipRecheck = !!(args && args.skipRecheck)
const MAX_JUDGE_PASSES = 2

// Decorrelation. Six lenses on one model are six views from one vantage point:
// a failure mode the model does not recognise is one that no lens catches, and
// running the same weights six times does not fix that.
//
// Two different problems, handled differently:
//
//   The judge and the recheck are set to DIFFERENT models by default. This is
//   the high-value case — one agent checking another's work — and it costs
//   nothing in capability, so it is on by default.
//
//   The six lenses inherit the session model unless told otherwise. Spreading
//   them across tiers buys diversity and spends per-lens capability, and there
//   is no evidence here on which way that trades. It is offered, not assumed.
//
// Override any of it with args.models, e.g. {correctness: 'opus',
// simplicity: 'sonnet', recheck: 'haiku'}. All options are Claude models, so
// this reduces correlation rather than removing it; a genuinely independent
// panel would span providers, which this harness cannot do.
const models = (args && args.models) || {}
const JUDGE_MODEL = models.judge || 'opus'
const RECHECK_MODEL = models.recheck || 'sonnet'

// Resolved once by /quorum:pipeline, which has a shell; this script does not.
// Handing every lens the same range is what makes "they all reviewed the same
// change" a fact rather than a hope.
const diffRange = (args && args.diffRange) || ''

// Agents are addressed by their namespaced names — <plugin>:<agent>, the same
// convention the skills use (/quorum:1-plan). A bare name does not resolve, and
// the failure lands at the first agent() call: after the approval gate has been
// spent, on a run that was never able to start. This prefix has been stripped
// and re-applied by hand twice; selftest.py now checks every agentType against
// plugin.json and agents/*.md so a third time fails CI instead of a run.

const FINDINGS_SCHEMA = {
  type: 'object',
  required: ['lens', 'verdict', 'diffRange', 'findings'],
  additionalProperties: false,
  properties: {
    lens: { type: 'string' },
    verdict: { type: 'string', enum: ['clean', 'findings'] },
    diffRange: { type: 'string', description: 'the git range actually reviewed' },
    notes: { type: 'string', description: 'optional context, e.g. why the lens was inapplicable' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'claim', 'file', 'line', 'what', 'failureScenario', 'severity'],
        additionalProperties: false,
        properties: {
          id: { type: 'string', description: 'F1, F2, ... unique within this lens' },
          claim: { type: 'string', description: 'one-line statement of the defect' },
          file: { type: 'string' },
          line: { type: 'integer' },
          what: { type: 'string' },
          failureScenario: {
            type: 'string',
            description: 'concrete inputs or state, and the wrong result that follows',
          },
          severity: { type: 'string', enum: ['blocker', 'major', 'minor', 'nit'] },
          suggestedDirection: { type: 'string' },
        },
      },
    },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  required: ['outcome', 'suiteGreen', 'unmetCriteria', 'escalations', 'accepted', 'rejected'],
  additionalProperties: false,
  properties: {
    outcome: { type: 'string', enum: ['ready', 'ready with follow-ups', 'blocked'] },
    suiteGreen: { type: 'boolean' },
    suiteSummary: { type: 'string' },
    unmetCriteria: {
      type: 'array',
      items: { type: 'string', description: 'acceptance criteria NOT met, e.g. "AC3: ..."' },
    },
    escalations: {
      type: 'array',
      items: { type: 'string', description: 'decisions a human must make, one line each' },
    },
    accepted: { type: 'integer', description: 'findings accepted and fixed' },
    rejected: { type: 'integer' },
    followUps: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string', description: 'two or three sentences for the human at QA time' },
  },
}

const PUBLISH_SCHEMA = {
  type: 'object',
  required: ['published', 'draft'],
  additionalProperties: false,
  properties: {
    published: { type: 'boolean' },
    url: { type: 'string' },
    draft: { type: 'boolean' },
    action: { type: 'string', enum: ['created', 'updated', 'none'] },
    host: { type: 'string', description: 'github, gitlab, or unsupported' },
    reason: { type: 'string', description: 'if not published, why, and what the human must do' },
  },
}

const LENSES = [
  {
    key: 'behavior',
    remit:
      'Launch the assembled application and operate it as a user would. This lens does not ' +
      'read the diff: it reports what the software actually does. Walk each acceptance ' +
      'criterion by driving the real artifact — the built app, the running server, the ' +
      'installed CLI, never a test harness — and then go off-script and exercise the ' +
      'controls and paths the change did not touch, to catch what it broke in passing. ' +
      'Report observed behavior: the steps you took, what you expected, what happened. If ' +
      'the project has no runnable surface, return clean with a note saying so rather than ' +
      'falling back to reading code, which other lenses already cover.',
  },
  {
    key: 'correctness',
    remit:
      'Logic errors, unhandled cases, off-by-one, null/undefined, race conditions, ' +
      'incorrect or missing error handling, broken edge cases. Does the code do what it claims?',
  },
  {
    key: 'spec-fidelity',
    remit:
      'Compare the diff against the plan. Is every acceptance criterion actually met? ' +
      'Was anything listed under Non-goals built anyway? Do the deviations recorded in ' +
      'Build notes hold up, and is there any PLAN DEFECT note that must be escalated? ' +
      'Also verify each numbered claim under Approach against the repository — those are ' +
      'assertions the planner believed, not facts, and a false one is a finding.',
  },
  {
    key: 'security',
    remit:
      'Injection, authentication and authorization gaps, secret handling, unsafe ' +
      'deserialization, dependency risk, sensitive data exposed in logs or error responses.',
  },
  {
    key: 'simplicity',
    remit:
      'Duplication, needless abstraction, dead code, and code that could be meaningfully ' +
      'shorter or clearer without changing behavior. Reuse of what already exists in this repo.',
  },
  {
    key: 'test-quality',
    remit:
      'Would each test fail if the behavior it guards broke? Look for assertion-free tests, ' +
      'tests coupled to implementation detail, acceptance criteria with no test at all, and ' +
      'flakiness risk from time, network, randomness, ordering, or shared state.',
  },
]

// ---------------------------------------------------------------- build

if (!skipBuild) {
  phase('Build')
  const built = await agent(
    'Implement the approved plan at ' + planPath + '.\n\n' +
      'Read the plan in full first. Work step by step, ticking each checkbox in the plan as ' +
      'you complete it, and appending every deviation to the Build notes section as it ' +
      'happens. Do not add unrequested features, fix unrelated issues, or refactor adjacent ' +
      'code. Never edit Intent, Acceptance criteria, or Non-goals. Never weaken or delete an ' +
      'existing test to make your change pass.\n\n' +
      'You are running unattended. If the plan turns out to be wrong, do the most defensible ' +
      'thing and record it under a "PLAN DEFECT" heading in Build notes — do not silently ' +
      'redesign around it.\n\n' +
      'When done, set Status in the plan to "built", record the state per the contract ' +
      '(stage "built", steps done, deviations, suite result, and head taken after your ' +
      'commit), and summarize what you built, what deviated, and what you left out.',
    { label: 'build', phase: 'Build', agentType: 'quorum:quorum-builder' }
  )
  log(built ? 'Build complete.' : 'Build agent returned nothing — reviewing the tree as it stands.')
} else {
  log('Skipping build (skipBuild set); reviewing the working tree as it stands.')
}

// ---------------------------------------------------------------- review

phase('Review')
log('Running ' + LENSES.length + ' independent review lenses in fresh context.')

// parallel() is a barrier, so without this the longest phase in the run reports
// nothing between "six started" and "six finished" — one slow lens hiding five
// that already landed. Each lens announces itself as it returns instead. The
// count is completion order, not lens order, which is the useful ordering: it
// says how much is left, and which lens is the one still out.
let lensesDone = 0

function announce(lens, result) {
  lensesDone++
  const at = ' (' + lensesDone + '/' + LENSES.length + ')'
  if (!result) {
    log('review:' + lens.key + ' returned nothing' + at)
    return result
  }
  const found = result.findings || []
  const blocking = found.filter(function (f) { return f.severity === 'blocker' }).length
  const summary = found.length
    ? found.length + ' finding' + (found.length === 1 ? '' : 's') +
      (blocking ? ', ' + blocking + ' blocker' + (blocking === 1 ? '' : 's') : '')
    : 'clean'
  log('review:' + lens.key + ' — ' + summary + at)
  return result
}

const reviews = (
  await parallel(
    LENSES.map(function (lens) {
      return function () {
        return agent(
          'Review the current change through the "' + lens.key + '" lens ONLY.\n\n' +
            'Your remit: ' + lens.remit + '\n\n' +
            'The plan, including its acceptance criteria and non-goals, is at ' + planPath + '.\n\n' +
            (diffRange
              ? 'The change under review is ' + diffRange + ', plus any uncommitted ' +
                'working-tree changes. This range was resolved once for the whole panel — use ' +
                'it as given, do not derive your own, and echo it back in diffRange.\n\n'
              : 'No range was supplied. Determine the diff yourself: the changes between this ' +
                'branch and the base branch it merges into, plus any uncommitted working-tree ' +
                'changes. Report the range you used in diffRange.\n\n') +
            'Read the diff as work you have never seen. Verify every claim against the code — ' +
            'never accept an explanation of why the code is the way it is as evidence that it ' +
            'is right.\n\n' +
            'Every finding needs a file, a line, and a concrete failure scenario: specific ' +
            'inputs or state and the wrong result that follows. If you cannot state that, you ' +
            'have a suspicion rather than a finding — verify it or drop it. Do not report that ' +
            'you would have written the code differently.\n\n' +
            'If your lens finds nothing, return verdict "clean". That is a useful result.',
          Object.assign(
            {
              label: 'review:' + lens.key,
              phase: 'Review',
              agentType: 'quorum:quorum-reviewer',
              schema: FINDINGS_SCHEMA,
            },
            models[lens.key] ? { model: models[lens.key] } : {}
          )
        ).then(function (result) {
          return announce(lens, result)
        })
      }
    })
  )
).filter(Boolean)

const missing = LENSES.filter(function (l) {
  return !reviews.some(function (r) { return r.lens === l.key })
}).map(function (l) { return l.key })

if (missing.length) log('WARNING — lenses that produced no review: ' + missing.join(', '))
if (!reviews.length) throw new Error('All review lenses failed; refusing to adjudicate blind.')

const allFindings = reviews.flatMap(function (r) {
  return (r.findings || []).map(function (f) {
    return Object.assign({ lens: r.lens }, f)
  })
})
const blockers = allFindings.filter(function (f) { return f.severity === 'blocker' }).length
log(
  allFindings.length + ' findings across ' + reviews.length + ' lenses (' + blockers + ' blockers).'
)

// ---------------------------------------------------------------- record

phase('Record')
await agent(
  'Transcribe these review findings verbatim into docs/work/' + slug + '/reviews/, one file ' +
    'per lens, named NNN-<lens>.md with NNN zero-padded to three digits and continuing from ' +
    'the highest number already present in that directory.\n\n' +
    'Preserve every finding exactly as given, including any that look trivial or wrong. Do ' +
    'not merge, reword, reorder, drop, add, or soften anything.\n\n' +
    'Findings JSON:\n```json\n' + JSON.stringify(reviews, null, 2) + '\n```',
  { label: 'record-reviews', phase: 'Record', agentType: 'quorum:quorum-scribe' }
)

// ---------------------------------------------------------------- adjudicate

phase('Adjudicate')

// The scribe is write-only and cannot record state, so the judge records the
// review round on its behalf. Compute the tally here, once, from the workflow's
// own view of what ran — it is the only place that knows which lenses came back.
const lensTally = LENSES.map(function (l) {
  const r = reviews.filter(function (x) { return x.lens === l.key })[0]
  const fs = r ? r.findings || [] : []
  return {
    lens: l.key,
    ran: !!r,
    findings: fs.length,
    blockers: fs.filter(function (f) { return f.severity === 'blocker' }).length,
  }
})

const reviewRecord = {
  lenses: reviews.map(function (r) { return r.lens }),
  missing: missing,
  findings: allFindings.length,
  blockers: blockers,
}

let verdict = null
let pass = 0

while (pass < MAX_JUDGE_PASSES) {
  pass++
  const retry =
    pass === 1
      ? ''
      : '\n\nThis is judging pass ' + pass + '. A previous pass left the regression suite RED: ' +
        (verdict && verdict.suiteSummary ? verdict.suiteSummary : 'see the last run') +
        '. Fix the cause. If you still cannot get it green on this pass, set suiteGreen false ' +
        'and outcome "blocked" and report exactly what fails — do not disable, skip, or ' +
        'weaken any test to turn it green. A reported red suite is an acceptable outcome; a ' +
        'suite made green by removing coverage is not.'

  verdict = await agent(
    'Adjudicate this change as the quorum judge.\n\n' +
      'Read the plan at ' + planPath + ', the diff, and every review under docs/work/' + slug +
      '/reviews/. You are the last step before a human sees this work — nobody will catch what ' +
      'you miss, and no one approves your edits before they land.\n\n' +
      'Verify each finding against the code yourself; reviewers are sometimes confidently ' +
      'wrong. Accept the real ones and fix them, reject the rest with reasons, and record as ' +
      'escalations anything a human must decide. Independently walk every acceptance ' +
      'criterion — one that no lens examined can still be unmet.\n\n' +
      'You may not weaken, skip, or delete a test to resolve a finding; you may not edit ' +
      'Intent, Acceptance criteria, or Non-goals; you may not mark a criterion met when it is ' +
      'not; you may not expand scope.\n\n' +
      'Finish by running the full regression suite. Then write docs/work/' + slug +
      '/verdict.md and set Status in the plan to "adjudicated". Lead the verdict with whatever ' +
      'is unmet, escalated, or failing — the human is scanning for what needs them.\n\n' +
      'Then record the state per the contract, taking head AFTER your commit lands. Record ' +
      'the review round on the scribe\'s behalf as well as your own verdict — the scribe is ' +
      'write-only and cannot record anything. Set review.round to one more than the highest ' +
      'round already in state.json, or 1 if there is none, and set review.head to the commit ' +
      'the lenses read, which is HEAD as it stood before your own fixes:\n```json\n' +
      JSON.stringify(reviewRecord, null, 2) + '\n```\n\n' +
      'Any escalation or unmet criterion means the outcome is "ready with follow-ups" or ' +
      '"blocked", never "ready".' +
      retry,
    {
      label: 'judge:pass-' + pass,
      phase: 'Adjudicate',
      agentType: 'quorum:quorum-judge',
      schema: VERDICT_SCHEMA,
      model: JUDGE_MODEL,
    }
  )

  if (!verdict) { log('Judge pass ' + pass + ' returned nothing.'); continue }
  if (verdict.suiteGreen) break
  log('Judge pass ' + pass + ' ended with a RED suite.')
}

if (!verdict) throw new Error('Adjudication produced no verdict after ' + MAX_JUDGE_PASSES + ' passes.')

if (!verdict.suiteGreen) {
  log('Regression suite still red after ' + pass + ' judging passes. Reported, not worked around.')
}

// ---------------------------------------------------------------- recheck

// Nothing reviews the judge. It applies fixes and commits them after all six
// lenses have already read the tree, so its own diff ships with zero coverage —
// and a judge vouching for its own edits is the exact self-assessment this
// pipeline exists to distrust.
//
// One read-only pass closes that hole without opening a regress: these findings
// are recorded and can force the PR to a draft, but nothing fixes them here. A
// fix would need its own review, and so on without end. Real findings against the
// judge's diff are for the human at PR time.

let recheck = null

if (skipRecheck) {
  log('Skipping recheck (skipRecheck set).')
} else {
  phase('Recheck')

  recheck = await agent(
    'Review ONLY the commits the judge made while adjudicating this change. Everything ' +
      'else on this branch has already been reviewed by six lenses; the judge\'s own edits ' +
      'have been reviewed by nobody.\n\n' +
      'Read docs/work/' + slug + '/state.json. The range you are reviewing is ' +
      'review.head..verdict.head — the commits that landed after the lenses read the tree. ' +
      'If those fields are missing, fall back to the commits touching this branch since the ' +
      'newest file in docs/work/' + slug + '/reviews/, and say so in notes. If the range is ' +
      'empty the judge accepted nothing; return verdict "clean".\n\n' +
      'The judge was fixing findings under time pressure, at the end of a long run, with no ' +
      'reviewer waiting. Look for what that produces: a fix that suppresses a symptom rather ' +
      'than its cause, a guard added in one call path and not its twin, a test adjusted to ' +
      'accommodate the fix, collateral damage to code the fix passed through.\n\n' +
      'The plan is at ' + planPath + '. Judge the code, not the verdict\'s account of it. ' +
      'Use lens "judge-diff". Report only what you can defend with a file, a line, and a ' +
      'concrete failure scenario — a blocker here turns the pull request into a draft.\n\n' +
      'You are deliberately running on a different model from the judge whose work you are ' +
      'checking. Look where a reviewer sharing its assumptions would not.',
    {
      label: 'recheck:judge-diff',
      phase: 'Recheck',
      agentType: 'quorum:quorum-reviewer',
      schema: FINDINGS_SCHEMA,
      model: RECHECK_MODEL,
    }
  )

  if (recheck && (recheck.findings || []).length) {
    await agent(
      'Transcribe these findings verbatim into docs/work/' + slug + '/reviews/, as a single ' +
        'file NNN-judge-diff.md continuing the existing numbering. Preserve every finding ' +
        'exactly as given. Note in the file that this review covers the judge\'s own ' +
        'adjudication commits, which no other lens saw.\n\n' +
        'Findings JSON:\n```json\n' + JSON.stringify([recheck], null, 2) + '\n```',
      { label: 'record-recheck', phase: 'Recheck', agentType: 'quorum:quorum-scribe' }
    )
  }
}

const recheckFindings = recheck ? recheck.findings || [] : []
const recheckBlockers = recheckFindings.filter(function (f) {
  return f.severity === 'blocker'
}).length

if (recheckBlockers) {
  log('RECHECK — ' + recheckBlockers + " blocker(s) in the judge's own diff; publishing as draft.")
} else if (recheckFindings.length) {
  log('Recheck: ' + recheckFindings.length + " finding(s) in the judge's diff, none blocking.")
} else if (recheck) {
  log("Recheck: the judge's own diff is clean.")
}

// ---------------------------------------------------------------- publish

let published = null

if (skipPublish) {
  log('Skipping publish (skipPublish set).')
} else {
  phase('Publish')

  published = await agent(
    'Publish this branch for human review.\n\n' +
      'The work is finished and adjudicated. Do not change any code — present what is there.\n\n' +
      'Commit anything still outstanding (the docs/work/' + slug + '/ artifacts belong in the ' +
      'branch), push the branch, then open a pull request or merge request — or update the ' +
      'existing one if this branch already has one open, which happens whenever the pipeline ' +
      'is re-run on a branch. Never open a second one.\n\n' +
      'The verdict is at docs/work/' + slug + '/verdict.md and the plan at ' + planPath +
      '. Read both; the plan supplies the intent and the acceptance criteria wording.\n\n' +
      'Verdict summary:\n```json\n' +
      JSON.stringify(
        {
          outcome: verdict.outcome,
          suiteGreen: verdict.suiteGreen,
          suiteSummary: verdict.suiteSummary,
          unmetCriteria: verdict.unmetCriteria,
          escalations: verdict.escalations,
          accepted: verdict.accepted,
          rejected: verdict.rejected,
          followUps: verdict.followUps,
          summary: verdict.summary,
          lenses: lensTally,
          lensesMissing: missing,
          judgeDiffReview: recheck
            ? { findings: recheckFindings.length, blockers: recheckBlockers }
            : 'not run',
        },
        null,
        2
      ) +
      '\n```\n\n' +
      (verdict.suiteGreen && verdict.outcome !== 'blocked' && !recheckBlockers
        ? 'Open it ready for review.'
        : recheckBlockers && verdict.suiteGreen && verdict.outcome !== 'blocked'
          ? 'Open it as a DRAFT. The verdict itself is clean, but a review of the judge\'s ' +
            'own adjudication commits found ' + recheckBlockers + ' blocker(s) — code that ' +
            'nothing else reviewed. Lead the body with those, name the review file under ' +
            'docs/work/' + slug + '/reviews/, and say plainly that they are unfixed because ' +
            'the pipeline does not let the judge grade its own repairs.'
          : 'Open it as a DRAFT: the verdict is not clean. Lead the body with what is failing ' +
            'or unresolved, and prefix the title with "[blocked]" if the outcome is blocked.') +
      '\n\nBefore publishing, run the quorum guard — the plugin\'s bin/guard.py, NOT a ' +
      'vendored .quorum/guard.py. The vendored copy cannot check itself for drift, and ' +
      'whether it has drifted is one of the rules. It settles what a machine can settle: ' +
      'requirements unchanged, no test deleted or skipped, reviews append-only, verdict not ' +
      'self-contradictory, cited evidence real, work on the branch the plan named, and the ' +
      'vendored enforcement layer present and matching. If it exits non-zero, open the PR as ' +
      'a DRAFT and lead the body with the violations verbatim — they are rules, not findings, ' +
      'and nothing at this stage may adjudicate them away. If it cannot run, say so rather ' +
      'than implying it passed.' +

      '\n\nThen run it again with --check-gate and put the answer in the PR body as one ' +
      'line. That reports whether "quorum guard" is actually a required status check — a ' +
      'branch-protection setting no agent can change, and one an unticked box makes look ' +
      'identical to a working gate. Report LIVE, NOT LIVE, or that it could not tell, and ' +
      'never round "could not tell" up to a pass. Do not draft the PR over this: branch ' +
      'protection is the repository owner\'s decision, not a defect in this change.' +
      '\n\nWhen the PR is open, record the state per the contract: stage "published", a pr ' +
      'object with the URL and draft flag, a recheck object with the judge-diff findings ' +
      'and blockers from the summary above, and a guard object with clean, the violation ' +
      'count, and gate set to "live", "not-live", or "unknown". If you could not publish, ' +
      'record no pr and say ' +
      'why in the log line.' +
      '\n\nNever merge, approve, or enable auto-merge. Never force-push. If the host is ' +
      'unsupported or its CLI is unavailable, do not fail — print the title, body, and command ' +
      'you would have used and report that a human must publish.',
    { label: 'publish', phase: 'Publish', agentType: 'quorum:quorum-publisher', schema: PUBLISH_SCHEMA }
  )

  if (published && published.published) {
    log((published.draft ? 'Draft ' : '') + 'PR ' + (published.action || 'opened') + ': ' + published.url)
  } else {
    log('NOT PUBLISHED — ' + ((published && published.reason) || 'publish stage returned nothing') )
  }
}

return {
  slug: slug,
  outcome: verdict.outcome,
  suiteGreen: verdict.suiteGreen,
  suiteSummary: verdict.suiteSummary,
  lensesRun: reviews.map(function (r) { return r.lens }),
  lensesMissing: missing,
  findings: allFindings.length,
  blockers: blockers,
  accepted: verdict.accepted,
  rejected: verdict.rejected,
  unmetCriteria: verdict.unmetCriteria,
  escalations: verdict.escalations,
  followUps: verdict.followUps,
  summary: verdict.summary,
  judgePasses: pass,
  diffRange: diffRange || 'derived per lens',
  judgeDiffFindings: recheckFindings.length,
  judgeDiffBlockers: recheckBlockers,
  judgeDiffReviewed: !!recheck,
  judgeModel: JUDGE_MODEL,
  recheckModel: RECHECK_MODEL,
  verdictPath: 'docs/work/' + slug + '/verdict.md',
  published: published ? !!published.published : false,
  prUrl: published ? published.url : undefined,
  prDraft: published ? published.draft : undefined,
  prAction: published ? published.action : undefined,
  publishBlockedReason: published && !published.published ? published.reason : undefined,
}
