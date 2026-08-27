export const meta = {
  name: 'quorum-audit',
  description: 'Measures a repository against approved spec criteria, read-only, and writes a report of the gaps',
  phases: [
    { title: 'Cluster', detail: 'group the criteria by the part of the repository that answers them' },
    { title: 'Audit', detail: 'one read-only auditor per cluster, in parallel' },
    { title: 'Refute', detail: 'a different model tries to prove every claimed gap wrong' },
    { title: 'Report', detail: 'transcribe the settled statuses to docs/audit/<slug>/report.md' },
  ],
}

const slug = (args && args.slug) || ''
if (!slug) throw new Error('audit requires args.slug')

// The slug is interpolated straight into the path the scribe is told to write,
// and the scribe is the one agent here that can write. A slug carrying `/` or
// `..` therefore aims that write outside docs/audit/ — over docs/work/, or out
// of the repository altogether, where the skill's own `git status --porcelain`
// check sees a clean tree and reports that nothing else moved. That check is the
// evidence AC1 rests on, so the slug is constrained here rather than trusted to
// the prose rule in reference/audit.md that a model is asked to follow.
if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(slug)) {
  throw new Error(
    'audit requires a kebab-case args.slug — got ' + JSON.stringify(slug) + '. It becomes a ' +
      'path under docs/audit/, so it may hold lowercase letters, digits and single hyphens ' +
      'and nothing else.'
  )
}

const criteria = (args && args.criteria) || []
if (!criteria.length) throw new Error('audit requires args.criteria — the list the user approved')

// As load-bearing as the two above: the hash is what lets a reader prove the
// report was measured against the list a human approved. Without it the scribe
// writes an empty "Criteria hash" field, and `audit.py --verify` then reports
// that the report and the criteria are different lists — after N auditors and a
// refutation pass have run, and for a reason that was knowable before any of it.
const criteriaHash = (args && args.criteriaHash) || ''
if (!criteriaHash) {
  throw new Error(
    'audit requires args.criteriaHash — the value bin/audit.py --hash printed for the ' +
      'criteria.md the user approved. Without it nothing can prove what the report measured.'
  )
}
const specSource = (args && args.specSource) || 'free text supplied to /quorum:audit'
const commit = (args && args.commit) || ''
const title = (args && args.title) || slug
const reportPath = 'docs/audit/' + slug + '/report.md'

// Decorrelation, for the one thing this command gets wrong most easily. Almost
// every finding here is an *absence* — "I searched and it is not there" — and
// the same weights that missed a file the first time miss it the second. So the
// refute pass runs on a different model by default, on the reasoning pipeline.js
// already applies to the judge and its recheck. Override with args.models.
const models = (args && args.models) || {}
const REFUTE_MODEL = models.refute || 'sonnet'

// Agents are addressed by their namespaced names — <plugin>:<agent>, the same
// convention the skills use. selftest.py checks every agentType here against
// plugin.json and agents/*.md, and additionally checks that no agent this script
// names declares a file-editing tool.
//
// That check is load-bearing rather than a floor. No agent this script names is
// granted a file-editing tool, none is granted a shell, and none is granted
// anything outside a fixed allowlist: quorum-auditor holds Read, Grep and Glob and
// nothing else, so it cannot edit a file, commit, push, or run a test suite however
// it is prompted — or however it is instructed by something it reads in the
// repository it is auditing, which is untrusted input. selftest.py asserts all
// three, so they survive someone editing this file or that agent without reading
// this.
//
// Scoped to the agents *this script* names, deliberately. The audit skill runs in
// an ordinary session that holds a shell and reads the spec out of the repository
// under audit; for that session the same rule is prose. reference/audit.md says so
// rather than letting a claim about "the agents" cover it.
//
// NEVER_RUN below is still prose, and prose is what a model can talk itself out
// of. It stays because an agent that cannot see a shell should know why, and
// because the "unverified, never gap" half of it is a judgment no tool grant can
// make. It is no longer what keeps the audited repository safe.

