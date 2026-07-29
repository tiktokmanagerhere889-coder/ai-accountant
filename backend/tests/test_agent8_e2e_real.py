"""Agent 8 E2E test — real Groq API through Orchestrator.

Tests all 4 tools: 2 non-approval + 2 approval.
"""
import sys, os, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

if sys.platform == "win32":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1, errors="replace", closefd=False)

from datetime import date, timedelta
from decimal import Decimal

from db.models import (
    JournalEntry, FlaggedEntry, StatutoryRegister, ComplianceDeadline,
)
from agent_defs.orchestrator import run_orchestrator


def seed_data():
    from db.database import init_db, get_session
    init_db()
    s = get_session()
    for t in [JournalEntry, FlaggedEntry, StatutoryRegister, ComplianceDeadline]:
        s.query(t).delete()
    s.commit()

    today = date.today()

    # Journal entries for anomaly/audit detection
    s.add(JournalEntry(entry_id="JE-001", description="Normal payroll", posted_date=today - timedelta(days=5), reference="PAY-001",
        debit_account="6100-Salary Expense", debit_amount=Decimal("150000.00"), credit_account="1000-Cash", credit_amount=Decimal("150000.00"), status="posted"))
    s.add(JournalEntry(entry_id="JE-002", description="Large round payment", posted_date=today - timedelta(days=10), reference="INV-001",
        debit_account="5000-Cost of Goods Sold", debit_amount=Decimal("500000.00"), credit_account="2000-Accounts Payable", credit_amount=Decimal("500000.00"), status="posted"))
    s.add(JournalEntry(entry_id="JE-003", description="Weekend transaction", posted_date=date(2026, 7, 11), reference="INV-002",
        debit_account="6000-Rent Expense", debit_amount=Decimal("50000.00"), credit_account="1000-Cash", credit_amount=Decimal("50000.00"), status="posted"))
    s.add(JournalEntry(entry_id="JE-004", description="Normal payroll", posted_date=today - timedelta(days=5), reference="PAY-002",
        debit_account="6100-Salary Expense", debit_amount=Decimal("150000.00"), credit_account="1000-Cash", credit_amount=Decimal("150000.00"), status="posted"))
    s.add(JournalEntry(entry_id="JE-005", description="Equity adjustment", posted_date=today - timedelta(days=3), reference="ADJ-001",
        debit_account="3100-Retained Earnings", debit_amount=Decimal("25000.00"), credit_account="1000-Cash", credit_amount=Decimal("25000.00"), status="posted"))
    s.add(JournalEntry(entry_id="JE-006", description="Office supplies", posted_date=today - timedelta(days=2), reference="INV-003",
        debit_account="6000-Office Expense", debit_amount=Decimal("45000.00"), credit_account="1000-Cash", credit_amount=Decimal("45000.00"), status="posted"))

    # Compliance deadlines
    s.add(ComplianceDeadline(deadline_id="DL-001", deadline_type="tax_filing",
        description="Sales tax filing for June 2026", due_date=today + timedelta(days=5),
        responsible_person="Accountant", status="upcoming", reminder_days=7, fiscal_year=2026))
    s.add(ComplianceDeadline(deadline_id="DL-002", deadline_type="statutory_filing",
        description="Annual return filing", due_date=today + timedelta(days=90),
        responsible_person="Company Secretary", status="upcoming", reminder_days=30, fiscal_year=2026))
    s.add(ComplianceDeadline(deadline_id="DL-003", deadline_type="audit",
        description="Q2 audit report submission", due_date=today - timedelta(days=10),
        responsible_person="Auditor", status="upcoming", reminder_days=14, fiscal_year=2026))
    s.add(ComplianceDeadline(deadline_id="DL-004", deadline_type="tax_filing",
        description="Income tax filing FY2025", due_date=today - timedelta(days=60),
        responsible_person="Accountant", status="completed", reminder_days=30, fiscal_year=2025))

    s.commit()
    s.close()
    print("  Seed data ready")


async def run_e2e():
    print("=" * 70)
    print("E2E TEST: Agent 8 (Audit & Regulatory)")
    print("Orchestrator -> Audit Agent -> 4 tools")
    print("=" * 70)

    results = []

    async def test(seq, name, query):
        print(f"\n  [{seq}/4] {name}")
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

    # Tool 1: detect_anomaly_transactions (No approval)
    await test(1, "Detect Anomalies",
        "Detect anomalies in journal entries from 2026-07-01 to 2026-07-31. Look for round amounts and weekend postings.")

    # Tool 2: get_compliance_deadlines (No approval)
    await test(2, "Compliance Deadlines",
        "Show all upcoming compliance deadlines for fiscal year 2026")

    # Tool 3: support_internal_audit (Approval)
    await test(3, "Internal Audit Support",
        "Run an internal audit for fiscal year 2026 with min severity medium")

    # Tool 4: maintain_statutory_registers (Approval)
    await test(4, "Statutory Register",
        "Add a directors register entry dated 2026-07-15: Appointment of Hassan Khan as Finance Director, reference DIR-001")

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
