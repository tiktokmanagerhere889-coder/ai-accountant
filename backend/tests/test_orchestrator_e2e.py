"""End-to-end test: Agents 1-5 with real Groq APIs.

Each agent is tested directly via its own run function:
- Daily Entry Agent: run_daily_entry_agent (4 tools)
- Ledger Agent: run_ledger_agent (8 tools)
- Reconciliation Agent: run_reconciliation_agent (7 tools)
- Month-End Agent: run_month_end_agent (10 tools)
- Year-End Agent: run_year_end_agent (8 tools)

Direct agent calls avoid Groq TPM limits on the 37-tool orchestrator prompt.
"""
import sys, os, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1, errors="replace", closefd=False)

from datetime import date
from decimal import Decimal

from db.models import (
    JournalEntry, BankAccount, BankTransaction, PettyCashFund,
    PayrollEntry, ChequeRegistry, LCBGRegistry, Contact,
    Budget, Loan, PrepaidExpense, FixedAsset, IntangibleAsset,
    RetainedEarnings, FiscalYearClose,
)
from agent_defs.daily_entry_agent import run_daily_entry_agent
from agent_defs.ledger_agent import run_ledger_agent
from agent_defs.reconciliation_agent import run_reconciliation_agent
from agent_defs.month_end_reporting_agent import run_month_end_agent
from agent_defs.year_end_agent import run_year_end_agent

TEST_DATE = "2026-07-29"


