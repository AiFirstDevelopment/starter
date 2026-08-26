#!/usr/bin/env python3
"""Self-test for the quorum enforcement layer.

The guard, the plan-lock hook, and the state recorder are what the rest of the
pipeline's promises now rest on. Prose about them is worth nothing; this builds
throwaway repositories, breaks each rule on purpose, and checks that the rule
fires — and, just as importantly, that legitimate edits are still allowed.

It also checks the one part of the orchestrator a machine can settle without a
live run: that pipeline.js calls its agents by names that actually register.
Everything else in that script needs real agents to exercise. This does not, and
it is the failure that has already cost two runs.

    python3 selftest.py [-v]

Exit 0 all passed, 1 something regressed.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, 'guard.py')
HOOK = os.path.join(HERE, 'plan-lock-hook.py')
STATE = os.path.join(HERE, 'state.py')

PLUGIN = os.path.dirname(HERE)
MANIFEST = os.path.join(PLUGIN, '.claude-plugin', 'plugin.json')
AGENTS_DIR = os.path.join(PLUGIN, 'agents')
PIPELINE = os.path.join(PLUGIN, 'workflow', 'pipeline.js')

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


def guard_version():
    """The VERSION literal guard.py stamps itself with."""
    with open(GUARD) as handle:
        for line in handle:
            match = re.match(r"^VERSION\s*=\s*'([^']+)'", line)
            if match:
                return match.group(1)
    return None


def record_branch(repo, name):
    """Record the branch a plan was written on, as 1-plan does."""
    run(['python3', STATE, 'docs/work/demo', json.dumps({'branch': name})], cwd=repo)


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


def test_lifetime():
    """The two ways a long-lived repo drifts out from under the checker.

    Both are invisible at the moment they happen and stay invisible: a work item
    whose branch no longer matches its plan writes internally consistent files
    under the wrong name, and a vendored .quorum/guard.py goes on reporting green
    against whichever rules it was frozen with.
    """
    def drift(repo):
        record_branch(repo, 'feature/demo')
        git(repo, 'checkout', '-q', '-b', 'feature/something-else')

    case('a branch that no longer matches the plan is caught', drift, 'branch')
    case('the branch the plan names is allowed',
         lambda r: record_branch(r, 'feature/demo'), None)
    case('no recorded branch is not a violation',
         lambda r: None, None)

    def vendor(repo):
        """What --install-ci writes: this exact file, plus the workflow that runs it."""
        write(repo, '.quorum/guard.py', open(GUARD).read())
        write(repo, '.github/workflows/quorum-guard.yml', 'name: quorum guard\n')

    def vendor_then_edit(repo):
        vendor(repo)
        with open(os.path.join(repo, '.quorum/guard.py'), 'a') as handle:
            handle.write('\n# someone tuned the rules here and nowhere else\n')

    def vendor_then_delete_guard(repo):
        vendor(repo)
        git(repo, 'add', '-A')
        git(repo, 'commit', '-q', '-m', 'vendor enforcement')
        git(repo, 'update-ref', 'refs/remotes/origin/main', 'HEAD')
        os.remove(os.path.join(repo, '.quorum/guard.py'))

    def vendor_then_delete_both(repo):
        vendor_then_delete_guard(repo)
        os.remove(os.path.join(repo, '.github/workflows/quorum-guard.yml'))

    case('a faithfully vendored guard is allowed', vendor, None)
    case('a workflow with no vendored guard is caught',
         lambda r: write(r, '.github/workflows/quorum-guard.yml', 'name: quorum guard\n'),
         'enforcement')
    case('a vendored guard nothing runs is caught',
         lambda r: write(r, '.quorum/guard.py', open(GUARD).read()), 'enforcement')
    case('deleting the vendored guard is caught', vendor_then_delete_guard, 'enforcement')
    case('deleting the whole enforcement layer is caught',
         vendor_then_delete_both, 'enforcement')
    case('a repo that never vendored is left alone', lambda r: None, None)
    case('a vendored guard edited in place is caught', vendor_then_edit, 'vendored')
    case('a vendored guard frozen at an older rule set is caught',
         lambda r: (write(r, '.quorum/guard.py', "VERSION = '0'\n# old rules\n"),
                    write(r, '.github/workflows/quorum-guard.yml', 'x\n')),
         'vendored')
    case('an unstamped vendored guard is caught',
         lambda r: (write(r, '.quorum/guard.py', '# no stamp here\n'),
                    write(r, '.github/workflows/quorum-guard.yml', 'x\n')),
         'vendored')


# ------------------------------------------------------------ the version stamp

def test_version():
    """guard.py carries a readable rule-set stamp, and reports it.

    The stamp is deliberately not the plugin version — drift is detected by
    comparing contents, so tying the two would make every unrelated release
    demand a re-vendor. What must hold is that the stamp exists and that a
    vendored copy can be interrogated for it without a plugin present.
    """
    stamped = guard_version()
    check('guard.py declares a VERSION', stamped is not None)

    code, out, _ = run(['python3', GUARD, '--version'])
    check('guard.py --version reports it', code == 0 and out.strip() == (stamped or ''),
          'exit %s, printed %r, constant is %r' % (code, out.strip(), stamped))


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


# ------------------------------------------------------------------ the agents

def frontmatter_name(path):
    """The `name:` field from a markdown file's YAML frontmatter, or None."""
    with open(path) as handle:
        lines = handle.read().split('\n')
    if not lines or lines[0].strip() != '---':
        return None
    for line in lines[1:]:
        if line.strip() == '---':
            break
        if line.startswith('name:'):
            return line.split(':', 1)[1].strip()
    return None


