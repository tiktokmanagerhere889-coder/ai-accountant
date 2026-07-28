from __future__ import annotations

import sys
import os
from decimal import Decimal
from datetime import date

# Ensure the backend directory is on the path so that `db` and `tools` are importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from db.models import Base, PettyCashFund
from tools.petty_cash_tools import (
    ManagePettyCashInput,
    ManagePettyCashOutput,
    PettyCashTransactionItem,
    manage_petty_cash,
)

TEST_DB_URL = "sqlite:///:memory:"


def setup_test_db() -> Session:
    """Create an in-memory SQLite DB with the petty cash schema and seed one fund."""
    engine = create_engine(TEST_DB_URL, echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    fund = PettyCashFund(
        id=1,
        fund_id="PC-001",
        fund_name="Main Petty Cash",
        current_balance=Decimal("5000.00"),
    )
    db.add(fund)
    db.commit()
    return db


def run_test(name: str, func) -> bool:
    """Run a test function and print PASS/FAIL."""
    try:
        func()
        print(f"PASS: {name}")
        return True
    except AssertionError as e:
        print(f"FAIL: {name} — {e}")
        return False
    except Exception as e:
        print(f"FAIL: {name} — unexpected error: {type(e).__name__}: {e}")
        return False


def test_expense_exceeds_balance() -> None:
    """Edge case a: Expense exceeds balance → needs_replenishment true, transaction recorded with warning."""
    db = setup_test_db()
    try:
        inp = ManagePettyCashInput(
            action="expense",
            fund_id="PC-001",
            amount=Decimal("6000.00"),
            description="Office supplies",
            paid_by="Ali",
            replenishment_threshold=Decimal("5000.00"),
        )
        result = manage_petty_cash(inp, db)

        assert result.needs_replenishment is True, f"Expected needs_replenishment=True, got {result.needs_replenishment}"
        assert result.current_balance == Decimal("-1000.00"), f"Expected balance -1000, got {result.current_balance}"
        assert len(result.transactions) == 1, f"Expected 1 transaction, got {len(result.transactions)}"
        assert result.transactions[0].remaining_balance == Decimal("-1000.00")
        assert result.message == "Balance is now negative — replenish immediately"

        print(f"  Output JSON: {result.model_dump_json(indent=2)}")
    finally:
        db.close()


def test_check_replenishment_sufficient_balance() -> None:
    """Edge case b: check_replenishment with sufficient balance → needs_replenishment false, message 'Balance is sufficient'."""
    db = setup_test_db()
    try:
        inp = ManagePettyCashInput(
            action="check_replenishment",
            fund_id="PC-001",
            replenishment_threshold=Decimal("5000.00"),
        )
        result = manage_petty_cash(inp, db)

        assert result.needs_replenishment is False, f"Expected needs_replenishment=False, got {result.needs_replenishment}"
        assert result.message == "Balance is sufficient", f"Expected 'Balance is sufficient', got '{result.message}'"
        assert result.current_balance == Decimal("5000.00")

        print(f"  Output JSON: {result.model_dump_json(indent=2)}")
    finally:
        db.close()


def test_fund_id_not_found() -> None:
    """Edge case c: fund_id not found → ValueError 'Petty cash fund not found'."""
    db = setup_test_db()
    try:
        inp = ManagePettyCashInput(
            action="check_replenishment",
            fund_id="PC-999",
            replenishment_threshold=Decimal("5000.00"),
        )
        try:
            manage_petty_cash(inp, db)
            raise AssertionError("Expected ValueError was not raised")
        except ValueError as e:
            assert str(e) == "Petty cash fund not found", f"Expected 'Petty cash fund not found', got '{e}'"

        print("  Correctly raised ValueError: Petty cash fund not found")
    finally:
        db.close()


def test_add_fund_zero_amount() -> None:
    """Edge case d: add_fund with zero amount → ValueError 'Add amount must be greater than zero'."""
    db = setup_test_db()
    try:
        inp = ManagePettyCashInput(
            action="add_fund",
            fund_id="PC-001",
            amount=Decimal("0.00"),
            description="Top up",
        )
        try:
            manage_petty_cash(inp, db)
            raise AssertionError("Expected ValueError was not raised")
        except ValueError as e:
            assert str(e) == "Add amount must be greater than zero", f"Expected 'Add amount must be greater than zero', got '{e}'"

        print("  Correctly raised ValueError: Add amount must be greater than zero")
    finally:
        db.close()


def test_normal_expense() -> None:
    """Normal expense recording: balance reduces, transaction recorded."""
    db = setup_test_db()
    try:
        inp = ManagePettyCashInput(
            action="expense",
            fund_id="PC-001",
            amount=Decimal("2000.00"),
            description="Office supplies",
            paid_by="Ali",
            replenishment_threshold=Decimal("5000.00"),
        )
        result = manage_petty_cash(inp, db)

        assert result.current_balance == Decimal("3000.00"), f"Expected 3000, got {result.current_balance}"
        assert result.needs_replenishment is True, f"Expected needs_replenishment=True, got {result.needs_replenishment}"
        assert len(result.transactions) == 1
        txn = result.transactions[0]
        assert txn.action == "expense"
        assert txn.amount == Decimal("2000.00")
        assert txn.description == "Office supplies"
        assert txn.paid_by == "Ali"
        assert txn.remaining_balance == Decimal("3000.00")
        assert txn.fund_id == "PC-001"
        assert isinstance(txn.date, date)

        print(f"  Output JSON: {result.model_dump_json(indent=2)}")
    finally:
        db.close()


def test_add_fund_action() -> None:
    """Normal add_fund: balance increases, transaction recorded."""
    db = setup_test_db()
    try:
        inp = ManagePettyCashInput(
            action="add_fund",
            fund_id="PC-001",
            amount=Decimal("1500.00"),
            description="Top up from bank",
            paid_by="Finance",
        )
        result = manage_petty_cash(inp, db)

        assert result.current_balance == Decimal("6500.00"), f"Expected 6500, got {result.current_balance}"
        assert result.needs_replenishment is False
        assert len(result.transactions) == 1
        txn = result.transactions[0]
        assert txn.action == "add_fund"
        assert txn.amount == Decimal("1500.00")
        assert txn.remaining_balance == Decimal("6500.00")

        print(f"  Output JSON: {result.model_dump_json(indent=2)}")
    finally:
        db.close()


def test_check_replenishment_action() -> None:
    """Normal check_replenishment: balance above threshold, no replenishment needed."""
    db = setup_test_db()
    try:
        inp = ManagePettyCashInput(
            action="check_replenishment",
            fund_id="PC-001",
            replenishment_threshold=Decimal("4000.00"),
        )
        result = manage_petty_cash(inp, db)

        assert result.needs_replenishment is False
        assert result.message == "Balance is sufficient"
        assert result.current_balance == Decimal("5000.00")

        print(f"  Output JSON: {result.model_dump_json(indent=2)}")
    finally:
        db.close()


def main() -> None:
    print("=" * 60)
    print("Petty Cash Tools — Test Suite")
    print("=" * 60)

    tests = [
        ("Normal expense recording", test_normal_expense),
        ("Add fund action", test_add_fund_action),
        ("Check replenishment (sufficient balance)", test_check_replenishment_action),
        ("Edge case a: Expense exceeds balance", test_expense_exceeds_balance),
        ("Edge case b: check_replenishment sufficient balance", test_check_replenishment_sufficient_balance),
        ("Edge case c: fund_id not found", test_fund_id_not_found),
        ("Edge case d: add_fund zero amount", test_add_fund_zero_amount),
    ]

    passed = 0
    failed = 0
    for name, func in tests:
        if run_test(name, func):
            passed += 1
        else:
            failed += 1

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("=" * 60)


if __name__ == "__main__":
    main()