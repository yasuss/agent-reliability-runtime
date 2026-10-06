from pathlib import Path
import importlib.util

SCRIPT=Path(__file__).resolve().parents[1]/'scripts'/'validate_compiled_skill.py'
spec=importlib.util.spec_from_file_location('validator',SCRIPT)
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

def test_good_package_passes():
    assert mod.validate(Path(__file__).resolve().parents[1]) == []

def test_missing_required_file_fails(tmp_path):
    root=tmp_path/'skill'; root.mkdir()
    (root/'SKILL.md').write_text('Exactly one production LangGraph agent graph\nNo side effect without exact valid approval\nPublic web is static recorded replay only\nMCP Python SDK as v2\nLocal evidence precedes remote publication\n')
    errors=mod.validate(root)
    assert any(e.startswith('missing:') for e in errors)
