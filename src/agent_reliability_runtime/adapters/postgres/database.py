"""Development connection configuration, with no implicit schema changes."""

import os

from sqlalchemy import URL, make_url


def database_url() -> URL:
    configured = os.environ.get("ARR_DATABASE_URL")
    if configured:
        return make_url(configured)
    return URL.create(
        "postgresql+psycopg",
        username="arr",
        password=os.environ.get("ARR_DB_PASSWORD", "local-development-fixture"),
        host="127.0.0.1",
        port=int(os.environ.get("ARR_DB_PORT", "5432")),
        database="arr",
    )
