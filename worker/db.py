"""
Synchronous SQLAlchemy session for Celery tasks.
"""
import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

DATABASE_URL_SYNC = os.environ.get(
    "DATABASE_URL_SYNC",
    "postgresql://zapper:zapper@postgres:5432/zapper_pm",
)

_engine = create_engine(DATABASE_URL_SYNC, pool_size=5, max_overflow=10)
_SessionFactory = sessionmaker(bind=_engine)


@contextmanager
def get_session() -> Session:
    session = _SessionFactory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
