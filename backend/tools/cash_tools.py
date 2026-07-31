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
    # Normalize "ALL" (case-insensitive) to None → consolidated cash view.
    # This lets users type ALL in the account field to see the full cash
    # position instead of the literal account "ALL" not being found.
    account_filter = input.account_id
    if account_filter is not None and account_filter.strip().upper() == "ALL":
        account_filter = None

    query = select(JournalEntry).where(
        JournalEntry.status == "posted",
        JournalEntry.posted_date <= input.as_of_date,
    )

    if account_filter is not None:
        query = query.where(
            (JournalEntry.debit_account == account_filter) |
            (JournalEntry.credit_account == account_filter)
        )

    entries = db.execute(query).scalars().all()

    if account_filter is not None and not entries:
        return CheckCashPositionOutput(
            account_id=account_filter,
            account_name=f"Account '{account_filter}' not found",
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
            account_id=account_filter or "ALL",
            account_name="All Cash Accounts" if account_filter is None else "Unknown",
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

    if account_filter is not None:
        bal = account_balances.get(account_filter, {"debits": Decimal("0.00"), "credits": Decimal("0.00")})
        closing = bal["debits"] - bal["credits"]
        return CheckCashPositionOutput(
            account_id=account_filter,
            account_name=account_filter,
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
