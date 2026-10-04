"""Local stdio entry point. Protocol stdout is owned entirely by the SDK."""

import logging
import sys

from sqlalchemy import create_engine

from agent_reliability_runtime.database import database_url
from mcp_server.opsdesk.server import create_server


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    engine = create_engine(database_url())
    try:
        create_server(engine).run()
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
