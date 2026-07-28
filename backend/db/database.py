import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from db.models import Base

# PostgreSQL is the production and dev database.
# Override with DATABASE_URL env var if needed (e.g. for CI).
DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/ai_accountant"

DATABASE_URL = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)

engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


def init_db() -> None:
    """Create all tables if they don't exist."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """Get a database session (FastAPI dependency compatible)."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_session() -> Session:
    """Get a direct database session."""
    return SessionLocal()
