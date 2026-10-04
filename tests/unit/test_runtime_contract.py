"""B60 strict configuration/state/serde and topology checker calibration."""

import ast
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from agent_reliability_runtime.runtime.checkpoints import strict_serde
from agent_reliability_runtime.runtime.service import RunConfig
from scripts.runtime_proof_support import primitive


@pytest.mark.parametrize("budget", [0, -1, 13, True, "8", 8.0])
def test_budget_rejects_invalid_configuration(budget: Any) -> None:
    with pytest.raises(ValidationError):
        RunConfig(model_budget=budget)


def test_strict_state_and_serde_calibration() -> None:
    assert (
        RunConfig().model_budget == 8 and RunConfig(model_budget=12).model_budget == 12
    )
    raw = {
        "messages": [{"role": "tool", "content": "untrusted"}],
        "counter": 2,
        "none": None,
    }
    serde = strict_serde()
    assert not serde.pickle_fallback
    assert serde.loads_typed(serde.dumps_typed(raw)) == raw
    primitive(raw)
    primitive(dict(reversed(list(raw.items()))))

    class Forbidden(BaseModel):
        value: int

    model = Forbidden(value=1)
    with pytest.raises(AssertionError):
        primitive({"model": model})
    decoded = serde.loads_typed(serde.dumps_typed(model))
    assert not isinstance(decoded, Forbidden)
    with pytest.raises((TypeError, NotImplementedError, ValueError)):
        serde.loads_typed(("pickle", b"not allowed"))


def check_topology(source: str) -> None:
    tree = ast.parse(source)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    assert (
        len(
            [
                n
                for n in calls
                if isinstance(n.func, ast.Name) and n.func.id == "StateGraph"
            ]
        )
        == 1
    )
    assert not [
        n
        for n in calls
        if isinstance(n.func, ast.Attribute)
        and n.func.attr in {"raw_wire_call_for_testing", "_dispatch_effect"}
    ]
    expected = {
        "prepare_run",
        "load_memory",
        "retrieve_context",
        "decide",
        "validate_action",
        "policy_gate",
        "await_approval",
        "execute_tool",
        "observe_result",
        "finalize",
    }
    nodes = {
        n.args[0].value
        for n in calls
        if isinstance(n.func, ast.Attribute)
        and n.func.attr == "add_node"
        and isinstance(n.args[0], ast.Constant)
    }
    assert nodes == expected
    pause = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "await_approval"
    )
    first = pause.body[0]
    assert isinstance(first, ast.Expr) and isinstance(first.value, ast.Call)
    assert isinstance(first.value.func, ast.Name) and first.value.func.id == "interrupt"


def test_topology_good_bad_alternate() -> None:
    source = (
        Path(__file__).resolve().parents[2]
        / "src/agent_reliability_runtime/runtime/graph.py"
    ).read_text()
    check_topology(source)
    check_topology("# harmless alternative\n" + source)
    for broken in (
        source.replace('graph.add_node("finalize", finalize)', "pass"),
        source + "\nraw.raw_wire_call_for_testing()\n",
        source + "\nStateGraph(State)\n",
        source.replace("    interrupt(", "    write()\n    interrupt("),
    ):
        with pytest.raises(AssertionError):
            check_topology(broken)
