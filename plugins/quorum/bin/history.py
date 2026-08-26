#!/usr/bin/env python3
"""Every work item this repository has planned, oldest first.

`docs/work/` accumulates one directory per change and never loses one, so it is
already a record of what this repository has been asked to do. This reads it back.

Where the facts come from, and why not from somewhere easier:

  title, intent   the plan's own heading and Intent section
  planned, who    the commit that ADDED plan.md — author name, email, date
  agent           Co-Authored-By trailers on that commit
  status          plan.md's Status, and state.json's stage where it exists
  pull request    state.json's pr object, or the merge commit that referenced the
                  branch — GitHub "(#12)" and "Merge pull request #12", GitLab
                  "See merge request group/proj!12"
  last touched    the newest commit against the work item's directory

Authorship comes from git rather than from the artifacts because the artifacts do
not record it: no plan says who asked for it. Note what that means in this
pipeline — commits are made under whatever git config was active, so the author is
the repository's owner whether a human or an agent did the work. The Co-Authored-By
trailer is what distinguishes them, and it is reported separately for that reason.

Timestamps are git author dates. Deliberately NOT file mtimes: a checkout rewrites
those, which is the same reason state.json exists at all.

Usage:
  history.py [--json] [--full] [--author NAME] [--limit N]

Exit: 0 fine, 2 could not run.
"""

import argparse
import json
import os
import re
import subprocess
import sys

WORK_ROOT = os.path.join('docs', 'work')
TITLE = re.compile(r'^#\s+Plan:\s*(.+?)\s*$', re.M)
STATUS = re.compile(r'^-\s+\*\*Status:\*\*\s*(.+?)\s*$', re.M)
COAUTHOR = re.compile(r'^Co-Authored-By:\s*(.+?)\s*<', re.M | re.I)
BRANCH = re.compile(r'^-\s+\*\*Branch:\*\*\s*(.+?)\s*$', re.M)

# How the hosts name a merged change in the commit they leave behind.
PR_PATTERNS = (
    re.compile(r'Merge pull request #(\d+)'),
    re.compile(r'See merge request\s+\S*!(\d+)'),
    # anchored to end-of-line, so the log format must put the subject on its own
    # line; a separator glued to the subject silently defeats this.
    re.compile(r'\(#(\d+)\)\s*$', re.M),
)


def git(*args):
    try:
        out = subprocess.check_output(('git',) + args, stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, OSError):
        return None
    return out.decode('utf-8', 'replace')


def section(text, heading):
    """The first paragraph under a '## <heading>' section, or ''."""
    match = re.search(r'^##\s+' + re.escape(heading) + r'\s*$', text, re.M)
    if not match:
        return ''
    rest = text[match.end():].lstrip('\n')
    para = []
    for line in rest.split('\n'):
        if line.startswith('#'):
            break
        if not line.strip():
            if para:
                break
            continue
        para.append(line.strip())
    return ' '.join(para)


def origin(plan_path):
    """The commit that first added this plan: date, author, email, agents.

    Reported as unknown rather than guessed when the plan is not committed yet.
    An uncommitted plan has no author on record, and a file mtime is not one —
    it says when this checkout wrote the file, not who planned the work.
    """
    out = git('log', '--diff-filter=A', '--format=%aI%x00%an%x00%ae%x00%H', '--', plan_path)
    if not out or not out.strip():
        return {'date': '', 'author': '', 'email': '', 'agents': [], 'committed': False}
    # newest first, so the earliest add is the last line
    date, author, email, sha = out.strip().split('\n')[-1].split('\x00')
    body = git('log', '-1', '--format=%b', sha) or ''
    return {
        'date': date,
        'author': author,
        'email': email,
        'agents': sorted(set(COAUTHOR.findall(body))),
        'committed': True,
    }


def find_pr(state, branch, work_dir):
    """Where to find the pull or merge request for this work item.

    state.json is the record when the publisher wrote one. Older work items
    predate it and a change merged by hand never had one, so fall back to what
    the host left in the history. Two places, because neither alone is enough:

      the commits carrying this work item — a squash merge collapses the branch
      into one commit that includes docs/work/<slug>/ and carries "(#12)", and
      the branch name appears nowhere in it

      the whole log, grepped for the branch — a real merge commit says "Merge
      pull request #12 from owner/<branch>", and GitLab writes "See merge
      request grp/proj!12", neither of which need touch the work item's files

    A reference found this way is inferred, not recorded, so `source` says which
    it was. It can be wrong: any commit touching this work item that ends in
    "(#12)" will match, and that may be a later fix rather than the change itself.
    """
    pr = state.get('pr') or {}
    if pr.get('url'):
        return {'ref': pr.get('url'), 'url': pr.get('url'),
                'draft': bool(pr.get('draft')), 'source': 'state.json'}

    haystacks = [git('log', '--format=%s%n%b%n', '--', work_dir)]
    if branch:
        haystacks.append(
            git('log', '--format=%s%n%b%n', '--fixed-strings', '--grep', branch))

    for hay in haystacks:
        if not hay:
            continue
        for pattern in PR_PATTERNS:
            match = pattern.search(hay)
            if match:
                sigil = '!' if 'merge request' in pattern.pattern else '#'
                return {'ref': sigil + match.group(1), 'url': '',
                        'draft': False, 'source': 'merge commit'}
    return {'ref': '', 'url': '', 'draft': False, 'source': ''}


