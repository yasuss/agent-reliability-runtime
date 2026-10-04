"""Request-time local assembly; importing this module opens no connections."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Self
from uuid import uuid4

from pydantic import model_validator
from sqlalchemy import Engine

from agent_reliability_runtime.contracts.domain import (
    Identifier,
    Record,
    Run,
    RunStatus,
)
from agent_reliability_runtime.evals.scenarios import load_scenarios
from agent_reliability_runtime.mcp.client import OpsDeskMCPClient
from agent_reliability_runtime.policy import VERSION, Gateway
from agent_reliability_runtime.providers.contracts import ModelSettings
from agent_reliability_runtime.providers.http import (
    HTTPProviderConfig,
    OllamaEmbeddingProvider,
    OpenAICompatibleChatProvider,
)
from agent_reliability_runtime.runtime.graph import Context
from agent_reliability_runtime.runtime.service import DurableRuntime, open_runtime


class RunRequest(Record):
    workspace_id: Identifier
    user_id: Identifier
    task: Identifier | None = None
    scenario_id: Identifier | None = None

    @model_validator(mode="after")
    def one_request(self) -> Self:
        if (self.task is None) == (self.scenario_id is None):
            raise ValueError("exactly one task or scenario is required")
        if self.scenario_id is not None and self.scenario_id not in {
            s.id for s in load_scenarios()[0]
        }:
            raise ValueError("unknown locked scenario")
        return self

    def run(self) -> Run:
        task = self.task
        if self.scenario_id is not None:
            scenario = next(s for s in load_scenarios()[0] if s.id == self.scenario_id)
            task = str(scenario.input["task"])
        now = datetime.now(UTC)
        assert task is not None
        return Run(
            run_id=uuid4().hex,
            workspace_id=self.workspace_id,
            user_id=self.user_id,
            request_text=task,
            scenario_id=self.scenario_id,
            provider_id="ollama-local",
            model_id="qwen3:4b",
            policy_version=VERSION,
            status=RunStatus.CREATED,
            created_at=now,
            updated_at=now,
        )


@asynccontextmanager
async def local_runtime(engine: Engine) -> AsyncIterator[DurableRuntime]:
    root = Path(__file__).resolve().parents[3]
    async with OpsDeskMCPClient(
        root, engine.url.render_as_string(hide_password=False)
    ) as client:
        context = Context(
            engine=engine,
            provider=OpenAICompatibleChatProvider(
                HTTPProviderConfig(
                    "ollama-local",
                    "qwen3:4b",
                    "http://127.0.0.1:11434/v1",
                    timeout_seconds=300,
                )
            ),
            embeddings=OllamaEmbeddingProvider(
                HTTPProviderConfig(
                    "ollama-local",
                    "qwen3-embedding:0.6b",
                    "http://127.0.0.1:11434",
                    timeout_seconds=300,
                )
            ),
            tools=client.model_tools,
            gateway=Gateway(engine, client),
            model_settings=ModelSettings(max_tokens=8192),
        )
        async with open_runtime(context, engine.url) as runtime:
            yield runtime
