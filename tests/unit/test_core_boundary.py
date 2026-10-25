"""Calibrated dependency boundaries and neutral extension semantics."""

import ast
import inspect
import sys
from importlib.util import resolve_name
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from agent_reliability_runtime.adapters.langgraph.checkpoints import (
    LangGraphPostgresCheckpointStore,
)
from agent_reliability_runtime.adapters.langgraph.graph import observe_result
from agent_reliability_runtime.adapters.postgres.execution import (
    Approvals,
    PostgresEffectStore,
)
from agent_reliability_runtime.adapters.postgres.retrieval import (
    PostgresHybridRetriever,
)
from agent_reliability_runtime.adapters.providers.http import (
    HTTPProviderConfig,
    OpenAICompatibleChatProvider,
)
from agent_reliability_runtime.core.ports import (
    Approver,
    CheckpointStore,
    EffectStore,
    ModelProvider,
    PolicyEngine,
    Retriever,
    TimerStore,
    Verifier,
)
from agent_reliability_runtime.core.verification import RuleVerifier, VerificationStatus
from agent_reliability_runtime.demo.opsdesk.policy import OpsDeskPolicyEngine, propose
from agent_reliability_runtime.demo.opsdesk.postconditions import opsdesk_verifier

ROOT = Path(__file__).resolve().parents[2] / "src/agent_reliability_runtime"


def violations(
    source: str, package: str = "agent_reliability_runtime.core"
) -> set[str]:
    errors = set()
    for node in ast.walk(ast.parse(source)):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [
                resolve_name("." * node.level + (node.module or ""), package)
                if node.level
                else node.module or ""
            ]
        for module in modules:
            if module.split(".")[0] in sys.stdlib_module_names | {
                "__future__",
                "pydantic",
            }:
                continue
            if module == "agent_reliability_runtime.core" or module.startswith(
                "agent_reliability_runtime.core."
            ):
                continue
            errors.add(module)
    return errors


def test_core_dependency_boundary_with_negative_calibration() -> None:
    assert violations(
        "from sqlalchemy import Engine\n"
        "from agent_reliability_runtime.demo.opsdesk import policy\n"
    ) == {"sqlalchemy", "agent_reliability_runtime.demo.opsdesk"}
    assert not violations(
        "import json\nfrom pydantic import BaseModel\nfrom . import policy\n"
    )
    assert violations("from ..demo import api") == {"agent_reliability_runtime.demo"}
    sources = list((ROOT / "core").rglob("*.py"))
    assert sources
    found = {}
    for path in sources:
        package = ".".join(path.relative_to(ROOT.parent).parts[:-1])
        errors = violations(path.read_text(encoding="utf-8"), package)
        if errors:
            found[str(path)] = errors
    assert found == {}


def test_adapters_do_not_import_demo() -> None:
    for path in (ROOT / "adapters").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith(
                    "agent_reliability_runtime.demo"
                )
            elif isinstance(node, ast.Import):
                assert not any(
                    a.name.startswith("agent_reliability_runtime.demo")
                    for a in node.names
                )


def test_generic_verifier_requires_registered_real_matching_later_read() -> None:
    action = propose(
        "run", "restart_service", {"service_id": "service", "reason": "test"}
    )
    assert RuleVerifier().obligation_for(action, 4) is None
    verifier = opsdesk_verifier()
    obligation = verifier.obligation_for(action, 4)
    assert obligation is not None
    args: dict[str, Any] = dict(
        tool_name="get_service_status",
        arguments={"service_id": "service"},
        result={"service_id": "service"},
    )
    assert (
        verifier.verify(obligation, effect_sequence=4, **args)
        == VerificationStatus.FAIL
    )
    assert (
        verifier.verify(obligation, effect_sequence=5, **args)
        == VerificationStatus.PASS
    )
    assert {s.value for s in VerificationStatus} == {"PASS", "FAIL", "PARTIAL"}


def test_implemented_adapters_conform_to_public_ports() -> None:
    policy: PolicyEngine = OpsDeskPolicyEngine()
    model: ModelProvider = OpenAICompatibleChatProvider(
        HTTPProviderConfig("fixture", "fixture", "http://127.0.0.1:11434/v1")
    )
    retriever: Retriever = PostgresHybridRetriever(Mock(), Mock())
    approver: Approver = Approvals(Mock(), policy=policy)
    effects: EffectStore = PostgresEffectStore(Mock())
    checkpoints: CheckpointStore = LangGraphPostgresCheckpointStore()
    verifier: Verifier = opsdesk_verifier()
    assert all(
        callable(method)
        for method in (
            model.complete,
            retriever.retrieve,
            policy.validate,
            approver.ensure,
            effects.receipt_for,
            checkpoints.has_checkpoint,
            verifier.verify,
        )
    )


def test_planned_timer_store_is_async_and_unimplemented() -> None:
    assert inspect.iscoroutinefunction(TimerStore.put)
    assert inspect.iscoroutinefunction(TimerStore.due)


@pytest.mark.parametrize(
    "status", [VerificationStatus.FAIL, VerificationStatus.PARTIAL]
)
def test_nonpass_verification_keeps_the_run_obligation(
    status: VerificationStatus,
) -> None:
    from types import SimpleNamespace
    from typing import cast

    action = propose(
        "run", "restart_service", {"service_id": "service", "reason": "test"}
    )
    obligation = opsdesk_verifier().obligation_for(action, 1)
    state = dict(
        proposed_call=dict(
            name="get_service_status",
            call_id="read",
            arguments={"service_id": "service"},
        ),
        result={"service_id": "service"},
        pending_calls=[],
        messages=[],
        verification_obligation=obligation,
        tool_steps=2,
    )
    verifier = Mock()
    verifier.verify.return_value = status
    update = observe_result(
        cast(Any, state),
        cast(Any, SimpleNamespace(context=SimpleNamespace(verifier=verifier))),
    )
    assert update["verification_obligation"] == obligation
    assert update["route"] == "decide"
