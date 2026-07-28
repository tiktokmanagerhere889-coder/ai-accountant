"""Test script for check_bank_transactions tool."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from decimal import Decimal
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from db.models import Base, BankTransaction, BankAccount
from tools.schemas import CheckBankTransactionsInput
from tools.bank_tools import check_bank_transactions


def run_tests():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    s = SessionLocal()

    s.add(BankAccount(account_id="BA-001", account_name="HBL Business Account", bank_name="HBL"))
    s.add_all([
        BankTransaction(transaction_id="BT-001", date=date(2026, 7, 25), description="Customer payment INV-045",
                        amount=Decimal("150000.00"), type="credit", status="cleared", reference="INV-045",
                        balance_after=Decimal("2350000.00"), account_id="BA-001"),
        BankTransaction(transaction_id="BT-002", date=date(2026, 7, 26), description="Rent payment",
                        amount=Decimal("50000.00"), type="debit", status="cleared", reference="RENT-07",
                        balance_after=Decimal("2300000.00"), account_id="BA-001"),
        BankTransaction(transaction_id="BT-003", date=date(2026, 7, 27), description="Utilities bill",
                        amount=Decimal("15000.00"), type="debit", status="pending", reference="UTIL-07",
                        balance_after=Decimal("2285000.00"), account_id="BA-001"),
        BankTransaction(transaction_id="BT-004", date=date(2026, 7, 28), description="Client payment INV-046",
                        amount=Decimal("200000.00"), type="credit", status="pending", reference="INV-046",
                        balance_after=Decimal("2485000.00"), account_id="BA-001"),
        BankTransaction(transaction_id="BT-005", date=date(2026, 7, 24), description="Bank charge",
                        amount=Decimal("500.00"), type="debit", status="reconciled", reference="CHG-07",
                        balance_after=Decimal("2499500.00"), account_id="BA-001"),
    ])
    s.commit()

    results = []

    def t(name, fn):
        try:
            fn()
            print(f"  PASS: {name}")
            results.append((name, True))
        except Exception as e:
            print(f"  FAIL: {name} — {type(e).__name__}: {e}")
            results.append((name, False))

    def t1():
        r = check_bank_transactions(CheckBankTransactionsInput(from_date=date(2026, 1, 1), to_date=date(2026, 1, 31)), s)
        assert r.total_count == 0
        assert len(r.transactions) == 0

    def t2():
        try:
            check_bank_transactions(CheckBankTransactionsInput(account_id="BA-999", from_date=date(2026, 1, 1), to_date=date(2026, 7, 31)), s)
            assert False
        except ValueError as e:
            assert "Bank account not found" in str(e)

    def t3():
        try:
            check_bank_transactions(CheckBankTransactionsInput(from_date=date(2026, 7, 31), to_date=date(2026, 1, 1)), s)
            assert False
        except ValueError as e:
            assert "from_date must be before" in str(e)

    def t4():
        r = check_bank_transactions(CheckBankTransactionsInput(from_date=date(2026, 7, 1), to_date=date(2026, 7, 31), limit=2), s)
        assert r.truncated == True
        assert len(r.transactions) == 2

    def t5():
        r = check_bank_transactions(CheckBankTransactionsInput(from_date=date(2026, 7, 1), to_date=date(2026, 7, 31), status="cleared"), s)
        assert r.total_count == 2

    t("No transactions → empty list", t1)
    t("Account not found → ValueError", t2)
    t("from_date > to_date → ValueError", t3)
    t("Limit reached → truncated=True", t4)
    t("Status filter works", t5)

    s.close()
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results: print(f"  [{ok}] {name}")
    print(f"\nResults: {passed}/{total} passed\n")
    return passed == total


if __name__ == "__main__":
    sys.exit(0 if run_tests() else 1)
