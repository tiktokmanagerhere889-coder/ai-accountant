"""Migration script for Agent 8 (Audit & Regulatory).

Adds 3 new tables: flagged_entries, statutory_registers, compliance_deadlines.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import create_engine, text

from db.models import Base, FlaggedEntry, StatutoryRegister, ComplianceDeadline
from db.database import DATABASE_URL


def run_migration():
    print(f"Connecting to {DATABASE_URL}...")
    engine = create_engine(DATABASE_URL)

    print("Creating flagged_entries table...")
    FlaggedEntry.__table__.create(bind=engine, checkfirst=True)

    print("Creating statutory_registers table...")
    StatutoryRegister.__table__.create(bind=engine, checkfirst=True)

    print("Creating compliance_deadlines table...")
    ComplianceDeadline.__table__.create(bind=engine, checkfirst=True)

    # Verify by listing tables
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
        ))
        tables = [row[0] for row in result]
        print(f"Tables after migration: {tables}")

    print("Agent 8 migration complete.")


if __name__ == "__main__":
    run_migration()
