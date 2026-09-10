#!/usr/bin/env python3
"""Score a review panel against fixtures whose defects are known in advance.

The pipeline counts findings, acceptances and rejections. None of those measure
whether the panel is any good, and they cannot be made to: a defect three lenses
report counts three times, and a finding whose diagnosis is accepted while its
remedy is refused counts as an acceptance. Across eight recorded runs that
arithmetic said 138 of 144 findings were accepted, which reads as a panel with
no false positives and is not evidence of anything.

The only way to get a real number is to know the answer first. Fixtures carry
planted defects declared in a manifest; the lenses read them without it; this
scores what came back.

  catch rate      of the defects planted for a lens, how many that lens found
  false positives on a fixture with nothing planted, findings at minor or above
  cross-catch     a lens finding another lens's defect — reported, never scored
  unmatched       a finding matching no planted defect — printed, never judged

That last one is the important restraint. On a fixture carrying planted defects,
an unmatched finding may be a false positive or may be a real defect nobody
planted; the fixture cannot tell you which, and a scorer that guessed would
manufacture exactly the kind of number this exists to replace. It prints them
for a human. Only clean controls, where nothing was planted and there is nothing
to have missed, produce a false-positive count.

Matching is mechanical: same file, line inside the declared range, and every
string in `match` present in the finding's text. A defect that needs judgment to
recognise is a defect declared too vaguely — tighten the manifest rather than
loosening this.

Usage:
  calibrate.py --cases <dir> --findings <file.json> [--out <dir>] [--json]
  calibrate.py --cases <dir> --validate     # manifests well-formed, no run

Exit: 0 scored, 1 a manifest or findings file could not be used, 2 could not run.
"""

import argparse
import json
import os
import sys

# Below this, a finding is a preference and counting it as a false positive
# would punish a lens for saying so. `nit` is explicitly invited by the reviewer
# prompt; scoring it here would contradict that.
FALSE_POSITIVE_FLOOR = ('minor', 'major', 'blocker')

SEVERITIES = ('nit', 'minor', 'major', 'blocker')


def die(msg, code=2):
    sys.stderr.write('calibrate.py: %s\n' % msg)
    sys.exit(code)


def load_json(path, what):
    try:
        with open(path) as handle:
            return json.load(handle)
    except (IOError, OSError) as exc:
        die('cannot read %s (%s): %s' % (what, path, exc), 1)
    except ValueError as exc:
        die('%s is not valid JSON (%s): %s' % (what, path, exc), 1)


def load_cases(root):
    """Read every manifest under <root>/*/manifest.json, oldest name first."""
    if not os.path.isdir(root):
        die('no such case directory: %s' % root, 1)

    cases = []
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name, 'manifest.json')
        if not os.path.exists(path):
            continue
        manifest = load_json(path, 'manifest')
        problems = validate(name, manifest)
        if problems:
            die('%s/manifest.json: %s' % (name, '; '.join(problems)), 1)
        manifest.setdefault('case', name)
        cases.append(manifest)

    if not cases:
        die('no manifests found under %s' % root, 1)
    return cases


def validate(name, manifest):
    """What a manifest must say for a score computed from it to mean anything."""
    problems = []
    if not isinstance(manifest, dict):
        return ['top level is not an object']

    planted = manifest.get('planted')
    if planted is None:
        problems.append('no "planted" key (a clean control declares [])')
        planted = []
    if not isinstance(planted, list):
        return ['"planted" is not a list']

    if not manifest.get('control') and not planted:
        problems.append(
            'no planted defects and control is not set — an unlabelled empty '
            'case scores as neither, so say which it is'
        )
    if manifest.get('control') and planted:
        problems.append('control cases must plant nothing')

    seen = set()
    for i, defect in enumerate(planted):
        where = 'planted[%d]' % i
        if not isinstance(defect, dict):
            problems.append('%s is not an object' % where)
            continue
        for key in ('id', 'lens', 'file', 'lines', 'match'):
            if key not in defect:
                problems.append('%s has no %s' % (where, key))
        if defect.get('id') in seen:
            problems.append('%s duplicates id %r' % (where, defect.get('id')))
        seen.add(defect.get('id'))

        lines = defect.get('lines')
        if not (isinstance(lines, list) and len(lines) == 2
                and all(isinstance(n, int) for n in lines) and lines[0] <= lines[1]):
            problems.append('%s lines must be [first, last] integers' % where)

        match = defect.get('match')
        if not (isinstance(match, list) and match
                and all(isinstance(s, str) and s for s in match)):
            problems.append(
                '%s match must be a non-empty list of strings a finding must '
                'contain to count as this defect' % where
            )
    return problems


