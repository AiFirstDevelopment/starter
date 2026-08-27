#!/usr/bin/env python3
"""Hash and verify an audit's criteria list. Exit 1 means they disagree.

`/quorum:audit` derives criteria from a spec, shows them, and stops. Only after a
human says yes does anything audit anything. Between those two moments the
criteria are the whole contract, and softening one — dropping a clause, widening
a "must" into a "should" — turns a gap into a pass with nothing to show for it.

So the criteria list is hashed when it is written, and the report cites the hash
it was audited against. Three values have to agree: what `criteria.md` contains
now, what `criteria.md` says it contained, and what `report.md` says it measured.

  audit.py --hash docs/audit/<slug>/criteria.md    # the hash of the criteria list
  audit.py --verify docs/audit/<slug> [--json]     # all three agree?
  audit.py --version                               # which hashing this copy does

Deliberately not a flag on guard.py. That file is vendored into every adopting
repo and checked for drift against the plugin's copy, so each change to it
obliges every adopter to re-vendor. An audit helper has no business forcing that
on anyone.

Exit: 0 clean, 1 a mismatch, 2 could not run.
"""

import argparse
import hashlib
import json
import os
import re
import sys

# What this copy hashes. Bump it only when the hashing itself changes — every
# audit written before that point then has a hash that no longer recomputes,
# which is a migration, not a release note.
VERSION = '1'

CRITERIA_HEADING = 'Criteria'
HASH_FIELD = 'Criteria hash'


def sections(text):
    """Split markdown into {heading: body} at level-2 headings.

    A deliberate copy of guard.py's splitter rather than an import of it. The
    hash below has to mean the same thing in a year, and guard.py is the
    vendored, drift-checked file that moves on its own schedule — importing from
    it would let an unrelated change there silently restate every audit's hash.
    Fifteen frozen lines are cheaper than a hash whose definition travels.
    """
    out, key, buf = {}, None, []
    for line in text.splitlines():
        match = re.match(r'^##\s+(.*?)\s*$', line)
        if match:
            if key is not None:
                out[key] = '\n'.join(buf)
            key, buf = match.group(1), []
        elif key is not None:
            buf.append(line)
    if key is not None:
        out[key] = '\n'.join(buf)
    return out


def section_body(text, name):
    for heading, body in sections(text).items():
        if heading.strip().lower() == name.lower():
            return body
    return None


def criteria_hash(text):
    """Hash the criteria list, or None when there is no criteria list.

    Formatting is normalised away — trailing whitespace, runs of blank lines,
    checkbox state — so reflowing the file is not the same act as changing what
    the repository is being measured against. Wording is not normalised away;
    that is the point.

    Only the `## Criteria` section is hashed. The title, the spec reference, the
    date, and the recorded hash itself all sit outside it, so writing the hash
    into the file does not change the thing the hash covers.
    """
    body = section_body(text, CRITERIA_HEADING)
    if body is None:
        return None
    body = re.sub(r'^(\s*[-*]\s*)\[[ xX]\]', r'\1[ ]', body, flags=re.M)
    body = '\n'.join(line.rstrip() for line in body.strip().splitlines())
    body = re.sub(r'\n{3,}', '\n\n', body)
    return hashlib.sha256(('criteria\n' + body).encode('utf-8')).hexdigest()


def field(text, name):
    """A `- **Name:** value` header field, or None."""
    match = re.search(r'^-\s*\*\*%s:?\*\*\s*(.+?)\s*$' % re.escape(name), text, re.M | re.I)
    return match.group(1).strip().strip('`') if match else None


def read(path):
    with open(path) as handle:
        return handle.read()


def verify(work_dir):
    """Compare the three hashes. Returns (exit code, result dict)."""
    criteria_path = os.path.join(work_dir, 'criteria.md')
    report_path = os.path.join(work_dir, 'report.md')

    if not os.path.exists(criteria_path):
        sys.stderr.write('audit: no criteria at %s\n' % criteria_path)
        return 2, None

    criteria_text = read(criteria_path)
    computed = criteria_hash(criteria_text)
    if computed is None:
        sys.stderr.write('audit: %s has no "## %s" section to hash\n'
                         % (criteria_path, CRITERIA_HEADING))
        return 2, None

    result = {
        'workDir': work_dir,
        'computed': computed,
        'recorded': field(criteria_text, HASH_FIELD),
        'cited': None,
        'reported': os.path.exists(report_path),
        'violations': [],
        'notes': [],
    }

    if result['recorded'] is None:
        result['violations'].append(
            'criteria.md records no "%s" field, so nothing fixes what was shown at the gate'
            % HASH_FIELD)
    elif result['recorded'] != computed:
        result['violations'].append(
            'criteria.md has changed since its hash was recorded — records %s, hashes to %s'
            % (result['recorded'], computed))

    if not result['reported']:
        result['notes'].append(
            'no report.md — the run stopped at the criteria gate, or has not been run')
        return (1 if result['violations'] else 0), result

    report_text = read(report_path)
    result['cited'] = field(report_text, HASH_FIELD)
    if result['cited'] is None:
        result['violations'].append(
            'report.md cites no "%s", so which criteria it measured is unknowable' % HASH_FIELD)
    elif result['cited'] != computed:
        result['violations'].append(
            'report.md was audited against different criteria — cites %s, criteria.md hashes to %s'
            % (result['cited'], computed))

    return (1 if result['violations'] else 0), result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hash', metavar='CRITERIA')
    parser.add_argument('--verify', metavar='AUDIT_DIR')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--version', action='store_true')
    opts = parser.parse_args()

    if opts.version:
        print(VERSION)
        return 0

    if opts.hash:
        if not os.path.exists(opts.hash):
            sys.stderr.write('audit: no such criteria file: %s\n' % opts.hash)
            return 2
        digest = criteria_hash(read(opts.hash))
        if digest is None:
            sys.stderr.write('audit: %s has no "## %s" section to hash\n'
                             % (opts.hash, CRITERIA_HEADING))
            return 2
        print(digest)
        return 0

    if not opts.verify:
        parser.print_usage()
        return 2

    code, result = verify(opts.verify)
    if result is None:
        return code

    if opts.json:
        print(json.dumps(dict(result, clean=not result['violations']), indent=2))
        return code

    print('quorum audit — %s' % result['workDir'])
    for note in result['notes']:
        print('  note: %s' % note)
    if not result['violations']:
        print('  clean — criteria hash %s' % result['computed'])
        return 0
    print('')
    for item in result['violations']:
        print('  MISMATCH %s' % item)
    print('')
    print('The report is measured against criteria a human approved. A mismatch means')
    print('the two are not the same list; re-run /quorum:audit rather than reconciling it.')
    return code


if __name__ == '__main__':
    sys.exit(main())