def test_agents():
    """The orchestrator names agents that exist, the way they actually register.

    Nothing else covers pipeline.js. The guard checks what the pipeline produces,
    not the script that runs it, so a wrong agentType stays invisible until a run
    reaches the first agent() call — which is after the approval gate, on work
    that then cannot start.

    Plugin agents register namespaced, <plugin>:<agent>. That prefix has twice
    been dropped from this script and hand-patched back into the installed plugin
    cache, where the next `claude plugin update` throws it away. Three files have
    to agree and all three are in the repo, so nothing here needs a model or a
    live run.
    """
    with open(MANIFEST) as handle:
        plugin = json.load(handle)['name']

    declared = {}
    for entry in sorted(os.listdir(AGENTS_DIR)):
        if not entry.endswith('.md'):
            continue
        name = frontmatter_name(os.path.join(AGENTS_DIR, entry))
        check('%s declares a frontmatter name' % entry, name is not None)
        if name is None:
            continue
        check('%s: frontmatter name matches filename' % entry, name == entry[:-3],
              'frontmatter says %r' % name)
        declared[name] = entry
    check('agents/ is not empty', bool(declared))

    with open(PIPELINE) as handle:
        source = handle.read()
    # The trailing delimiter matters: it means a literal and nothing else. Any
    # concatenation or lookup fails to match and shows up as a count mismatch
    # below, rather than half-matching and quietly narrowing what is checked.
    used = re.findall(r"agentType:\s*'([^']*)'\s*[,}\n]", source)

    # A computed agentType would slip past the regex and take the whole check
    # with it, silently. Every site must be a plain literal for this to mean
    # anything.
    check('every agentType in pipeline.js is a plain string literal',
          len(used) == source.count('agentType:'),
          '%d agentType keys, %d literals — a computed name escapes this check'
          % (source.count('agentType:'), len(used)))
    check('pipeline.js calls agents at all', bool(used))

    registered = set('%s:%s' % (plugin, name) for name in declared)
    for ref in sorted(set(used)):
        check('pipeline.js agentType %r resolves' % ref, ref in registered,
              'nothing registers under that name; expected one of %s' % sorted(registered))

    for name in sorted(declared):
        check('agent %s is wired into the pipeline' % name,
              '%s:%s' % (plugin, name) in used,
              '%s defines it, pipeline.js never calls it' % declared[name])


def main():
    code, _, _ = run(['git', '--version'])
    if code != 0:
        sys.stderr.write('selftest: git is required\n')
        return 2

    test_guard()
    test_default_branch()
    test_hook()
    test_state()
    test_agents()
    test_lifetime()
    test_version()

    failed = [r for r in results if not r[1]]
    print('')
    print('%d/%d passed' % (len(results) - len(failed), len(results)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
