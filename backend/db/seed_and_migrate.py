"""Idempotent DB migration + seed. Safe to run every startup.

Guarantees:
  - fetched_at column added only if missing (information_schema check)
  - Tax rates, EOBI rates, asset configs seeded only if absent (check-then-insert
    where no unique constraint exists; ON CONFLICT where it does)
  - Running this 5x in a row produces no errors and no duplicates
"""
from __future__ import annotations

import json
import logging

from sqlalchemy import inspect, text

from db.database import SessionLocal, engine

logger = logging.getLogger("db.seed_and_migrate")

# ---------------------------------------------------------------------------
# 1. Schema migration: add exchange_rates.fetched_at if missing
# ---------------------------------------------------------------------------

def _ensure_fetched_at_column() -> None:
    """Add exchange_rates.fetched_at if it does not already exist (idempotent)."""
    insp = inspect(engine)
    if "exchange_rates" not in insp.get_table_names():
        logger.info("exchange_rates table missing - skipping fetched_at migration")
        return

    cols = {c["name"] for c in insp.get_columns("exchange_rates")}
    if "fetched_at" in cols:
        logger.info("exchange_rates.fetched_at already present - skip")
        return

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE exchange_rates ADD COLUMN fetched_at TIMESTAMP"))
    logger.info("Added exchange_rates.fetched_at column")


# ---------------------------------------------------------------------------
# 2. Seed tax rates (idempotent - check-then-insert, no unique constraint)
# ---------------------------------------------------------------------------

DEFAULT_TAX_RATES = [
    # WHT (lookup key: wht_<type>)
    ("wht_rent", 7.5),
    ("wht_salary", 5.0),
    ("wht_service", 3.0),
    ("wht_contract", 7.5),
    ("wht_supply", 4.0),
    ("wht_commission", 10.0),
    # Sales tax (SALES_TAX) and corporate income tax (INCOME_TAX)
    ("SALES_TAX", 16.0),
    ("INCOME_TAX", 29.0),
    # AMT by business type (amt_<type>)
    ("amt_company", 1.5),
    ("amt_individual", 1.0),
    ("amt_aop", 1.25),
]


def _seed_tax_rates() -> None:
    with engine.begin() as conn:
        for tax_type, rate in DEFAULT_TAX_RATES:
            exists = conn.execute(
                text("SELECT 1 FROM tax_rates WHERE tax_type = :t LIMIT 1"),
                {"t": tax_type},
            ).scalar()
            if exists:
                logger.info("tax_rates %s already present - skip", tax_type)
                continue
            conn.execute(
                text(
                    "INSERT INTO tax_rates (tax_type, rate, effective_from, effective_to, description) "
                    "VALUES (:t, :r, '2026-01-01', NULL, :t)"
                ),
                {"t": tax_type, "r": rate},
            )
            logger.info("Seeded tax_rates %s = %s", tax_type, rate)


# ---------------------------------------------------------------------------
# 3. Seed EOBI rates (idempotent - check-then-insert, no unique constraint)
# ---------------------------------------------------------------------------

def _seed_eobi_rates() -> None:
    with engine.begin() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM eobi_rates WHERE rate_type = 'standard' LIMIT 1")
        ).scalar()
        if exists:
            logger.info("eobi_rates standard already present - skip")
            return
        conn.execute(
            text(
                "INSERT INTO eobi_rates (rate_type, rate, employee_rate, effective_from, effective_to, "
                "max_insurable_amount, description) "
                "VALUES ('standard', 5.0, 2.5, '2026-01-01', NULL, 50000, 'Standard EOBI')"
            )
        )
        logger.info("Seeded eobi_rates standard = 5.0 / employee 2.5")


# ---------------------------------------------------------------------------
# 4. Seed asset depreciation configs (idempotent - config_key is unique)
# ---------------------------------------------------------------------------

ASSET_DEPRECIATION_CONFIGS = {
    "vehicle": {"useful_life": 10, "method": "declining_balance", "residual_pct": 0.10, "label": "Vehicle"},
    "computer": {"useful_life": 5, "method": "straight_line", "residual_pct": 0.05, "label": "Computer/IT"},
    "furniture": {"useful_life": 10, "method": "straight_line", "residual_pct": 0.10, "label": "Furniture"},
    "building": {"useful_life": 40, "method": "straight_line", "residual_pct": 0.10, "label": "Building"},
}


def _seed_asset_configs() -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO system_config (config_key, config_value, description, updated_at) "
                "VALUES ('asset_depreciation_configs', :cfg, 'Asset depreciation configs', CURRENT_DATE) "
                "ON CONFLICT (config_key) DO NOTHING"
            ),
            {"cfg": json.dumps(ASSET_DEPRECIATION_CONFIGS)},
        )
        # idempotent regardless - count to report
        present = conn.execute(
            text("SELECT count(*) FROM system_config WHERE config_key = 'asset_depreciation_configs'")
        ).scalar()
        logger.info("asset_depreciation_configs rows after seed: %s", present)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _ensure_bank_transactions_custom_fields() -> None:
    """Add bank_transactions.custom_fields if missing (idempotent)."""
    insp = inspect(engine)
    if "bank_transactions" not in insp.get_table_names():
        logger.info("bank_transactions table missing - skipping custom_fields migration")
        return

    cols = {c["name"] for c in insp.get_columns("bank_transactions")}
    if "custom_fields" in cols:
        logger.info("bank_transactions.custom_fields already present - skip")
        return

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE bank_transactions ADD COLUMN custom_fields TEXT"))
    logger.info("Added bank_transactions.custom_fields column")


def run_migrations() -> None:
    """Run all idempotent migrations + seeds. Safe to call every startup."""
    _ensure_fetched_at_column()
    _ensure_bank_transactions_custom_fields()
    _seed_tax_rates()
    _seed_eobi_rates()
    _seed_asset_configs()
    logger.info("DB migrations + seed complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migrations()
    print("Migration/seed done (idempotent).")
