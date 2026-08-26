#!/usr/bin/env python3
"""Merge a terse patch into a quorum work item's state.json.

    state.py docs/work/<slug> '{"stage":"built","build":{"stepsDone":6},"log":"built 6/6"}'

The patch is deep-merged into whatever is already on disk, so each step records
only its own section and leaves the rest alone. Three keys are handled specially:

  log      a string, appended as one timestamped line (newest last, capped)
  updated  always set from the clock; never pass it yourself
  null     any key whose patch value is null is removed

Prints the merged state so the caller can see what was recorded.
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone

STAGES = ['planned', 'approved', 'building', 'built', 'reviewed', 'adjudicated', 'published']
KEY_ORDER = ['slug', 'branch', 'stage', 'updated', 'plan', 'build', 'review', 'verdict', 'pr', 'log']
LOG_LINES = 12


def die(msg):
    sys.stderr.write('state.py: ' + msg + '\n')
    sys.exit(1)


def merge(base, patch):
    for key, value in patch.items():
        if value is None:
            base.pop(key, None)
        elif isinstance(value, dict) and isinstance(base.get(key), dict):
            merge(base[key], value)
        else:
            base[key] = value
    return base


def ordered(state):
    out = {}
    for key in KEY_ORDER:
        if key in state:
            out[key] = state[key]
    for key in state:
        if key not in out:
            out[key] = state[key]
    return out


def main():
    if len(sys.argv) != 3:
        die('usage: state.py <work-dir> <json-patch>')

    work_dir, raw = sys.argv[1], sys.argv[2]
    path = os.path.join(work_dir, 'state.json')

    try:
        patch = json.loads(raw)
    except ValueError as exc:
        die('patch is not valid JSON: %s' % exc)
    if not isinstance(patch, dict):
        die('patch must be a JSON object')

    stage = patch.get('stage')
    if stage is not None and stage not in STAGES:
        die('unknown stage %r; expected one of %s' % (stage, ', '.join(STAGES)))

    state = {}
    if os.path.exists(path):
        try:
            with open(path) as handle:
                state = json.load(handle)
            if not isinstance(state, dict):
                raise ValueError('top level is not an object')
        except ValueError as exc:
            # The artifacts are the record; a corrupt index is rebuilt, not mourned.
            sys.stderr.write('state.py: %s was unreadable (%s); starting fresh\n' % (path, exc))
            state = {}

    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    entry = patch.pop('log', None)

    merge(state, patch)
    state['updated'] = now
    state.setdefault('slug', os.path.basename(os.path.normpath(work_dir)))

    if entry:
        log = state.get('log')
        if not isinstance(log, list):
            log = []
        log.append('%s %s' % (now, entry))
        state['log'] = log[-LOG_LINES:]

    if not os.path.isdir(work_dir):
        os.makedirs(work_dir)

    handle = tempfile.NamedTemporaryFile(
        mode='w', dir=work_dir, prefix='.state-', suffix='.json', delete=False
    )
    try:
        json.dump(ordered(state), handle, indent=2)
        handle.write('\n')
        handle.close()
        os.replace(handle.name, path)
    except Exception:
        os.unlink(handle.name)
        raise

    print(json.dumps(ordered(state), indent=2))


if __name__ == '__main__':
    main()
