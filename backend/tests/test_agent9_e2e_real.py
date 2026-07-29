"""Agent 9 E2E test — real Groq API through Orchestrator.

Tests all 5 tools: 4 non-approval + 1 approval.
"""
import sys, os, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

if sys.platform == "win32":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1, errors="replace", closefd=False)

from datetime import date, timedelta
from decimal import Decimal

from db.models import (
    JournalEntry, Budget, RetainedEarnings,
)
from agent_defs.orchestrator import run_orchestrator


def seed_data():
    from db.database import init_db, get_session
    init_db()
    s = get_session()
    for t in [JournalEntry, Budget, RetainedEarnings]:
        s.query(t).delete()
    s.commit()

    today = date.today()

    # Revenue
    s.add(JournalEntry(entry_id="REV-001", description="Sales revenue - Q1", posted_date=today - timedelta(days=60), reference="INV-001",
        debit_account="1000-Cash", debit_amount=Decimal("500000.00"), credit_account="4000-Sales Revenue", credit_amount=Decimal("500000.00"), status="posted"))
    s.add(JournalEntry(entry_id="REV-002", description="Sales revenue - Q2", posted_date=today - timedelta(days=30), reference="INV-002",
        debit_account="1000-Cash", debit_amount=Decimal("600000.00"), credit_account="4000-Sales Revenue", credit_amount=Decimal("600000.00"), status="posted"))
    # COGS
    s.add(JournalEntry(entry_id="COGS-001", description="Raw materials purchase", posted_date=today - timedelta(days=55), reference="PO-001",
        debit_account="5000-Cost of Goods Sold", debit_amount=Decimal("200000.00"), credit_account="2000-Accounts Payable", credit_amount=Decimal("200000.00"), status="posted"))
    s.add(JournalEntry(entry_id="COGS-002", description="Raw materials purchase Q2", posted_date=today - timedelta(days=25), reference="PO-002",
        debit_account="5000-Cost of Goods Sold", debit_amount=Decimal("250000.00"), credit_account="2000-Accounts Payable", credit_amount=Decimal("250000.00"), status="posted"))
    # Operating Expenses
    s.add(JournalEntry(entry_id="OPEX-001", description="Office rent", posted_date=today - timedelta(days=50), reference="RENT-001",
        debit_account="6000-Rent Expense", debit_amount=Decimal("150000.00"), credit_account="1000-Cash", credit_amount=Decimal("150000.00"), status="posted"))
    s.add(JournalEntry(entry_id="OPEX-002", description="Salary expense Q1", posted_date=today - timedelta(days=40), reference="PAY-001",
        debit_account="6100-Salary Expense", debit_amount=Decimal("200000.00"), credit_account="1000-Cash", credit_amount=Decimal("200000.00"), status="posted"))
    s.add(JournalEntry(entry_id="OPEX-003", description="Salary expense Q2", posted_date=today - timedelta(days=20), reference="PAY-002",
        debit_account="6100-Salary Expense", debit_amount=Decimal("200000.00"), credit_account="1000-Cash", credit_amount=Decimal("200000.00"), status="posted"))
    # Other expenses
    s.add(JournalEntry(entry_id="OTHER-001", description="Bank charges", posted_date=today - timedelta(days=15), reference=None,
        debit_account="8000-Bank Charges", debit_amount=Decimal("5000.00"), credit_account="1000-Cash", credit_amount=Decimal("5000.00"), status="posted"))
    # Balance sheet items
    s.add(JournalEntry(entry_id="BS-001", description="Equipment purchase", posted_date=today - timedelta(days=90), reference="FA-001",
        debit_account="1200-Equipment", debit_amount=Decimal("800000.00"), credit_account="1000-Cash", credit_amount=Decimal("800000.00"), status="posted"))
    s.add(JournalEntry(entry_id="BS-002", description="Bank loan", posted_date=today - timedelta(days=90), reference="LN-001",
        debit_account="1000-Cash", debit_amount=Decimal("500000.00"), credit_account="2200-Bank Loan", credit_amount=Decimal("500000.00"), status="posted"))

    # Budget
    s.add(Budget(budget_id="BUG-001", fiscal_year=today.year, period=today.month, account_code="6000", budget_amount=Decimal("300000.00")))
    s.add(Budget(budget_id="BUG-002", fiscal_year=today.year, period=today.month, account_code="6100", budget_amount=Decimal("400000.00")))

    s.commit()
    s.close()
    print("  Seed data ready")


async def run_e2e():
    print("=" * 70)
    print("E2E TEST: Agent 9 (Advisory)")
    print("Orchestrator -> Advisory Agent -> 5 tools")
    print("=" * 70)

    results = []

    async def test(seq, name, query):
        print(f"\n  [{seq}/5] {name}")
        print(f"  Q: {query[:100]}...")
        start = asyncio.get_event_loop().time()
        try:
            resp = await run_orchestrator(query)
            elapsed = asyncio.get_event_loop().time() - start
            safe = resp[:400].encode("utf-8", errors="replace").decode("utf-8", errors="replace")
            ok = len(resp) > 20 and "Error" not in resp[:50]
            print(f"  {'PASS' if ok else 'FAIL'} ({elapsed:.1f}s)")
            print(f"  -> {safe}")
            results.append((seq, name, ok, elapsed))
        except Exception as e:
            elapsed = asyncio.get_event_loop().time() - start
            print(f"  FAIL ({elapsed:.1f}s): {type(e).__name__}: {e}")
            results.append((seq, name, False, elapsed))
        await asyncio.sleep(3)

    seed_data()

    # Tool 1: analyze_spending_patterns (No approval)
    await test(1, "Spending Patterns",
        "Analyze my spending patterns for this year. Look at all expense categories.")

    # Tool 2: calculate_financial_ratios (No approval)
    await test(2, "Financial Ratios",
        f"Calculate all financial ratios for fiscal year {date.today().year}")

    # Tool 3: assess_financial_health (No approval)
    await test(3, "Financial Health",
        f"Assess the financial health of my business for fiscal year {date.today().year}")

    # Tool 4: generate_cost_cutting_recommendations (No approval)
    await test(4, "Cost Cutting",
        f"Give me cost cutting recommendations for fiscal year {date.today().year}. Focus on operating expenses.")

    # Tool 5: generate_custom_report (Approval)
    await test(5, "Custom Report",
        f"Generate a detailed financial report for fiscal year {date.today().year}")

    print("\n" + "=" * 70)
    passed = sum(1 for _, _, ok, _ in results if ok)
    print(f"RESULTS: {passed}/{len(results)} passed")
    for seq, name, ok, lat in results:
        print(f"  {'PASS' if ok else 'FAIL'}: Tool {seq} {name} ({lat:.1f}s)")
    print("=" * 70)
    return passed == len(results)


if __name__ == "__main__":
    success = asyncio.run(run_e2e())
    sys.exit(0 if success else 1)
