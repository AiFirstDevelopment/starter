#!/usr/bin/env python3
"""Self-test for the quorum enforcement layer.

The guard, the plan-lock hook, and the state recorder are what the rest of the
pipeline's promises now rest on. Prose about them is worth nothing; this builds
throwaway repositories, breaks each rule on purpose, and checks that the rule
fires — and, just as importantly, that legitimate edits are still allowed.

It also checks the one part of the orchestrators a machine can settle without a
live run: that every script under workflow/ calls its agents by names that
actually register, and that every agent workflow/audit.js calls is granted
nothing but the tools it needs to read. Everything else in those scripts needs
real agents to exercise. This does not, and the first of them is the failure that
has already cost two runs.

Note what the second check settles and what it does not. It settles the declared
grants of the agents audit.js names: no file-editing tool, no shell, and nothing
outside a fixed allowlist, so "cannot write to or execute the repository it
audits" is proven here rather than promised in a prompt. It settles nothing about
the audit *skill*, which runs in an ordinary session holding a shell and reads the
spec file out of the repository under audit; that restraint is prose, and
reference/audit.md says so.

    python3 selftest.py [-v]

Exit 0 all passed, 1 something regressed.
"""

import datetime
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
HISTORY = os.path.join(HERE, 'history.py')
WATCH = os.path.join(HERE, 'watch.py')
AUDIT = os.path.join(HERE, 'audit.py')

PLUGIN = os.path.dirname(HERE)
MANIFEST = os.path.join(PLUGIN, '.claude-plugin', 'plugin.json')
AGENTS_DIR = os.path.join(PLUGIN, 'agents')
WORKFLOW_DIR = os.path.join(PLUGIN, 'workflow')

# Scripts whose agents must not be granted a way to touch the repository they run
# against — neither to edit it nor to execute it. /quorum:audit runs on the default
# branch of a production repository that never asked for this pipeline, and the
# reason that is safe has to be a property of the tool grants: the audited
# repository is untrusted input, so a rule an agent is merely asked to follow can
# be argued out of it by a README it reads.
READ_ONLY_WORKFLOWS = ['audit.js']

# quorum-scribe grants Write and nothing else: it writes the audit report and
# cannot read a line of the repository under audit, transcribing what the
# auditors hand it. Something has to write report.md, and a write-only agent
# that cannot read is the smallest thing that can. Nothing else is exempt, and
# the exemption is checked rather than trusted — see test_agents().
WRITE_ONLY_EXEMPT = ['quorum-scribe']

WRITE_TOOLS = ['Write', 'Edit', 'MultiEdit', 'NotebookEdit']
READ_TOOLS = ['Read', 'Grep', 'Glob', 'Bash', 'NotebookRead']

# Tools that can run the audited repository. A shell is the whole list, and it is
# kept separate from WRITE_TOOLS because the two fail differently: a write tool
# edits a file, while a shell can edit it, commit it, push it, and run the test
# suite and the application besides. Bash appears in READ_TOOLS as well — a shell
# genuinely can read — and the two memberships answer different questions.
EXEC_TOOLS = ['Bash']

# And the allowlist the three lists above cannot replace. WRITE_TOOLS, READ_TOOLS
# and EXEC_TOOLS are membership tests over exact tool names, which makes them only
# as good as the spellings someone thought of: `Bash(git log:*)` is a shell and is
# not the string 'Bash', and `mcp__filesystem__write_file` edits files and is not
# in WRITE_TOOLS. Both passed every denylist check while holding exactly the power
# those checks exist to deny. So the grant is matched positively as well — an
# audit.js agent may hold these tools and nothing else, and an unfamiliar name
# fails rather than passing unseen. Widening either list is a decision someone has
# to make on purpose, which is the point.
AUDIT_READ_TOOLS = ['Read', 'Grep', 'Glob']
AUDIT_WRITE_ONLY_TOOLS = ['Write']

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

## Steps

- [ ] S1: Add the retry wrapper around the transport call
- [ ] S2: Surface the final failure to the caller
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
    # Coerced, because a check that crashes instead of failing is worse than one
    # that never ran: it takes the whole suite down at exactly the moment a real
    # regression made it fail, and reports a TypeError rather than the defect.
    detail = str(detail) if detail else ''
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
    # host-detection reads this; GitHub is the case most rules assume
    git(repo, 'remote', 'add', 'origin', 'https://github.com/acme/demo.git')
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

    def as_gitlab(repo):
        git(repo, 'remote', 'set-url', 'origin', 'https://gitlab.com/acme/demo.git')

    def gitlab_vendored_unwired(repo):
        as_gitlab(repo)
        write(repo, '.quorum/guard.py', open(GUARD).read())

    def gitlab_vendored_wired(repo):
        gitlab_vendored_unwired(repo)
        write(repo, '.gitlab-ci.yml',
              'quorum-guard:\n  script:\n    - python3 .quorum/guard.py --base x\n')

    def unknown_host_vendored(repo):
        git(repo, 'remote', 'set-url', 'origin', 'git@example.invalid:acme/demo.git')
        write(repo, '.quorum/guard.py', open(GUARD).read())

    case('a GitLab repo whose vendored guard nothing runs is caught',
         gitlab_vendored_unwired, 'enforcement')
    case('a GitLab repo with a .gitlab-ci.yml job is left alone',
         gitlab_vendored_wired, None)
    case('an unrecognised host is not told its CI is wrong',
         unknown_host_vendored, None)

    def edited_same_version(repo):
        source = open(GUARD).read()
        write(repo, '.github/workflows/quorum-guard.yml', 'name: quorum guard\n')
        write(repo, '.quorum/guard.py', source + '\n# tweaked, version left alone\n')

    case('a vendored guard edited without touching its version is caught',
         edited_same_version, 'vendored')

    # Firing is not enough here: the whole reason that branch exists is the
    # wording. "rule set 2, this checker is 2" reads as a bug in the checker
    # rather than a fact about the copy, so assert what it actually says.
    repo = make_repo()
    try:
        edited_same_version(repo)
        git(repo, 'add', '-A')
        git(repo, 'commit', '-q', '-m', 'edit the vendored copy')
        code, out, _ = run(['python3', GUARD, '--base', 'origin/main', '--json'], cwd=repo)
        try:
            detail = ' '.join(v['detail'] for v in json.loads(out)['violations']
                              if v['rule'] == 'vendored')
        except (ValueError, KeyError):
            detail = ''
        check('a same-version edit is reported as an edit, not as being behind',
              'same rule set' in detail and 'is rule set' not in detail,
              detail[:180] or out[:180])
    finally:
        shutil.rmtree(repo, ignore_errors=True)


