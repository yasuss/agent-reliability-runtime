#!/usr/bin/env python3
from pathlib import Path
import json, re, sys

root=Path(__file__).resolve().parents[1]
errors=[]
req=json.loads((root/'requirements/REQUIREMENTS.json').read_text(encoding='utf-8'))
ids=[r['id'] for r in req['requirements']]
if len(ids)!=len(set(ids)): errors.append('duplicate requirement IDs')

accept=(root/'11_ACCEPTANCE_GATES.md').read_text(encoding='utf-8')
backlog=(root/'10_ENGINEERING_BACKLOG.md').read_text(encoding='utf-8')
for r in req['requirements']:
    if not r.get('acceptance'): errors.append(f"{r['id']} has no acceptance mapping")

# Ensure all mandatory scenario files exist and IDs match filenames.
for n in range(1,13):
    pref=f'S{n:02d}_'
    matches=list((root/'fixtures/scenarios').glob(pref+'*.json'))
    if len(matches)!=1:
        errors.append(f'{pref} expected exactly one scenario file, got {len(matches)}')
        continue
    obj=json.loads(matches[0].read_text(encoding='utf-8'))
    if obj['id']!=matches[0].stem: errors.append(f'{matches[0].name}: id mismatch')
    if not obj.get('expected_invariants'): errors.append(f'{matches[0].name}: missing invariants')

# Calendar planning is explicitly forbidden in implementation backlog.
calendar_patterns=[r'\bday\s+[0-9]+',r'\bweek\s+[0-9]+',r'\bdays?\s+[0-9]+',r'\bweeks?\s+[0-9]+']
for pat in calendar_patterns:
    if re.search(pat, backlog, re.I): errors.append(f'calendar-tied backlog pattern found: {pat}')

# Locked no-public-chat choice should remain explicit.
scope=(root/'01_SCOPE_AND_NON_GOALS.md').read_text(encoding='utf-8').lower()
if 'no public arbitrary prompt field' not in (root/'08_DEMO_UX.md').read_text(encoding='utf-8').lower():
    errors.append('demo does not explicitly forbid public arbitrary prompt field')
if 'multi-agent' not in scope: errors.append('scope lacks multi-agent non-goal')

if errors:
    print('FAIL')
    for e in errors: print('-',e)
    sys.exit(1)
print(f'PASS: {len(ids)} requirements, 12 mandatory scenarios, backlog is acceptance-based')
