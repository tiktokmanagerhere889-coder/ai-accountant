from __future__ import annotations

from decimal import Decimal
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import CashPosition
from tools.schemas import CheckCashPositionInput, CheckCashPositionOutput


def check_cash_position(input: CheckCashPositionInput, db: Session) -> CheckCashPositionOutput:
    """Query cash_position table. Returns deterministic closing balance — no AI reasoning."""
    as_of_date = input.as_of_date
    account_id = input.account_id

    query = select(CashPosition).where(CashPosition.as_of_date == as_of_date)
    if account_id is not None:
        query = query.where(CashPosition.account_id == account_id)

    results = db.execute(query).scalars().all()

    if account_id is not None and len(results) == 0:
        raise ValueError("Account not found")

    if len(results) == 0:
        return CheckCashPositionOutput(
            account_id=account_id or "ALL",
            account_name="All Cash Accounts" if account_id is None else "Unknown",
            opening_balance=Decimal("0.00"),
            total_debits=Decimal("0.00"),
            total_credits=Decimal("0.00"),
            closing_balance=Decimal("0.00"),
            currency="PKR",
            as_of_date=as_of_date,
            warning=False,
        )

    total_opening = sum(r.opening_balance for r in results)
    total_debits = sum(r.total_debits for r in results)
    total_credits = sum(r.total_credits for r in results)
    total_closing = sum(r.closing_balance for r in results)
    first = results[0]
    warning = total_closing < Decimal("0.00")

    details = None
    if account_id is None and len(results) > 1:
        details = []
        for r in results:
            details.append({
                "account_id": r.account_id,
                "account_name": r.account_name,
                "opening_balance": r.opening_balance,
                "total_debits": r.total_debits,
                "total_credits": r.total_credits,
                "closing_balance": r.closing_balance,
            })

    return CheckCashPositionOutput(
        account_id=account_id or "ALL",
        account_name="All Cash Accounts" if account_id is None else first.account_name,
        opening_balance=total_opening,
        total_debits=total_debits,
        total_credits=total_credits,
        closing_balance=total_closing,
        currency=first.currency,
        as_of_date=as_of_date,
        warning=warning,
        details=details,
    )