def last_touched(work_dir):
    out = git('log', '-1', '--format=%aI%x00%an', '--', work_dir)
    if not out or not out.strip():
        return {'date': '', 'author': ''}
    date, author = out.strip().split('\x00')
    return {'date': date, 'author': author}


def read_state(work_dir):
    path = os.path.join(work_dir, 'state.json')
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as handle:
            loaded = json.load(handle)
        return loaded if isinstance(loaded, dict) else {}
    except (ValueError, IOError, OSError):
        return {}


def collect():
    if not os.path.isdir(WORK_ROOT):
        return []

    items = []
    for slug in sorted(os.listdir(WORK_ROOT)):
        work_dir = os.path.join(WORK_ROOT, slug)
        plan_path = os.path.join(work_dir, 'plan.md')
        if not os.path.isfile(plan_path):
            continue
        try:
            with open(plan_path) as handle:
                plan = handle.read()
        except (IOError, OSError):
            continue

        title = TITLE.search(plan)
        status = STATUS.search(plan)
        state = read_state(work_dir)
        verdict = state.get('verdict') or {}
        started = origin(plan_path)
        branch_match = BRANCH.search(plan)
        branch = state.get('branch') or (branch_match.group(1) if branch_match else '')
        pr = find_pr(state, branch, work_dir)

        items.append({
            'slug': slug,
            'title': title.group(1) if title else slug,
            'intent': section(plan, 'Intent'),
            'status': status.group(1).strip() if status else '',
            'stage': state.get('stage', ''),
            'outcome': verdict.get('outcome', ''),
            'branch': branch,
            'pr': pr,
            'planned': started['date'],
            'author': started['author'],
            'email': started['email'],
            'agents': started['agents'],
            'committed': started['committed'],
            'lastTouched': last_touched(work_dir),
        })

    # Uncommitted items have no date and sort last: they are the work in progress.
    items.sort(key=lambda i: (i['planned'] == '', i['planned']))
    return items


def clip(text, width):
    return text if len(text) <= width else text[:width - 1] + '\u2026'


def pr_label(pr):
    """A short handle for the request: #12, !12, or nothing."""
    if pr.get('ref', '').startswith(('#', '!')):
        return pr['ref']
    url = pr.get('url', '')
    if url:
        tail = re.search(r'/(?:pull|merge_requests)/(\d+)', url)
        sigil = '!' if 'merge_requests' in url else '#'
        return sigil + tail.group(1) if tail else clip(url, 12)
    return '\u2014'


def render(items, full):
    if not items:
        print('No work items. docs/work/ is empty or absent \u2014 nothing has been planned yet.')
        return

    rows = []
    for item in items:
        label = pr_label(item['pr'])
        if item['pr'].get('draft'):
            label += '*'
        rows.append((
            item['planned'][:10] or '(uncommitted)',
            item['author'] or '\u2014',
            item['stage'] or item['status'] or '\u2014',
            label,
            item['slug'],
            item['title'],
        ))

    header = ('PLANNED', 'BY', 'STAGE', 'PR', 'SLUG')
    widths = [max(len(r[i]) for r in rows) for i in range(5)]
    widths = [min(w, cap) for w, cap in zip(widths, (13, 22, 12, 14, 30))]
    widths = [max(w, len(h)) for w, h in zip(widths, header)]

    line = '  '.join([h.ljust(w) for h, w in zip(header, widths)] + ['TITLE'])
    print(line)
    print('-' * min(len(line) + 20, 100))

    indent = ' ' * (sum(widths) + 2 * len(widths))
    for item, row in zip(items, rows):
        print('  '.join([clip(v, w).ljust(w) for v, w in zip(row[:5], widths)] + [row[5]]))
        notes = []
        if item['pr'].get('url'):
            notes.append(item['pr']['url'])
        elif item['pr'].get('source') == 'merge commit':
            notes.append('request found in the merge commit, not recorded in state.json')
        if item['agents']:
            notes.append('with ' + ', '.join(item['agents']))
        for note in notes:
            print(indent + note)
        if full and item['intent']:
            print(indent + clip(item['intent'], 96))

    print('')
    print('%d work item(s).' % len(items))
    uncommitted = [i for i in items if not i['committed']]
    if uncommitted:
        print('%d not committed yet, so nothing records who planned them: %s'
              % (len(uncommitted), ', '.join(i['slug'] for i in uncommitted)))
    nopr = [i for i in items if not i['pr'].get('ref')]
    if nopr:
        print('%d with no pull or merge request found: %s'
              % (len(nopr), ', '.join(i['slug'] for i in nopr)))
    if any(i['pr'].get('draft') for i in items):
        print('* marks a draft request.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--full', action='store_true', help='include each plan\'s Intent')
    parser.add_argument('--author', help='only items planned by an author matching this')
    parser.add_argument('--limit', type=int, help='show only the most recent N')
    opts = parser.parse_args()

    if git('rev-parse', '--git-dir') is None:
        sys.stderr.write('history.py: not a git repository, so there is no history to read\n')
        return 2

    items = collect()

    if opts.author:
        needle = opts.author.lower()
        items = [i for i in items
                 if needle in i['author'].lower() or needle in i['email'].lower()]
    if opts.limit:
        items = items[-opts.limit:]

    if opts.json:
        print(json.dumps(items, indent=2))
    else:
        render(items, opts.full)
    return 0


if __name__ == '__main__':
    sys.exit(main())
