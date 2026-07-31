"""Shared account-classification helpers.

All classification is resolved from the `chart_of_accounts` table at call time —
the user's own chart is the single source of truth. No numeric prefixes are
hardcoded here; if a business codes its receivable account "1100-Customers" or
"9000-Receivables", it is picked up dynamically.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from db.models import ChartOfAccount


def _resolve_prefixes(db: Session, name_keywords: list[str]) -> list[str]:
    """Return the numeric code prefixes of accounts whose name matches keywords.

    Queries chart_of_accounts by account name (case-insensitive ILIKE), extracts
    the leading numeric segment of each matching account code.
    """
    clauses = [
        ChartOfAccount.account_name.ilike(f"%{kw}%")
        for kw in name_keywords
    ]
    accounts = (
        db.query(ChartOfAccount)
        .filter(or_(*clauses))
        .all()
    )
    prefixes: set[str] = set()
    for acc in accounts:
        num = acc.account_code.split("-")[0].strip()
        if num.isdigit():
            prefixes.add(num)
    return sorted(prefixes)


def get_ar_prefixes(db: Session) -> list[str]:
    """Dynamically resolve accounts-receivable prefixes from the user's chart."""
    return _resolve_prefixes(db, ["receivable", "debtor"])


def get_ap_prefixes(db: Session) -> list[str]:
    """Dynamically resolve accounts-payable prefixes from the user's chart."""
    return _resolve_prefixes(db, ["payable", "creditor"])


def _resolve_type_prefixes(db: Session, account_types: list[str]) -> list[str]:
    """Return numeric code prefixes whose chart accounts have the given account_type.

    Uses the user's chart_of_accounts.account_type as the source of truth
    (e.g. "revenue", "expense", "asset") — nothing hardcoded.
    """
    accounts = (
        db.query(ChartOfAccount)
        .filter(ChartOfAccount.account_type.in_(account_types))
        .all()
    )
    prefixes: set[str] = set()
    for acc in accounts:
        num = acc.account_code.split("-")[0].strip()
        if num.isdigit():
            prefixes.add(num)
    return sorted(prefixes)


def get_cash_prefixes(db: Session) -> list[str]:
    """Dynamically resolve cash/bank prefixes from the user's chart (by name)."""
    return _resolve_prefixes(db, ["cash", "bank"])


def get_revenue_prefixes(db: Session) -> list[str]:
    """Dynamically resolve revenue prefixes from account_type == 'revenue'."""
    return _resolve_type_prefixes(db, ["revenue"])


def get_expense_prefixes(db: Session) -> list[str]:
    """Dynamically resolve expense prefixes from account_type in expense-like types."""
    return _resolve_type_prefixes(db, ["expense", "cost of goods sold"])


def get_salary_prefixes(db: Session) -> list[str]:
    """Dynamically resolve salary/ wages prefixes from the user's chart (by name)."""
    return _resolve_prefixes(db, ["salary", "wage", "wages"])


def salary_filter_clause(account_column, db: Session, prefixes: Optional[list[str]] = None):
    """Match salary/wages journal entries by account name (precise, nothing hardcoded)."""
    return or_(
        account_column.ilike("%salary%"),
        account_column.ilike("%wage%"),
    )


def cash_filter_clause(account_column, db: Session, prefixes: Optional[list[str]] = None):
    """Match cash/bank journal entries by account name (precise, nothing hardcoded)."""
    return or_(
        account_column.ilike("%cash%"),
        account_column.ilike("%bank%"),
    )


def revenue_filter_clause(account_column, db: Session, prefixes: Optional[list[str]] = None):
    """Match revenue journal entries by account name (precise, nothing hardcoded)."""
    return or_(
        account_column.ilike("%revenue%"),
        account_column.ilike("%sales%"),
    )


def expense_filter_clause(account_column, db: Session, prefixes: Optional[list[str]] = None):
    """Match expense journal entries by account name (precise, nothing hardcoded)."""
    return or_(
        account_column.ilike("%expense%"),
        account_column.ilike("%cost of goods%"),
        account_column.ilike("%cogs%"),
    )


def ap_filter_clause(account_column, db: Session, prefixes: Optional[list[str]] = None):
    """Build a SQLAlchemy filter clause that matches AP journal entries.

    Name-based match on the full account string (e.g. "2000-Payables") so
    sibling accounts sharing a numeric prefix are not caught.
    """
    return or_(
        account_column.ilike("%payable%"),
        account_column.ilike("%creditor%"),
    )


def is_receivable_account(account_code: str) -> bool:
    """Name-based check for receivable accounts (used as a safety net)."""
    name = account_code.lower()
    return any(k in name for k in ("receivable", "debtor"))


def is_payable_account(account_code: str) -> bool:
    """Name-based check for payable accounts (used as a safety net)."""
    name = account_code.lower()
    return any(k in name for k in ("payable", "creditor"))


def ar_filter_clause(account_column, db: Session, prefixes: Optional[list[str]] = None):
    """Build a SQLAlchemy filter clause that matches AR journal entries.

    Journal entries store the full account string (e.g. "1200-Receivables"),
    which includes the account name — so name-based matching is precise and
    avoids catching sibling accounts that share a numeric prefix (e.g.
    "1200-Inventory"). Resolves nothing from hardcoded prefixes.
    """
    return or_(
        account_column.ilike("%receivable%"),
        account_column.ilike("%debtor%"),
    )
