"""Verify compliance_deadlines seed on prod (reads DATABASE_URL from ../.env)."""
import os

for line in open('../.env', encoding='utf-8'):
    line = line.strip()
    if line.startswith('DATABASE_URL='):
        os.environ['DATABASE_URL'] = line.split('=', 1)[1].strip().strip('"').strip("'")
        break

from sqlalchemy import create_engine, text

eng = create_engine(os.environ['DATABASE_URL'])
with eng.connect() as c:
    n = c.execute(text("SELECT count(*) FROM compliance_deadlines")).scalar()
    rows = c.execute(
        text("SELECT deadline_id, deadline_type, due_date, status FROM compliance_deadlines ORDER BY due_date")
    ).fetchall()
print("compliance_deadlines rows:", n)
for r in rows:
    print(" ", r)
