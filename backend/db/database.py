import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from db.models import Base

# Default: file-based SQLite for dev (shared across connections).
# Set DATABASE_URL to postgresql://... for production.
DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "dev.db"
DEFAULT_DATABASE_URL = f"sqlite:///{DEFAULT_DB_PATH}"

DATABASE_URL = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)

engine = create_engine(DATABASE_URL, echo=False)
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
