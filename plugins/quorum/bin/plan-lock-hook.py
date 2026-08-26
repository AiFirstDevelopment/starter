#!/usr/bin/env python3
"""Refuse tool edits that would change a plan's requirements.

The pipeline tells every agent not to touch Intent, Acceptance criteria, or
Non-goals. This makes it so. It runs as a PreToolUse hook, before the write
lands, and it is the one rule in the system that does not depend on an agent
choosing to honour it.

Allowed: everything else in the plan — ticking checkboxes, Build notes,
Approach, Steps. Blocked: any change to the wording of the requirements.

Fails open. A hook that breaks must not wedge every edit in the repo.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ALLOW = 0
BLOCK = 2

PLAN = re.compile(r'(^|/)docs/work/[^/]+/plan\.md$')


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return ALLOW

    tool = payload.get('tool_name') or ''
    data = payload.get('tool_input') or {}
    path = data.get('file_path') or ''

    if not path or not PLAN.search(path.replace(os.sep, '/')):
        return ALLOW
    if not os.path.exists(path):
        return ALLOW                      # 1-plan creating it for the first time

    try:
        from guard import requirements_hash
        with open(path) as handle:
            before = handle.read()
        after = project(tool, data, before)
    except Exception:
        return ALLOW

    if after is None:
        return ALLOW

    try:
        if requirements_hash(before) == requirements_hash(after):
            return ALLOW
    except Exception:
        return ALLOW

    sys.stderr.write(
        'Blocked: this edit changes Intent, Acceptance criteria, or Non-goals in\n'
        '%s.\n\n'
        'Those are the requirements every later step is measured against, and only\n'
        'the user may change them. If the plan is genuinely wrong, say so and stop —\n'
        'record it under Build notes as a PLAN DEFECT, or escalate it in the verdict.\n'
        'Do not move the target you are being measured against.\n\n'
        'Editing any other part of the plan, including ticking checkboxes, is fine.\n'
        % path
    )
    return BLOCK


def project(tool, data, before):
    """What the file would contain if this call went through."""
    if tool == 'Write':
        return data.get('content')

    if tool == 'Edit':
        old, new = data.get('old_string'), data.get('new_string')
        if old is None or new is None:
            return None
        if data.get('replace_all'):
            return before.replace(old, new)
        return before.replace(old, new, 1)

    if tool == 'MultiEdit':
        text = before
        for edit in data.get('edits') or []:
            old, new = edit.get('old_string'), edit.get('new_string')
            if old is None or new is None:
                return None
            text = text.replace(old, new) if edit.get('replace_all') else text.replace(old, new, 1)
        return text

    return None


if __name__ == '__main__':
    sys.exit(main())