// Repeated into every prompt rather than stated once, because it is the single
// constraint that makes this command safe to run against production code.
const NEVER_RUN =
  'You must NOT execute anything belonging to the repository under audit — not ' +
  'its application, not its build, not its test suite, not a script it ships, not ' +
  'an install step. You hold no shell at all — Read, Grep and Glob are the whole ' +
  'grant, so this is settled rather than asked. The target is production ' +
  'code that may hold live credentials, migrate on boot, or consume from a real ' +
  'queue, and the rule is fixed rather than judged so that no agent has to decide ' +
  'whether launching is safe. A criterion that could only be settled by running ' +
  'the software is "unverified" with that as its reason — never "gap". Absence of ' +
  'runtime evidence is not evidence of absence.'

const NEVER_EXTRA =
  'Behaviour this repository has that the spec never mentions is NOT a finding — ' +
  'not a gap, not an observation, not a suggestion to remove it. More implemented ' +
  'than the spec is explicitly fine. The question is only whether the spec is ' +
  'implemented faithfully. The same goes for ordinary defects unrelated to a ' +
  'criterion: out of scope here.'

const criteriaBlock = criteria
  .map(function (c) {
    return '- ' + c.id + ' — ' + c.text + '\n  Source: ' + (c.source || '(none recorded)')
  })
  .join('\n')

const CLUSTER_SCHEMA = {
  type: 'object',
  required: ['clusters'],
  additionalProperties: false,
  properties: {
    clusters: {
      type: 'array',
      items: {
        type: 'object',
        required: ['name', 'criteria', 'where'],
        additionalProperties: false,
        properties: {
          name: { type: 'string', description: 'short kebab-case name for this cluster' },
          criteria: { type: 'array', items: { type: 'string', description: 'criterion id' } },
          where: {
            type: 'string',
            description: 'the parts of the repository that would answer these criteria',
          },
        },
      },
    },
    notes: { type: 'string' },
  },
}

const AUDIT_SCHEMA = {
  type: 'object',
  required: ['cluster', 'ranNothing', 'results'],
  additionalProperties: false,
  properties: {
    cluster: { type: 'string' },
    // Kept deliberately, now that selftest.py asserts no agent named here is
    // granted a shell. It is a tripwire for the case the grant check cannot see:
    // an agent reaching execution some way the allowlist did not anticipate, or
    // a future edit that widens the grant and a stale suite that does not catch
    // it. It should now never fire, and that is the point of leaving it in.
    //
    // The question is worded to be unambiguous about Read/Grep/Glob, because the
    // failure mode of a vague one is a false alarm printed into a production
    // repository's report: an auditor that searched the repository is not an
    // auditor that ran it, and answering "false" for having grepped would tell an
    // operator their software may have been started when it cannot have been.
    ranNothing: {
      type: 'boolean',
      description:
        'true if you started no process belonging to the repository under audit — no ' +
        'application, build, test suite, script, install step or linter. Reading, ' +
        'searching and listing its files with Read, Grep and Glob is not running it: ' +
        'answer true if that is all you did. Answer false only if a process actually ran.',
    },
    results: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'status', 'evidence'],
        additionalProperties: false,
        properties: {
          id: { type: 'string' },
          status: { type: 'string', enum: ['met', 'gap', 'unverified'] },
          evidence: {
            type: 'string',
            description:
              'met: the file and line, or the test, that implements it. unverified: why it ' +
              'could not be settled from code and tests. gap: what is missing.',
          },
          searched: {
            type: 'string',
            description:
              'REQUIRED for a gap: the search patterns and the paths that came back empty, ' +
              'verbatim, so a reader can re-run them and disagree.',
          },
          proposedChange: {
            type: 'string',
            description:
              'for a gap: the criterion restated as an observable acceptance criterion, in the ' +
              'form "when <situation>, <observable result>"',
          },
        },
      },
    },
  },
}

const REFUTE_SCHEMA = {
  type: 'object',
  required: ['refutations'],
  additionalProperties: false,
  properties: {
    refutations: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'outcome', 'evidence'],
        additionalProperties: false,
        properties: {
          id: { type: 'string' },
          outcome: { type: 'string', enum: ['refuted', 'upheld', 'unsettled'] },
          evidence: {
            type: 'string',
            description:
              'refuted: the file and line that implements it. upheld: what you tried that the ' +
              'first auditor did not. unsettled: why code and tests cannot settle it.',
          },
        },
      },
    },
  },
}

// ---------------------------------------------------------------- cluster

phase('Cluster')
log('Auditing ' + criteria.length + ' criterion(s) derived from ' + specSource + '.')

