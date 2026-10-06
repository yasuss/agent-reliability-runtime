"""Exact locked v1 scenario authority and path/raw-byte subject identity."""

import hashlib
import json
from pathlib import Path

from agent_reliability_runtime.evals.contracts import ScenarioDefinition
from agent_reliability_runtime.observability import canonical
from agent_reliability_runtime.replay import locked_validate

ROOT = Path(__file__).resolve().parents[3]
RELATIVE = Path("docs/project/spec/v1.0/fixtures/scenarios")
IDS = (
    "S01_READ_ONLY_GROUNDED",
    "S02_APPROVAL_REQUIRED",
    "S03_APPROVAL_REJECTED",
    "S04_STALE_APPROVAL",
    "S05_RAG_PROMPT_INJECTION",
    "S06_MALICIOUS_TOOL_OUTPUT",
    "S07_TRANSIENT_TIMEOUT",
    "S08_PROCESS_KILL_RESUME",
    "S09_DUPLICATE_EFFECT",
    "S10_MEMORY_POISONING",
    "S11_STEP_BUDGET",
    "S12_PROVIDER_FAILURE",
)


def load_scenarios(root: Path = ROOT) -> tuple[tuple[ScenarioDefinition, ...], str]:
    definitions = []
    files = []
    for path in sorted((root / RELATIVE).iterdir()):
        if not path.is_file() or path.suffix != ".json":
            raise ValueError("unknown locked scenario entry")
        raw = path.read_bytes()
        value = json.loads(raw)
        locked_validate(value, "scenario")
        scenario = ScenarioDefinition.model_validate(value)
        if scenario.id != path.stem:
            raise ValueError("scenario filename/ID mismatch")
        definitions.append(scenario)
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    if tuple(d.id for d in definitions) != IDS:
        raise ValueError("exact twelve unique scenarios required")
    return tuple(definitions), hashlib.sha256(canonical(files)).hexdigest()


def lockfile_digests(root: Path = ROOT) -> dict[str, str]:
    return {
        p: hashlib.sha256((root / p).read_bytes()).hexdigest()
        for p in ("uv.lock", "web/package-lock.json")
    }
