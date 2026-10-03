"""Real disposable schema shared by domain and retrieval regression tests."""

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url


@pytest.fixture
def isolated_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Engine, Config]]:
    raw_url = os.environ.get("ARR_TEST_DATABASE_URL")
    if not raw_url:
        pytest.fail("ARR_TEST_DATABASE_URL must explicitly select a disposable test DB")
    name = "test_b10_" + uuid4().hex
    admin = create_engine(raw_url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{name}"'))
        # Shadow public's marker before enabling public extension types/operators.
        # All application tables are still created exclusively by real migrations.
        connection.execute(
            text(
                f'CREATE TABLE "{name}".alembic_version '
                "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
    # Extension types/operators live in public; tables still live in this schema.
    url = make_url(raw_url).update_query_dict(
        {"options": f"-csearch_path={name},public"}
    )
    monkeypatch.setenv("ARR_DATABASE_URL", url.render_as_string(hide_password=False))
    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    engine = create_engine(url)
    try:
        command.upgrade(cfg, "head")
        yield engine, cfg
    finally:
        engine.dispose()
        with admin.begin() as connection:
            # Only this test's fresh random schema; never public or other state.
            connection.execute(text(f'DROP SCHEMA "{name}" CASCADE'))
        admin.dispose()
