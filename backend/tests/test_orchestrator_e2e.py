"""End-to-end test: Orchestrator + Agents 1 & 2 with real Groq APIs."""
import sys, os, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from decimal import Decimal

from db.models import JournalEntry, BankAccount, BankTransaction, PettyCashFund, PayrollEntry
from agent_defs.orchestrator import run_orchestrator
from agent_defs.daily_entry_agent import run_daily_entry_agent

TEST_DATE = "2026-07-29"


def seed_data():
    from db.database import init_db, get_session
    init_db()
    s = get_session()
    # Clear
    for t in [JournalEntry, BankTransaction, BankAccount, PettyCashFund, PayrollEntry]:
        s.query(t).delete()
    s.commit()
    # Seed
    s.add(JournalEntry(entry_id="JE-SEED-001", description="Opening balance",
        posted_date=date(2026, 7, 1), reference=None,
        debit_account="1000-Cash", debit_amount=Decimal("500000.00"),
        credit_account="3000-Equity", credit_amount=Decimal("500000.00"), status="posted"))
    s.add(JournalEntry(entry_id="JE-SEED-002", description="Client payment",
        posted_date=date(2026, 7, 26), reference="INV-099",
        debit_account="1000-Cash", debit_amount=Decimal("150000.00"),
        credit_account="4000-Revenue", credit_amount=Decimal("150000.00"), status="posted"))
    s.add(JournalEntry(entry_id="JE-SEED-003", description="Vendor bill - stationery",
        posted_date=date(2026, 7, 15), reference="VENDOR-001",
        debit_account="6300-Office Supplies", debit_amount=Decimal("25000.00"),
        credit_account="2000-Accounts Payable", credit_amount=Decimal("25000.00"), status="posted"))
    s.add(BankAccount(account_id="BA-001", account_name="HBL Current", bank_name="HBL"))
    s.add(BankTransaction(transaction_id="BT-E2E-001", date=date(2026, 7, 25),
        description="Client payment INV-100", amount=Decimal("150000.00"), type="credit",
        status="cleared", reference="INV-100", account_id="BA-001", balance_after=Decimal("2150000.00")))
    s.add(PettyCashFund(fund_id="PC-001", fund_name="Main Petty Cash", current_balance=Decimal("3000.00")))
    s.add(PayrollEntry(entry_id="PR-SEED-001", employee_name="Ali Khan",
        salary_amount=Decimal("100000.00"), deductions=Decimal("15000.00"),
        net_pay=Decimal("85000.00"), period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 31), posted_date=date(2026, 7, 28)))
    s.commit()
    s.close()


async def run_e2e():
    print("=" * 60)
    print("E2E TEST: Orchestrator + Agents 1 & 2")
    print(f"Date: {TEST_DATE}")
    print("=" * 60)

    results = []

    async def test(name, fn):
        try:
            resp = await fn()
            truncated = (resp[:200] + "...") if len(resp) > 200 else resp
            print(f"  [{name}]")
            print(f"  -> {truncated}")
            results.append((name, True))
        except Exception as e:
            print(f"  [{name}] FAIL -> {type(e).__name__}: {e}")
            results.append((name, False))

    seed_data()

    # Agent 1 tests
    print("\n--- Agent 1 Tests ---")
    await test("Cash position", lambda: run_orchestrator("What is our cash position as of " + TEST_DATE + "?"))
    await test("Record transaction", lambda: run_orchestrator("Record office rent 50000 for July using date " + TEST_DATE))
    await test("Petty cash", lambda: run_orchestrator("Check petty cash fund PC-001 status, is replenishment needed?"))
    await test("Direct agent", lambda: run_daily_entry_agent("Record electricity bill payment of 12000 using date " + TEST_DATE))

    # Agent 2 tests
    print("\n--- Agent 2 Tests ---")
    await test("General ledger", lambda: run_orchestrator("Show me the general ledger for July 2026"))
    await test("Chart of accounts", lambda: run_orchestrator("Suggest chart of accounts for a retail business"))
    await test("AP subledger", lambda: run_orchestrator("Show me accounts payable, what do we owe vendors?"))
    await test("Payroll", lambda: run_orchestrator("Show me payroll records for July 2026"))
    await test("Journal entry", lambda: run_orchestrator("Create a journal entry debiting office rent 50000 from account 6000-Office Rent and crediting 1000-Cash"))

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