def finding_text(finding):
    """Everything a finding says, lowercased, for substring matching."""
    parts = []
    for key in ('title', 'summary', 'detail', 'description', 'scenario',
                'failure_scenario', 'evidence', 'symbol'):
        value = finding.get(key)
        if isinstance(value, str):
            parts.append(value)
    return ' '.join(parts).lower()


def finding_line(finding):
    for key in ('line', 'lineNumber', 'start_line'):
        value = finding.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def same_file(planted_path, found_path):
    """Compare by normalized tail, so a lens quoting a fuller path still matches."""
    if not isinstance(found_path, str):
        return False
    a = planted_path.replace('\\', '/').lstrip('./')
    b = found_path.replace('\\', '/').lstrip('./')
    return a == b or a.endswith('/' + b) or b.endswith('/' + a)


def matches(defect, finding):
    """Does this finding identify this planted defect?

    Three tests, all mechanical. The line test allows a finding to be absent a
    line number — some lenses report a symbol instead — but never allows a wrong
    one, because a lens pointing at the wrong place has not found the defect.
    """
    if not same_file(defect['file'], finding.get('file')):
        return False

    line = finding_line(finding)
    if line is not None:
        first, last = defect['lines']
        if not first <= line <= last:
            return False

    text = finding_text(finding)
    return all(needle.lower() in text for needle in defect['match'])


def severity_at_or_above(finding, floor):
    sev = str(finding.get('severity', '')).strip().lower()
    return sev in floor


def score(cases, results):
    """Match every finding against every planted defect. Nothing is inferred."""
    by_case = {}
    for entry in results:
        by_case.setdefault(entry.get('case'), []).append(entry)

    lenses = set()
    for case in cases:
        for defect in case['planted']:
            lenses.add(defect['lens'])
    for entries in by_case.values():
        for entry in entries:
            if entry.get('lens'):
                lenses.add(entry['lens'])

    tally = dict((lens, {
        'planted': 0, 'caught': 0, 'missed': [], 'cross': [],
        'false_positives': [], 'unmatched': [], 'findings': 0, 'unrun': [],
    }) for lens in sorted(lenses))

    per_case = []

    for case in cases:
        name = case['case']
        entries = by_case.get(name, [])
        control = bool(case.get('control'))

        ran = {}
        unrun = set()
        for entry in entries:
            lens = entry.get('lens')
            if entry.get('status') == 'unrun':
                # A lens that could not run is not a lens that found nothing.
                # It leaves every rate alone and is named in the report instead.
                unrun.add(lens)
                if lens in tally:
                    tally[lens]['unrun'].append(
                        {'case': name, 'reason': entry.get('reason', 'not stated')})
                continue
            ran.setdefault(lens, []).extend(entry.get('findings') or [])

        for lens, found in ran.items():
            if lens in tally:
                tally[lens]['findings'] += len(found)

        case_row = {'case': name, 'control': control,
                    'planted': len(case['planted']), 'caught': 0}

        # Which findings explain a planted defect, and which defect each one is.
        claimed = {}
        for defect in case['planted']:
            lens = defect['lens']
            # Its lens never looked. Counting this as a miss would report a
            # blind spot the panel does not have, so the defect leaves the
            # denominator with the lens that could not read it.
            if lens in unrun:
                continue
            tally[lens]['planted'] += 1
            hit_own = None
            hit_cross = []
            for other_lens, found in ran.items():
                for finding in found:
                    if not matches(defect, finding):
                        continue
                    claimed.setdefault(id(finding), []).append(defect['id'])
                    if other_lens == lens and hit_own is None:
                        hit_own = finding
                    elif other_lens != lens:
                        hit_cross.append(other_lens)

            if hit_own is not None:
                tally[lens]['caught'] += 1
                case_row['caught'] += 1
            else:
                tally[lens]['missed'].append({'case': name, 'id': defect['id'],
                                              'file': defect['file']})
            for other in sorted(set(hit_cross)):
                tally[other]['cross'].append(
                    {'case': name, 'id': defect['id'], 'owner': lens})

        # What is left over. On a control this is a false positive; anywhere
        # else it is a finding the fixture cannot adjudicate, so it is printed.
        for lens, found in ran.items():
            if lens not in tally:
                continue
            for finding in found:
                if id(finding) in claimed:
                    continue
                record = {
                    'case': name,
                    'file': finding.get('file'),
                    'line': finding_line(finding),
                    'severity': finding.get('severity'),
                    'title': finding.get('title') or finding.get('summary') or '',
                }
                if control and severity_at_or_above(finding, FALSE_POSITIVE_FLOOR):
                    tally[lens]['false_positives'].append(record)
                else:
                    tally[lens]['unmatched'].append(record)

        per_case.append(case_row)

    controls = [c['case'] for c in cases if c.get('control')]
    for lens, row in tally.items():
        row['catch_rate'] = (
            None if not row['planted'] else row['caught'] / float(row['planted'])
        )
    return {'lenses': tally, 'cases': per_case, 'controls': controls}


