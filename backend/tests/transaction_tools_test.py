"""Test script for record_transaction_nl tool."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from decimal import Decimal
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, JournalEntry
from tools.schemas import RecordTransactionNLInput
from tools.transaction_tools import record_transaction_nl


def run_tests():
    results = []

    def fresh_session():
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(bind=engine)
        return sessionmaker(bind=engine)()

    def t(name, fn):
        try:
            fn()
            print(f"  PASS: {name}")
            results.append((name, True))
        except Exception as e:
            print(f"  FAIL: {name} — {type(e).__name__}: {e}")
            results.append((name, False))

    # Test 1: Normal transaction
    def t1():
        s = fresh_session()
        s.add(JournalEntry(entry_id="JE-20260728-001", description="Office rent for July",
            posted_date=date(2026, 7, 28), reference=None,
            debit_account="6000-Office Rent", debit_amount=Decimal("50000.00"),
            credit_account="1000-Cash", credit_amount=Decimal("50000.00"), status="posted"))
        s.commit()
        r = record_transaction_nl(RecordTransactionNLInput(
            description="Paid salary 75000 for July", posted_date=date(2026, 7, 28)), s)
        assert r.status == "posted", f"Expected posted, got {r.status}"
        assert r.debit_account == "6100-Salary", f"Expected 6100-Salary, got {r.debit_account}"
        assert r.debit_amount == Decimal("75000.00"), f"Expected 75000, got {r.debit_amount}"
        assert r.entry_id != "JE-20260728-001"
        s.close()

    # Test 2: Duplicate detection
    def t2():
        s = fresh_session()
        s.add(JournalEntry(entry_id="JE-20260728-001", description="Office rent for July",
            posted_date=date(2026, 7, 28), reference=None,
            debit_account="6000-Office Rent", debit_amount=Decimal("50000.00"),
            credit_account="1000-Cash", credit_amount=Decimal("50000.00"), status="posted"))
        s.commit()
        r = record_transaction_nl(RecordTransactionNLInput(
            description="Office rent for July paid 50000", posted_date=date(2026, 7, 28)), s)
        assert r.status == "duplicate_ignored", f"Expected duplicate_ignored, got {r.status}"
        s.close()

    # Test 3: No amount in description
    def t3():
        s = fresh_session()
        try:
            record_transaction_nl(RecordTransactionNLInput(
                description="Bought office supplies", posted_date=date(2026, 7, 28)), s)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "No valid amount found" in str(e)
        s.close()

    # Test 4: Misc categorization
    def t4():
        s = fresh_session()
        r = record_transaction_nl(RecordTransactionNLInput(
            description="Paid subscription 2000 for software tools", posted_date=date(2026, 7, 28)), s)
        assert r.debit_account == "7200-Miscellaneous", f"Expected Misc, got {r.debit_account}"
        assert r.status == "posted"
        s.close()

    # Test 5: Rent categorization
    def t5():
        s = fresh_session()
        r = record_transaction_nl(RecordTransactionNLInput(
            description="Office rent paid 50000 for July", posted_date=date(2026, 7, 28)), s)
        assert r.debit_account == "6000-Office Rent", f"Expected 6000-Office Rent, got {r.debit_account}"
        assert r.debit_amount == Decimal("50000.00")
        s.close()

    t("Normal salary transaction", t1)
    t("Duplicate transaction detection", t2)
    t("No amount -> ValueError", t3)
    t("Misc category fallback", t4)
    t("Rent category mapping", t5)

    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results: print(f"  [{ok}] {name}")
    print(f"\nResults: {passed}/{total} passed\n")
    return passed == total


if __name__ == "__main__":
    sys.exit(0 if run_tests() else 1)
