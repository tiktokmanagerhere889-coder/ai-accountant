"""check_cash_position — real-time cash position from journal entries."""
from __future__ import annotations

from decimal import Decimal
from datetime import date

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from db.models import JournalEntry
from tools.account_utils import get_cash_prefixes
from tools.schemas import CheckCashPositionInput, CheckCashPositionOutput


def _is_cash_account(account_code: str, db: Session) -> bool:
    """Check if an account is a cash/bank account — resolved from the user's chart."""
    name = account_code.lower()
    if any(k in name for k in ("cash", "bank")):
        return True
    prefixes = get_cash_prefixes(db)
    if prefixes:
        return any(account_code.startswith(p) for p in prefixes)
    return False


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
        return CheckCashPositionOutput(
            account_id=input.account_id,
            account_name=f"Account '{input.account_id}' not found",
            opening_balance=Decimal("0.00"),
            total_debits=Decimal("0.00"),
            total_credits=Decimal("0.00"),
            closing_balance=Decimal("0.00"),
            currency="PKR",
            as_of_date=input.as_of_date,
            warning=False,
        )

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

    # Aggregate by account
    account_balances: dict[str, dict] = {}
    for entry in entries:
        for acc in (entry.debit_account, entry.credit_account):
            if acc not in account_balances:
                account_balances[acc] = {"debits": Decimal("0.00"), "credits": Decimal("0.00")}

        account_balances[entry.debit_account]["debits"] += entry.debit_amount
        account_balances[entry.credit_account]["credits"] += entry.credit_amount

    if input.account_id is not None:
        bal = account_balances.get(input.account_id, {"debits": Decimal("0.00"), "credits": Decimal("0.00")})
        closing = bal["debits"] - bal["credits"]
        return CheckCashPositionOutput(
            account_id=input.account_id,
            account_name=input.account_id,
            opening_balance=Decimal("0.00"),
            total_debits=bal["debits"],
            total_credits=bal["credits"],
            closing_balance=closing,
            currency="PKR",
            as_of_date=input.as_of_date,
            warning=closing < 0,
        )

    # Consolidated: only CASH accounts (resolved from the user's chart)
    cash_accounts = {acc: b for acc, b in account_balances.items() if _is_cash_account(acc, db)}
    total_debits = sum(b["debits"] for b in cash_accounts.values())
    total_credits = sum(b["credits"] for b in cash_accounts.values())
    closing_balance = total_debits - total_credits

    details = [
        {"account_id": acc, "total_debits": b["debits"], "total_credits": b["credits"],
         "net": b["debits"] - b["credits"]}
        for acc, b in sorted(cash_accounts.items())
    ] if cash_accounts else None

    return CheckCashPositionOutput(
        account_id="ALL",
        account_name="All Cash Accounts",
        opening_balance=Decimal("0.00"),
        total_debits=total_debits,
        total_credits=total_credits,
        closing_balance=closing_balance,
        currency="PKR",
        as_of_date=input.as_of_date,
        warning=closing_balance < 0,
        details=details,
    )
