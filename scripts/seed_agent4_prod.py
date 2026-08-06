"""Seed production Neon with test data for the 5 empty Agent-4 tables.

Writes rows to: prepaid_expenses, intangible_assets, payroll_entries, budgets,
loans — plus a matching June 2026 salary GL journal entry so reconcile_payroll
finds a real match. Requires DATABASE_URL to point at the production DB.

Usage:
    DATABASE_URL=<prod-url> python scripts/seed_agent4_prod.py

Idempotent: skips rows whose IDs already exist.
"""
from __future__ import annotations

import os
import sys
from datetime import date

from sqlalchemy.orm import Session

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from db.database import engine
from db.models import (
    Budget,
    IntangibleAsset,
    JournalEntry,
    Loan,
    PayrollEntry,
    PrepaidExpense,
)

# Largest existing JE sequence per date prefix (from the ledger dump), so the
# seeded June salary JE does not collide. JE-2026* only — no June entries exist.
SEEDED_PREFIXES = set()


def _next_entry_id(period_date: date) -> str:
    """Return the next free JE-YYYYMMDD-NNN id for the given date."""
    prefix = f"JE-{period_date.strftime('%Y%m%d')}-"
    if prefix in SEEDED_PREFIXES:
        raise RuntimeError(f"already seeded a JE for {prefix}")
    SEEDED_PREFIXES.add(prefix)
    # No existing June JEs in prod, so this is safe; recompute from DB to be robust.
    existing = Session(bind=engine).query(JournalEntry.entry_id).filter(
        JournalEntry.entry_id.like(prefix + "%")
    ).all()
    max_seq = 0
    for row in existing:
        eid = row[0] if not isinstance(row, str) else row
        suffix = str(eid)[len(prefix):]
        if suffix.isdigit():
            max_seq = max(max_seq, int(suffix))
    return f"{prefix}{max_seq + 1:03d}"


def main() -> None:
    db = Session(bind=engine)

    # --- 1. Prepaid expenses: 12-month insurance policy, 10,000/month ---
    if db.query(PrepaidExpense).filter(PrepaidExpense.prepaid_id == "PPE-001").first() is None:
        db.add(PrepaidExpense(
            prepaid_id="PPE-001",
            description="Annual office insurance premium",
            total_amount=120000,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            monthly_amount=10000,
            remaining_balance=120000,
            status="active",
        ))
        print("  + prepaid PPE-001 (insurance 120000, 10000/mo)")

    # --- 2. Intangible asset: software license, 5-year amortization ---
    if db.query(IntangibleAsset).filter(IntangibleAsset.asset_id == "INT-001").first() is None:
        db.add(IntangibleAsset(
            asset_id="INT-001",
            asset_name="Accounting Software License",
            cost=60000,
            acquisition_date=date(2026, 1, 1),
            useful_life_years=5,
            residual_value=0,
            current_book_value=60000,
            status="active",
        ))
        print("  + intangible INT-001 (software 60000, 5yr)")

    # --- 3. Payroll: June 2026, 3 employees (net = salary - deductions) ---
    june_payroll = [
        ("PY-2026-06-001", "Aftab Ahmed", 150000, 15000, 135000),
        ("PY-2026-06-002", "Sana Malik", 120000, 12000, 108000),
        ("PY-2026-06-003", "Bilal Khan", 80000, 8000, 72000),
    ]
    for pid, name, sal, ded, net in june_payroll:
        if db.query(PayrollEntry).filter(PayrollEntry.entry_id == pid).first() is None:
            db.add(PayrollEntry(
                entry_id=pid,
                employee_name=name,
                salary_amount=sal,
                deductions=ded,
                net_pay=net,
                period_start=date(2026, 6, 1),
                period_end=date(2026, 6, 30),
                posted_date=date(2026, 6, 30),
            ))
            print(f"  + payroll {pid} {name} {sal}/{ded}/{net}")

    # Matching GL salary JE for June (dr 6100-Salary / cr 1000-Cash) so
    # reconcile_payroll finds a real match (total 350000).
    june_je = _next_entry_id(date(2026, 6, 30))
    if db.query(JournalEntry).filter(JournalEntry.entry_id == june_je).first() is None:
        db.add(JournalEntry(
            entry_id=june_je,
            description="June 2026 salary expense",
            posted_date=date(2026, 6, 30),
            reference="PY-2026-06",
            debit_account="6100-Salary",
            debit_amount=350000,
            credit_account="1000-Cash",
            credit_amount=350000,
            status="posted",
        ))
        print(f"  + journal {june_je} (6100-Salary 350000 / 1000-Cash)")

    # --- 4. Budgets: FY 2026, period 7 (July) ---
    july_budgets = [
        ("BUD-2026-07-01", 2026, 7, "6000-Rent", 50000),
        ("BUD-2026-07-02", 2026, 7, "6100-Salary", 150000),
        ("BUD-2026-07-03", 2026, 7, "6200-Utilities", 20000),
        ("BUD-2026-07-04", 2026, 7, "6300-Office Supplies", 15000),
    ]
    for bid, fy, period, acct, amt in july_budgets:
        if db.query(Budget).filter(Budget.budget_id == bid).first() is None:
            db.add(Budget(
                budget_id=bid,
                fiscal_year=fy,
                period=period,
                account_code=acct,
                budget_amount=amt,
                created_at=date(2026, 7, 1),
            ))
            print(f"  + budget {bid} {acct} {amt} (FY{fy} P{period})")

    # --- 5. Loan: LN-001, 500000 @ 12%/yr, 12 months ---
    if db.query(Loan).filter(Loan.loan_id == "LN-001").first() is None:
        db.add(Loan(
            loan_id="LN-001",
            loan_name="Business Term Loan",
            principal_amount=500000,
            interest_rate=12,
            term_months=12,
            start_date=date(2026, 1, 1),
            status="active",
        ))
        print("  + loan LN-001 (500000 @12%, 12mo)")

    db.commit()
    print("\nSeed complete.")


if __name__ == "__main__":
    main()
