"""Test script for check_cash_position tool on PostgreSQL."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from decimal import Decimal
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, JournalEntry
from tools.schemas import CheckCashPositionInput
from tools.cash_tools import check_cash_position

from tests.test_helpers import TEST_DATABASE_URL

engine = create_engine(TEST_DATABASE_URL, echo=False)


def run_tests():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    today = date(2026, 7, 28)
    session.add_all([
        JournalEntry(entry_id="JE-001", description="Opening balance", posted_date=date(2026, 7, 1),
            debit_account="1000-Cash", debit_amount=Decimal("500000.00"),
            credit_account="3000-Equity", credit_amount=Decimal("500000.00"), status="posted"),
        JournalEntry(entry_id="JE-002", description="Office rent", posted_date=date(2026, 7, 5),
            debit_account="6000-Office Rent", debit_amount=Decimal("120000.00"),
            credit_account="1000-Cash", credit_amount=Decimal("120000.00"), status="posted"),
        JournalEntry(entry_id="JE-003", description="Client payment", posted_date=date(2026, 7, 10),
            debit_account="1000-Cash", debit_amount=Decimal("45000.00"),
            credit_account="4000-Revenue", credit_amount=Decimal("45000.00"), status="posted"),
        JournalEntry(entry_id="JE-004", description="Large expense", posted_date=date(2026, 7, 15),
            debit_account="6000-Office Rent", debit_amount=Decimal("600000.00"),
            credit_account="1000-Cash", credit_amount=Decimal("600000.00"), status="posted"),
    ])
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

    def t1():
        r = check_cash_position(CheckCashPositionInput(as_of_date=date(2026, 6, 30)), session)
        assert r.closing_balance == Decimal("0.00")

    def t2():
        r = check_cash_position(CheckCashPositionInput(as_of_date=today, account_id="9999-Nope"), session)
        assert "not found" in r.account_name.lower()

    def t3():
        r = check_cash_position(CheckCashPositionInput(as_of_date=today, account_id="1000-Cash"), session)
        assert r.closing_balance < 0
        assert r.warning == True

    def t4():
        r = check_cash_position(CheckCashPositionInput(as_of_date=date(2026, 7, 10)), session)
        assert r.account_id == "ALL"

    def t5():
        r = check_cash_position(CheckCashPositionInput(as_of_date=date(2026, 7, 10), account_id="1000-Cash"), session)
        assert r.total_debits == Decimal("545000.00")

    t("No transactions -> zero balance", t1)
    t("Account not found -> graceful response", t2)
    t("Negative balance -> warning=True", t3)
    t("Multi-account consolidated", t4)
    t("Single account calculation", t5)

    session.close()
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results: print(f"  [{ok}] {name}")
    print(f"\nResults: {passed}/{total} passed\n")
    return passed == total


if __name__ == "__main__":
    sys.exit(0 if run_tests() else 1)