def seed_data():
    from db.database import init_db, get_session
    init_db()
    s = get_session()
    # Clear all tables
    for t in [JournalEntry, BankTransaction, BankAccount, PettyCashFund, PayrollEntry, ChequeRegistry, LCBGRegistry, Contact, Budget, Loan, PrepaidExpense, FixedAsset, IntangibleAsset]:
        s.query(t).delete()
    s.commit()
    # Seed Agent 1+2 data
    s.add(JournalEntry(entry_id="JE-SEED-001", description="Opening balance",
        posted_date=date(2026, 7, 1), reference=None,
        debit_account="1000-Cash", debit_amount=Decimal("500000.00"),
        credit_account="3000-Equity", credit_amount=Decimal("500000.00"), status="posted"))
    s.add(JournalEntry(entry_id="JE-SEED-002", description="Client payment",
        posted_date=date(2026, 7, 26), reference="INV-099",
        debit_account="1000-Cash", debit_amount=Decimal("150000.00"),
        credit_account="4000-Revenue", credit_amount=Decimal("150000.00"), status="posted"))
    s.add(JournalEntry(entry_id="JE-SEED-003", description="Vendor bill stationery",
        posted_date=date(2026, 7, 15), reference="VENDOR-001",
        debit_account="6300-Office Supplies", debit_amount=Decimal("25000.00"),
        credit_account="2000-Accounts Payable", credit_amount=Decimal("25000.00"), status="posted"))
    s.add(BankAccount(account_id="BA-001", account_name="HBL Current", bank_name="HBL"))
    s.add(BankTransaction(transaction_id="BT-E2E-001", date=date(2026, 7, 25),
        description="Client payment INV-100", amount=Decimal("150000.00"), type="credit",
        status="cleared", reference="INV-100", account_id="BA-001", balance_after=Decimal("2150000.00")))
    s.add(BankTransaction(transaction_id="BT-E2E-002", date=date(2026, 7, 28),
        description="Bank service charges", amount=Decimal("-500.00"), type="debit",
        status="cleared", account_id="BA-001", balance_after=Decimal("2149500.00")))
    s.add(PettyCashFund(fund_id="PC-001", fund_name="Main Petty Cash", current_balance=Decimal("3000.00")))
    s.add(PayrollEntry(entry_id="PR-SEED-001", employee_name="Ali Khan",
        salary_amount=Decimal("100000.00"), deductions=Decimal("15000.00"),
        net_pay=Decimal("85000.00"), period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 31), posted_date=date(2026, 7, 28)))
    # Seed Agent 3 data
    s.add(Contact(contact_id="CNT-V001", contact_name="Abdullah General Store",
        contact_type="vendor", phone="0300-1234567"))
    s.add(ChequeRegistry(cheque_id="CHQ-000001", vendor_name="Ali Traders",
        amount=Decimal("50000.00"), issue_date=date(2026, 7, 1),
        status="issued", bank_account_id="BA-001"))
    s.add(LCBGRegistry(lc_id="LC-202607-001", type="LC", beneficiary="ABC Trading",
        amount=Decimal("5000000.00"), currency="PKR",
        issue_date=date(2026, 7, 1), expiry_date=date(2026, 12, 31), status="active"))
    # Seed Agent 4 data — month-end reporting
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
    # AR entries for aging
    s.add(JournalEntry(entry_id="JE-AR-E2E-001", description="Customer invoice",
        posted_date=date(2026, 7, 1), reference="CNT-V001",
        debit_account="1200-Accounts Receivable", debit_amount=Decimal("150000.00"),
        credit_account="4000-Revenue", credit_amount=Decimal("150000.00"), status="posted"))
    # Seed Agent 5 data — full year entries for financial statements
    s.add(JournalEntry(entry_id="JE-REV-Q1", description="Sales Q1",
        posted_date=date(2026, 3, 31), reference="INV-Q1",
        debit_account="1000-Cash", debit_amount=Decimal("200000.00"),
        credit_account="4000-Revenue", credit_amount=Decimal("200000.00"), status="posted"))
    s.add(JournalEntry(entry_id="JE-REV-Q2", description="Sales Q2",
        posted_date=date(2026, 6, 30), reference="INV-Q2",
        debit_account="1000-Cash", debit_amount=Decimal("180000.00"),
        credit_account="4000-Revenue", credit_amount=Decimal("180000.00"), status="posted"))
    s.add(JournalEntry(entry_id="JE-EXP-RENT", description="Rent Jan-Jun",
        posted_date=date(2026, 6, 30), reference=None,
        debit_account="6000-Rent Expense", debit_amount=Decimal("120000.00"),
        credit_account="1000-Cash", credit_amount=Decimal("120000.00"), status="posted"))
    s.add(JournalEntry(entry_id="JE-EXP-SAL", description="Salary Jan-Jun",
        posted_date=date(2026, 6, 30), reference=None,
        debit_account="6100-Salary Expense", debit_amount=Decimal("300000.00"),
        credit_account="1000-Cash", credit_amount=Decimal("300000.00"), status="posted"))
    s.add(JournalEntry(entry_id="JE-EXP-UTIL", description="Utilities Jan-Jun",
        posted_date=date(2026, 6, 30), reference=None,
        debit_account="6200-Utilities Expense", debit_amount=Decimal("30000.00"),
        credit_account="1000-Cash", credit_amount=Decimal("30000.00"), status="posted"))
    s.add(JournalEntry(entry_id="JE-LOAN", description="Business loan",
        posted_date=date(2026, 2, 1), reference="LN-001",
        debit_account="1000-Cash", debit_amount=Decimal("500000.00"),
        credit_account="2100-Business Loan", credit_amount=Decimal("500000.00"), status="posted"))
    s.add(JournalEntry(entry_id="JE-FA", description="Purchase equipment",
        posted_date=date(2026, 4, 1), reference="FA-001",
        debit_account="1500-Equipment", debit_amount=Decimal("100000.00"),
        credit_account="1000-Cash", credit_amount=Decimal("100000.00"), status="posted"))
    s.add(JournalEntry(entry_id="JE-AP-OPEN", description="Opening AP",
        posted_date=date(2026, 1, 1), reference=None,
        debit_account="1000-Cash", debit_amount=Decimal("50000.00"),
        credit_account="2000-Accounts Payable", credit_amount=Decimal("50000.00"), status="posted"))
    s.commit()
    s.close()


