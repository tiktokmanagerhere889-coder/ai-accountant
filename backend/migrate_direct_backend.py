"""Migration script for Direct-Backend Features (AuditLog, UserRole)."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import create_engine, text
from db.models import Base, AuditLog, UserRole
from db.database import DATABASE_URL


def run_migration():
    print(f"Connecting to {DATABASE_URL}...")
    engine = create_engine(DATABASE_URL)

    print("Creating audit_log table...")
    AuditLog.__table__.create(bind=engine, checkfirst=True)

    print("Creating user_roles table...")
    UserRole.__table__.create(bind=engine, checkfirst=True)

    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
        ))
        tables = [row[0] for row in result]
        print(f"Tables after direct backend migration: {tables}")

    print("Direct-Backend migration complete.")


if __name__ == "__main__":
    run_migration()
