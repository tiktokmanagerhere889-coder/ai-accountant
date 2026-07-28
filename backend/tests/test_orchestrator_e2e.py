"""End-to-end test: Orchestrator + Daily Entry Agent with real Cerebras/Groq APIs."""
from __future__ import annotations

import sys
import os
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, CashPosition, JournalEntry, BankAccount, BankTransaction, PettyCashFund
from agent_defs.orchestrator import run_orchestrator
from agent_defs.daily_entry_agent import run_daily_entry_agent

TEST_DATE = "2026-07-28"


async def run_e2e():
    """Test Orchestrator + Daily Entry Agent end-to-end with real APIs."""
    print("=" * 60)
    print("E2E TEST: Orchestrator + Daily Entry Agent")
    print(f"Test date: {TEST_DATE}")
    print("=" * 60)

    results = []

    async def test(name, fn):
        try:
            resp = await fn()
            truncated = (resp[:180] + "...") if len(resp) > 180 else resp
            print(f"  [{name}]")
            print(f"  -> {truncated}")
            results.append((name, True))
        except Exception as e:
            print(f"  [{name}] FAIL -> {type(e).__name__}: {e}")
            results.append((name, False))

    # Seed test data into the shared dev database
    from db.database import init_db, get_session
    init_db()
    s = get_session()
    # Clear existing test data
    s.query(JournalEntry).delete()
    s.query(BankTransaction).delete()
    s.query(BankAccount).delete()
    s.query(PettyCashFund).delete()
    s.commit()
    s.add(JournalEntry(entry_id="JE-SEED-001", description="Opening balance",
        posted_date=date(2026, 7, 1), reference=None,
        debit_account="1000-Cash", debit_amount=Decimal("500000.00"),
        credit_account="3000-Equity", credit_amount=Decimal("500000.00"), status="posted"))
    s.add(JournalEntry(entry_id="JE-SEED-002", description="Client payment received",
        posted_date=date(2026, 7, 26), reference="INV-099",
        debit_account="1000-Cash", debit_amount=Decimal("150000.00"),
        credit_account="4000-Revenue", credit_amount=Decimal("150000.00"), status="posted"))
    s.add(BankAccount(account_id="BA-001", account_name="HBL Current", bank_name="HBL"))
    s.add(BankTransaction(transaction_id="BT-E2E-001", date=date(2026, 7, 25),
        description="Client payment INV-100", amount=Decimal("150000.00"), type="credit",
        status="cleared", reference="INV-100", account_id="BA-001", balance_after=Decimal("2150000.00")))
    s.add(BankTransaction(transaction_id="BT-E2E-002", date=date(2026, 7, 27),
        description="Office rent payment", amount=Decimal("50000.00"), type="debit",
        status="cleared", reference="RENT-07", account_id="BA-001", balance_after=Decimal("2100000.00")))
    s.add(PettyCashFund(fund_id="PC-001", fund_name="Main Petty Cash", current_balance=Decimal("3000.00")))
    s.commit()
    s.close()

    print("\n1. Orchestrator: Cash Position Check")
    await test("Cash position", lambda: run_orchestrator("What is our cash position as of " + TEST_DATE + "?"))

    print("\n2. Orchestrator: Record Transaction")
    await test("Record transaction", lambda: run_orchestrator("Record office rent 50000 for July using date " + TEST_DATE))

    print("\n3. Orchestrator: Bank Transactions")
    await test("Bank query", lambda: run_orchestrator("Show me bank transactions from 2026-07-21 to " + TEST_DATE + " for account BA-001"))

    print("\n4. Orchestrator: Petty Cash")
    await test("Petty cash", lambda: run_orchestrator("Check petty cash fund PC-001 status, the fund_id is PC-001, do we need replenishment?"))

    print("\n5. Direct Daily Entry Agent")
    await test("Direct agent", lambda: run_daily_entry_agent("Record electricity bill payment of 12000 using date " + TEST_DATE))

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
