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
import sys
import time

TERMINAL = ('published',)


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

    if now['ticked'] != before['ticked'] and now['steps']:
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

    state = snapshot(opts.work_dir)
    start = state.copy()
    start.update({'ticked': -1, 'reviews': [], 'stage': '', 'last': '',
                  'verdict': False})
    for line in differences(start, state):
        print(line)
        sys.stdout.flush()

    if opts.once or state['stage'] in TERMINAL:
        return 0

    deadline = time.time() + opts.max_seconds
    while time.time() < deadline:
        time.sleep(opts.interval)
        now = snapshot(opts.work_dir)
        for line in differences(state, now):
            print(line)
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
