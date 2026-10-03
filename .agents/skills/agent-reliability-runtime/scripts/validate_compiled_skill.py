from __future__ import annotations
import sys
from pathlib import Path

REQUIRED = [
    'SKILL.md','agents/openai.yaml','references/source-of-truth.md','references/repository-contract.md',
    'references/project-architecture.md','references/security-trust.md','references/verification.md',
    'references/debugging-and-proof.md','references/dependencies-current.md','references/state-integrity.md',
    'references/active-modules.md','evals/CODEX_PRESSURE_SCENARIOS.md'
]
MARKERS = [
    'Exactly one production LangGraph agent graph',
    'No side effect without exact valid approval',
    'Public web is static recorded replay only',
    'MCP Python SDK as v2',
    'Local evidence precedes remote publication',
]

def validate(root: Path) -> list[str]:
    errors=[]
    for rel in REQUIRED:
        if not (root/rel).is_file(): errors.append(f'missing:{rel}')
    p=root/'SKILL.md'
    if p.is_file():
        txt=p.read_text(encoding='utf-8')
        if len(txt.splitlines()) > 180: errors.append('skill_not_concise')
        if '<project' in txt.lower() or '<list>' in txt.lower(): errors.append('template_placeholder')
        for m in MARKERS:
            if m not in txt: errors.append(f'missing_marker:{m}')
    return errors

if __name__ == '__main__':
    root=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
    errs=validate(root)
    if errs:
        print('FAIL')
        for e in errs: print(e)
        raise SystemExit(1)
    print('PASS: compiled skill structure and load-bearing markers verified')
