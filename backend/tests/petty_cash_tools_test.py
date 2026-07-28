"""Test script for manage_petty_cash tool on PostgreSQL."""
import sys, os
from decimal import Decimal
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.models import Base, PettyCashFund
from tools.petty_cash_tools import (
    ManagePettyCashInput,
    ManagePettyCashOutput,
    PettyCashTransactionItem,
    manage_petty_cash,
)
from tests.test_helpers import TEST_DATABASE_URL

engine = create_engine(TEST_DATABASE_URL, echo=False)


def setup_test_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    fund = PettyCashFund(
        fund_id="PC-001",
        fund_name="Main Petty Cash",
        current_balance=Decimal("5000.00"),
    )
    db.add(fund)
    db.commit()
    return db


def run_test(name: str, func) -> bool:
    try:
        func()
        print(f"PASS: {name}")
        return True
    except AssertionError as e:
        print(f"FAIL: {name} — {e}")
        return False
    except Exception as e:
        print(f"FAIL: {name} — {type(e).__name__}: {e}")
        return False


def test_expense_exceeds_balance():
    db = setup_test_db()
    try:
        inp = ManagePettyCashInput(
            action="expense", fund_id="PC-001", amount=Decimal("6000.00"),
            description="Office supplies", paid_by="Ali", replenishment_threshold=Decimal("5000.00"))
        result = manage_petty_cash(inp, db)
        assert result.needs_replenishment is True
        assert result.current_balance == Decimal("-1000.00")
        assert result.message == "Balance is now negative — replenish immediately"
        print(f"  Output: {result.model_dump_json(indent=2)}")
    finally:
        db.close()


def test_check_replenishment_sufficient():
    db = setup_test_db()
    try:
        inp = ManagePettyCashInput(
            action="check_replenishment", fund_id="PC-001", replenishment_threshold=Decimal("5000.00"))
        result = manage_petty_cash(inp, db)
        assert result.needs_replenishment is False
        assert result.message == "Balance is sufficient"
        print(f"  Output: {result.model_dump_json(indent=2)}")
    finally:
        db.close()


def test_fund_id_not_found():
    db = setup_test_db()
    try:
        inp = ManagePettyCashInput(action="check_replenishment", fund_id="PC-999")
        try:
            manage_petty_cash(inp, db)
            raise AssertionError("No error raised")
        except ValueError as e:
            assert str(e) == "Petty cash fund not found"
        print("  Correctly raised ValueError: Petty cash fund not found")
    finally:
        db.close()


def test_add_fund_zero():
    db = setup_test_db()
    try:
        inp = ManagePettyCashInput(action="add_fund", fund_id="PC-001", amount=Decimal("0.00"))
        try:
            manage_petty_cash(inp, db)
            raise AssertionError("No error raised")
        except ValueError as e:
            assert str(e) == "Add amount must be greater than zero"
        print("  Correctly raised ValueError: Add amount must be greater than zero")
    finally:
        db.close()


def test_normal_expense():
    db = setup_test_db()
    try:
        inp = ManagePettyCashInput(
            action="expense", fund_id="PC-001", amount=Decimal("2000.00"),
            description="Office supplies", paid_by="Ali", replenishment_threshold=Decimal("5000.00"))
        result = manage_petty_cash(inp, db)
        assert result.current_balance == Decimal("3000.00")
        assert result.needs_replenishment is True
        assert result.transactions[0].action == "expense"
        print(f"  Output: {result.model_dump_json(indent=2)}")
    finally:
        db.close()


def test_add_fund_action():
    db = setup_test_db()
    try:
        inp = ManagePettyCashInput(
            action="add_fund", fund_id="PC-001", amount=Decimal("1500.00"),
            description="Top up from bank", paid_by="Finance")
        result = manage_petty_cash(inp, db)
        assert result.current_balance == Decimal("6500.00")
        assert result.needs_replenishment is False
        print(f"  Output: {result.model_dump_json(indent=2)}")
    finally:
        db.close()


def test_check_replenishment_action():
    db = setup_test_db()
    try:
        inp = ManagePettyCashInput(
            action="check_replenishment", fund_id="PC-001", replenishment_threshold=Decimal("4000.00"))
        result = manage_petty_cash(inp, db)
        assert result.needs_replenishment is False
        assert result.message == "Balance is sufficient"
        print(f"  Output: {result.model_dump_json(indent=2)}")
    finally:
        db.close()


def main():
    print("=" * 60)
    print("Petty Cash Tools — Test Suite (PostgreSQL)")
    print("=" * 60)
    tests = [
        ("Normal expense recording", test_normal_expense),
        ("Add fund action", test_add_fund_action),
        ("Check replenishment (sufficient balance)", test_check_replenishment_action),
        ("Edge case a: Expense exceeds balance", test_expense_exceeds_balance),
        ("Edge case b: check_replenishment sufficient balance", test_check_replenishment_sufficient),
        ("Edge case c: fund_id not found", test_fund_id_not_found),
        ("Edge case d: add_fund zero amount", test_add_fund_zero),
    ]
    passed, failed = 0, 0
    for name, func in tests:
        if run_test(name, func): passed += 1
        else: failed += 1
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("=" * 60)


if __name__ == "__main__":
    main()