# --------------------------------------------------------------------- watching

def _load_watch():
    import importlib.util
    spec = importlib.util.spec_from_file_location('quorum_watch', WATCH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_watch():
    """Progress comes from the repo's own files, and only when it moves.

    The point of the watcher is that silence means nothing happened. A watcher
    that repeats itself trains people to ignore it, and one that reports a change
    that did not occur is worse than none — so the cases check both directions.
    """
    repo = make_repo()
    work = os.path.join(repo, 'docs/work/demo')
    try:
        def look():
            code, out, err = run(['python3', WATCH, 'docs/work/demo', '--once'], cwd=repo)
            return code, out.strip().split('\n') if out.strip() else []

        code, first = look()
        check('watch runs against a live work item', code == 0)
        check('watch reports the stage it finds',
              any(l.startswith('stage: planned') for l in first), first)

        code, again = look()
        check('watch repeats nothing when nothing moved',
              again == first, 'first=%s again=%s' % (first, again))

        # naming beats counting: "S2 done - surface the failure" tells a watcher
        # what just finished, where "2/2 ticked" only tells them how far along
        code, out, _ = run(['python3', WATCH, 'docs/work/demo', '--once'], cwd=repo)
        check('watch names the steps still outstanding',
              'S1 ' in out and 'S2 ' in out and 'step(s) left' in out, out.strip())

        plan = read(repo, 'docs/work/demo/plan.md')
        write(repo, 'docs/work/demo/plan.md', plan.replace('- [ ] S2:', '- [x] S2:', 1))
        watch_mod = _load_watch()
        before = {'steps_list': watch_mod.parse_steps(plan), 'ticked': 0, 'steps': 2,
                  'reviews': [], 'stage': '', 'last': '', 'verdict': False, 'raw': {}}
        after = watch_mod.snapshot(os.path.join(repo, 'docs/work/demo'))
        moved = watch_mod.differences(before, after)
        check('watch reports which step finished, by name and title',
              any(l.startswith('S2 \u2014 ') and 'Surface' in l and '[done 1/2]' in l
                  for l in moved), moved)
        check('a ticked step is reported once, not on every look',
              watch_mod.differences(after, after) == [], watch_mod.differences(after, after))

        os.makedirs(os.path.join(work, 'reviews'), exist_ok=True)
        write(repo, 'docs/work/demo/reviews/002-security.md', '# Review\n')
        run(['python3', STATE, 'docs/work/demo',
             json.dumps({'stage': 'reviewed', 'log': 'panel complete'})], cwd=repo)
        write(repo, 'docs/work/demo/verdict.md', '# Verdict\n')
        code, out, _ = run(['python3', WATCH, 'docs/work/demo', '--once'], cwd=repo)
        for wanted in ('stage: reviewed', '002-security.md', 'verdict.md written',
                       'panel complete'):
            check('watch reports %r' % wanted, wanted in out, out.strip())

        code, out, _ = run(['python3', WATCH, 'docs/work/nope', '--once'], cwd=repo)
        check('watch refuses a work item that does not exist', code == 2, out.strip())

        # --- minutes remaining, or an honest refusal ------------------------
        import importlib.util as _il
        _spec = _il.spec_from_file_location('quorum_watch_est', WATCH)
        est = _il.module_from_spec(_spec)
        _spec.loader.exec_module(est)

        # --- elapsed must time THIS attempt, not the work item ---------------
        def stamp(mins_ago):
            when = datetime.datetime.utcnow() - datetime.timedelta(minutes=mins_ago)
            return when.strftime('%Y-%m-%dT%H:%M:%SZ')

        four_tries = {'log': [
            '%s pipeline launched' % stamp(70),
            '%s run died before build; approval reset' % stamp(64),
            '%s pipeline launched' % stamp(40),
            '%s run died before build; approval reset' % stamp(33),
            '%s pipeline launched' % stamp(2),
        ]}
        start, end = est.run_window(four_tries)
        age = (datetime.datetime.utcnow() - start).total_seconds() / 60.0
        check('elapsed times the latest attempt, not the whole work item',
              1 <= age <= 4, 'measured %.1f minutes, the item is 70 minutes old' % age)

        check('an item never launched by the pipeline has no run to time',
              est.run_window({'log': ['%s planned' % stamp(30)]}) == (None, None),
              est.run_window({'log': ['%s planned' % stamp(30)]}))
        check('an empty log has no run to time',
              est.run_window({}) == (None, None), est.run_window({}))

        one_try = {'log': ['%s pipeline launched' % stamp(30),
                           '%s published' % stamp(10)]}
        start, end = est.run_window(one_try)
        check('a single attempt measures launch to last event',
              round((end - start).total_seconds() / 60.0) == 20,
              (end - start).total_seconds())

        check('one prior run is not a distribution',
              'no estimate' in est.estimate(600, [1200]), est.estimate(600, [1200]))
        check('no prior runs is not a distribution',
              'no estimate' in est.estimate(600, []), est.estimate(600, []))

        got = est.estimate(600, [1200, 1800, 2400])
        check('a real estimate quotes the spread and what is left',
              'roughly' in got and 'left' in got and 'previous 3 runs' in got, got)

        got = est.estimate(9999, [1200, 1800, 2400])
        check('running longer than every prior run withdraws the estimate',
              'no estimate stands' in got, got)

        got = est.estimate(1900, [1200, 1800, 2400])
        check('past the median it says so rather than counting backwards',
              'tail' in got and 'roughly' not in got, got)

        # and it must read only finished runs
        write(repo, 'docs/work/done-a/state.json', json.dumps({'stage': 'published',
              'log': ['2026-01-01T09:00:00Z pipeline launched',
                      '2026-01-01T09:20:00Z published']}))
        write(repo, 'docs/work/done-b/state.json', json.dumps({'stage': 'published',
              'log': ['2026-01-01T09:00:00Z pipeline launched',
                      '2026-01-01T09:40:00Z published']}))
        write(repo, 'docs/work/mid/state.json', json.dumps({'stage': 'building',
              'log': ['2026-01-01T09:00:00Z pipeline launched',
                      '2026-01-01T12:00:00Z still going']}))
        write(repo, 'docs/work/handbuilt/state.json', json.dumps({'stage': 'published',
              'log': ['2026-01-01T09:00:00Z built by hand',
                      '2026-01-01T09:50:00Z published']}))
        totals = est.completed_runs(os.path.join(repo, 'docs/work'))
        check('only finished runs count toward the estimate',
              totals == [1200, 2400], 'got %s' % totals)
        check('an item the pipeline never launched contributes nothing',
              3000 not in totals, 'got %s' % totals)

        # a retried item must contribute its last attempt, not its whole lifetime
        write(repo, 'docs/work/retried/state.json', json.dumps({'stage': 'published',
              'log': ['2026-01-01T09:00:00Z pipeline launched',
                      '2026-01-01T09:30:00Z run died before build; approval reset',
                      '2026-01-01T10:00:00Z pipeline launched',
                      '2026-01-01T10:15:00Z published']}))
        totals = est.completed_runs(os.path.join(repo, 'docs/work'))
        check('a retried item contributes only its successful attempt',
              900 in totals and 4500 not in totals, 'got %s' % totals)

        # --once cannot test change detection: every invocation starts from a
        # fresh baseline, so it emits the same lines whether or not the diff
        # works. Exercise the comparison itself.
        import importlib.util
        spec = importlib.util.spec_from_file_location('quorum_watch', WATCH)
        watch = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(watch)

        was = watch.snapshot(work)
        check('an unchanged item produces no lines at all',
              watch.differences(was, was) == [], watch.differences(was, was))

        # A plan that does not use the S<n> convention still gets progress, from
        # the raw checkbox count. Named steps take precedence when they exist, so
        # this branch is only reachable with an empty step list.
        plain = dict(was)
        plain['steps_list'] = []
        plain['ticked'], plain['steps'] = 1, 4
        bumped = dict(plain)
        bumped['ticked'] = 2
        lines = watch.differences(plain, bumped)
        check('a plan without named steps still reports a count',
              lines == ['build: 2/4 steps ticked'], lines)

        staged = dict(was)
        staged['stage'] = 'adjudicated'
        check('a stage change produces exactly one line',
              watch.differences(was, staged) == ['stage: adjudicated'],
              watch.differences(was, staged))
    finally:
        shutil.rmtree(repo, ignore_errors=True)


# ------------------------------------------------------------------- install

def test_install_ci():
    """--install-ci wires up only what it knows how to wire up.

    The checker is host-agnostic and always lands. The runner is GitHub Actions,
    so writing it into a GitLab repository and reporting success would leave a
    gate that never runs — worse than no gate, because the green tick is read as
    enforcement.
    """
    def install(repo, url):
        if url:
            git(repo, 'remote', 'set-url', 'origin', url)
        else:
            git(repo, 'remote', 'remove', 'origin')
        return run(['python3', GUARD, '--install-ci'], cwd=repo)

    for label, url, wants_flow, needle in (
        ('github', 'https://github.com/acme/demo.git', True, 'quorum-guard.yml'),
        ('gitlab', 'https://gitlab.com/acme/demo.git', False, '.gitlab-ci.yml'),
        ('an unknown host', '', False, 'neither GitHub nor GitLab'),
    ):
        repo = make_repo()
        try:
            code, out, err = install(repo, url)
            check('install-ci succeeds on %s' % label, code == 0, err.strip())
            check('install-ci vendors the checker on %s' % label,
                  os.path.exists(os.path.join(repo, '.quorum/guard.py')), out[:200])
            wrote = os.path.exists(
                os.path.join(repo, '.github/workflows/quorum-guard.yml'))
            check('install-ci writes a workflow on %s: %s' % (label, wants_flow),
                  wrote == wants_flow, 'wrote=%s' % wrote)
            check('install-ci says what to do on %s' % label, needle in out, out[:300])
            if not wants_flow:
                check('install-ci does not claim a gate on %s' % label,
                      'NO CI JOB WAS WRITTEN' in out, out[:300])
        finally:
            shutil.rmtree(repo, ignore_errors=True)



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


def test_frontmatter():
    """Every SKILL.md frontmatter key is one Claude Code actually reads.

    An unrecognised key does not error — it is ignored. `argument_hint` instead
    of `argument-hint` produces a skill that loads fine and simply never shows
    its hint, which is indistinguishable from not having set one. That is the
    same silent-failure shape as the rest of this file, so it gets the same
    treatment.

    If Claude Code adds a frontmatter field, add it here; an allowlist that
    rejects a newly valid key is the expected cost of catching a typo.
    """
    supported = set([
        'name', 'description', 'when_to_use', 'argument-hint', 'arguments',
        'disable-model-invocation', 'user-invocable', 'allowed-tools',
        'disallowed-tools', 'model', 'effort', 'context', 'agent', 'background',
        'hooks', 'paths', 'shell', 'metadata', 'license', 'compatibility',
    ])

    root = os.path.dirname(PLUGIN)
    skills = []
    for plugin in sorted(os.listdir(root)):
        skill_root = os.path.join(root, plugin, 'skills')
        if not os.path.isdir(skill_root):
            continue
        for entry in sorted(os.listdir(skill_root)):
            path = os.path.join(skill_root, entry, 'SKILL.md')
            if os.path.exists(path):
                skills.append((plugin, entry, path))

    check('found skills to check', bool(skills))
    for plugin, entry, path in skills:
        with open(path) as handle:
            lines = handle.read().split('\n')
        check('%s:%s opens with frontmatter' % (plugin, entry),
              bool(lines) and lines[0].strip() == '---')
        keys = []
        for line in lines[1:]:
            if line.strip() == '---':
                break
            match = re.match(r'^([a-z][a-z0-9_-]*):', line)
            if match:
                keys.append(match.group(1))
        check('%s:%s declares name and description' % (plugin, entry),
              'name' in keys and 'description' in keys, 'has %s' % keys)
        # The code-writing steps must guard on Status rather than on a flag.
        # Removing disable-model-invocation without that guard would let a
        # spontaneous invocation start building an unapproved plan, which is
        # exactly what the flag used to prevent by accident.
        if entry in ('2-build', '4-quorum'):
            body = open(path).read()
            check('%s:%s guards on the plan being authorized' % (plugin, entry),
                  'planned' in body and 'Status' in body,
                  'no Status check found in the procedure')

        unknown = [k for k in keys if k not in supported]
        check('%s:%s uses only supported frontmatter keys' % (plugin, entry),
              not unknown, 'unrecognised (silently ignored): %s' % unknown)


# ----------------------------------------------------------------- the history

def test_history():
    """The record of what a repository has been asked to do, read back.

    Everything here is derived from git and the artifacts, never from file
    mtimes — a checkout rewrites those, which is the same reason state.json
    exists. So the cases check provenance specifically: the right author on the
    right item, ordering by when a plan was actually committed, and an
    uncommitted plan reported as having no author rather than being given one.
    """
    repo = make_repo()
    try:
        def commit_as(name, email, when, message):
            env = {'GIT_AUTHOR_NAME': name, 'GIT_AUTHOR_EMAIL': email,
                   'GIT_AUTHOR_DATE': when, 'GIT_COMMITTER_NAME': name,
                   'GIT_COMMITTER_EMAIL': email, 'GIT_COMMITTER_DATE': when}
            merged = dict(os.environ)
            merged.update(env)
            subprocess.run(['git', 'add', '-A'], cwd=repo, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
            subprocess.run(['git', 'commit', '-q', '-m', message], cwd=repo, env=merged,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # an older item by someone else, committed before the demo plan
        write(repo, 'docs/work/older/plan.md',
              PLAN.replace('# Plan: demo', '# Plan: An earlier change'))
        commit_as('Ada Lovelace', 'ada@example.com', '2020-01-01T09:00:00+00:00',
                  'plan the earlier change\n\nCo-Authored-By: Some Agent <a@b.c>\n')

        # and one nobody has committed
        write(repo, 'docs/work/inflight/plan.md',
              PLAN.replace('# Plan: demo', '# Plan: Not committed yet'))

        code, out, err = run(['python3', HISTORY, '--json'], cwd=repo)
        check('history runs', code == 0, err.strip() or out.strip())
        try:
            items = json.loads(out)
        except ValueError:
            check('history emits JSON', False, out[:200])
            return

        by_slug = dict((i['slug'], i) for i in items)
        check('history lists every planned item',
              set(by_slug) == set(['demo', 'older', 'inflight']),
              'listed %s' % sorted(by_slug))

        check('history reads the plan title',
              by_slug.get('older', {}).get('title') == 'An earlier change',
              'got %r' % by_slug.get('older', {}).get('title'))
        check('history attributes an item to whoever committed its plan',
              by_slug.get('older', {}).get('author') == 'Ada Lovelace',
              'got %r' % by_slug.get('older', {}).get('author'))
        check('history reports co-authoring agents separately from the author',
              by_slug.get('older', {}).get('agents') == ['Some Agent'],
              'got %r' % by_slug.get('older', {}).get('agents'))
        check('history does not credit the wrong author',
              by_slug.get('demo', {}).get('author') == 'selftest',
              'got %r' % by_slug.get('demo', {}).get('author'))

        check('history marks an uncommitted plan as unattributed',
              by_slug.get('inflight', {}).get('committed') is False
              and not by_slug.get('inflight', {}).get('author'),
              'got %r' % by_slug.get('inflight'))

        committed = [i['slug'] for i in items if i['committed']]
        check('history orders by when the plan was committed, oldest first',
              committed == ['older', 'demo'], 'got %s' % committed)
        check('history sorts the uncommitted item last',
              items[-1]['slug'] == 'inflight', 'got %s' % [i['slug'] for i in items])

        # --- where to find the request ------------------------------------
        # recorded by the publisher
        write(repo, 'docs/work/shipped/plan.md',
              PLAN.replace('# Plan: demo', '# Plan: A shipped change'))
        run(['python3', STATE, 'docs/work/shipped',
             json.dumps({'stage': 'published', 'branch': 'feature/shipped',
                         'pr': {'url': 'https://github.com/o/r/pull/12', 'draft': True}})],
            cwd=repo)
        commit_as('Ada Lovelace', 'ada@example.com', '2021-01-01T09:00:00+00:00',
                  'plan a shipped change')

        # squash-merged: the number rides on the commit, the branch appears nowhere
        write(repo, 'docs/work/squashed/plan.md',
              PLAN.replace('# Plan: demo', '# Plan: A squash-merged change'))
        commit_as('Ada Lovelace', 'ada@example.com', '2021-02-01T09:00:00+00:00',
                  'A squash-merged change (#42)')

        # gitlab names it in the merge commit, which need not touch these files
        write(repo, 'docs/work/mr/plan.md',
              PLAN.replace('# Plan: demo', '# Plan: A merge-requested change')
                  + '\n- **Branch:** feature/mr\n')
        commit_as('Ada Lovelace', 'ada@example.com', '2021-03-01T09:00:00+00:00',
                  'plan a merge-requested change')
        write(repo, 'unrelated.txt', 'x\n')
        commit_as('Ada Lovelace', 'ada@example.com', '2021-03-02T09:00:00+00:00',
                  "Merge branch 'feature/mr'\n\nSee merge request grp/proj!7\n")

        code, out, _ = run(['python3', HISTORY, '--json'], cwd=repo)
        prs = dict((i['slug'], i['pr']) for i in json.loads(out))

        check('history reports a request recorded by the publisher',
              prs.get('shipped', {}).get('url') == 'https://github.com/o/r/pull/12'
              and prs['shipped']['source'] == 'state.json', 'got %r' % prs.get('shipped'))
        check('history carries the draft flag through',
              prs.get('shipped', {}).get('draft') is True, 'got %r' % prs.get('shipped'))
        check('history recovers a squash-merged request from the commit',
              prs.get('squashed', {}).get('ref') == '#42'
              and prs['squashed']['source'] == 'merge commit', 'got %r' % prs.get('squashed'))
        check('history recovers a GitLab merge request from the merge commit',
              prs.get('mr', {}).get('ref') == '!7', 'got %r' % prs.get('mr'))
        check('history claims no request when there is none',
              prs.get('older', {}).get('ref') == '', 'got %r' % prs.get('older'))

        code, out, _ = run(['python3', HISTORY], cwd=repo)
        check('the table shows the request column',
              code == 0 and '#42' in out and '!7' in out, out[:300])

        # --- elapsed, from the log's own stamps ----------------------------
        write(repo, 'docs/work/timed/plan.md',
              PLAN.replace('# Plan: demo', '# Plan: A timed change'))
        write(repo, 'docs/work/timed/state.json', json.dumps({
            'slug': 'timed', 'stage': 'published',
            'log': ['2026-01-01T09:00:00Z pipeline launched',
                    '2026-01-01T09:12:00Z panel complete, adjudication started',
                    '2026-01-01T09:41:00Z published'],
        }))
        commit_as('Ada Lovelace', 'ada@example.com', '2022-01-01T09:00:00+00:00',
                  'plan a timed change')

        code, out, _ = run(['python3', HISTORY, '--json'], cwd=repo)
        items = dict((i['slug'], i) for i in json.loads(out))
        check('history measures elapsed from the recorded stamps',
              items.get('timed', {}).get('elapsed', {}).get('seconds') == 41 * 60,
              'got %r' % items.get('timed', {}).get('elapsed'))
        check('history reports no duration when nothing was recorded',
              items.get('older', {}).get('elapsed', {}).get('seconds') is None,
              'got %r' % items.get('older', {}).get('elapsed'))

        code, out, _ = run(['python3', HISTORY], cwd=repo)
        check('the table shows how long it took', 'took 41m' in out, out[:400])

        code, out, _ = run(['python3', HISTORY, '--author', 'ada'], cwd=repo)
        check('history filters by author',
              code == 0 and 'An earlier change' in out and 'Plan: demo' not in out
              and 'demo' not in out.split('\n')[2] if len(out.split('\n')) > 2 else False,
              out[:200])

        # --- the prompt that produced the plan ----------------------------
        # Recorded verbatim or not at all. A prompt flattened into one line is a
        # different prompt, and one reconstructed from the Intent is not a
        # record — it reads as evidence and is not.
        write(repo, 'docs/work/asked/plan.md', PLAN.replace('# Plan: demo\n', '\n'.join([
            '# Plan: A change somebody asked for',
            '',
            '## Prompt',
            '',
            'make the widget retry',
            '',
            '- three times, not once',
            '- surface the last error',
            '',
        ])))
        commit_as('Ada Lovelace', 'ada@example.com', '2023-01-01T09:00:00+00:00',
                  'plan a change somebody asked for')

        code, out, _ = run(['python3', HISTORY, '--json'], cwd=repo)
        items = dict((i['slug'], i) for i in json.loads(out))
        check('history reads the prompt verbatim, keeping its line breaks',
              items.get('asked', {}).get('prompt', '').split('\n')
              == ['make the widget retry', '', '- three times, not once',
                  '- surface the last error'],
              'got %r' % items.get('asked', {}).get('prompt'))
        check('history records no prompt where the plan has no Prompt section',
              items.get('demo', {}).get('prompt') == '',
              'got %r' % items.get('demo', {}).get('prompt'))

        code, out, _ = run(['python3', HISTORY, '--markdown'], cwd=repo)
        check('markdown gives every item its own section',
              out.count('\n## ') == len(items),
              'got %d sections for %d items' % (out.count('\n## '), len(items)))
        check('markdown quotes the prompt as it was written',
              '> make the widget retry' in out and '> - three times, not once' in out,
              out[:600])
        check('markdown says so when no prompt was recorded',
              '*Not recorded.*' in out, out[:600])
        check('markdown never fabricates a prompt from the intent',
              '> Make the widget retry.' not in out, out[:600])
        check('markdown counts the items with no recorded prompt',
              'have no recorded prompt' in out, out[-400:])

        # A request that arrived as a quotation is not quoted a second time.
        write(repo, 'docs/work/quoted/plan.md', PLAN.replace('# Plan: demo\n', '\n'.join([
            '# Plan: A quoted prompt', '', '## Prompt', '', '> already a quote', ''])))
        commit_as('Ada Lovelace', 'ada@example.com', '2024-01-01T09:00:00+00:00',
                  'plan a quoted prompt')

        code, out, _ = run(['python3', HISTORY, '--markdown'], cwd=repo)
        check('markdown does not double-quote a prompt that is already a quotation',
              '> already a quote' in out and '> > already a quote' not in out,
              out[:800])

        code, out, _ = run(['python3', HISTORY], cwd=repo)
        check('the table carries no prompt, which is the reason --markdown exists',
              code == 0 and 'three times, not once' not in out, out[:400])
    finally:
        shutil.rmtree(repo, ignore_errors=True)


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


# ------------------------------------------------------- the criteria hash

CRITERIA = """# Audit criteria: demo

- **Slug:** demo
- **Spec:** `docs/spec.md`
- **Criteria hash:** %s

## Criteria

- [ ] **AC1** — when a request arrives with no bearer token, the API answers 401.
  - Source: "every endpoint requires a bearer token" — `docs/spec.md:14`

- [ ] **AC2** — a failed charge is retried three times.
  - Source: "retry three times" — *Retries*
"""

REPORT = """# Audit report: demo

- **Slug:** demo
- **Criteria hash:** %s

## Outcome

All clear
"""


def write_audit(work, criteria_body=None, recorded=None, cited=None):
    """An audit directory whose three hashes can each be moved independently."""
    path = os.path.join(work, 'criteria.md')
    body = CRITERIA if criteria_body is None else criteria_body
    with open(path, 'w') as handle:
        handle.write(body % (recorded if recorded is not None else 'PLACEHOLDER'))
    if recorded is None:
        code, out, _ = run(['python3', AUDIT, '--hash', path])
        with open(path, 'w') as handle:
            handle.write(body % out.strip())
    if cited is not None:
        with open(os.path.join(work, 'report.md'), 'w') as handle:
            handle.write(REPORT % cited)
    return path


def audit_hash(path):
    code, out, _ = run(['python3', AUDIT, '--hash', path])
    return out.strip() if code == 0 else None


def test_audit():
    """A softened criterion changes the hash, and verification says so.

    The gate is the only human decision in an audit, and it is spent on a list of
    criteria. If that list can be edited afterwards without anything noticing,
    the gate bought nothing — a report measured against quietly weakened criteria
    reads exactly like a report measured against the ones a human approved.
    """
    print('criteria hash')
    work = tempfile.mkdtemp(prefix='quorum-audit-')
    try:
        path = write_audit(work)
        original = audit_hash(path)
        check('--hash prints a sha256', bool(original) and len(original or '') == 64,
              'printed %r' % original)

        code, _, _ = run(['python3', AUDIT, '--verify', work])
        check('criteria alone verify clean', code == 0)

        # criteria_hash normalises three things away, and each gets its own
        # reformat here so a regression names the rule that broke rather than
        # reporting that the hash moved. Every variant is the same list of
        # criteria, worded identically — only the typography differs, and a user
        # who tidies the file after the gate must not be told to re-run the audit.
        reflows = {
            'trailing whitespace': lambda t: t.replace('answers 401.', 'answers 401.   '),
            'a ticked checkbox': lambda t: t.replace('- [ ] **AC2**', '- [x] **AC2**'),
            'a doubled blank line': lambda t: t.replace(
                '`docs/spec.md:14`\n\n', '`docs/spec.md:14`\n\n\n'),
        }
        for label, reflow in sorted(reflows.items()):
            body = reflow(CRITERIA)
            check('the %s reflow actually reformats the fixture' % label, body != CRITERIA,
                  'the variant is identical to the original, so it tests nothing')
            write_audit(work, criteria_body=body, recorded=original)
            check('%s does not change the hash' % label, audit_hash(path) == original,
                  'reflowed to %r' % audit_hash(path))
            code, _, _ = run(['python3', AUDIT, '--verify', work])
            check('a criteria file reflowed with %s still verifies' % label, code == 0)

        # Softened: "three times" becomes "at least once". Same criterion to
        # skim, a different thing to be measured against.
        softened = CRITERIA.replace('retried three times', 'retried at least once')
        write_audit(work, criteria_body=softened, recorded=original)
        weakened = audit_hash(path)
        check('a softened criterion changes the hash', weakened != original,
              'both hash to %s' % original)
        code, out, _ = run(['python3', AUDIT, '--verify', work])
        check('verification catches criteria edited after the gate', code == 1,
              'exit %s: %s' % (code, out.strip()))

        # A report citing the hash it was actually audited against.
        write_audit(work, cited=original)
        code, _, _ = run(['python3', AUDIT, '--verify', work])
        check('a report citing the current criteria verifies', code == 0)

        # ...and one citing a list that is no longer what criteria.md holds.
        write_audit(work, cited='0' * 64)
        code, out, _ = run(['python3', AUDIT, '--verify', work])
        check('verification catches a report measured against other criteria', code == 1,
              'exit %s: %s' % (code, out.strip()))
        code, out, _ = run(['python3', AUDIT, '--verify', work, '--json'])
        try:
            parsed = json.loads(out)
        except ValueError:
            parsed = {}
        check('--json reports the mismatch machine-readably',
              parsed.get('clean') is False and bool(parsed.get('violations')),
              'printed %r' % out.strip())

        # A report that cites no hash at all. This is what the scribe writes when
        # it is handed an empty criteriaHash, and "which criteria it measured is
        # unknowable" has to be a violation rather than a blank that reads clean.
        write_audit(work, cited=original)
        with open(os.path.join(work, 'report.md'), 'w') as handle:
            handle.write('# Audit report: demo\n\n- **Slug:** demo\n\n## Outcome\n\nAll clear\n')
        code, out, _ = run(['python3', AUDIT, '--verify', work])
        check('a report citing no criteria hash does not verify', code == 1,
              'exit %s: %s' % (code, out.strip()))

        # A missing report.md means two opposite things, and only the caller
        # knows which: a run that stopped at the gate, or a run that was meant to
        # write a report and did not. Clean by default, a violation on request.
        os.remove(os.path.join(work, 'report.md'))
        code, _, _ = run(['python3', AUDIT, '--verify', work])
        check('an audit stopped at the gate verifies clean', code == 0)
        code, out, _ = run(['python3', AUDIT, '--verify', work, '--expect-report'])
        check('a finished audit that wrote no report does not verify', code == 1,
              'exit %s: %s' % (code, out.strip()))

        # No hash recorded at all is a violation, not a pass by omission.
        with open(path, 'w') as handle:
            handle.write(re.sub(r'^- \*\*Criteria hash.*$', '', CRITERIA % '', flags=re.M))
        code, _, _ = run(['python3', AUDIT, '--verify', work])
        check('criteria with no recorded hash do not verify', code == 1)

        # Nothing to hash is a could-not-run, distinct from a mismatch.
        with open(path, 'w') as handle:
            handle.write('# Audit criteria: demo\n\nno criteria section here\n')
        code, _, _ = run(['python3', AUDIT, '--hash', path])
        check('a file with no criteria section cannot be hashed', code == 2)
        code, _, _ = run(['python3', AUDIT, '--verify', os.path.join(work, 'nope')])
        check('a missing audit directory is could-not-run, not clean', code == 2)

        # --check-slug. The slug is pasted into docs/audit/<slug>/ and written to
        # before audit.js — which validates its own copy — ever runs, so this is
        # the only thing standing between a slug carrying ".." and a file written
        # outside the working tree, where the skill's own `git status` check
        # cannot see it. It had no coverage at all: replacing the pattern with
        # `.*` left the suite green.
        for good in ['widget-api', 'billing', 'a1', 'two-three-four']:
            code, _, err = run(['python3', AUDIT, '--check-slug', good])
            check('slug %r is accepted' % good, code == 0, 'exit %s: %s' % (code, err.strip()))

        # Each of these is a different way to leave the audit directory or to
        # produce a path nothing downstream can handle, and each is named so a
        # regression says which one stopped being caught.
        bad = {
            'parent directory': '..',
            'a traversal': '../../etc',
            'a nested path': 'a/b',
            'an absolute path': '/etc',
            'uppercase': 'Foo',
            'a leading hyphen': '-x',
            'a trailing hyphen': 'x-',
            'a doubled hyphen': 'a--b',
            'the empty string': '',
            'a space': 'two words',
            'a dollar substitution': '$(printf INJECTED)',
            'a backtick substitution': '`printf INJECTED`',
        }
        for label, slug in sorted(bad.items()):
            code, _, _ = run(['python3', AUDIT, '--check-slug', slug])
            check('slug rejected: %s' % label, code == 2, 'exit %s on %r' % (code, slug))

        # Python's `$` also matches immediately before a trailing newline and
        # JavaScript's does not, so `match()` here blessed a slug audit.js would
        # reject afterwards — after criteria.md was written and the gate spent.
        # fullmatch() is what keeps the two validators agreeing.
        code, _, _ = run(['python3', AUDIT, '--check-slug', 'ok\n'])
        check('a trailing newline is rejected, as audit.js rejects it', code == 2)

        # The skill passes the slug on stdin behind a quoted heredoc, because a
        # slug interpolated into a shell word is expanded by bash before audit.py
        # sees it. One trailing newline is the delimiter's and is stripped; a
        # second one is not.
        code, _, err = run(['python3', AUDIT, '--check-slug', '-'], stdin=b'widget-api\n')
        check('a slug on stdin is accepted', code == 0, 'exit %s: %s' % (code, err.strip()))
        code, _, _ = run(['python3', AUDIT, '--check-slug', '-'], stdin=b'../../etc\n')
        check('a traversal on stdin is rejected', code == 2)
        code, _, _ = run(['python3', AUDIT, '--check-slug', '-'], stdin=b'widget-api\n\n')
        check('only the delimiter newline is stripped from stdin', code == 2)

        # --check-slug-file is the form the skill actually uses, and the reason it
        # exists is that both earlier forms were defeated by the same class of
        # attack: untrusted repository bytes reaching bash before audit.py runs.
        # A quoted heredoc ended at the first line equal to its delimiter, so a
        # candidate carrying that word on its own line closed the heredoc and the
        # rest was parsed as shell. Trimming to the first line would have hidden
        # exactly that, which is why an embedded newline is a rejection and not a
        # trim.
        candidate = os.path.join(work, 'cand')

        def check_slug_file(raw):
            with open(candidate, 'wb') as handle:
                handle.write(raw)
            return run(['python3', AUDIT, '--check-slug-file', candidate])[0]

        check('a slug in a file is accepted', check_slug_file(b'widget-api\n') == 0)
        check('one trailing newline is tolerated in a slug file',
              check_slug_file(b'widget-api') == 0)
        check('a traversal in a slug file is rejected',
              check_slug_file(b'../../etc\n') == 2)
        check('a heredoc-delimiter collision payload is rejected, not truncated',
              check_slug_file(b'widget-api\nSLUG\ntouch INJECTED\n') == 2,
              'a multi-line candidate must fail rather than validate its first line')
        check('command substitution in a slug file is rejected',
              check_slug_file(b'a$(id)b\n') == 2)
        check('a backtick payload in a slug file is rejected',
              check_slug_file(b'a`id`b\n') == 2)
        check('a missing slug file is an error, not a pass',
              run(['python3', AUDIT, '--check-slug-file',
                   os.path.join(work, 'nope')])[0] == 2)
        os.remove(candidate)

        # The skill is instructed to use the file form and never a shell word.
        # If that instruction reverts to interpolating the slug, this fires.
        with open(os.path.join(PLUGIN, 'skills', 'audit', 'SKILL.md')) as handle:
            skill = handle.read()
        check('the audit skill checks the slug from a file, not the shell',
              '--check-slug-file' in skill and "--check-slug -" not in skill,
              'a slug in a shell word or heredoc reaches bash before audit.py')

        # Rejection must write nothing. The whole point of running this before
        # criteria.md is that a bad slug costs the target repository nothing.
        before = sorted(os.listdir(work))
        run(['python3', AUDIT, '--check-slug', '../../etc'], cwd=work)
        check('a rejected slug writes nothing', sorted(os.listdir(work)) == before)
    finally:
        shutil.rmtree(work, ignore_errors=True)


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


def frontmatter_tools(path):
    """The declared `tools:` list, or None when it cannot be read as a grant.

    None is not "no tools" — it is *every* tool, inherited. The two are
    opposites, and this check exists precisely to catch a grant it must not
    mistake for an absence, so everything ambiguous returns None and fails loudly
    rather than passing quietly.

    Both YAML spellings of the field mean the same thing to the runtime and must
    mean the same thing here, or the guarantee is defeated by a reformat:

        tools: Read, Grep, Write          # inline scalar
        tools: "Read, Grep, Write"        # quoted scalar
        tools: [Read, Grep, Write]        # flow sequence
        tools:                            # block sequence
          - Read
          - Write

    Quotes are stripped for the same reason. A `tools:` field present but
    yielding no names is returned as None: an unreadable grant is treated as
    every tool, never as none.
    """
    with open(path) as handle:
        lines = handle.read().split('\n')
    if not lines or lines[0].strip() != '---':
        return None

    found, parts = False, []
    for line in lines[1:]:
        if line.strip() == '---':
            break
        if found:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith('-'):
                parts.append(stripped[1:])
                continue
            break  # the next key ends the block sequence
        if line.startswith('tools:'):
            found = True
            parts.extend(line.split(':', 1)[1].strip().strip('[]').split(','))
    if not found:
        return None

    names = [part.strip().strip('\'"').strip() for part in parts]
    names = [name for name in names if name]
    return names or None


def test_agent_tools():
    """The read-only guard reads every YAML spelling of `tools:` the same way.

    The guard that keeps /quorum:audit safe on a default branch is a comparison
    against a parsed tool list, so the parser *is* the guarantee. It used to read
    only the inline comma form: a block sequence yielded [], a quoted scalar
    yielded names with quotes still attached, and in both cases `Write` failed to
    match WRITE_TOOLS and the check reported PASS on an agent that really could
    edit the repository it was auditing. The guarantee was defeated by a reformat,
    which is the quietest way a check can stop meaning anything.

    So each spelling is asserted to parse to the same grant, and an unreadable
    grant is asserted to come back None — inherit-everything — so the caller
    fails closed.
    """
    print('agent tool grants')
    work = tempfile.mkdtemp(prefix='quorum-tools-')
    try:
        def parse(text):
            path = os.path.join(work, 'agent.md')
            with open(path, 'w') as handle:
                handle.write(text)
            return frontmatter_tools(path)

        want = ['Read', 'Grep', 'Write']
        spellings = {
            'inline': 'tools: Read, Grep, Write',
            'quoted': 'tools: "Read, Grep, Write"',
            'single-quoted': "tools: 'Read, Grep, Write'",
            'flow sequence': 'tools: [Read, Grep, Write]',
            'quoted flow sequence': 'tools: ["Read", "Grep", "Write"]',
            'block sequence': 'tools:\n  - Read\n  - Grep\n  - Write',
        }
        for label, field in sorted(spellings.items()):
            tools = parse('---\nname: probe\n%s\n---\n\nbody\n' % field)
            check('a %s tools: field parses to the grant it makes' % label,
                  tools == want, 'parsed to %r' % (tools,))
            writes = sorted(t for t in (tools or []) if t in WRITE_TOOLS)
            check('a %s tools: field exposes its write tool' % label,
                  writes == ['Write'], 'writes %r' % (writes,))

        # A key after the block sequence ends it — a description holding a dash
        # must not be swept up as another tool.
        tools = parse('---\nname: probe\ntools:\n  - Read\n'
                      'description: reads things - and nothing else\n---\n\nbody\n')
        check('a key after a block sequence ends it', tools == ['Read'],
              'parsed to %r' % (tools,))

        # None means "inherits everything", and every unreadable grant must land
        # there rather than on the empty list, which reads as "grants nothing".
        check('no tools: field at all is inherit-everything',
              parse('---\nname: probe\n---\n\nbody\n') is None)
        check('an empty tools: field is inherit-everything, not a grant of nothing',
              parse('---\nname: probe\ntools:\n---\n\nbody\n') is None)
        check('a tools: field of only separators is inherit-everything',
              parse('---\nname: probe\ntools: [ , ]\n---\n\nbody\n') is None)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def test_agents():
    """Every workflow script names agents that exist, the way they register.

    Nothing else covers the workflow scripts. The guard checks what the pipeline
    produces, not the script that runs it, so a wrong agentType stays invisible
    until a run reaches the first agent() call — which is after the approval
    gate, on work that then cannot start.

    Plugin agents register namespaced, <plugin>:<agent>. That prefix has twice
    been dropped from pipeline.js and hand-patched back into the installed plugin
    cache, where the next `claude plugin update` throws it away. Three files have
    to agree and all three are in the repo, so nothing here needs a model or a
    live run.

    Every script under workflow/ is scanned, not just pipeline.js — a second
    orchestrator that nothing checks is the same failure waiting a second time.
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

    scripts = sorted(e for e in os.listdir(WORKFLOW_DIR) if e.endswith('.js'))
    check('workflow/ holds scripts to check', bool(scripts))

    used_by = {}
    for entry in scripts:
        with open(os.path.join(WORKFLOW_DIR, entry)) as handle:
            source = handle.read()
        # The trailing delimiter matters: it means a literal and nothing else. Any
        # concatenation or lookup fails to match and shows up as a count mismatch
        # below, rather than half-matching and quietly narrowing what is checked.
        refs = re.findall(r"agentType:\s*'([^']*)'\s*[,}\n]", source)
        used_by[entry] = refs

        # A computed agentType would slip past the regex and take the whole check
        # with it, silently. Every site must be a plain literal for this to mean
        # anything.
        check('every agentType in %s is a plain string literal' % entry,
              len(refs) == source.count('agentType:'),
              '%d agentType keys, %d literals — a computed name escapes this check'
              % (source.count('agentType:'), len(refs)))
        check('%s calls agents at all' % entry, bool(refs))

    registered = set('%s:%s' % (plugin, name) for name in declared)
    for entry in scripts:
        for ref in sorted(set(used_by[entry])):
            check('%s agentType %r resolves' % (entry, ref), ref in registered,
                  'nothing registers under that name; expected one of %s' % sorted(registered))

    everywhere = set()
    for refs in used_by.values():
        everywhere.update(refs)
    for name in sorted(declared):
        check('agent %s is wired into a workflow' % name,
              '%s:%s' % (plugin, name) in everywhere,
              '%s defines it, no script under workflow/ ever calls it' % declared[name])

    # workflow/audit.js runs against a repository that never asked for this
    # pipeline, on its default branch. Two properties make that safe, and both are
    # settled here rather than promised in prose: no agent it names is granted a
    # file-editing tool, and no agent it names is granted a shell. The second one
    # is what closes the door — a shell can edit, commit, push, and run a test
    # suite, so without it the first check is only a floor.
    #
    # The audited repository is untrusted input. An agent reading a README that
    # carries instructions aimed at it cannot act on them if the tools are not
    # there, which is the difference between this and asking it not to.
    for entry in sorted(READ_ONLY_WORKFLOWS):
        check('%s exists to be checked' % entry,
              os.path.exists(os.path.join(WORKFLOW_DIR, entry)),
              'the read-only guarantee is asserted over a script that is not there')
        for ref in sorted(set(used_by.get(entry, []))):
            name = ref.split(':', 1)[-1]
            if name not in declared:
                continue  # the resolve check above already failed on this one
            tools = frontmatter_tools(os.path.join(AGENTS_DIR, declared[name]))
            if tools is None:
                check('%s: %s declares its tools readably' % (entry, name), False,
                      'no tools: field, or one that yields no names — either way it must be '
                      'read as inheriting every tool, file editing included')
                continue
            writes = sorted(t for t in tools if t in WRITE_TOOLS)
            reads = sorted(t for t in tools if t in READ_TOOLS)
            execs = sorted(t for t in tools if t in EXEC_TOOLS)
            check('%s: %s cannot execute the audited repository' % (entry, name),
                  not execs,
                  'grants %s — a shell can edit a file, commit, push, and run the test '
                  'suite, which defeats every prose rule in the prompts at once' % execs)

            # The positive half. The three checks around it ask "is this tool one
            # of the bad ones"; this one asks "is this tool one of the ones we
            # meant", which is the only form that survives a spelling nobody
            # anticipated — a scoped shell, an MCP tool, a tool invented after
            # this line was written.
            allowed = AUDIT_WRITE_ONLY_TOOLS if name in WRITE_ONLY_EXEMPT else AUDIT_READ_TOOLS
            extra = sorted(t for t in tools if t not in allowed)
            check('%s: %s grants only %s' % (entry, name, ', '.join(allowed)),
                  not extra,
                  'also grants %s — an agent audit.js names may hold only the allowlist, '
                  'because a denylist cannot see a scoped shell such as Bash(git log:*) '
                  'or an MCP tool that writes' % extra)

            if name in WRITE_ONLY_EXEMPT:
                # The exemption is itself checked, so it cannot be widened by
                # quietly granting the scribe a way to read what it overwrites.
                check('%s: %s is write-only, as its exemption requires' % (entry, name),
                      bool(writes) and not reads,
                      'grants %s — an agent that can read the audited repository may not write' % tools)
                continue
            check('%s: %s grants no file-editing tool' % (entry, name),
                  not writes, 'grants %s' % writes)


def main():
    code, _, _ = run(['git', '--version'])
    if code != 0:
        sys.stderr.write('selftest: git is required\n')
        return 2

    test_guard()
    test_default_branch()
    test_hook()
    test_state()
    test_audit()
    test_agent_tools()
    test_agents()
    test_lifetime()
    test_version()
    test_frontmatter()
    test_history()
    test_install_ci()
    test_watch()

    failed = [r for r in results if not r[1]]
    print('')
    print('%d/%d passed' % (len(results) - len(failed), len(results)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