async def run_e2e():
    print("=" * 60)
    print("E2E TEST: Agents 1-5 (direct agent calls)")
    print(f"Date: {TEST_DATE}")
    print("=" * 60)

    results = []

    async def test(name, fn):
        try:
            resp = await fn()
            truncated = (resp[:250] + "...") if len(resp) > 250 else resp
            safe = truncated.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
            print(f"  [{name}]")
            print(f"  -> {safe}")
            results.append((name, True))
        except Exception as e:
            print(f"  [{name}] FAIL -> {type(e).__name__}: {e}")
            results.append((name, False))
        await asyncio.sleep(1.5)  # throttle to avoid Groq rate limits

    seed_data()

    # Agent 1
    print("\n--- AGENT 1: Daily Entry ---")
    await test("Cash position", lambda: run_daily_entry_agent("What is our cash position as of " + TEST_DATE + "?"))
    await asyncio.sleep(2)
    await test("Record transaction", lambda: run_daily_entry_agent("Record office rent 50000 for July using date " + TEST_DATE))
    await asyncio.sleep(2)
    await test("Petty cash", lambda: run_daily_entry_agent("Check petty cash fund PC-001 status, is replenishment needed?"))

    # Agent 2
    print("\n--- AGENT 2: Ledger & Master Data ---")
    await test("General ledger", lambda: run_ledger_agent("Show me the general ledger for July 2026"))
    await asyncio.sleep(2)
    await test("Payroll", lambda: run_ledger_agent("Show me payroll records for July 2026"))
    await asyncio.sleep(2)
    await test("Journal entry", lambda: run_ledger_agent("Create a journal entry: debit office rent 50000 from 6000-Office Rent and credit to 1000-Cash"))

    # Agent 3
    print("\n--- AGENT 3: Reconciliation & Banking ---")
    await test("Bank charges", lambda: run_reconciliation_agent("Reconcile bank charges for BA-001 for July 2026"))
    await asyncio.sleep(2)
    await test("Cheque status", lambda: run_reconciliation_agent("Check cheque CHQ-000001 status, is it cleared yet?"))
    await asyncio.sleep(2)
    await test("LC status", lambda: run_reconciliation_agent("Check LC-202607-001 status, how many days to expiry?"))

    # Agent 4
    print("\n--- AGENT 4: Month-End Reporting ---")
    await test("Unpaid bills", lambda: run_month_end_agent("Show me unpaid bills as of 2026-07-29"))
    await asyncio.sleep(2)
    await test("AP aging", lambda: run_month_end_agent("Generate AP aging report as of 2026-07-29"))
    await asyncio.sleep(2)
    await test("AR aging", lambda: run_month_end_agent("Generate AR aging report as of 2026-07-29"))
    await asyncio.sleep(2)
    await test("Budget variance", lambda: run_month_end_agent("Analyze budget variance for fiscal year 2026 period 7"))
    await asyncio.sleep(2)
    await test("Loan schedule", lambda: run_month_end_agent("Get loan repayment schedule for LN-E2E-001"))
    await asyncio.sleep(2)
    await test("Depreciation", lambda: run_month_end_agent("Calculate depreciation for July 2026"))
    await asyncio.sleep(2)
    await test("Amortization", lambda: run_month_end_agent("Calculate amortization for July 2026"))

    # Agent 5
    print("\n--- AGENT 5: Year-End Close & Financial Statements ---")
    await test("Trial balance", lambda: run_year_end_agent("Show me the trial balance as of 2026-07-29"))
    await asyncio.sleep(8)
    await test("Profit & Loss", lambda: run_year_end_agent("Generate profit and loss statement for July 2026"))
    await asyncio.sleep(8)
    await test("Balance sheet", lambda: run_year_end_agent("What is our balance sheet as of 31 July 2026?"))
    await asyncio.sleep(8)
    await test("Cash flow", lambda: run_year_end_agent("Generate cash flow statement for July 2026"))
    await asyncio.sleep(8)
    await test("Retained earnings", lambda: run_year_end_agent("Calculate retained earnings for fiscal year 2026"))
    await asyncio.sleep(8)
    await test("Carry forward", lambda: run_year_end_agent("Carry forward balances from 2026 to 2027"))
    await asyncio.sleep(8)
    await test("Notes to financials", lambda: run_year_end_agent("Draft notes to financial statements for fiscal year 2026"))
    await asyncio.sleep(8)
    await test("Close fiscal year", lambda: run_year_end_agent("Close fiscal year 2026 with confirm=True"))

    print("\n" + "=" * 60)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}: {name}")
    print(f"\n  Result: {passed}/{total} passed")
    print("=" * 60)
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_e2e())
    sys.exit(0 if success else 1)
