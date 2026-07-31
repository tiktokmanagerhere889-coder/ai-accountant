import json
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db.database import SessionLocal
from sqlalchemy import text

config = {
    "vehicle": {"useful_life": 10, "method": "declining_balance", "residual_pct": 0.10, "label": "Vehicle"},
    "computer": {"useful_life": 5, "method": "straight_line", "residual_pct": 0.05, "label": "Computer/IT"},
    "furniture": {"useful_life": 10, "method": "straight_line", "residual_pct": 0.10, "label": "Furniture"},
    "building": {"useful_life": 40, "method": "straight_line", "residual_pct": 0.10, "label": "Building"},
}
db = SessionLocal()
try:
    db.execute(text("DELETE FROM system_config WHERE config_key='asset_depreciation_configs'"))
    db.execute(
        text(
            "INSERT INTO system_config (config_key, config_value, description, updated_at) "
            "VALUES ('asset_depreciation_configs', :cfg, 'Asset depreciation configs', '2026-07-31')"
        ),
        {"cfg": json.dumps(config)},
    )
    db.commit()
    print("Asset config seeded OK")
finally:
    db.close()
