import os

import pytest
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration


def test_foundation_database() -> None:
    url = os.environ.get("ARR_TEST_DATABASE_URL")
    if not url:
        pytest.fail("ARR_TEST_DATABASE_URL must explicitly select a disposable test DB")
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT extversion FROM pg_extension WHERE extname='vector'")
                )
                == "0.8.6"
            )
            assert (
                connection.scalar(text("SELECT version_num FROM alembic_version"))
                == "0001_foundation"
            )
    finally:
        engine.dispose()
