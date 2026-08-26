#!/usr/bin/env python3
"""Emit a line whenever a running work item visibly moves.

`/quorum:pipeline` runs detached: it returns a run id and the session goes quiet
until the whole thing finishes. The workflow's own progress tree lives behind
`/workflows`, which you have to go and look at. This is the other half — one line
per observable change, so a long run reports into the conversation as it goes.

Everything it watches is a file the pipeline already writes, in your repository:

  plan.md      steps ticked by the builder, as it ticks them
  reviews/     one file per lens, appearing when the panel is transcribed
  state.json   the stage, and the newest log line

Deliberately NOT the workflow's internal state file. That exists, and it records
more, and it lives in Claude Code's private directory under a path that is free to
change at any release — a progress watcher that silently stops working after an
update is worse than one that never existed, because silence reads as "nothing has
happened yet".

The blind spot is honest and unavoidable: the review phase writes nothing until
every lens is done, so this reports the panel starting and finishing and nothing
between. Six agents reading in parallel leave no trace in the repository.

    watch.py docs/work/<slug> [--interval 20] [--max-seconds 7200]

Exits 0 when the item reaches a terminal stage, or when --max-seconds runs out.
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime

TERMINAL = ('published',)


STEP = re.compile(r'^-\s*\[([ xX])\]\s*(S\d+)\s*:\s*(.+?)\s*$', re.M)


def parse_steps(plan):
    """The plan's Steps list: which ones exist, and which are done.

    Named steps beat a bare count. "4/9 ticked" says how far along a build is;
    "S4 done - build the page" says what it just finished, which is the thing
    somebody watching actually wants to know.
    """
    out = []
    for mark, ident, title in STEP.findall(plan):
        out.append({'id': ident, 'title': title, 'done': mark.lower() == 'x'})
    return out


def short(title, width=58):
    title = title.rstrip(' -\u2014,;')
    return title if len(title) <= width else title[:width - 1].rstrip() + '\u2026'


def stamps(state):
    """The timestamps state.py wrote, oldest first."""
    log = state.get('log')
    if not isinstance(log, list):
        return []
    out = []
    for line in log:
        head = str(line).split(' ', 1)[0]
        try:
            out.append(datetime.strptime(head, '%Y-%m-%dT%H:%M:%SZ'))
        except ValueError:
            continue
    return out


def completed_runs(work_root):
    """How long every finished work item in this repo took, in seconds.

    The only defensible basis for an estimate. Not a model, not an average of
    somebody else's runs — what this repository has actually done before.
    """
    totals = []
    try:
        slugs = sorted(os.listdir(work_root))
    except (IOError, OSError):
        return totals
    for slug in slugs:
        raw = read(os.path.join(work_root, slug, 'state.json'))
        if not raw:
            continue
        try:
            state = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(state, dict) or state.get('stage') not in TERMINAL:
            continue
        marks = stamps(state)
        if len(marks) >= 2:
            totals.append(int((marks[-1] - marks[0]).total_seconds()))
    return sorted(totals)


def estimate(elapsed, totals):
    """Minutes remaining, or an honest refusal.

    Refuses below two completed runs rather than extrapolating from one. A single
    data point is not a distribution, and a confident number drawn from it is the
    kind of claim this pipeline exists to distrust.
    """
    if len(totals) < 2:
        return 'no completed runs to compare against yet (%d recorded), so no estimate' % len(totals)

    median = totals[len(totals) // 2]
    low, high = totals[0], totals[-1]
    span = 'previous %d runs took %s\u2013%s (median %s)' % (
        len(totals), minutes(low), minutes(high), minutes(median))

    if elapsed > high:
        return '%s \u00b7 already longer than any of them, so no estimate stands'  % span
    remaining = median - elapsed
    if remaining <= 0:
        return '%s \u00b7 past the median, somewhere in the tail' % span
    return '%s \u00b7 roughly %s left if this one is typical' % (span, minutes(remaining))


def minutes(seconds):
    if seconds < 90:
        return '%ds' % seconds
    if seconds < 5400:
        return '%dm' % round(seconds / 60.0)
    return '%.1fh' % (seconds / 3600.0)


def read(path):
    try:
        with open(path) as handle:
            return handle.read()
    except (IOError, OSError):
        return ''


def snapshot(work_dir):
    plan = read(os.path.join(work_dir, 'plan.md'))
    done = plan.count('- [x]') + plan.count('- [X]')
    total = done + plan.count('- [ ]')

    reviews_dir = os.path.join(work_dir, 'reviews')
    try:
        reviews = sorted(f for f in os.listdir(reviews_dir) if f.endswith('.md'))
    except (IOError, OSError):
        reviews = []

    state = {}
    raw = read(os.path.join(work_dir, 'state.json'))
    if raw:
        try:
            loaded = json.loads(raw)
            state = loaded if isinstance(loaded, dict) else {}
        except ValueError:
            state = {}

    log = state.get('log')
    last = log[-1] if isinstance(log, list) and log else ''

    return {
        'raw': state,
        'steps_list': parse_steps(plan),
        'ticked': done,
        'steps': total,
        'reviews': reviews,
        'stage': state.get('stage', ''),
        'last': last,
        'verdict': os.path.exists(os.path.join(work_dir, 'verdict.md')),
    }


def differences(before, now):
    """One line per thing that actually changed. Nothing when nothing did."""
    lines = []

    if now['stage'] and now['stage'] != before['stage']:
        lines.append('stage: %s' % now['stage'])

    # Name what finished. Falls back to a count only when the plan does not use
    # the S<n> convention, since a number is better than silence.
    was_done = set(s['id'] for s in before.get('steps_list', []) if s['done'])
    now_list = now.get('steps_list', [])
    total = len(now_list)
    fresh = [s for s in now_list if s['done'] and s['id'] not in was_done]
    if fresh:
        done_count = sum(1 for s in now_list if s['done'])
        for step in fresh:
            lines.append('%s done (%d/%d) %s'
                         % (step['id'], done_count, total, short(step['title'])))
    elif not now_list and now['ticked'] != before['ticked'] and now['steps']:
        lines.append('build: %d/%d steps ticked' % (now['ticked'], now['steps']))

    fresh = [r for r in now['reviews'] if r not in before['reviews']]
    if fresh:
        lines.append('reviews recorded: %s' % ', '.join(fresh))

    if now['verdict'] and not before['verdict']:
        lines.append('verdict.md written')

    # The log carries what the stage alone cannot — a red suite, a judge pass, a
    # PR url. Report a new entry even when nothing else moved.
    if now['last'] and now['last'] != before['last']:
        entry = now['last'].split(' ', 1)
        lines.append('log: %s' % (entry[1] if len(entry) == 2 else now['last']))

    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('work_dir')
    parser.add_argument('--interval', type=float, default=20.0)
    parser.add_argument('--max-seconds', type=float, default=7200.0)
    parser.add_argument('--once', action='store_true',
                        help='report the current state and exit; for testing')
    opts = parser.parse_args()

    if not os.path.isdir(opts.work_dir):
        sys.stderr.write('watch.py: no work item at %s\n' % opts.work_dir)
        return 2

    work_root = os.path.dirname(os.path.normpath(opts.work_dir))
    totals = completed_runs(work_root)

    def progress_line(now):
        marks = stamps(now.get('raw', {}))
        if not marks:
            return ''
        elapsed = int((datetime.utcnow() - marks[0]).total_seconds())
        if elapsed < 0:
            return ''
        return 'elapsed %s \u00b7 %s' % (minutes(elapsed), estimate(elapsed, totals))

    state = snapshot(opts.work_dir)
    start = state.copy()
    start.update({'ticked': -1, 'reviews': [], 'stage': '', 'last': '',
                  'verdict': False})
    for line in differences(start, state):
        print(line)
    roster = [s for s in state.get('steps_list', []) if not s['done']]
    if roster:
        print('%d step(s) left:' % len(roster))
        for step in roster:
            print('  %s %s' % (step['id'], short(step['title'])))
    hint = progress_line(state)
    if hint:
        print(hint)
    sys.stdout.flush()

    if opts.once or state['stage'] in TERMINAL:
        return 0

    deadline = time.time() + opts.max_seconds
    while time.time() < deadline:
        time.sleep(opts.interval)
        now = snapshot(opts.work_dir)
        moved = differences(state, now)
        if moved:
            for line in moved:
                print(line)
            hint = progress_line(now)
            if hint:
                print(hint)
            sys.stdout.flush()
        state = now
        if state['stage'] in TERMINAL:
            return 0

    print('still running after %d minutes; watcher stopping, the run has not'
          % int(opts.max_seconds / 60))
    sys.stdout.flush()
    return 0


if __name__ == '__main__':
    sys.exit(main())
