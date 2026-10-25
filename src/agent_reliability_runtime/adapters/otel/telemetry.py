"""Safe manual OpenTelemetry spans."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode, Tracer

from agent_reliability_runtime.core.evidence import sanitize

REQUIRED_SPANS = (
    "agent.run",
    "agent.model.call",
    "agent.retrieval.search",
    "agent.memory.read",
    "agent.memory.write",
    "agent.action.validate",
    "agent.policy.evaluate",
    "agent.approval.wait",
    "agent.approval.resume",
    "agent.tool.call",
    "agent.recovery.resume",
    "agent.finalize",
)


class Telemetry:
    def __init__(self, tracer: Tracer | None = None) -> None:
        self.tracer = tracer or trace.get_tracer("agent-reliability-runtime")

    @contextmanager
    def span(self, name: str, **attrs: Any) -> Iterator[Span]:
        if name not in REQUIRED_SPANS:
            raise ValueError("unknown runtime span")
        allowed = {
            "gen_ai.operation.name",
            "gen_ai.request.model",
            "gen_ai.response.model",
            "gen_ai.response.finish_reasons",
            "gen_ai.usage.input_tokens",
            "gen_ai.usage.output_tokens",
            "gen_ai.tool.name",
        }
        allowed.update(
            {
                "arr.run.id",
                "arr.scenario.id",
                "arr.provider.id",
                "arr.run.phase",
                "arr.tool.name",
                "arr.tool.risk_class",
                "arr.approval.required",
                "arr.approval.status",
                "arr.effect.replayed",
                "arr.model.steps",
                "arr.tool.steps",
                "arr.run.status",
                "arr.failure.class",
                "arr.recovery.kind",
                "arr.memory.operation",
                "arr.retrieval.result_count",
            }
        )
        safe = {
            k: sanitize(v) for k, v in attrs.items() if v is not None and k in allowed
        }
        with self.tracer.start_as_current_span(
            name, attributes=safe, record_exception=False, set_status_on_exception=False
        ) as span:
            try:
                yield span
            except BaseException as error:
                # Exceptions may carry prompts, credentials or raw vendor bodies.
                span.set_attribute("arr.failure.class", type(error).__name__)
                span.set_status(Status(StatusCode.ERROR))
                raise
