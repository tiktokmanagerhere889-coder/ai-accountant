"""Test Agent 4 (Month-End Reporting) with real Groq API - all 10 tools."""
import sys, os, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from decimal import Decimal

from db.models import (
    Budget, Loan, PrepaidExpense, FixedAsset, IntangibleAsset,
    JournalEntry, BankAccount, BankTransaction, PayrollEntry,
)
from agent_defs.orchestrator import run_orchestrator


def seed_agent4_data():
    from db.database import init_db, get_session
    init_db()
    s = get_session()
    # Clear all tables we touch
    for t in [Budget, Loan, PrepaidExpense, FixedAsset, IntangibleAsset,
              JournalEntry, BankAccount, BankTransaction, PayrollEntry]:
        s.query(t).delete()
    s.commit()
    # Seed
    s.add(Budget(budget_id="BDG-E2E-001", fiscal_year=2026, period=7,
        account_code="6000", budget_amount=Decimal("100000.00")))
    s.add(Budget(budget_id="BDG-E2E-002", fiscal_year=2026, period=7,
        account_code="6100", budget_amount=Decimal("200000.00")))
    s.add(Loan(loan_id="LN-E2E-001", loan_name="E2E Business Loan",
        principal_amount=Decimal("500000.00"), interest_rate=Decimal("10"),
        term_months=12, start_date=date(2026, 1, 1), status="active"))
    s.add(PrepaidExpense(prepaid_id="PRE-E2E-001", description="E2E Insurance",
        total_amount=Decimal("120000.00"), start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31), monthly_amount=Decimal("10000.00"),
        remaining_balance=Decimal("50000.00"), status="active"))
    s.add(FixedAsset(asset_id="FA-E2E-001", asset_name="E2E Delivery Truck",
        asset_category="vehicle", purchase_cost=Decimal("2400000.00"),
        purchase_date=date(2026, 1, 1), useful_life_years=10,
        depreciation_method="straight_line", residual_value=Decimal("240000.00"),
        current_book_value=Decimal("2400000.00"), status="approved"))
    s.add(IntangibleAsset(asset_id="IA-E2E-001", asset_name="E2E Software License",
        cost=Decimal("120000.00"), acquisition_date=date(2026, 1, 1),
        useful_life_years=5, residual_value=Decimal("0"),
        current_book_value=Decimal("120000.00"), status="active"))
    # AR entry for aging
    s.add(JournalEntry(entry_id="JE-AR-E2E-001", description="Customer invoice",
        posted_date=date(2026, 7, 1), reference="CNT-V001",
        debit_account="1200-Accounts Receivable", debit_amount=Decimal("150000.00"),
        credit_account="4000-Revenue", credit_amount=Decimal("150000.00"), status="posted"))
    # AP entry for aging
    s.add(JournalEntry(entry_id="JE-AP-E2E-001", description="Vendor bill",
        posted_date=date(2026, 7, 15), reference="VENDOR-001",
        debit_account="6300-Office Supplies", debit_amount=Decimal("25000.00"),
        credit_account="2000-Accounts Payable", credit_amount=Decimal("25000.00"), status="posted"))
    # Payroll entry
    s.add(PayrollEntry(entry_id="PR-SEED-001", employee_name="Ali Khan",
        salary_amount=Decimal("100000.00"), deductions=Decimal("15000.00"),
        net_pay=Decimal("85000.00"), period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 31), posted_date=date(2026, 7, 28)))
    s.add(BankAccount(account_id="BA-001", account_name="HBL Current", bank_name="HBL"))
    s.add(BankTransaction(transaction_id="BT-E2E-001", date=date(2026, 7, 25),
        description="Client payment INV-100", amount=Decimal("150000.00"), type="credit",
        status="cleared", reference="INV-100", account_id="BA-001",
        balance_after=Decimal("2150000.00")))
    s.commit()
    s.close()
    print("  Seed data inserted.\n")


async def main():
    print("=" * 60)
    print("AGENT 4: MONTH-END REPORTING (10 tools) - REAL GROQ API")
    print("=" * 60)

    print("Seeding database...")
    seed_agent4_data()

    queries = [
        ("01. review_unpaid_bills", "Show me unpaid bills as of 2026-07-29"),
        ("02. get_ap_aging_report", "Generate AP aging report as of 2026-07-29"),
        ("03. get_ar_aging_report", "Generate AR aging report as of 2026-07-29"),
        ("04. analyze_budget_variance", "Analyze budget variance for fiscal year 2026 period 7"),
        ("05. get_loan_debt_schedule", "Get loan repayment schedule for LN-E2E-001"),
        ("06. calculate_depreciation", "Calculate depreciation for July 2026"),
        ("07. calculate_amortization", "Calculate amortization for July 2026"),
        ("08. calculate_prepaid_adjustment", "Calculate prepaid expense adjustment for PRE-E2E-001"),
        ("09. reconcile_payroll", "Reconcile payroll for July 2026"),
        ("10. forecast_cash_flow", "Forecast cash flow for next 30 days with starting balance 2149500"),
    ]

    results = []
    for name, query in queries:
        print(f"\n--- {name} ---")
        try:
            resp = await run_orchestrator(query)
            truncated = (resp[:400] + "...") if len(resp) > 400 else resp
            print(f">> {truncated}")
            results.append((name, True))
        except Exception as e:
            print(f">> FAIL - {type(e).__name__}: {e}")
            results.append((name, False))

    print("\n" + "=" * 60)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"RESULTS: {passed}/{total} tools passed")
    for name, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}: {name}")
    print("=" * 60)
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
