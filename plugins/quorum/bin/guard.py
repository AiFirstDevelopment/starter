#!/usr/bin/env python3
"""Mechanical checks on a quorum work item. Exit 1 means a rule was broken.

Every rule the pipeline states in prose is a rule an agent can talk itself out
of. These are the ones a machine can settle, so a machine settles them:

  requirements   Intent / Acceptance criteria / Non-goals unchanged since planning
  tests          no test file deleted, no test case removed, no new skip or .only
  reviews        the review record is append-only
  verdict        the verdict does not contradict itself
  coverage       every acceptance criterion in the plan is accounted for
  evidence       files and lines cited as proof of a met criterion actually exist
  branch         work is not happening on the default branch

Usage:
  guard.py [--work-dir docs/work/<slug>] [--base <ref>] [--json] [--check-gate]
  guard.py --hash docs/work/<slug>/plan.md      # baseline for the requirements rule
  guard.py --install-ci                         # vendor into the repo + CI workflow

Exit: 0 clean, 1 violations found, 2 could not run.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

REQUIREMENT_SECTIONS = ['Intent', 'Acceptance criteria', 'Non-goals']

TEST_PATH = re.compile(r'(^|[/_.-])(tests?|specs?|__tests__)([/_.-]|$)', re.I)

TEST_CASE = re.compile(
    r'\bx?(?:it|test|describe|context)\s*(?:\.\s*(?:only|skip|todo)\s*)?\(|'  # js/ts, rspec
    r'^\s*def\s+test_\w+|'                            # python
    r'^\s*(?:public\s+)?void\s+test\w*\s*\(|'         # java-ish
    r'@Test\b|'                                       # java/kotlin
    r'^\s*func\s+Test\w+\s*\(|'                       # go
    r'^\s*#\[test\]',                                 # rust
    re.M | re.I,
)

SKIP_MARKER = re.compile(
    r'\b(?:it|test|describe|context)\s*\.\s*(?:skip|todo)\s*\(|'
    r'\bx(?:it|describe|test)\s*\(|'
    r'@pytest\.mark\.(?:skip|xfail)|'
    r'@(?:Ignore|Disabled)\b|'
    r'\bt\.Skip\s*\(|'
    r'^\s*#\[ignore\]|'
    r'\.\s*(?:skip|todo)\s*\(',
    re.M | re.I,
)

# .only silently disables every other test in the file while the suite still
# reports green. It is the quietest way to buy a passing run.
ONLY_MARKER = re.compile(r'\b(?:it|test|describe|context)\s*\.\s*only\s*\(', re.I)

CI_WORKFLOW = '''# Runs the quorum guard on every pull request.
#
# This is the only enforcement in the pipeline that no agent can reach: it
# executes on the CI runner, after the work is done, and a failure here blocks
# the merge regardless of what any verdict claims.
name: quorum guard

on:
  pull_request:
  workflow_dispatch:

jobs:
  guard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v7
        with:
          python-version: '3.x'
      - name: Check the work item against the rules
        run: python3 .quorum/guard.py --base "origin/${{ github.base_ref }}"
'''


class Guard(object):
    def __init__(self, work_dir, base):
        self.work_dir = work_dir
        self.base = base
        self.violations = []
        self.notes = []

    def fail(self, rule, detail):
        self.violations.append({'rule': rule, 'detail': detail})

    def note(self, text):
        self.notes.append(text)

    # ---------------------------------------------------------------- helpers

    def git(self, *cmd):
        try:
            out = subprocess.check_output(('git',) + cmd, stderr=subprocess.DEVNULL)
        except (subprocess.CalledProcessError, OSError):
            return None
        return out.decode('utf-8', 'replace')

    def state(self):
        path = os.path.join(self.work_dir, 'state.json')
        if not os.path.exists(path):
            return {}
        try:
            with open(path) as handle:
                loaded = json.load(handle)
                return loaded if isinstance(loaded, dict) else {}
        except ValueError:
            return {}

    def changed_files(self):
        out = self.git('diff', '--name-status', self.base + '...HEAD')
        if out is None:
            return None
        rows = []
        for line in out.splitlines():
            parts = line.split('\t')
            if len(parts) >= 2:
                rows.append((parts[0][0], parts[-1]))
        return rows

    def blob(self, ref, path):
        return self.git('show', '%s:%s' % (ref, path))

    # ---------------------------------------------------------------- rules

    def check_requirements(self):
        """The plan's requirements are the yardstick. Nothing may move them."""
        plan = os.path.join(self.work_dir, 'plan.md')
        if not os.path.exists(plan):
            self.note('no plan.md; requirements not checked')
            return
        recorded = (self.state().get('plan') or {}).get('requirementsHash')
        if not recorded:
            self.note('no requirementsHash recorded at plan time; cannot verify the '
                      'requirements are unchanged')
            return
        with open(plan) as handle:
            current = requirements_hash(handle.read())
        if current != recorded:
            self.fail(
                'requirements',
                'Intent / Acceptance criteria / Non-goals changed since the plan was '
                'written (recorded %s, now %s). Only the user may change them; every '
                'later step is measured against them.' % (recorded[:12], current[:12]),
            )

    def check_tests(self):
        """A suite made green by removing coverage is the failure mode this
        whole pipeline exists to prevent."""
        rows = self.changed_files()
        if rows is None:
            self.note('could not diff against %s; test integrity not checked' % self.base)
            return

        for status, path in rows:
            if not TEST_PATH.search(path):
                continue

            if status == 'D':
                self.fail('tests', 'test file deleted: %s' % path)
                continue

            after = self.blob('HEAD', path)
            if after is None:
                continue

            for marker, label in ((SKIP_MARKER, 'skip'), (ONLY_MARKER, 'only')):
                added = count(marker, after) - count(marker, self.blob(self.base, path) or '')
                if added > 0:
                    self.fail(
                        'tests',
                        '%d new %s marker(s) in %s — the suite reports green while '
                        'those tests do not run' % (added, label, path),
                    )

            if status == 'M':
                before = self.blob(self.base, path)
                if before is not None:
                    lost = count(TEST_CASE, before) - count(TEST_CASE, after)
                    if lost > 0:
                        self.fail(
                            'tests',
                            '%d test case(s) removed from %s' % (lost, path),
                        )

    def check_reviews(self):
        """Reviews are evidence. A superseded review is still evidence of what
        was true then, so nothing may edit or delete one."""
        rows = self.changed_files()
        if rows is None:
            return
        prefix = os.path.join(self.work_dir, 'reviews') + os.sep
        for status, path in rows:
            if path.startswith(prefix) and status in ('M', 'D'):
                verb = 'deleted' if status == 'D' else 'modified'
                self.fail(
                    'reviews',
                    'review file %s: %s — the review record is append-only' % (verb, path),
                )

    def check_verdict(self):
        """The judge's own output must not contradict itself."""
        path = os.path.join(self.work_dir, 'verdict.md')
        if not os.path.exists(path):
            return
        with open(path) as handle:
            text = handle.read()

        outcome = field(text, 'Outcome')
        suite = field(text, 'Test suite')

        if outcome and outcome.lower().startswith('ready'):
            if suite and 'red' in suite.lower():
                self.fail('verdict', 'outcome "%s" over a red suite' % outcome)
            if has_content(text, 'Escalations'):
                self.fail(
                    'verdict',
                    'outcome "%s" alongside open escalations — an escalation forces '
                    '"ready with follow-ups" or "blocked"' % outcome,
                )
            if outcome.strip().lower() == 'ready' and re.search(
                r'^\|\s*AC\d+\s*\|\s*\**no\**\s*\|', text, re.M | re.I
            ):
                self.fail('verdict', 'outcome "ready" with an acceptance criterion marked not met')

        st = self.state().get('verdict') or {}
        if st.get('suite') == 'red' and str(st.get('outcome', '')).startswith('ready'):
            self.fail('verdict', 'state.json records a red suite with outcome "%s"' % st['outcome'])

    def check_coverage(self):
        """An unmet criterion can be hidden by omission as easily as by lying
        about it. Silence about AC4 reads exactly like success."""
        plan = os.path.join(self.work_dir, 'plan.md')
        verdict = os.path.join(self.work_dir, 'verdict.md')
        if not (os.path.exists(plan) and os.path.exists(verdict)):
            return
        with open(plan) as handle:
            planned = set(re.findall(r'^\s*[-*]\s*\[[ xX]\]\s*(AC\d+)\b', handle.read(), re.M))
        if not planned:
            return
        with open(verdict) as handle:
            judged = set(re.findall(r'^\|\s*\**(AC\d+)\**\s*\|', handle.read(), re.M | re.I))

        for missing in sorted(planned - judged, key=ac_order):
            self.fail(
                'coverage',
                '%s is in the plan and absent from the verdict — a criterion nobody '
                'judged is not a criterion met' % missing,
            )
        for phantom in sorted(judged - planned, key=ac_order):
            self.fail(
                'coverage',
                '%s appears in the verdict and not in the plan' % phantom,
            )

    def check_evidence(self):
        """A criterion marked met cites a file. If the file is not there, the
        citation is decoration."""
        path = os.path.join(self.work_dir, 'verdict.md')
        if not os.path.exists(path):
            return
        with open(path) as handle:
            text = handle.read()
        seen = {}
        for row in re.findall(r'^\|\s*\**(AC\d+)\**\s*\|\s*\**yes\**\s*\|([^|]*)\|', text, re.M | re.I):
            ac, evidence = row
            cites = [c.strip() for c in re.findall(r'`([^`]+)`', evidence)]
            if not cites:
                self.note('%s is marked met with no file cited' % ac)
            for cited in cites:
                path_part = cited.split(':')[0]
                if '/' not in path_part and '.' not in path_part:
                    continue
                if not os.path.exists(path_part):
                    self.fail(
                        'evidence',
                        '%s is marked met, citing `%s`, which does not exist' % (ac, cited),
                    )
                    continue
                line = re.search(r':(\d+)', cited)
                if line:
                    wanted = int(line.group(1))
                    with open(path_part, 'rb') as handle:
                        total = sum(1 for _ in handle)
                    if wanted > total:
                        self.fail(
                            'evidence',
                            '%s cites `%s`, but that file has only %d lines'
                            % (ac, cited, total),
                        )
                seen.setdefault(path_part, []).append(ac)

        for path_part, acs in seen.items():
            if len(acs) > 2:
                self.note(
                    '%s criteria (%s) all rest on %s — one citation covering many '
                    'criteria is worth a closer look'
                    % (len(acs), ', '.join(acs), path_part)
                )

    def check_branch(self):
        current = (self.git('branch', '--show-current') or '').strip()
        if not current:
            return
        head = self.git('symbolic-ref', '--quiet', 'refs/remotes/origin/HEAD') or ''
        default = head.strip().rsplit('/', 1)[-1] or 'main'
        if current == default or current in ('main', 'master'):
            self.fail(
                'branch',
                'work item artifacts on default branch "%s"; the pipeline writes to a '
                'work branch' % current,
            )

    def run(self):
        self.check_requirements()
        self.check_tests()
        self.check_reviews()
        self.check_verdict()
        self.check_coverage()
        self.check_evidence()
        self.check_branch()
        return self.violations


