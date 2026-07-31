"""Check actual DB column names for all tables."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from sqlalchemy import inspect, text
from db.database import engine

insp = inspect(engine)
tables = sorted(insp.get_table_names())
for t in tables:
    cols = [c['name'] for c in insp.get_columns(t)]
    print(f"{t}: {','.join(cols)}")
