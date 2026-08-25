export const meta = {
  name: 'quorum-pipeline',
  description: 'Autonomous build, multi-lens review, and adjudication for an approved quorum plan',
  phases: [
    { title: 'Build', detail: 'implement the approved plan' },
    { title: 'Review', detail: 'five independent lenses in parallel, read-only' },
    { title: 'Record', detail: 'transcribe findings to docs/work/<slug>/reviews/' },
    { title: 'Adjudicate', detail: 'judge the panel, apply fixes, end green or blocked' },
    { title: 'Publish', detail: 'push the branch and open or update the PR/MR' },
  ],
}

const slug = (args && args.slug) || ''
if (!slug) throw new Error('pipeline requires args.slug')

const planPath = 'docs/work/' + slug + '/plan.md'
const skipBuild = !!(args && args.skipBuild)
const skipPublish = !!(args && args.skipPublish)
const MAX_JUDGE_PASSES = 2

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
      'Build notes hold up, and is there any PLAN DEFECT note that must be escalated?',
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
      'When done, set Status in the plan to "built" and summarize what you built, what ' +
      'deviated, and what you left out.',
    { label: 'build', phase: 'Build', agentType: 'quorum-builder' }
  )
  log(built ? 'Build complete.' : 'Build agent returned nothing — reviewing the tree as it stands.')
} else {
  log('Skipping build (skipBuild set); reviewing the working tree as it stands.')
}

// ---------------------------------------------------------------- review

phase('Review')
log('Running ' + LENSES.length + ' independent review lenses in fresh context.')

const reviews = (
  await parallel(
    LENSES.map(function (lens) {
      return function () {
        return agent(
          'Review the current change through the "' + lens.key + '" lens ONLY.\n\n' +
            'Your remit: ' + lens.remit + '\n\n' +
            'The plan, including its acceptance criteria and non-goals, is at ' + planPath + '. ' +
            'Read it, then determine the diff: the changes between this branch and the base ' +
            'branch it merges into, plus any uncommitted working-tree changes. Report the range ' +
            'you used in diffRange.\n\n' +
            'Read the diff as work you have never seen. Verify every claim against the code — ' +
            'never accept an explanation of why the code is the way it is as evidence that it ' +
            'is right.\n\n' +
            'Every finding needs a file, a line, and a concrete failure scenario: specific ' +
            'inputs or state and the wrong result that follows. If you cannot state that, you ' +
            'have a suspicion rather than a finding — verify it or drop it. Do not report that ' +
            'you would have written the code differently.\n\n' +
            'If your lens finds nothing, return verdict "clean". That is a useful result.',
          {
            label: 'review:' + lens.key,
            phase: 'Review',
            agentType: 'quorum-reviewer',
            schema: FINDINGS_SCHEMA,
          }
        )
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
  { label: 'record-reviews', phase: 'Record', agentType: 'quorum-scribe' }
)

// ---------------------------------------------------------------- adjudicate

phase('Adjudicate')

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
      'Any escalation or unmet criterion means the outcome is "ready with follow-ups" or ' +
      '"blocked", never "ready".' +
      retry,
    { label: 'judge:pass-' + pass, phase: 'Adjudicate', agentType: 'quorum-judge', schema: VERDICT_SCHEMA }
  )

  if (!verdict) { log('Judge pass ' + pass + ' returned nothing.'); continue }
  if (verdict.suiteGreen) break
  log('Judge pass ' + pass + ' ended with a RED suite.')
}

if (!verdict) throw new Error('Adjudication produced no verdict after ' + MAX_JUDGE_PASSES + ' passes.')

if (!verdict.suiteGreen) {
  log('Regression suite still red after ' + pass + ' judging passes. Reported, not worked around.')
}

// ---------------------------------------------------------------- publish

let published = null

if (skipPublish) {
  log('Skipping publish (skipPublish set).')
} else {
  phase('Publish')

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
        },
        null,
        2
      ) +
      '\n```\n\n' +
      (verdict.suiteGreen && verdict.outcome !== 'blocked'
        ? 'Open it ready for review.'
        : 'Open it as a DRAFT: the verdict is not clean. Lead the body with what is failing ' +
          'or unresolved, and prefix the title with "[blocked]" if the outcome is blocked.') +
      '\n\nNever merge, approve, or enable auto-merge. Never force-push. If the host is ' +
      'unsupported or its CLI is unavailable, do not fail — print the title, body, and command ' +
      'you would have used and report that a human must publish.',
    { label: 'publish', phase: 'Publish', agentType: 'quorum-publisher', schema: PUBLISH_SCHEMA }
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
  verdictPath: 'docs/work/' + slug + '/verdict.md',
  published: published ? !!published.published : false,
  prUrl: published ? published.url : undefined,
  prDraft: published ? published.draft : undefined,
  prAction: published ? published.action : undefined,
  publishBlockedReason: published && !published.published ? published.reason : undefined,
}