# -------------------------------------------------------------------- helpers


def count(pattern, text):
    return len(pattern.findall(text or ''))


def ac_order(name):
    digits = re.search(r'\d+', name)
    return int(digits.group()) if digits else 0


def sections(text):
    """Split markdown into {heading: body} at level-2 headings."""
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


def requirements_hash(plan_text):
    """Hash the requirement sections' text.

    Checkbox state is normalized away: ticking a criterion is progress, editing
    its wording is moving the target.
    """
    found = sections(plan_text)
    parts = []
    for name in REQUIREMENT_SECTIONS:
        body = ''
        for heading, text in found.items():
            if heading.strip().lower() == name.lower():
                body = text
                break
        body = re.sub(r'^(\s*[-*]\s*)\[[ xX]\]', r'\1[ ]', body, flags=re.M)
        body = '\n'.join(line.rstrip() for line in body.strip().splitlines())
        body = re.sub(r'\n{3,}', '\n\n', body)
        parts.append(name.lower() + '\n' + body)
    return hashlib.sha256('\n---\n'.join(parts).encode('utf-8')).hexdigest()


def field(text, name):
    match = re.search(r'^-\s*\*\*%s:?\*\*\s*(.+?)\s*$' % re.escape(name), text, re.M | re.I)
    return match.group(1) if match else None