const grouped = await agent(
  'Group these spec criteria into clusters, so that each cluster can be audited by one agent ' +
    'reading one coherent part of the repository. Do not audit anything yet — this pass only ' +
    'decides who looks where.\n\n' +
    'Criteria:\n' + criteriaBlock + '\n\n' +
    'Aim for two to five clusters. Every criterion must appear in exactly one cluster; a ' +
    'criterion left out is one nothing will audit. Group by the part of the repository that ' +
    'would answer the criterion, not by wording — two criteria about the same module belong ' +
    'together even when the spec words them differently. For each cluster, say in "where" ' +
    'which directories, modules, or config the auditor should start from.\n\n' +
    'You may read and search the repository to decide this. ' + NEVER_RUN,
  { label: 'cluster', phase: 'Cluster', agentType: 'quorum:quorum-auditor', schema: CLUSTER_SCHEMA }
)

const known = {}
criteria.forEach(function (c) { known[c.id] = c })

let clusters = ((grouped && grouped.clusters) || []).filter(function (c) {
  return c && (c.criteria || []).length
})

// Every criterion must be audited by exactly one cluster. Two failures are
// possible and only one of them is visible in the clustering: a criterion in no
// cluster is never looked at, and a criterion in two gets two answers that can
// disagree. Both are settled here rather than left to the merge below.
const assigned = {}
clusters = clusters.map(function (c) {
  const mine = []
  ;(c.criteria || []).forEach(function (id) {
    if (!known[id] || assigned[id]) return
    assigned[id] = c.name
    mine.push(id)
  })
  return Object.assign({}, c, { criteria: mine })
}).filter(function (c) { return c.criteria.length })

const unassigned = criteria.filter(function (c) { return !assigned[c.id] })
if (unassigned.length) {
  log('Clustering left out ' + unassigned.length + ' criterion(s); auditing them as their own cluster.')
  clusters.push({
    name: 'unclustered',
    where: 'the whole repository — these were not assigned to a cluster',
    criteria: unassigned.map(function (c) { return c.id }),
  })
}

if (!clusters.length) throw new Error('Clustering produced nothing to audit.')
log(clusters.length + ' cluster(s): ' + clusters.map(function (c) { return c.name }).join(', '))
if (grouped && grouped.notes) log('Clustering note: ' + grouped.notes)

// ---------------------------------------------------------------- audit

phase('Audit')

let clustersDone = 0

function announce(cluster, result) {
  clustersDone++
  const at = ' (' + clustersDone + '/' + clusters.length + ')'
  if (!result) {
    log('audit:' + cluster.name + ' returned nothing' + at)
    return result
  }
  const rows = result.results || []
  const tally = ['met', 'gap', 'unverified']
    .map(function (status) {
      const n = rows.filter(function (r) { return r.status === status }).length
      return n ? n + ' ' + status : ''
    })
    .filter(Boolean)
    .join(', ')
  log('audit:' + cluster.name + ' — ' + (tally || 'no statuses returned') + at)
  return result
}

const audits = (
  await parallel(
    clusters.map(function (cluster) {
      return function () {
        const mine = cluster.criteria
          .map(function (id) {
            const c = known[id]
            return '- ' + c.id + ' — ' + c.text + '\n  Source: ' + (c.source || '(none recorded)')
          })
          .join('\n')
        return agent(
          'Audit this repository against the criteria below, and return one status for each.\n\n' +
            'Cluster: ' + cluster.name + '\nStart from: ' + (cluster.where || 'the whole repository') +
            '\n\nCriteria:\n' + mine + '\n\n' +
            'These criteria came from a spec (' + specSource + ') and a human approved this exact ' +
            'list. Audit the list as given: do not reword a criterion, do not split it, do not ' +
            'decide one of them does not matter.\n\n' +
            'Each criterion gets exactly one status:\n' +
            '  met — you found the implementation. Cite a file and a line, or a test by name. An ' +
            'intention, a TODO, a config key nothing reads, or a function nothing calls is not an ' +
            'implementation.\n' +
            '  gap — it is not there. You MUST fill in "searched" with the patterns and the paths ' +
            'that came back empty, verbatim. A gap that does not say where you looked is a guess ' +
            'with a status attached, and it will be downgraded to unverified rather than reported. ' +
            'Search for the concept and not the wording — three or four terms, including the ' +
            'synonym and the abbreviation the codebase might use instead — and read the module ' +
            'that would own the behaviour rather than grepping around it. Also fill in ' +
            '"proposedChange": the criterion restated as an observable acceptance criterion.\n' +
            '  unverified — you could not settle it from code and tests alone. Say why in one ' +
            'sentence.\n\n' +
            NEVER_RUN + '\n\n' + NEVER_EXTRA + '\n\n' +
            'Set ranNothing true if you started no process belonging to the repository under ' +
            'audit. Reading, searching and listing its files is not running it — that is your ' +
            'whole job here, and it does not make the answer false. Answer false only if a ' +
            'process actually ran. Ten weak gaps are worse than two real ' +
            'ones: report what you can defend with a citation or a search.',
          {
            label: 'audit:' + cluster.name,
            phase: 'Audit',
            agentType: 'quorum:quorum-auditor',
            schema: AUDIT_SCHEMA,
          }
        ).then(function (result) {
          return announce(cluster, result)
        })
      }
    })
  )
).filter(Boolean)

