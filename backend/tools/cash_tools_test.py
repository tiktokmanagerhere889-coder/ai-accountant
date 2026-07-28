"""Test script for check_cash_position tool."""
import sys
import os
from decimal import Decimal
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.models import Base, CashPosition
from tools.schemas import CheckCashPositionInput
from tools.cash_tools import check_cash_position


def run_tests():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    session = Session(bind=engine)

    today = date(2026, 7, 28)
    yesterday = date(2026, 7, 27)

    # Seed data (omit id — autoincrement handles it)
    session.add(CashPosition(account_id="CA-001", account_name="Main Cash", as_of_date=today,
        opening_balance=Decimal("500000.00"), total_debits=Decimal("120000.00"),
        total_credits=Decimal("45000.00"), closing_balance=Decimal("575000.00"), currency="PKR"))
    session.add(CashPosition(account_id="CA-002", account_name="Petty Cash", as_of_date=today,
        opening_balance=Decimal("10000.00"), total_debits=Decimal("2000.00"),
        total_credits=Decimal("1500.00"), closing_balance=Decimal("10500.00"), currency="PKR"))
    session.add(CashPosition(account_id="CA-003", account_name="Overdrawn Account", as_of_date=today,
        opening_balance=Decimal("5000.00"), total_debits=Decimal("10000.00"),
        total_credits=Decimal("2000.00"), closing_balance=Decimal("-3000.00"), currency="PKR"))
    session.add(CashPosition(account_id="CA-004", account_name="Savings Account", as_of_date=yesterday,
        opening_balance=Decimal("200000.00"), total_debits=Decimal("0.00"),
        total_credits=Decimal("0.00"), closing_balance=Decimal("200000.00"), currency="PKR"))
    session.commit()

    results = []

    def t(name, fn):
        try:
            fn()
            print(f"  PASS: {name}")
            results.append((name, True))
        except Exception as e:
            print(f"  FAIL: {name} — {type(e).__name__}: {e}")
            results.append((name, False))

    # Test 1: No transactions for date
    def t1():
        r = check_cash_position(CheckCashPositionInput(as_of_date=date(2026, 7, 27), account_id="CA-004"), session)
        assert r.opening_balance == Decimal("200000.00")
        assert r.total_debits == Decimal("0.00")
        assert r.total_credits == Decimal("0.00")
        assert r.closing_balance == Decimal("200000.00")
        assert r.warning == False

    # Test 2: Account not found
    def t2():
        try:
            check_cash_position(CheckCashPositionInput(as_of_date=today, account_id="CA-999"), session)
            assert False, "Should raise"
        except ValueError as e:
            assert "Account not found" in str(e)

    # Test 3: Negative balance → warning
    def t3():
        r = check_cash_position(CheckCashPositionInput(as_of_date=today, account_id="CA-003"), session)
        assert r.closing_balance < Decimal("0.00")
        assert r.warning == True

    # Test 4: Multiple accounts consolidated
    def t4():
        r = check_cash_position(CheckCashPositionInput(as_of_date=today), session)
        assert r.account_id == "ALL"
        assert r.details is not None
        assert len(r.details) == 3

    # Test 5: Normal single account
    def t5():
        r = check_cash_position(CheckCashPositionInput(as_of_date=today, account_id="CA-001"), session)
        assert r.closing_balance == Decimal("575000.00")
        assert r.account_name == "Main Cash"

    t("No transactions → opening balance", t1)
    t("Account not found → ValueError", t2)
    t("Negative balance → warning=True", t3)
    t("Multi-account consolidated", t4)
    t("Normal single account query", t5)

    session.close()
    engine.dispose()

    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results: print(f"  [{ok}] {name}")
    print(f"\nResults: {passed}/{total} passed\n")
    return passed == total


if __name__ == "__main__":
    all_passed = run_tests()
    sys.exit(0 if all_passed else 1)
