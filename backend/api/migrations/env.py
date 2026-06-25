"""
Alembic env.py — configured for async SQLAlchemy + offline migrations.
"""
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Alembic Config
config = context.config
fileConfig(config.config_file_name)

# Override database URL from env
DATABASE_URL_SYNC = os.environ.get(
    "DATABASE_URL_SYNC",
    "postgresql://zapper:zapper@localhost:5432/zapper_pm",
)
config.set_main_option("sqlalchemy.url", DATABASE_URL_SYNC)

# Import metadata for autogenerate support
try:
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from app.db import Base
    from app.models.models import *  # noqa: F401,F403 — registers all models
    target_metadata = Base.metadata
except ImportError:
    target_metadata = None


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
