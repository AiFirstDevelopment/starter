#!/usr/bin/env python3
"""Self-test for the quorum enforcement layer.

The guard, the plan-lock hook, and the state recorder are what the rest of the
pipeline's promises now rest on. Prose about them is worth nothing; this builds
throwaway repositories, breaks each rule on purpose, and checks that the rule
fires — and, just as importantly, that legitimate edits are still allowed.

    python3 selftest.py [-v]

Exit 0 all passed, 1 something regressed.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, 'guard.py')
HOOK = os.path.join(HERE, 'plan-lock-hook.py')
STATE = os.path.join(HERE, 'state.py')

PLAN = """# Plan: demo

## Intent

Make the widget retry.

## Acceptance criteria

- [ ] AC1: when the call fails, it retries three times
- [ ] AC2: when it still fails, the error surfaces

## Non-goals

- Rewriting the transport

## Approach

Use the existing retry helper.
"""

TESTS = """it('retries three times', () => { expect(1).toBe(1) })
it('surfaces the error', () => { expect(1).toBe(1) })
it('does something else', () => { expect(1).toBe(1) })
"""

VERDICT_OK = """# Verdict — demo

- **Outcome:** ready
- **Test suite:** green

## Acceptance criteria

| AC | Met | Evidence |
|---|---|---|
| AC1 | yes | `tests/widget.test.js:1` asserts the retry |
| AC2 | yes | `tests/widget.test.js:2` asserts the error |
"""

results = []
VERBOSE = '-v' in sys.argv


def check(name, ok, detail=''):
    results.append((name, ok, detail))
    if VERBOSE or not ok:
        print('  %s  %s%s' % ('PASS' if ok else 'FAIL', name, (' — ' + detail) if detail and not ok else ''))


def run(cmd, cwd=None, stdin=None):
    proc = subprocess.run(
        cmd, cwd=cwd, input=stdin,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return proc.returncode, proc.stdout.decode('utf-8', 'replace'), proc.stderr.decode('utf-8', 'replace')


def git(repo, *args):
    return run(['git'] + list(args), cwd=repo)


def make_repo():
    """A work item mid-pipeline: planned, built, reviewed, on a feature branch."""
    repo = tempfile.mkdtemp(prefix='quorum-selftest-')
    git(repo, 'init', '-q', '-b', 'main', '.')
    git(repo, 'config', 'user.email', 'selftest@example.com')
    git(repo, 'config', 'user.name', 'selftest')

    os.makedirs(os.path.join(repo, 'tests'))
    os.makedirs(os.path.join(repo, 'docs/work/demo/reviews'))
    write(repo, 'docs/work/demo/plan.md', PLAN)
    write(repo, 'tests/widget.test.js', TESTS)
    write(repo, 'docs/work/demo/reviews/001-correctness.md', '# Review 001\n\nClean.\n')

    git(repo, 'add', '-A')
    git(repo, 'commit', '-q', '-m', 'base')
    git(repo, 'update-ref', 'refs/remotes/origin/main', 'HEAD')
    git(repo, 'symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/main')
    git(repo, 'checkout', '-q', '-b', 'feature/demo')

    code, out, _ = run(['python3', GUARD, '--hash', 'docs/work/demo/plan.md'], cwd=repo)
    run(['python3', STATE, 'docs/work/demo',
         json.dumps({'slug': 'demo', 'stage': 'planned',
                     'plan': {'acs': 2, 'requirementsHash': out.strip()}})], cwd=repo)
    return repo


def write(repo, rel, text):
    path = os.path.join(repo, rel)
    parent = os.path.dirname(path)
    if not os.path.isdir(parent):
        os.makedirs(parent)
    with open(path, 'w') as handle:
        handle.write(text)


def read(repo, rel):
    with open(os.path.join(repo, rel)) as handle:
        return handle.read()


def guard_rules(repo):
    """Run the guard and return the set of rules that fired."""
    git(repo, 'add', '-A')
    git(repo, 'commit', '-q', '-m', 'change')
    code, out, err = run(['python3', GUARD, '--base', 'origin/main', '--json'], cwd=repo)
    try:
        return set(v['rule'] for v in json.loads(out)['violations'])
    except (ValueError, KeyError):
        return {'<guard failed: %s>' % (err.strip() or out.strip())}


def case(name, mutate, expected):
    """Apply one mutation to a fresh repo and assert exactly what fires."""
    repo = make_repo()
    try:
        mutate(repo)
        fired = guard_rules(repo)
        if expected is None:
            check(name, not fired, 'fired: %s' % sorted(fired))
        else:
            check(name, expected in fired, 'fired: %s, wanted %s' % (sorted(fired), expected))
    finally:
        shutil.rmtree(repo, ignore_errors=True)


# ------------------------------------------------------------------ the guard

def test_guard():
    print('guard')

    case('clean work item stays clean',
         lambda r: write(r, 'docs/work/demo/verdict.md', VERDICT_OK), None)

    case('acceptance criterion reworded',
         lambda r: write(r, 'docs/work/demo/plan.md',
                         PLAN.replace('retries three times', 'retries at least once')),
         'requirements')

    case('non-goal deleted',
         lambda r: write(r, 'docs/work/demo/plan.md',
                         PLAN.replace('- Rewriting the transport', '')),
         'requirements')

    case('criterion ticked is not a change',
         lambda r: (write(r, 'docs/work/demo/plan.md', PLAN.replace('- [ ] AC1', '- [x] AC1')),
                    write(r, 'docs/work/demo/verdict.md', VERDICT_OK)), None)

    case('test file deleted',
         lambda r: os.remove(os.path.join(r, 'tests/widget.test.js')), 'tests')

    case('test case removed',
         lambda r: write(r, 'tests/widget.test.js',
                         '\n'.join(TESTS.splitlines()[:2]) + '\n'), 'tests')

    case('skip marker added',
         lambda r: write(r, 'tests/widget.test.js', TESTS.replace("it('surfaces", "it.skip('surfaces")),
         'tests')

    case('only marker added',
         lambda r: write(r, 'tests/widget.test.js', TESTS.replace("it('retries", "it.only('retries")),
         'tests')

    case('existing review edited',
         lambda r: write(r, 'docs/work/demo/reviews/001-correctness.md', '# Review 001\n\nReworded.\n'),
         'reviews')

    case('new review appended is fine',
         lambda r: (write(r, 'docs/work/demo/reviews/002-security.md', '# Review 002\n\nClean.\n'),
                    write(r, 'docs/work/demo/verdict.md', VERDICT_OK)), None)

    case('ready alongside an open escalation',
         lambda r: write(r, 'docs/work/demo/verdict.md',
                         VERDICT_OK + '\n## Escalations\n\n### E1 — rewrite the transport?\n\nNeeds a human.\n'),
         'verdict')

    case('ready with a criterion marked not met',
         lambda r: write(r, 'docs/work/demo/verdict.md',
                         VERDICT_OK.replace('| AC2 | yes |', '| AC2 | **no** |')),
         'verdict')

    case('criterion missing from the verdict',
         lambda r: write(r, 'docs/work/demo/verdict.md',
                         VERDICT_OK.replace('| AC2 | yes | `tests/widget.test.js:2` asserts the error |\n', '')),
         'coverage')

    case('criterion invented by the verdict',
         lambda r: write(r, 'docs/work/demo/verdict.md',
                         VERDICT_OK + '| AC9 | yes | `tests/widget.test.js:1` |\n'),
         'coverage')

    case('evidence file does not exist',
         lambda r: write(r, 'docs/work/demo/verdict.md',
                         VERDICT_OK.replace('tests/widget.test.js:1', 'tests/imaginary.test.js:1')),
         'evidence')

    case('evidence line is past the end of the file',
         lambda r: write(r, 'docs/work/demo/verdict.md',
                         VERDICT_OK.replace('tests/widget.test.js:1', 'tests/widget.test.js:900')),
         'evidence')


def test_default_branch():
    repo = make_repo()
    try:
        git(repo, 'checkout', '-q', 'main')
        code, out, _ = run(['python3', GUARD, '--base', 'origin/main', '--json'], cwd=repo)
        rules = set(v['rule'] for v in json.loads(out)['violations'])
        check('artifacts on the default branch', 'branch' in rules, 'fired: %s' % sorted(rules))
    finally:
        shutil.rmtree(repo, ignore_errors=True)


# ------------------------------------------------------------------- the hook

def hook(repo, payload):
    code, _, _ = run(['python3', HOOK], cwd=repo, stdin=json.dumps(payload).encode())
    return code


def test_hook():
    print('plan-lock hook')
    repo = make_repo()
    plan = 'docs/work/demo/plan.md'
    try:
        blocked = [
            ('weakening a criterion', {'tool_name': 'Edit', 'tool_input': {
                'file_path': plan, 'old_string': 'retries three times',
                'new_string': 'retries at least once'}}),
            ('deleting a criterion', {'tool_name': 'Edit', 'tool_input': {
                'file_path': plan, 'old_string': '- [ ] AC2: when it still fails, the error surfaces',
                'new_string': ''}}),
            ('rewording the intent', {'tool_name': 'Edit', 'tool_input': {
                'file_path': plan, 'old_string': 'Make the widget retry.',
                'new_string': 'Make the widget better.'}}),
            ('a Write that drops a non-goal', {'tool_name': 'Write', 'tool_input': {
                'file_path': plan, 'content': PLAN.replace('- Rewriting the transport', '')}}),
            ('a MultiEdit smuggling a criterion change', {'tool_name': 'MultiEdit', 'tool_input': {
                'file_path': plan, 'edits': [
                    {'old_string': 'Use the existing retry helper.', 'new_string': 'Use a new helper.'},
                    {'old_string': 'the error surfaces', 'new_string': 'the error is logged'}]}}),
        ]
        for name, payload in blocked:
            check('blocks ' + name, hook(repo, payload) == 2)

        allowed = [
            ('ticking a checkbox', {'tool_name': 'Edit', 'tool_input': {
                'file_path': plan, 'old_string': '- [ ] AC1:', 'new_string': '- [x] AC1:'}}),
            ('editing Approach', {'tool_name': 'Edit', 'tool_input': {
                'file_path': plan, 'old_string': 'Use the existing retry helper.',
                'new_string': 'Use the retry helper in src/retry.js.'}}),
            ('appending Build notes', {'tool_name': 'Edit', 'tool_input': {
                'file_path': plan, 'old_string': '## Approach',
                'new_string': '## Build notes\n\n- S1 deviation\n\n## Approach'}}),
            ('editing an unrelated source file', {'tool_name': 'Edit', 'tool_input': {
                'file_path': 'src/app.js', 'old_string': 'a', 'new_string': 'b'}}),
            ('editing the verdict', {'tool_name': 'Edit', 'tool_input': {
                'file_path': 'docs/work/demo/verdict.md', 'old_string': 'x', 'new_string': 'y'}}),
        ]
        for name, payload in allowed:
            check('allows ' + name, hook(repo, payload) == 0)

        code, _, _ = run(['python3', HOOK], cwd=repo, stdin=b'not json at all')
        check('fails open on malformed input', code == 0)

        code, _, _ = run(['python3', HOOK], cwd=repo, stdin=json.dumps(
            {'tool_name': 'Edit', 'tool_input': {'file_path': plan}}).encode())
        check('fails open on an unusable payload', code == 0)
    finally:
        shutil.rmtree(repo, ignore_errors=True)


# ------------------------------------------------------------------- the state

def test_state():
    print('state recorder')
    repo = make_repo()
    work = 'docs/work/demo'
    try:
        run(['python3', STATE, work, '{"stage":"built","build":{"stepsDone":4,"head":"abc1234"}}'], cwd=repo)
        run(['python3', STATE, work, '{"stage":"reviewed","review":{"round":1}}'], cwd=repo)
        state = json.loads(read(repo, work + '/state.json'))
        check('merging preserves earlier sections', state.get('build', {}).get('head') == 'abc1234')
        check('merging preserves the plan baseline', 'requirementsHash' in state.get('plan', {}))
        check('the log accumulates in order', state['stage'] == 'reviewed')

        code, _, _ = run(['python3', STATE, work, '{"stage":"invented"}'], cwd=repo)
        check('an unknown stage is rejected', code == 1)

        write(repo, work + '/state.json', 'not json')
        code, _, _ = run(['python3', STATE, work, '{"stage":"planned","log":"rebuilt"}'], cwd=repo)
        rebuilt = json.loads(read(repo, work + '/state.json'))
        check('a corrupt state file is rebuilt', code == 0 and rebuilt['stage'] == 'planned')
        check('a rebuilt state recovers its slug', rebuilt.get('slug') == 'demo')
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def main():
    code, _, _ = run(['git', '--version'])
    if code != 0:
        sys.stderr.write('selftest: git is required\n')
        return 2

    test_guard()
    test_default_branch()
    test_hook()
    test_state()

    failed = [r for r in results if not r[1]]
    print('')
    print('%d/%d passed' % (len(results) - len(failed), len(results)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
