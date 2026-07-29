"""Migration script for Agent 10 (System Admin).

Adds 2 new tables: system_config, system_backup_log.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import create_engine, text

from db.models import Base, SystemConfig, SystemBackupLog
from db.database import DATABASE_URL


def run_migration():
    print(f"Connecting to {DATABASE_URL}...")
    engine = create_engine(DATABASE_URL)

    print("Creating system_config table...")
    SystemConfig.__table__.create(bind=engine, checkfirst=True)

    print("Creating system_backup_log table...")
    SystemBackupLog.__table__.create(bind=engine, checkfirst=True)

    # Verify
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
        ))
        tables = [row[0] for row in result]
        print(f"Tables after migration: {tables}")

    print("Agent 10 migration complete.")


if __name__ == "__main__":
    run_migration()