const ranSomething = audits.filter(function (a) { return a.ranNothing === false })
if (ranSomething.length) {
  log(
    'WARNING — ' + ranSomething.map(function (a) { return a.cluster }).join(', ') +
      ' did not confirm it ran nothing belonging to the repository under audit.'
  )
}

// One status per criterion, and every criterion present. A criterion nothing
// returned is "unverified" with that as the reason — never absent, because a
// criterion missing from a report reads exactly like one that passed.
const settled = {}
audits.forEach(function (a) {
  ;(a.results || []).forEach(function (r) {
    if (!known[r.id] || settled[r.id]) return
    settled[r.id] = Object.assign({ cluster: a.cluster }, r)
  })
})

criteria.forEach(function (c) {
  if (settled[c.id]) return
  settled[c.id] = {
    id: c.id,
    cluster: assigned[c.id] || 'unclustered',
    status: 'unverified',
    evidence:
      'No auditor returned a status for this criterion — the cluster that owned it failed or ' +
      'omitted it. Nothing here examined it, which is not the same as it being satisfied.',
  }
})

// A gap with no searches behind it cannot be checked by a reader, so it does not
// reach the report as a gap. Downgraded rather than dropped: the criterion was
// still not shown to be met, and dropping it would be the one thing worse.
criteria.forEach(function (c) {
  const r = settled[c.id]
  if (r.status !== 'gap' || (r.searched || '').trim()) return
  log('audit: ' + c.id + ' was called a gap with no searches recorded; recording it as unverified.')
  r.status = 'unverified'
  r.evidence =
    'Reported as missing, but the audit recorded no searches to support that. A claim that ' +
    'something is absent cannot be checked without the patterns and paths that came back ' +
    'empty, so it is not reported as a gap. Original note: ' + (r.evidence || '(none)')
})

function withStatus(status) {
  return criteria.filter(function (c) { return settled[c.id].status === status })
}

log(
  withStatus('met').length + ' met, ' + withStatus('gap').length + ' gap, ' +
    withStatus('unverified').length + ' unverified.'
)

// ---------------------------------------------------------------- refute

// The quality risk in this command is negative evidence. In a diff review a
// finding is a positive claim with a file and a line; here most findings are
// absences, and "I looked and did not find it" is far easier to get wrong — one
// synonym the codebase happens to prefer and a perfectly implemented criterion
// is reported missing. So every claimed gap is put to an agent whose job is to
// prove it wrong, on a different model, before it reaches the report.

let refuted = {}
const claimed = withStatus('gap')

