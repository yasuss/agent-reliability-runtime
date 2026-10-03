"""Explicit project schema migration entrypoint."""

from alembic import context
from sqlalchemy import create_engine

from agent_reliability_runtime.database import database_url
from agent_reliability_runtime.persistence.schema import metadata

if context.is_offline_mode():
    context.configure(url=database_url(), literal_binds=True, target_metadata=metadata)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(database_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
