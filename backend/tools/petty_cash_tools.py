from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import PettyCashFund, PettyCashTransaction
from tools.schemas import (
    ManagePettyCashInput,
    ManagePettyCashOutput,
    PettyCashTransactionItem,
)


def _generate_transaction_id(db: Session) -> str:
    result = db.execute(
        select(PettyCashTransaction).order_by(PettyCashTransaction.id.desc())
    ).scalars().first()
    if result is None:
        return "PCT-001"
    last_id = result.transaction_id
    number = int(last_id.split("-")[1]) + 1
    return f"PCT-{number:03d}"


def manage_petty_cash(input: ManagePettyCashInput, db: Session) -> ManagePettyCashOutput:
    """Handle petty cash operations: expense, add_fund, check_replenishment."""
    action = input.action
    fund_id = input.fund_id
    amount = input.amount
    description = input.description
    paid_by = input.paid_by
    threshold = input.replenishment_threshold

    if fund_id is None:
        raise ValueError("Petty cash fund not found")

    fund = db.execute(select(PettyCashFund).where(PettyCashFund.fund_id == fund_id)).scalar_one_or_none()
    if fund is None:
        raise ValueError("Petty cash fund not found")

    transactions: list[PettyCashTransactionItem] = []
    message: str | None = None
    needs_replenishment = False

    if action == "expense":
        if amount is None:
            raise ValueError("Amount is required for expense action")

        new_balance = fund.current_balance - amount
        needs_replenishment = new_balance < threshold

        if new_balance < Decimal("0.00"):
            message = "Balance is now negative - replenish immediately"
        elif needs_replenishment:
            message = "Replenishment recommended - balance below threshold"

        txn_id = _generate_transaction_id(db)
        txn = PettyCashTransaction(
            transaction_id=txn_id, fund_id=fund_id, action="expense",
            amount=amount, description=description or "", paid_by=paid_by or "",
            date=date.today(), remaining_balance=new_balance,
        )
        db.add(txn)
        fund.current_balance = new_balance
        db.commit()
        db.refresh(txn)

        transactions.append(PettyCashTransactionItem(
            transaction_id=txn.transaction_id, fund_id=fund_id,
            action="expense", amount=amount, description=description,
            paid_by=paid_by, date=txn.date, remaining_balance=new_balance,
        ))

    elif action == "add_fund":
        if amount is None or amount <= Decimal("0.00"):
            raise ValueError("Add amount must be greater than zero")

        new_balance = fund.current_balance + amount
        txn_id = _generate_transaction_id(db)
        txn = PettyCashTransaction(
            transaction_id=txn_id, fund_id=fund_id, action="add_fund",
            amount=amount, description=description or "", paid_by=paid_by or "",
            date=date.today(), remaining_balance=new_balance,
        )
        db.add(txn)
        fund.current_balance = new_balance
        db.commit()
        db.refresh(txn)

        transactions.append(PettyCashTransactionItem(
            transaction_id=txn.transaction_id, fund_id=fund_id,
            action="add_fund", amount=amount, description=description,
            paid_by=paid_by, date=txn.date, remaining_balance=new_balance,
        ))

    elif action == "check_replenishment":
        needs_replenishment = fund.current_balance < threshold
        message = "Replenishment recommended - balance below threshold" if needs_replenishment else "Balance is sufficient"

    else:
        raise ValueError(f"Unknown action: {action}")

    return ManagePettyCashOutput(
        fund_id=fund_id, fund_name=fund.fund_name,
        current_balance=fund.current_balance, threshold=threshold,
        needs_replenishment=needs_replenishment,
        transactions=transactions, message=message,
    )
