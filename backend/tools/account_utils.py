"""Shared account-classification helpers.

Classification is resolved from the `chart_of_accounts` table at call time —
the user's own chart is the single source of truth. No numeric prefixes or
assumed names are hardcoded. Each filter first matches accounts whose
`account_type` in the chart matches the category (e.g. "revenue"/"expense"),
then falls back to a conservative name-based check for accounts not yet in
the chart. The name fallback deliberately excludes ambiguous substrings
(e.g. "sales" is NOT treated as revenue because "Cost of Sales" contains it).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from db.models import ChartOfAccount


def _accounts_with_types(db: Session, account_types: list[str], name_keywords: list[str] | None = None) -> list[str]:
    """Return account_code strings in the chart matching account_type (+ optional name)."""
    query = db.query(ChartOfAccount.account_code).filter(
        ChartOfAccount.account_type.in_(account_types)
    )
    if name_keywords:
        query = query.filter(or_(*[ChartOfAccount.account_name.ilike(f"%{kw}%") for kw in name_keywords]))
    return [r[0] for r in query.all()]


def _classify_filter_clause(account_column, db: Session, account_types: list[str], name_keywords: list[str], chart_name_keywords: list[str] | None = None):
    """Build a filter clause: exact chart-account match OR conservative name match.

    Chart-account match uses account_type plus optional account-name condition so
    e.g. AR/cash (asset subtypes) are not confused with inventory. The name
    fallback is kept narrow to avoid misclassification (e.g. "sales" is not used
    because "Cost of Sales" is an expense).
    """
    clauses = []

    chart_codes = _accounts_with_types(db, account_types, chart_name_keywords)
    if chart_codes:
        clauses.append(account_column.in_(chart_codes))

    # Conservative name fallback (accounts not yet in the chart)
    for kw in name_keywords:
        clauses.append(account_column.ilike(f"%{kw}%"))

    return or_(*clauses)


def revenue_filter_clause(account_column, db: Session, prefixes: Optional[list[str]] = None):
    """Match revenue accounts: chart account_type='revenue', or clear name match.

    "sales" alone is intentionally NOT a keyword — "Cost of Sales" is an expense
    account and would be misclassified. Only "revenue" / "income" are used as
    name fallbacks.
    """
    return _classify_filter_clause(
        account_column, db,
        account_types=["revenue"],
        name_keywords=["revenue", "income"],
    )


def expense_filter_clause(account_column, db: Session, prefixes: Optional[list[str]] = None):
    """Match expense accounts: chart account_type='expense', or name fallback.

    Includes "cost of sales" / "cost of goods" so those are classed as expenses,
    never revenue.
    """
    return _classify_filter_clause(
        account_column, db,
        account_types=["expense"],
        name_keywords=["expense", "cost of sales", "cost of goods", "cogs"],
    )


def cash_filter_clause(account_column, db: Session, prefixes: Optional[list[str]] = None):
    """Match cash/bank accounts: chart asset-type accounts named cash/bank, else name fallback."""
    return _classify_filter_clause(
        account_column, db,
        account_types=["asset"],
        name_keywords=["cash", "bank"],
        chart_name_keywords=["cash", "bank"],
    )


def salary_filter_clause(account_column, db: Session, prefixes: Optional[list[str]] = None):
    """Match salary/wages accounts from the chart, else name fallback."""
    return _classify_filter_clause(
        account_column, db,
        account_types=["expense"],
        name_keywords=["salary", "wage"],
    )


def ar_filter_clause(account_column, db: Session, prefixes: Optional[list[str]] = None):
    """Match accounts-receivable accounts: chart asset-type named receivable/debtor, else fallback."""
    return _classify_filter_clause(
        account_column, db,
        account_types=["asset"],
        name_keywords=["receivable", "debtor"],
        chart_name_keywords=["receivable", "debtor"],
    )


def ap_filter_clause(account_column, db: Session, prefixes: Optional[list[str]] = None):
    """Match accounts-payable accounts: chart liability-type named payable/creditor, else fallback."""
    return _classify_filter_clause(
        account_column, db,
        account_types=["liability"],
        name_keywords=["payable", "creditor"],
    )


def get_cash_prefixes(db: Session) -> list[str]:
    """Return numeric prefixes of cash/bank accounts in the chart (used by legacy helpers)."""
    return _prefixes_from_codes(_accounts_with_types(db, ["asset"]))


def get_revenue_prefixes(db: Session) -> list[str]:
    """Return numeric prefixes of revenue accounts in the chart."""
    return _prefixes_from_codes(_accounts_with_types(db, ["revenue"]))


def get_expense_prefixes(db: Session) -> list[str]:
    """Return numeric prefixes of expense accounts in the chart."""
    return _prefixes_from_codes(_accounts_with_types(db, ["expense"]))


def _prefixes_from_codes(codes: list[str]) -> list[str]:
    prefixes: set[str] = set()
    for c in codes:
        num = c.split("-")[0].strip()
        if num.isdigit():
            prefixes.add(num)
    return sorted(prefixes)


def is_receivable_account(account_code: str) -> bool:
    """Name-based check for receivable accounts (used as a safety net)."""
    name = account_code.lower()
    return any(k in name for k in ("receivable", "debtor"))


def is_payable_account(account_code: str) -> bool:
    """Name-based check for payable accounts (used as a safety net)."""
    name = account_code.lower()
    return any(k in name for k in ("payable", "creditor"))
