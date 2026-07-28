import os
from decimal import Decimal
from datetime import date
from typing import Optional

from sqlalchemy import create_engine, Column, String, Numeric, Date, Text
from sqlalchemy.orm import sessionmaker, Session, declarative_base

from db.models import Base

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///:memory:")

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()