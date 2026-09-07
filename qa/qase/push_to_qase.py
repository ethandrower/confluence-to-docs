#!/usr/bin/env python3
"""Push the support-portal test cases in support-portal-cases.yaml into Qase.

Idempotent on purpose: it matches the project by code, suites by title, and
cases by title-within-suite, so running it twice does not produce a second copy
of anything. Editing the YAML and re-running is the intended workflow — the
file is the source of truth and Qase is a projection of it.

    export QASE_TESTOPS_API_TOKEN=...
    python qa/qase/push_to_qase.py            # create/update
    python qa/qase/push_to_qase.py --dry-run  # show what would change

The token comes from https://app.qase.io → user menu → API tokens. It is read
from the environment only; do not put it in this file or in the YAML.
"""
import argparse
import os
import sys

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is needed for this script: pip install pyyaml")

import requests

API = 'https://api.qase.io/v1'
HERE = os.path.dirname(os.path.abspath(__file__))
CASES_FILE = os.path.join(HERE, 'support-portal-cases.yaml')

# Qase encodes these as integers. Spelling them out here keeps the YAML
# readable and means a typo fails loudly rather than silently filing
# everything as "undefined".
SEVERITY = {'undefined': 0, 'blocker': 1, 'critical': 2, 'major': 3,
            'normal': 4, 'minor': 5, 'trivial': 6}
PRIORITY = {'undefined': 0, 'high': 1, 'medium': 2, 'low': 3}


class Qase:
    def __init__(self, token, dry_run=False):
        self.s = requests.Session()
        self.s.headers.update({'Token': token, 'Content-Type': 'application/json'})
        self.dry_run = dry_run

    def _call(self, method, path, **kw):
        r = self.s.request(method, f'{API}{path}', timeout=30, **kw)
        if r.status_code == 401:
            sys.exit('Qase rejected the token (401). Check QASE_TESTOPS_API_TOKEN.')
        if not r.ok:
            sys.exit(f'{method} {path} -> {r.status_code}: {r.text[:400]}')
        return r.json().get('result')

    def get(self, path):
        return self._call('GET', path)

    def post(self, path, payload):
        if self.dry_run:
            print(f'    [dry-run] POST {path} {payload.get("title", "")}')
            return {'id': -1}
        return self._call('POST', path, json=payload)

    def patch(self, path, payload):
        if self.dry_run:
            print(f'    [dry-run] PATCH {path}')
            return {'id': -1}
        return self._call('PATCH', path, json=payload)

    def project_exists(self, code):
        r = self.s.get(f'{API}/project/{code}', timeout=30)
        if r.status_code == 401:
            sys.exit('Qase rejected the token (401). Check QASE_TESTOPS_API_TOKEN.')
        return r.ok

    def all_pages(self, path):
        """Qase paginates at 100. Suites and cases both outgrow that eventually."""
        out, offset = [], 0
        while True:
            sep = '&' if '?' in path else '?'
            page = self.get(f'{path}{sep}limit=100&offset={offset}')
            entities = page.get('entities', [])
            out.extend(entities)
            if len(entities) < 100:
                return out
            offset += 100


def build_steps(case):
    steps = []
    for i, step in enumerate(case.get('steps') or [], start=1):
        steps.append({
            'position': i,
            'action': step['action'],
            'expected_result': step.get('expected', ''),
        })
    return steps


def case_payload(case, suite_id):
    payload = {
        'title': case['title'],
        'suite_id': suite_id,
        'severity': SEVERITY[case.get('severity', 'normal')],
        'priority': PRIORITY[case.get('priority', 'medium')],
        # 1 = functional. These are all behavioural cases run against a
        # deployed portal, not unit or performance tests.
        'type': 1,
        # 0 = manual. The steps are written for a person; `manage.py smoke`
        # is what covers the automated slice.
        'automation': 0,
        'steps': build_steps(case),
    }
    if case.get('description'):
        payload['description'] = case['description'].strip()
    if case.get('preconditions'):
        payload['preconditions'] = case['preconditions'].strip()
    if case.get('tags'):
        payload['tags'] = case['tags']
    return payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true',
                    help='Report what would be created or updated, change nothing.')
    ap.add_argument('--file', default=CASES_FILE)
    args = ap.parse_args()

    token = os.environ.get('QASE_TESTOPS_API_TOKEN')
    if not token:
        sys.exit('Set QASE_TESTOPS_API_TOKEN (app.qase.io → user menu → API tokens).')

    with open(args.file) as fh:
        spec = yaml.safe_load(fh)

    q = Qase(token, dry_run=args.dry_run)
    proj = spec['project']
    code = proj['code']

    if q.project_exists(code):
        print(f'project {code}: already exists')
    else:
        print(f'project {code}: creating')
        q.post('/project', {
            'title': proj['title'],
            'code': code,
            'description': (proj.get('description') or '').strip(),
            'access': 'all',
        })

    existing_suites = {s['title']: s['id'] for s in q.all_pages(f'/suite/{code}')} \
        if not args.dry_run or q.project_exists(code) else {}

    created = updated = skipped = 0
    for suite in spec['suites']:
        title = suite['title']
        suite_id = existing_suites.get(title)
        if suite_id:
            print(f'suite "{title}": exists (id {suite_id})')
        else:
            print(f'suite "{title}": creating')
            res = q.post(f'/suite/{code}', {
                'title': title,
                'description': (suite.get('description') or '').strip(),
            })
            suite_id = res['id']

        by_title = {}
        if suite_id != -1:
            by_title = {c['title']: c['id']
                        for c in q.all_pages(f'/case/{code}?suite_id={suite_id}')}

        for case in suite['cases']:
            payload = case_payload(case, suite_id)
            case_id = by_title.get(case['title'])
            if case_id:
                q.patch(f'/case/{code}/{case_id}', payload)
                print(f'  ~ {case["title"]}')
                updated += 1
            else:
                q.post(f'/case/{code}', payload)
                print(f'  + {case["title"]}')
                created += 1

    total = sum(len(s['cases']) for s in spec['suites'])
    print(f'\n{total} case(s) in the file: {created} created, {updated} updated, '
          f'{skipped} skipped.')
    if args.dry_run:
        print('Dry run — nothing was written to Qase.')


if __name__ == '__main__':
    main()