def has_content(text, heading):
    found = sections(text)
    for key, body in found.items():
        if key.strip().lower() == heading.lower():
            stripped = re.sub(r'<[^>]*>', '', body).strip()
            stripped = re.sub(r'^[-*]\s*\.\.\.\s*$', '', stripped, flags=re.M).strip()
            return bool(stripped)
    return False


def resolve_work_dir(explicit):
    if explicit:
        return explicit
    try:
        branch = subprocess.check_output(
            ['git', 'branch', '--show-current'], stderr=subprocess.DEVNULL
        ).decode().strip()
    except (subprocess.CalledProcessError, OSError):
        branch = ''
    slug = re.sub(r'^(feature|fix|chore)/', '', branch).lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug).strip('-')
    candidate = os.path.join('docs', 'work', slug)
    if slug and os.path.isdir(candidate):
        return candidate
    root = os.path.join('docs', 'work')
    if os.path.isdir(root):
        items = sorted(
            d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))
        )
        if len(items) == 1:
            return os.path.join(root, items[0])
    return candidate


def check_gate():
    """Report whether the CI check is actually a required status check.

    Writing the workflow is not the gate. The gate is branch protection
    requiring it, which is a repo-admin action in the hosting UI — so an
    unticked box looks identical to a working gate from in here unless
    somebody asks.
    """
    try:
        out = subprocess.check_output(
            ['gh', 'api', 'repos/{owner}/{repo}/rulesets', '--jq', '.[].name'],
            stderr=subprocess.DEVNULL,
        ).decode()
    except (subprocess.CalledProcessError, OSError):
        out = None

    checks = None
    for endpoint in (
        'repos/{owner}/{repo}/branches/main/protection',
        'repos/{owner}/{repo}/branches/master/protection',
    ):
        try:
            raw = subprocess.check_output(
                ['gh', 'api', endpoint], stderr=subprocess.DEVNULL
            ).decode()
        except (subprocess.CalledProcessError, OSError):
            continue
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        checks = (data.get('required_status_checks') or {}).get('contexts') or []
        break

    if checks is None:
        if out is None:
            print('gate: cannot tell — `gh` is unavailable or not authenticated here.')
        else:
            print('gate: cannot read branch protection (admin access is needed to query it).')
        print('      Verify by hand that "quorum guard" is a required status check.')
        return 0

    if any('quorum' in c.lower() for c in checks):
        print('gate: LIVE — "quorum guard" is a required status check.')
        return 0

    print('gate: NOT LIVE — the workflow may run, but nothing blocks a merge on it.')
    print('      Required checks currently: %s' % (', '.join(checks) or 'none'))
    print('      Add "quorum guard" in branch protection to make it a gate.')
    return 1


