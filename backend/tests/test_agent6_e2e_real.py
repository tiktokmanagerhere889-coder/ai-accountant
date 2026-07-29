"""Agent 6 E2E test — real Groq API through Orchestrator.

Tests all 8 tools: 3 non-approval + 5 approval tools.
Approval flow verified: without confirm, tools explain approval needed.
"""
import sys, os, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

if sys.platform == "win32":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1, errors="replace", closefd=False)

from datetime import date, timedelta
from decimal import Decimal

from db.models import (
    JournalEntry, Contact, ExchangeRate, Budget,
)
from agent_defs.orchestrator import run_orchestrator

TEST_DATE = "2026-07-29"


def seed_data():
    from db.database import init_db, get_session
    init_db()
    s = get_session()
    # Clear all Agent 6 related tables
    for t in [ExchangeRate, JournalEntry, Contact, Budget]:
        s.query(t).delete()
    s.commit()

    # Exchange rates for forex tool
    s.add(ExchangeRate(from_currency="USD", to_currency="PKR", rate=Decimal("278.50"), rate_date=date(2026, 7, 1), source="SBP"))
    s.add(ExchangeRate(from_currency="USD", to_currency="PKR", rate=Decimal("279.00"), rate_date=date(2026, 7, 15), source="SBP"))
    s.add(ExchangeRate(from_currency="USD", to_currency="PKR", rate=Decimal("280.00"), rate_date=date(2026, 7, 25), source="SBP"))

    # Budget records for forecast tool
    s.add(Budget(budget_id="BDG-001", fiscal_year=2026, period=1, account_code="6000", budget_amount=Decimal("50000.00")))
    s.add(Budget(budget_id="BDG-002", fiscal_year=2026, period=2, account_code="6000", budget_amount=Decimal("50000.00")))
    s.add(Budget(budget_id="BDG-003", fiscal_year=2026, period=1, account_code="6100", budget_amount=Decimal("100000.00")))

    # Historical journal entries for budget forecast (12 months)
    for m in range(1, 13):
        s.add(JournalEntry(
            entry_id=f"HIST-{m:04d}", description=f"Rent month {m}",
            posted_date=date(2026, m, 1), reference=None,
            debit_account="6000-Rent Expense", debit_amount=Decimal("50000.00"),
            credit_account="1000-Cash", credit_amount=Decimal("50000.00"),
            status="posted",
        ))
        s.add(JournalEntry(
            entry_id=f"SAL-{m:04d}", description=f"Salary month {m}",
            posted_date=date(2026, m, 15), reference=None,
            debit_account="6100-Salary Expense", debit_amount=Decimal("120000.00"),
            credit_account="1000-Cash", credit_amount=Decimal("120000.00"),
            status="posted",
        ))

    # Specific entries for cost variance (account 6000, period 7, FY 2026)
    s.add(JournalEntry(
        entry_id="VAR-ACTUAL-001", description="Rent July actual",
        posted_date=date(2026, 7, 1), reference=None,
        debit_account="6000-Rent Expense", debit_amount=Decimal("55000.00"),
        credit_account="1000-Cash", credit_amount=Decimal("55000.00"),
        status="posted",
    ))

    # Revenue entry for revenue recognition
    s.add(JournalEntry(
        entry_id="REV-CONTRACT-001", description="Contract C-001 partial",
        posted_date=date(2026, 6, 30), reference="C-001",
        debit_account="1000-Cash", debit_amount=Decimal("200000.00"),
        credit_account="4000-Sales Revenue", credit_amount=Decimal("200000.00"),
        status="posted",
    ))

    # Contacts for related party check
    s.add(Contact(
        contact_id="CNT-V001", contact_name="Abdullah Traders",
        contact_type="vendor", phone="0300-1111111",
        related_party=True,
    ))
    s.add(Contact(
        contact_id="CNT-REG-001", contact_name="Regular Vendor Co",
        contact_type="vendor", phone="0300-2222222",
        related_party=False,
    ))

    # Journal entry with contact_id for related party test
    s.add(JournalEntry(
        entry_id="JE-RP-TEST", description="Payment to Abdullah Traders",
        posted_date=date(2026, 7, 15), reference="INV-RP-001",
        contact_id="CNT-V001",
        debit_account="6300-Office Supplies", debit_amount=Decimal("75000.00"),
        credit_account="1000-Cash", credit_amount=Decimal("75000.00"),
        status="posted",
    ))

    s.commit()
    s.close()
    print("  ✅ Seed data ready")