if (!claimed.length) {
  log('No gaps claimed; skipping the refutation pass.')
} else {
  phase('Refute')
  log('Putting ' + claimed.length + ' claimed gap(s) to a ' + REFUTE_MODEL + ' refutation pass.')

  const block = claimed
    .map(function (c) {
      const r = settled[c.id]
      return (
        '- ' + c.id + ' — ' + c.text + '\n' +
        '  Source: ' + (c.source || '(none recorded)') + '\n' +
        '  Claimed missing because: ' + (r.evidence || '(nothing said)') + '\n' +
        '  Searches that came back empty: ' + (r.searched || '(none recorded)')
      )
    })
    .join('\n')

  const rebuttal = await agent(
    'Another auditor claims this repository does NOT implement the criteria below. Your job is ' +
      'to prove that wrong.\n\n' + block + '\n\n' +
      'Assume the first auditor searched badly, because that is the failure this pass exists to ' +
      'catch. Read the module that would own the behaviour rather than grepping around it. Try ' +
      'the vocabulary they did not: the framework\'s name for the concept, the library that ' +
      'provides it for free, the config file that switches it on, the base class it might be ' +
      'inherited from, the generated or vendored code they may not have searched.\n\n' +
      'For each criterion return one outcome:\n' +
      '  refuted — you found the implementation. Cite the file and the line. The first auditor ' +
      'was wrong and the criterion is met.\n' +
      '  upheld — you looked, in the places they did not, and it is genuinely not there. Say what ' +
      'you tried; that goes into the report beside their searches.\n' +
      '  unsettled — code and tests cannot settle it. The criterion becomes unverified.\n\n' +
      NEVER_RUN + '\n\n' + NEVER_EXTRA + '\n\n' +
      'An honest "refuted" is the most valuable thing you can return: a wrong gap in the report ' +
      'costs the reader their trust in every other line of it. Do not uphold a gap merely because ' +
      'repeating the first search also failed.',
    {
      label: 'refute',
      phase: 'Refute',
      agentType: 'quorum:quorum-auditor',
      schema: REFUTE_SCHEMA,
      model: REFUTE_MODEL,
    }
  )

  ;((rebuttal && rebuttal.refutations) || []).forEach(function (r) {
    if (settled[r.id] && settled[r.id].status === 'gap') refuted[r.id] = r
  })

  claimed.forEach(function (c) {
    const r = refuted[c.id]
    const row = settled[c.id]
    if (!r) {
      row.refutation = 'not settled — the refutation pass returned nothing for this criterion'
      return
    }
    row.refutation = r.outcome + ' — ' + r.evidence
    if (r.outcome === 'refuted') {
      row.status = 'met'
      row.evidence = r.evidence
      row.refutation =
        'The first auditor reported this missing; a second pass on a different model found it. ' +
        r.evidence
    } else if (r.outcome === 'unsettled') {
      row.status = 'unverified'
      row.evidence = r.evidence
    }
  })

  log(
    'Refutation: ' +
      claimed.filter(function (c) { return settled[c.id].status === 'met' }).length + ' refuted, ' +
      claimed.filter(function (c) { return settled[c.id].status === 'gap' }).length + ' upheld, ' +
      claimed.filter(function (c) { return settled[c.id].status === 'unverified' }).length +
      ' unsettled.'
  )
}

// ---------------------------------------------------------------- report

phase('Report')

// Every gap has to reach the report already phrased as an observable criterion,
// because that is what the closing /quorum:1-plan invocation consumes and
// rewriting it there loses the citation. A schema cannot require one field only
// when another holds a particular value, so — as with `searched` above — it is
// settled here. The fallback is the criterion's own text, which the skill already
// requires to be in the "when <situation>, <observable result>" form: restating
// the criterion is exactly what a proposed change is. The alternative is leaving
// the scribe a blank it is explicitly forbidden to fill in.
criteria.forEach(function (c) {
  const r = settled[c.id]
  if (r.status !== 'gap' || (r.proposedChange || '').trim()) return
  r.proposedChange = c.text
  r.proposedChangeNote = 'restated from the criterion; the audit proposed no wording of its own'
})

const gaps = withStatus('gap')
const unverified = withStatus('unverified')
const met = withStatus('met')
const allClear = !gaps.length && !unverified.length

const rows = criteria.map(function (c) {
  return Object.assign({ text: c.text, source: c.source || '' }, settled[c.id])
})

// Recorded in the report, not just in the run log. An auditor that admits it
// executed the repository under audit has broken the one rule that makes this
// command safe on a default branch, and a run log scrolls away — the artifact is
// what the operator of a production repo still has tomorrow. Silence here would
// leave a report that reads exactly like a clean static audit.
const ranWarning = ranSomething.length
  ? '\n\nBEFORE the Outcome section, write a section headed "## Ran during the audit" ' +
    'containing exactly this line, verbatim: "The audit is supposed to execute nothing ' +
    'belonging to this repository. These clusters did not confirm that they executed nothing: ' +
    ranSomething.map(function (a) { return a.cluster }).join(', ') +
    '. Treat every finding below as coming from a run that may have started this software."\n\n'
  : ''

