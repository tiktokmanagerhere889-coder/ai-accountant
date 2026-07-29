"""Agent 7 E2E test — real Groq API through Orchestrator.

Tests all 8 tools: 4 non-approval + 4 approval. Filing tools gated by confirm=True.
"""
import sys, os, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

if sys.platform == "win32":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1, errors="replace", closefd=False)

from datetime import date, timedelta
from decimal import Decimal

from db.models import (
    JournalEntry, TaxRate, EobiRate, Contact,
)
from agent_defs.orchestrator import run_orchestrator


def seed_data():
    from db.database import init_db, get_session
    init_db()
    s = get_session()
    for t in [JournalEntry, TaxRate, EobiRate, Contact]:
        s.query(t).delete()
    s.commit()

    # Tax rates
    s.add(TaxRate(tax_type="wht_service", rate=Decimal("8"), effective_from=date(2025,1,1), effective_to=None, description="WHT on services"))
    s.add(TaxRate(tax_type="wht_supply", rate=Decimal("4"), effective_from=date(2025,1,1), effective_to=None, description="WHT on supplies"))
    s.add(TaxRate(tax_type="amt_company", rate=Decimal("1.5"), effective_from=date(2025,1,1), effective_to=None, description="AMT for companies"))

    # EOBI rates
    s.add(EobiRate(rate_type="standard", rate=Decimal("5"), employee_rate=Decimal("2.5"),
                   effective_from=date(2025,1,1), effective_to=None,
                   description="Standard EOBI", max_insurable_amount=Decimal("50000")))

    # Journal entries for July 2026
    s.add(JournalEntry(entry_id="JE-REV-001", description="Sales revenue", posted_date=date(2026,7,15), reference="INV-001",
        debit_account="1000-Cash", debit_amount=Decimal("500000.00"), credit_account="4000-Sales Revenue", credit_amount=Decimal("500000.00"), status="posted"))
    s.add(JournalEntry(entry_id="JE-EXP-001", description="Purchase of goods", posted_date=date(2026,7,10), reference=None,
        debit_account="5000-Cost of Goods Sold", debit_amount=Decimal("200000.00"), credit_account="1000-Cash", credit_amount=Decimal("200000.00"), status="posted"))
    s.add(JournalEntry(entry_id="JE-EXP-002", description="Office rent", posted_date=date(2026,7,5), reference=None,
        debit_account="6000-Rent Expense", debit_amount=Decimal("50000.00"), credit_account="1000-Cash", credit_amount=Decimal("50000.00"), status="posted"))
    s.add(JournalEntry(entry_id="JE-EXP-003", description="Salary expense", posted_date=date(2026,7,28), reference=None,
        debit_account="6100-Salary Expense", debit_amount=Decimal("150000.00"), credit_account="1000-Cash", credit_amount=Decimal("150000.00"), status="posted"))

    s.commit()
    s.close()
    print("  Seed data ready")


async def run_e2e():
    print("=" * 70)
    print("E2E TEST: Agent 7 (Tax)")
    print("Orchestrator -> Tax Agent -> 8 tools")
    print("=" * 70)

    results = []

    async def test(seq, name, query):
        print(f"\n  [{seq}/8] {name}")
        print(f"  Q: {query[:80]}...")
        start = asyncio.get_event_loop().time()
        try:
            resp = await run_orchestrator(query)
            elapsed = asyncio.get_event_loop().time() - start
            safe = resp[:300].encode("utf-8", errors="replace").decode("utf-8", errors="replace")
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

    # Tool 1: calculate_withholding_tax (No approval)
    await test(1, "Withholding Tax", "Calculate withholding tax on a payment of 50000 for services dated 2026-07-15")

    # Tool 2: get_tax_planning_advice (No approval)
    await test(2, "Tax Planning Advice", "Give me tax planning advice for fiscal year 2026")

    # Tool 3: calculate_advance_minimum_tax (No approval)
    await test(3, "Advance Minimum Tax", "Calculate advance minimum tax for a company with 10 million turnover for fiscal year 2026")

    # Tool 4: calculate_eobi_deductions (No approval)
    await test(4, "EOBI Deductions", "Calculate EOBI deductions on a gross salary of 45000 for period 7 fiscal year 2026")

    # Tool 5: adjust_sales_tax_input_output (Approval)
    await test(5, "Sales Tax Adjustment", "Adjust sales tax for period 7 fiscal year 2026. Output tax override 50000, input tax override 30000")

    # Tool 6: flag_tax_exemption_zero_rating (Approval)
    await test(6, "Flag Tax Exemption", "Flag zero-rated or tax exempt transactions for fiscal year 2026")

    # Tool 7: prepare_sales_tax_filing (Approval + confirm)
    await test(7, "Sales Tax Filing", "Prepare sales tax filing for period 7 fiscal year 2026 with confirm=True")

    # Tool 8: prepare_income_tax_filing (Approval + confirm)
    await test(8, "Income Tax Filing", "Prepare income tax filing for fiscal year 2026 with confirm=True")

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
