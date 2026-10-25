"""All twelve real mechanism scenarios are mandatory in the database CI job."""

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Engine

from agent_reliability_runtime.adapters.langgraph.checkpoints import (
    run_async,
    setup_checkpoints,
)
from agent_reliability_runtime.demo.evals.execution import mandatory_suite

pytestmark = pytest.mark.integration


def test_exact_twelve_mandatory_scenarios(
    isolated_db: tuple[Engine, Config], tmp_path: Path
) -> None:
    engine, _ = isolated_db

    async def exercise() -> None:
        await setup_checkpoints(engine.url)
        result = await mandatory_suite(engine, tmp_path / "mandatory")
        assert result["passed"], result
        assert len(result["results"]) == 12

    run_async(exercise())