def pct(value):
    return '—' if value is None else '%d%%' % round(value * 100)


def report(scored, cases):
    out = []
    add = out.append

    add('# Review panel calibration')
    add('')
    add('%d fixture case(s), %d clean control(s).'
        % (len(cases), len(scored['controls'])))
    add('')
    add('Catch rate counts only defects planted for that lens. False positives')
    add('are counted only on clean controls, where nothing was planted and there')
    add('is nothing a finding could have legitimately found. Everything else is')
    add('listed below unscored, because the fixtures cannot settle it.')
    add('')
    add('| Lens | Planted | Caught | Catch rate | False pos. (controls) | Cross-catches | Unmatched | Findings |')
    add('|---|---|---|---|---|---|---|---|')
    for lens in sorted(scored['lenses']):
        row = scored['lenses'][lens]
        add('| `%s` | %d | %d | %s | %d | %d | %d | %d |' % (
            lens, row['planted'], row['caught'], pct(row['catch_rate']),
            len(row['false_positives']), len(row['cross']),
            len(row['unmatched']), row['findings']))
    add('')

    missed = [(l, m) for l in sorted(scored['lenses'])
              for m in scored['lenses'][l]['missed']]
    add('## Planted and not found')
    add('')
    if not missed:
        add('None. Every planted defect was found by the lens it was planted for.')
    else:
        for lens, m in missed:
            add('- `%s` — %s in `%s` (case `%s`)' % (lens, m['id'], m['file'], m['case']))
    add('')

    fps = [(l, f) for l in sorted(scored['lenses'])
           for f in scored['lenses'][l]['false_positives']]
    add('## False positives on clean controls')
    add('')
    if not fps:
        add('None at `minor` or above.')
    else:
        for lens, f in fps:
            add('- `%s` — %s `%s:%s` — %s'
                % (lens, f['severity'], f['file'], f['line'], f['title']))
    add('')

    cross = [(l, c) for l in sorted(scored['lenses'])
             for c in scored['lenses'][l]['cross']]
    add('## Cross-catches')
    add('')
    add('A lens finding a defect planted for another. Not scored either way —')
    add('recorded because it is the panel overlapping, which is the argument for')
    add('having several lenses and the argument against paying for all of them.')
    add('')
    if not cross:
        add('None.')
    else:
        for lens, c in cross:
            add('- `%s` found `%s`, planted for `%s` (case `%s`)'
                % (lens, c['id'], c['owner'], c['case']))
    add('')

    unmatched = [(l, u) for l in sorted(scored['lenses'])
                 for u in scored['lenses'][l]['unmatched']]
    add('## Unmatched findings')
    add('')
    add('Findings on cases that carry planted defects, matching none of them.')
    add('**Not scored, in either direction.** Each is either a false positive or')
    add('a real defect nobody planted, and the fixture cannot tell you which.')
    add('Read them.')
    add('')
    if not unmatched:
        add('None.')
    else:
        for lens, u in unmatched:
            add('- `%s` — %s `%s:%s` — %s (case `%s`)'
                % (lens, u['severity'], u['file'], u['line'], u['title'], u['case']))
    add('')

    unrun = [(l, u) for l in sorted(scored['lenses'])
             for u in scored['lenses'][l]['unrun']]
    if unrun:
        add('## Not run')
        add('')
        add('Excluded from every rate above rather than scored as a miss.')
        add('')
        for lens, u in unrun:
            add('- `%s` on case `%s` — %s' % (lens, u['case'], u['reason']))
        add('')

    return '\n'.join(out) + '\n'


def main():
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument('--cases', required=True)
    parser.add_argument('--findings')
    parser.add_argument('--out')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--validate', action='store_true')
    opts = parser.parse_args()

    cases = load_cases(opts.cases)

    if opts.validate:
        planted = sum(len(c['planted']) for c in cases)
        controls = len([c for c in cases if c.get('control')])
        print('%d case(s) valid: %d planted defect(s), %d clean control(s).'
              % (len(cases), planted, controls))
        return 0

    if not opts.findings:
        die('--findings is required unless --validate is given')

    results = load_json(opts.findings, 'findings')
    if isinstance(results, dict):
        results = results.get('results') or results.get('cases') or []
    if not isinstance(results, list):
        die('findings must be a list of {case, lens, findings} objects', 1)

    scored = score(cases, results)

    if opts.json:
        print(json.dumps(scored, indent=2, sort_keys=True))
        return 0

    text = report(scored, cases)
    if opts.out:
        if not os.path.isdir(opts.out):
            os.makedirs(opts.out)
        path = os.path.join(opts.out, 'report.md')
        with open(path, 'w') as handle:
            handle.write(text)
        print('Wrote %s' % path)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