await agent(
  'Transcribe this finished audit into ' + reportPath + ', following the report format in ' +
    '${CLAUDE_PLUGIN_ROOT}/reference/audit.md — you cannot read that file, so the format is ' +
    'restated below and the findings are given to you in full.\n\n' +
    'You may hold a standing instruction to write review files under docs/work/<slug>/reviews/. ' +
    'It does not apply here. This is an audit, not a review; docs/work/ is not yours to touch on ' +
    'this run, and writing anything there would break the one property that makes this command ' +
    'safe to run on a default branch.\n\n' +
    'Open the file with the line "# Audit report: ' + title + '", then a blank line.\n\n' +
    ranWarning +
    'Header fields, exactly these:\n' +
    '- **Slug:** ' + slug + '\n' +
    '- **Spec:** ' + specSource + '\n' +
    '- **Criteria hash:** ' + criteriaHash + '\n' +
    '- **Audited:** the current date, ISO 8601\n' +
    (commit ? '- **Commit:** ' + commit + '\n' : '') +
    '\nThen, in order:\n\n' +
    '## Outcome — ' + (allClear
      ? 'the single line "All clear", and nothing else. Every criterion is met.'
      : 'one line: ' + gaps.length + ' gap(s) and ' + unverified.length + ' unverified, out of ' +
        criteria.length + ' criteria.') + '\n\n' +
    '## Criteria — a table of every criterion: id, the criterion text, and its status. All ' +
    criteria.length + ' of them, in the order given below, each with exactly one status.\n\n' +
    '## Gaps — one `###` section per gap, headed "<id> — <the proposed change, as an observable ' +
    'criterion>", containing the searches that came back empty verbatim, the refutation result, ' +
    'and the proposed change. Keep this section even when it is empty, so that "All clear" has ' +
    'something to be empty about.\n\n' +
    '## Unverified — one `###` section per unverified criterion, with the stated reason. Omit ' +
    'the section if there are none.\n\n' +
    '## Met — one line each, with the evidence. Omit the section if there are none.\n\n' +
    '## Next — ' + (gaps.length
      ? 'a fenced code block naming the invocation that turns this report into a work item:\n' +
        '```\n/quorum:1-plan Close the gaps in ' + reportPath + ' — ' +
        gaps.map(function (c) { return c.id }).join(', ') + ', quoted there as acceptance ' +
        'criteria.\n```'
      : 'say that there is nothing to plan, and name ' + reportPath + ' as the record.') + '\n\n' +
    'Transcribe verbatim. Do not merge, reword, reorder, drop, add, or soften anything, and do ' +
    'not change a status. You have no tools to read the repository and no license to interpret ' +
    'the findings — your only judgment is formatting.\n\n' +
    'Two things must not appear anywhere in the file: any behaviour this repository has that the ' +
    'spec never mentioned, and any defect unrelated to a criterion. Implementation beyond the ' +
    'spec is explicitly fine and reporting it buries what matters. Nothing below contains any; ' +
    'do not add any.\n\n' +
    'Write only ' + reportPath + '. Write no other file.\n\n' +
    'Findings JSON:\n```json\n' + JSON.stringify(rows, null, 2) + '\n```',
  { label: 'report', phase: 'Report', agentType: 'quorum:quorum-scribe' }
)

log(allClear ? 'All clear — every criterion met.' : gaps.length + ' gap(s) reported.')

return {
  slug: slug,
  title: title,
  spec: specSource,
  criteriaHash: criteriaHash,
  commit: commit,
  reportPath: reportPath,
  outcome: allClear ? 'All clear' : gaps.length + ' gap(s), ' + unverified.length + ' unverified',
  allClear: allClear,
  total: criteria.length,
  met: met.map(function (c) { return c.id }),
  gaps: gaps.map(function (c) { return c.id }),
  unverified: unverified.map(function (c) { return c.id }),
  refutedGaps: Object.keys(refuted).filter(function (id) {
    return refuted[id].outcome === 'refuted'
  }),
  clusters: clusters.map(function (c) { return c.name }),
  clustersReturningNothing: clusters.length - audits.length,
  refuteModel: REFUTE_MODEL,
  ranNothing: !ranSomething.length,
}
