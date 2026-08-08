"""Migration script: add review columns to flagged_entries.

Adds: resolved_by (VARCHAR), resolution_note (TEXT).
Used by resolve_flagged_entry (confirm/waive workflow).
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import create_engine, text

from db.database import DATABASE_URL


def run_migration():
    print(f"Connecting to {DATABASE_URL}...")
    engine = create_engine(DATABASE_URL)

    statements = [
        "ALTER TABLE flagged_entries ADD COLUMN IF NOT EXISTS resolved_by VARCHAR NULL",
        "ALTER TABLE flagged_entries ADD COLUMN IF NOT EXISTS resolution_note TEXT NULL",
    ]

    with engine.connect() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
            print(f"OK: {stmt}")
        conn.commit()

    # Verify columns
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='flagged_entries' ORDER BY ordinal_position"
        ))
        cols = [row[0] for row in result]
        print(f"flagged_entries columns: {cols}")

    print("Flagged resolution migration complete.")


if __name__ == "__main__":
    run_migration()
