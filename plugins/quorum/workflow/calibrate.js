export const meta = {
  name: 'quorum-calibrate',
  description: 'Run the review lenses over fixtures with known planted defects and collect raw findings',
  phases: [{ title: 'Review', detail: 'every lens over every fixture case, read-only' }],
}

// Measure the panel by giving it work whose answer is already known.
//
// The pipeline's own counters cannot do this. A defect three lenses report
// counts three times; a finding whose diagnosis is accepted and whose remedy is
// refused counts as an acceptance. Eight runs of that arithmetic said 138 of
// 144 findings were accepted, which is not evidence about anything.
//
// This script only collects. It plants nothing, matches nothing and scores
// nothing — bin/calibrate.py does that against the manifests, which the lenses
// never see. Keeping the two apart is what stops the harness from grading on a
// curve it drew itself.

const cases = (args && args.cases) || []
if (!cases.length) throw new Error('calibrate requires args.cases')

const models = (args && args.models) || {}

// Copied from pipeline.js verbatim, and held there by selftest.py: a lens
// prompted differently is a different lens, and a calibration of a panel
// nobody runs is worth nothing. If these drift, the score stops describing
// production and the test fails rather than letting it happen quietly.
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

const FINDINGS_SCHEMA = {
  type: 'object',
  required: ['lens', 'verdict', 'findings'],
  additionalProperties: false,
  properties: {
    lens: { type: 'string' },
    verdict: { type: 'string', enum: ['clean', 'findings'] },
    notes: { type: 'string' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'claim', 'file', 'line', 'what', 'failureScenario', 'severity'],
        additionalProperties: false,
        properties: {
          id: { type: 'string' },
          claim: { type: 'string' },
          file: { type: 'string' },
          line: { type: 'integer' },
          what: { type: 'string' },
          failureScenario: { type: 'string' },
          severity: { type: 'string', enum: ['blocker', 'major', 'minor', 'nit'] },
          suggestedDirection: { type: 'string' },
        },
      },
    },
  },
}

phase('Review')

const jobs = []
for (const c of cases) {
  const unrunnable = c.unrunnable || []
  for (const lens of LENSES) {
    if (unrunnable.indexOf(lens.key) !== -1) {
      // Declared in the manifest, not discovered here. A lens that cannot run
      // is excluded from the rates rather than scored as having missed
      // everything — scoring it would report a blind spot the panel has not got.
      jobs.push({
        skip: true,
        row: {
          case: c.case,
          lens: lens.key,
          status: 'unrun',
          reason: c.unrunnableReason || 'declared unrunnable by the case manifest',
        },
      })
      continue
    }
    jobs.push({ skip: false, c: c, lens: lens })
  }
}

log(
  'Running ' +
    jobs.filter(function (j) { return !j.skip }).length +
    ' lens/case pairs across ' + cases.length + ' case(s); ' +
    jobs.filter(function (j) { return j.skip }).length + ' declared unrunnable.'
)

const results = await parallel(
  jobs.map(function (job) {
    return function () {
      if (job.skip) return Promise.resolve(job.row)

      const c = job.c
      const lens = job.lens

      // The prompt below is pipeline.js's, with the diff-range paragraph
      // replaced by the fixture's root. Everything a lens is told about how to
      // judge is identical, because that is the thing being measured.
      return agent(
        'Review the code under ' + c.root + ' through the "' + lens.key + '" lens ONLY.\n\n' +
          'Your remit: ' + lens.remit + '\n\n' +
          'The plan, including its acceptance criteria and non-goals, is at ' + c.plan + '.\n\n' +
          'This is a self-contained snapshot rather than a branch: there is no diff and no ' +
          'base to compare against. Review everything under ' + c.root + ' as the change. ' +
          'Do not run git, and do not look outside that directory — the surrounding ' +
          'repository is not part of what you are reviewing.\n\n' +
          'Read the code as work you have never seen. Verify every claim against the code — ' +
          'never accept an explanation of why the code is the way it is as evidence that it ' +
          'is right.\n\n' +
          'Every finding needs a file, a line, and a concrete failure scenario: specific ' +
          'inputs or state and the wrong result that follows. If you cannot state that, you ' +
          'have a suspicion rather than a finding — verify it or drop it. Do not report that ' +
          'you would have written the code differently.\n\n' +
          'Report file paths relative to ' + c.root + '.\n\n' +
          'If your lens finds nothing, return verdict "clean". That is a useful result.',
        Object.assign(
          {
            label: 'calibrate:' + c.case + ':' + lens.key,
            phase: 'Review',
            agentType: 'quorum:quorum-reviewer',
            schema: FINDINGS_SCHEMA,
          },
          models[lens.key] ? { model: models[lens.key] } : {}
        )
      ).then(function (result) {
        const findings = (result && result.findings) || []
        log(
          c.case + '/' + lens.key + ': ' +
            (findings.length ? findings.length + ' finding(s)' : 'clean')
        )
        // Normalized to what bin/calibrate.py matches on. `claim` and `what`
        // become the text the manifest's match strings are sought in.
        return {
          case: c.case,
          lens: lens.key,
          verdict: (result && result.verdict) || 'clean',
          notes: (result && result.notes) || '',
          findings: findings.map(function (f) {
            return {
              id: f.id,
              file: f.file,
              line: f.line,
              severity: f.severity,
              title: f.claim,
              summary: f.what,
              failure_scenario: f.failureScenario,
            }
          }),
        }
      })
    }
  })
)

return { results: results.filter(Boolean) }
