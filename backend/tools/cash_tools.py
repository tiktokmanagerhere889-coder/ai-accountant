"""check_cash_position — real-time cash position from journal entries."""
from __future__ import annotations

from decimal import Decimal
from datetime import date

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from db.models import JournalEntry
from tools.schemas import CheckCashPositionInput, CheckCashPositionOutput


CASH_ACCOUNT_PREFIXES = ("1000", "1001", "1002", "1100")


def _is_cash_account(account_code: str) -> bool:
    """Check if an account code is a cash/bank account."""
    return account_code.startswith(CASH_ACCOUNT_PREFIXES)


def check_cash_position(input: CheckCashPositionInput, db: Session) -> CheckCashPositionOutput:
    """Real-time cash position aggregated from journal entries.

    Queries all posted journal entries up to as_of_date, groups by account,
    and returns the net position. Uses deterministic DB aggregation — no AI.
    """
    query = select(JournalEntry).where(
        JournalEntry.status == "posted",
        JournalEntry.posted_date <= input.as_of_date,
    )

    if input.account_id is not None:
        query = query.where(
            (JournalEntry.debit_account == input.account_id) |
            (JournalEntry.credit_account == input.account_id)
        )

    entries = db.execute(query).scalars().all()

    if input.account_id is not None and not entries:
        raise ValueError("Account not found")

    if not entries:
        return CheckCashPositionOutput(
            account_id=input.account_id or "ALL",
            account_name="All Cash Accounts" if input.account_id is None else "Unknown",
            opening_balance=Decimal("0.00"),
            total_debits=Decimal("0.00"),
            total_credits=Decimal("0.00"),
            closing_balance=Decimal("0.00"),
            currency="PKR",
            as_of_date=input.as_of_date,
            warning=False,
        )

    # Aggregate by account using cash-side entries
    account_balances: dict[str, dict] = {}
    for entry in entries:
        for acc in (entry.debit_account, entry.credit_account):
            if acc not in account_balances:
                account_balances[acc] = {"debits": Decimal("0.00"), "credits": Decimal("0.00")}

        account_balances[entry.debit_account]["debits"] += entry.debit_amount
        account_balances[entry.credit_account]["credits"] += entry.credit_amount

    # Cash account: debits increase, credits decrease
    # Expense accounts: debits increase expense (no effect on cash directly)

    if input.account_id is not None:
        bal = account_balances.get(input.account_id, {"debits": Decimal("0.00"), "credits": Decimal("0.00")})
        closing = bal["debits"] - bal["credits"]
        warning = closing < 0
        return CheckCashPositionOutput(
            account_id=input.account_id,
            account_name=input.account_id,
            opening_balance=Decimal("0.00"),
            total_debits=bal["debits"],
            total_credits=bal["credits"],
            closing_balance=closing,
            currency="PKR",
            as_of_date=input.as_of_date,
            warning=warning,
        )

    # Consolidated: all accounts
    all_debits = sum(b["debits"] for b in account_balances.values())
    all_credits = sum(b["credits"] for b in account_balances.values())

    details = [
        {"account_id": acc, "total_debits": b["debits"], "total_credits": b["credits"],
         "net": b["debits"] - b["credits"]}
        for acc, b in sorted(account_balances.items())
    ]

    return CheckCashPositionOutput(
        account_id="ALL",
        account_name="All Accounts",
        opening_balance=Decimal("0.00"),
        total_debits=all_debits,
        total_credits=all_credits,
        closing_balance=all_debits - all_credits,
        currency="PKR",
        as_of_date=input.as_of_date,
        warning=(all_debits - all_credits) < 0,
        details=details,
    )
