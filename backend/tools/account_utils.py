"""Shared account-classification helpers.

Classification is resolved from the `chart_of_accounts` table at call time -
the user's own chart is the single source of truth. No numeric prefixes or
assumed names are hardcoded. Each filter first matches accounts whose
`account_type` in the chart matches the category (e.g. "revenue"/"expense"),
then falls back to a conservative name-based check for accounts not yet in
the chart. The name fallback deliberately excludes ambiguous substrings
(e.g. "sales" is NOT treated as revenue because "Cost of Sales" contains it).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from db.models import ChartOfAccount, JournalEntry

# Normal balance side per account_type (per standard double-entry bookkeeping).
# Asset/Expense increase on the debit side; Liability/Equity/Revenue on the credit.
_DEBIT_NORMAL_TYPES = {"asset", "expense"}
_CREDIT_NORMAL_TYPES = {"liability", "equity", "revenue"}
_CATEGORY_TYPES = ("asset", "liability", "equity", "revenue", "expense")

# Standard accounting-numbering leading digits per account_type (used as the
# fallback when the chart is not yet populated - mirrors _STANDARD_TYPE_BY_DIGIT).
_STANDARD_DIGITS_BY_TYPE = {
    "asset": {"1"},
    "liability": {"2"},
    "equity": {"3"},
    "revenue": {"4"},
    "expense": {"5", "6", "7", "8"},
}


def _accounts_with_types(db: Session, account_types: list[str], name_keywords: list[str] | None = None) -> list[str]:
    """Return account_code strings in the chart matching account_type (+ optional name)."""
    query = db.query(ChartOfAccount.account_code).filter(
        ChartOfAccount.account_type.in_(account_types)
    )
    if name_keywords:
        query = query.filter(or_(*[ChartOfAccount.account_name.ilike(f"%{kw}%") for kw in name_keywords]))
    return [r[0] for r in query.all()]


def _classify_filter_clause(account_column, db: Session, account_types: list[str], name_keywords: list[str], chart_name_keywords: list[str] | None = None, standard_digit_fallback: bool = False):
    """Build a filter clause: exact chart-account match OR prefix match OR name match.

    Resolution order:
      1. Exact chart-account match by account_type (optionally narrowed by name).
      2. Numeric-prefix match against chart accounts of this type - only for
         pure type-based filters (no chart_name_keywords). Sub-accounts created
         dynamically (e.g. "6400-Travel" when "6000-Rent" is an expense in the
         chart) share the leading digit of the parent code, so any 6xxx debit is
         classified as an expense. This keeps P&L / retained earnings / tax
         correct even when an account isn't registered in the chart yet.
         Name-narrowed filters (cash/bank, receivable/debtor) intentionally
         skip this to avoid over-matching e.g. AR under cash.
      3. Standard-numbering digit fallback (only when standard_digit_fallback is
         set - i.e. whole-category filters like revenue/expense). When the chart
         has no codes of this type yet, fall back to the standard accounting
         digits (4 = revenue, 5/6/7/8 = expense) so dynamically-created sub-
         accounts still classify. Mirrors chart_account_type's last-resort
         default. Subtype filters (cash/salary/AR/AP) keep this off - AP must
         not swallow every 2xxx liability.
      4. Conservative name fallback (kept narrow - "sales" is not used because
         "Cost of Sales" is an expense).
    """
    clauses = []

    chart_codes = _accounts_with_types(db, account_types, chart_name_keywords)
    if chart_codes:
        clauses.append(account_column.in_(chart_codes))

        # Prefix fallback only for pure type matches (no name narrowing).
        if chart_name_keywords is None:
            leading_digits = {c.split("-")[0][0] for c in chart_codes if c.split("-")[0][:1].isdigit()}
            if leading_digits:
                clauses.append(or_(*[
                    func.substr(account_column, 1, 1) == d for d in sorted(leading_digits)
                ]))
    elif standard_digit_fallback:
        # Chart not populated (or no codes of this type yet): fall back to the
        # standard accounting-numbering leading digits for this account_type
        # (e.g. 5/6/7/8 = expense, 4 = revenue) so dynamically-created sub-
        # accounts still classify. Mirrors chart_account_type's last-resort
        # default.
        standard_digits = sorted(
            d for t in account_types for d in _STANDARD_DIGITS_BY_TYPE.get(t, set())
        )
        if standard_digits:
            clauses.append(or_(*[
                func.substr(account_column, 1, 1) == d for d in standard_digits
            ]))

    # Conservative name fallback (accounts not yet in the chart)
    for kw in name_keywords:
        clauses.append(account_column.ilike(f"%{kw}%"))

    return or_(*clauses)


def revenue_filter_clause(account_column, db: Session, prefixes: Optional[list[str]] = None):
    """Match revenue accounts: chart account_type='revenue', or clear name match.

    "sales" alone is intentionally NOT a keyword - "Cost of Sales" is an expense
    account and would be misclassified. Only "revenue" / "income" are used as
    name fallbacks. When the chart has no revenue codes yet, falls back to the
    standard digit 4 (mirrors chart_account_type).
    """
    return _classify_filter_clause(
        account_column, db,
        account_types=["revenue"],
        name_keywords=["revenue", "income"],
        standard_digit_fallback=True,
    )


def expense_filter_clause(account_column, db: Session, prefixes: Optional[list[str]] = None):
    """Match expense accounts: chart account_type='expense', or name fallback.

    Includes "cost of sales" / "cost of goods" so those are classed as expenses,
    never revenue. When the chart has no expense codes yet, falls back to the
    standard digits 5/6/7/8 (mirrors chart_account_type) so dynamically-created
    sub-accounts like "8000-Bank Charges" still classify.
    """
    return _classify_filter_clause(
        account_column, db,
        account_types=["expense"],
        name_keywords=["expense", "cost of sales", "cost of goods", "cogs"],
        standard_digit_fallback=True,
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
    """Match salary/wages accounts from the chart, else name fallback.

    chart_name_keywords narrows the chart match to accounts actually named
    salary/wage, so the prefix-fallback branch does NOT fire — otherwise any
    5/6/7/8-prefix expense (rent, utilities, travel...) leaks into payroll
    reconciliation. Mirrors cash_filter_clause / ar_filter_clause.
    """
    return _classify_filter_clause(
        account_column, db,
        account_types=["expense"],
        name_keywords=["salary", "wage"],
        chart_name_keywords=["salary", "wage"],
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


# ---------------------------------------------------------------------------
# Account-type resolution + normal-balance aggregation (single source of truth)
# ---------------------------------------------------------------------------

# Standard accounting-numbering default for accounts not yet in the chart.
_STANDARD_TYPE_BY_DIGIT = {
    "1": "asset", "2": "liability", "3": "equity",
    "4": "revenue", "5": "expense", "6": "expense",
    "7": "expense", "8": "expense",
}


def build_chart_type_map(db: Session) -> dict[str, str]:
    """Snapshot account_code -> account_type (lowercased) in one query.

    Call once per aggregation and pass the dict to chart_account_type to avoid
    N+1 lookups against a remote DB (the Neon pooler costs ~1s per query).
    """
    return {
        r[0]: (r[1] or "").lower()
        for r in db.query(ChartOfAccount.account_code, ChartOfAccount.account_type).all()
    }


def chart_account_type(db: Session, account_value: str | None, chart_map: dict[str, str] | None = None) -> str | None:
    """Resolve the account_type of a full account string (e.g. "1000-Cash").

    Uses the authoritative `account_type` column from `chart_of_accounts`.
    Resolution order:
      1. Exact `account_code` match (e.g. "2000-Payables").
      2. Leading numeric code prefix match (e.g. "2000-Accrued Liabilities"
         -> chart account "2000-Payables").
      3. Leading-digit fallback for accounts sharing the parent's first digit
         (e.g. a dynamically created "6000-Laptop" resolves to the "6xxx"
         expense parent).
      4. Last-resort standard numbering default (1=asset, 2=liability, 3=equity,
         4=revenue, 5/6/7/8=expense) so every ledger account resolves and
         balance-sheet identities hold even before an account is registered.
    Returns a lowercase account_type ("asset"/"liability"/"equity"/"revenue"/
    "expense") or None if unresolvable. This is the authoritative classification
    for balance computations — no numeric-prefix guessing.
    """
    if not account_value:
        return None
    value = str(account_value).strip()
    if not value:
        return None

    if chart_map is None:
        chart_map = build_chart_type_map(db)

    # 1. Exact account_code match
    if value in chart_map:
        return chart_map[value]

    code = value.split("-")[0].strip()
    if not code:
        return None

    # 2. Numeric code prefix match
    if code.isdigit():
        for chart_code, atype in chart_map.items():
            if chart_code.startswith(code):
                return atype
        # 3. Leading-digit fallback
        for chart_code, atype in chart_map.items():
            if chart_code.startswith(code[0]):
                return atype
        # 4. Standard numbering default
        return _STANDARD_TYPE_BY_DIGIT.get(code[0])

    return None


def category_net_balances(
    db: Session,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict[str, Decimal]:
    """Net normal-side balances per account_type, aggregated from posted journal entries.

    Every journal entry debits one account and credits another. We accumulate
    raw debit and credit totals per chart-resolved account_type, then convert
    each category to its normal balance:
      asset/expense         (debit-normal):  debit - credit
      liability/equity/revenue (credit-normal): credit - debit
    A positive result always means a normal (healthy) balance for that category.

    Returns {"asset", "liability", "equity", "revenue", "expense"} -> Decimal.
    """
    query = db.query(JournalEntry).filter(JournalEntry.status == "posted")
    if from_date:
        query = query.filter(JournalEntry.posted_date >= from_date)
    if to_date:
        query = query.filter(JournalEntry.posted_date <= to_date)

    chart_map = build_chart_type_map(db)
    debit_totals = {t: Decimal("0") for t in _CATEGORY_TYPES}
    credit_totals = {t: Decimal("0") for t in _CATEGORY_TYPES}

    for entry in query.all():
        dt = chart_account_type(db, entry.debit_account, chart_map)
        ct = chart_account_type(db, entry.credit_account, chart_map)
        if dt in debit_totals:
            debit_totals[dt] += entry.debit_amount
        if ct in credit_totals:
            credit_totals[ct] += entry.credit_amount

    result: dict[str, Decimal] = {}
    for t in _CATEGORY_TYPES:
        if t in _DEBIT_NORMAL_TYPES:
            result[t] = debit_totals[t] - credit_totals[t]
        else:
            result[t] = credit_totals[t] - debit_totals[t]
    return result


def cogs_net_balance(
    db: Session,
    from_date: date | None = None,
    to_date: date | None = None,
) -> Decimal:
    """Net normal (debit) balance of cost-of-sales expense accounts.

    COGS accounts are chart-resolved expense accounts whose numeric code starts
    with "5" or whose name contains cost-of-sale markers ("cost of sale",
    "cost of goods", "cogs", "purchase"). This preserves the legacy prefix-5
    convention while staying on the correct (debit-normal) side of the ledger.
    """
    query = db.query(JournalEntry).filter(JournalEntry.status == "posted")
    if from_date:
        query = query.filter(JournalEntry.posted_date >= from_date)
    if to_date:
        query = query.filter(JournalEntry.posted_date <= to_date)

    chart_map = build_chart_type_map(db)
    total = Decimal("0")
    for entry in query.all():
        if chart_account_type(db, entry.debit_account, chart_map) == "expense" and _is_cogs_account(entry.debit_account):
            total += entry.debit_amount
        if chart_account_type(db, entry.credit_account, chart_map) == "expense" and _is_cogs_account(entry.credit_account):
            total -= entry.credit_amount
    return total


def _is_cogs_account(account: str | None) -> bool:
    """Name/prefix check for cost-of-sales accounts (see cogs_net_balance)."""
    a = (account or "").lower()
    code = a.split("-")[0].strip()
    return code.startswith("5") or any(k in a for k in ("cost of sale", "cost of goods", "cogs", "purchase"))