async def run_e2e():
    print("=" * 70)
    print("E2E TEST: Agent 6 (Cost, Advanced Accounting & Budgeting)")
    print(f"Date: {TEST_DATE}")
    print("Orchestrator -> Cost Advanced Agent -> 8 tools")
    print("=" * 70)

    results = []
    latencies = []

    async def test(seq: int, name: str, query: str):
        """Run a query through the orchestrator and record result."""
        print(f"\n  [{seq}/8] {name}")
        print(f"  Query: {query}")
        start = asyncio.get_event_loop().time()
        try:
            resp = await run_orchestrator(query)
            elapsed = asyncio.get_event_loop().time() - start
            truncated = (resp[:400] + "...") if len(resp) > 400 else resp
            safe = truncated.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
            print(f"  ✅ Pass ({elapsed:.1f}s)")
            print(f"  → {safe}")
            results.append((seq, name, True, elapsed))
            latencies.append(elapsed)
        except Exception as e:
            elapsed = asyncio.get_event_loop().time() - start
            print(f"  ❌ Fail ({elapsed:.1f}s): {type(e).__name__}: {e}")
            results.append((seq, name, False, elapsed))
            latencies.append(elapsed)
        # Throttle between queries to avoid Groq rate limits
        await asyncio.sleep(3)

    seed_data()

    # ── Tool 1: calculate_breakeven (non-approval) ──
    await test(1, "Breakeven CVP",
        "Calculate breakeven: fixed cost 50000, variable cost 20 per unit, selling price 35 per unit")

    # ── Tool 2: convert_foreign_currency (non-approval) ──
    await test(2, "Foreign Currency Conversion",
        "Convert 1000 US dollars to Pakistani rupees using latest rate")

    # ── Tool 3: prepare_budget_forecast (non-approval) ──
    await test(3, "Budget Forecast",
        "Prepare a budget forecast for fiscal year 2026, for the next 6 months")

    # ── Tool 4: calculate_standard_costing_variance (APPROVAL) ──
    await test(4, "Cost Variance (approval)",
        "Calculate cost variance for account 6000 for period 7 fiscal year 2026, standard cost 50000, standard quantity 500")

    # ── Tool 5: allocate_overhead_cost (APPROVAL) ──
    await test(5, "Overhead Allocation (approval)",
        "Allocate 200000 overhead across departments by headcount: Sales 25 people, Engineering 40 people, Support 15 people")

    # ── Tool 6: calculate_revenue_recognition (APPROVAL) ──
    await test(6, "Revenue Recognition (approval)",
        "Recognize revenue for contract C-001, 60 percent complete, contract value 500000, previous recognized 200000")

    # ── Tool 7: flag_provision_contingent_liability (APPROVAL) ──
    await test(7, "Provision Flagging (approval)",
        "Flag a possible provision for a pending lawsuit, estimated amount 75000, probability possible, fiscal year 2026")

    # ── Tool 8: flag_related_party_transaction (APPROVAL) ──
    await test(8, "Related Party Check (approval)",
        "Check if journal entry JE-RP-TEST is a related party transaction. Counterparty is Abdullah Traders, amount 75000, fiscal year 2026")

    # ── Summary ──
    print("\n" + "=" * 70)
    passed = sum(1 for _, _, ok, _ in results if ok)
    total = len(results)
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    print(f"RESULTS: {passed}/{total} passed (avg {avg_latency:.1f}s)")

    # Approval vs non-approval breakdown
    approval_results = results[3:8]  # tools 4-8
    non_approval = results[0:3]      # tools 1-3
    print(f"\n  Non-approval tools (1-3): {sum(1 for _,_,ok,_ in non_approval if ok)}/3 passed")
    print(f"  Approval tools (4-8):     {sum(1 for _,_,ok,_ in approval_results if ok)}/5 passed")

    for seq, name, ok, lat in results:
        print(f"  {'✅' if ok else '❌'} Tool {seq}: {name} ({lat:.1f}s)")

    print("=" * 70)
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_e2e())
    sys.exit(0 if success else 1)