def install_ci():
    target = os.path.join('.quorum', 'guard.py')
    if not os.path.isdir('.quorum'):
        os.makedirs('.quorum')
    with open(__file__) as src, open(target, 'w') as dst:
        dst.write(src.read())
    os.chmod(target, 0o755)

    flow_dir = os.path.join('.github', 'workflows')
    if not os.path.isdir(flow_dir):
        os.makedirs(flow_dir)
    flow = os.path.join(flow_dir, 'quorum-guard.yml')
    with open(flow, 'w') as handle:
        handle.write(CI_WORKFLOW)

    print('Wrote %s and %s' % (target, flow))
    print('')
    print('Commit both, then make "quorum guard" a required status check in your')
    print('branch protection settings — that is what turns it into a real gate.')
    print('Until then the workflow reports and nothing blocks a merge on it.')
    print('')
    print('Check whether it is live with:  guard.py --check-gate')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir')
    parser.add_argument('--base', default='')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--install-ci', action='store_true')
    parser.add_argument('--hash', metavar='PLAN')
    parser.add_argument('--check-gate', action='store_true')
    opts = parser.parse_args()

    if opts.check_gate:
        return check_gate()

    if opts.install_ci:
        return install_ci()

    if opts.hash:
        if not os.path.exists(opts.hash):
            sys.stderr.write('guard: no such plan: %s\n' % opts.hash)
            return 2
        with open(opts.hash) as handle:
            print(requirements_hash(handle.read()))
        return 0

    work_dir = resolve_work_dir(opts.work_dir)
    if not os.path.isdir(work_dir):
        sys.stderr.write('guard: no work item at %s\n' % work_dir)
        return 2

    base = opts.base
    if not base:
        try:
            head = subprocess.check_output(
                ['git', 'symbolic-ref', '--quiet', 'refs/remotes/origin/HEAD'],
                stderr=subprocess.DEVNULL,
            ).decode().strip()
            base = 'origin/' + head.rsplit('/', 1)[-1]
        except (subprocess.CalledProcessError, OSError):
            base = 'origin/main'

    guard = Guard(work_dir, base)
    violations = guard.run()

    if opts.json:
        print(json.dumps(
            {'workDir': work_dir, 'base': base, 'clean': not violations,
             'violations': violations, 'notes': guard.notes},
            indent=2,
        ))
        return 1 if violations else 0

    print('quorum guard — %s (against %s)' % (work_dir, base))
    for note in guard.notes:
        print('  note: %s' % note)
    if not violations:
        print('  clean — no rule violations found')
        return 0
    print('')
    for item in violations:
        print('  VIOLATION [%s] %s' % (item['rule'], item['detail']))
    print('')
    print('%d violation(s). These are not opinions and not findings to adjudicate;' % len(violations))
    print('they are rules the pipeline states it does not break.')
    return 1


if __name__ == '__main__':
    sys.exit(main())
