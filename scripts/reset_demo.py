"""Destructively restore fictional demo state in a development/test database."""

import argparse

from sqlalchemy import create_engine

from agent_reliability_runtime.database import database_url
from agent_reliability_runtime.demo_state.reset import reset_demo


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-development-reset", action="store_true", required=True
    )
    parser.parse_args()
    engine = create_engine(database_url())
    try:
        reset_demo(engine, confirm_development_reset=True)
    finally:
        engine.dispose()
    print("Restored fictional demo_* state; non-demo evidence preserved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
