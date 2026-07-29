"""Migration script: additive schema changes for Agent 6.

Adds:
  - contacts.related_party (Boolean)
  - journal_entries.contact_id (Varchar, nullable)
  - exchange_rates table
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import create_engine, text
from db.models import Base, ExchangeRate

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ai_accountant")
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    conn.execute(text("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS related_party BOOLEAN DEFAULT FALSE"))
    conn.execute(text("ALTER TABLE journal_entries ADD COLUMN IF NOT EXISTS contact_id VARCHAR"))
    conn.commit()
    print("[OK] contacts.related_party + journal_entries.contact_id added")

ExchangeRate.__table__.create(bind=engine, checkfirst=True)
print("[OK] exchange_rates table created")

print("\nAll migrations complete.")
