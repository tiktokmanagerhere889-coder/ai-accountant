"""Test utilities — shared PostgreSQL test database."""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from db.models import Base

# PostgreSQL test database (isolated from production)
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/ai_accountant_test"
)


def make_test_session() -> Session:
    """Create a fresh PostgreSQL test session with all tables created."""
    engine = create_engine(TEST_DATABASE_URL, echo=False)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()
