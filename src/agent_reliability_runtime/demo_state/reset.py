"""Reset only the four demo tables, atomically and with explicit confirmation."""

from pathlib import Path

from sqlalchemy import Connection, Engine, delete

from agent_reliability_runtime.contracts.domain import DemoSeed
from agent_reliability_runtime.persistence.schema import (
    demo_incident_notes,
    demo_incidents,
    demo_notifications,
    demo_services,
)

SEED_PATH = Path(__file__).resolve().parents[3] / "data/seed/demo_state.json"


def load_seed(path: Path = SEED_PATH) -> DemoSeed:
    return DemoSeed.model_validate_json(path.read_bytes())


def reset_demo(engine: Engine, *, confirm_development_reset: bool = False) -> None:
    if not confirm_development_reset:
        raise ValueError(
            "explicit development/test destructive reset confirmation required"
        )
    seed = load_seed()
    with engine.begin() as connection:
        _restore(connection, seed)


def _restore(connection: Connection, seed: DemoSeed) -> None:
    # No TRUNCATE CASCADE, schema-wide operation or non-demo table access.
    for table in (
        demo_incident_notes,
        demo_notifications,
        demo_incidents,
        demo_services,
    ):
        connection.execute(delete(table))
    connection.execute(
        demo_services.insert(), [item.model_dump() for item in seed.services]
    )
    connection.execute(
        demo_incidents.insert(), [item.model_dump() for item in seed.incidents]
    )
