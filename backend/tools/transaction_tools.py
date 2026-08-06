from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy import select

from db.models import JournalEntry, ChartOfAccount
from tools.schemas import RecordTransactionNLInput, RecordTransactionNLOutput


# Mapping of expense keywords to account names
EXPENSE_ACCOUNTS = {
    "rent": "6000-Office Rent",
    "salary": "6100-Salary",
    "wage": "6100-Salary",
    "utilities": "6200-Utilities",
    "electric": "6200-Utilities",
    "gas": "6200-Utilities",
    "water": "6200-Utilities",
    "office supplies": "6300-Office Supplies",
    "stationery": "6300-Office Supplies",
    "travel": "6400-Travel",
    "transport": "6400-Travel",
    "fuel": "6400-Travel",
    "petrol": "6400-Travel",
    "food": "6500-Meals",
    "meal": "6500-Meals",
    "entertainment": "6600-Entertainment",
    "advertising": "6700-Advertising",
    "marketing": "6700-Advertising",
    "insurance": "6800-Insurance",
    "maintenance": "6900-Maintenance",
    "repair": "6900-Maintenance",
    "tax": "7000-Tax",
    "professional fee": "7100-Professional Fees",
    "consultant": "7100-Professional Fees",
    "miscellaneous": "7200-Miscellaneous",
}

CASH_ACCOUNT = "1000-Cash"
REVENUE_ACCOUNT = "4000-Revenue"


def _parse_amount(description: str) -> Decimal | None:
    """Extract the first numeric amount from a description string."""
    amounts = re.findall(r'\d+(?:\.\d{2})?', description.replace(",", ""))
    if not amounts:
        return None
    return Decimal(amounts[0])


def _categorize_description(description: str, db: Session) -> str:
    """Map a description to the most appropriate expense account.

    Resolution order (dynamic, nothing forced):
      1. Exact match: a chart expense account whose NAME matches the full
         description (e.g. "Home Rent" exists and user says "paid home rent").
      2. Chart descriptor+category match: account name contains both the category
         keyword and a descriptor word (e.g. "Rent - Home", "Electricity - Office").
      3. Category-only chart match when the description carries no descriptor
         (e.g. plain "rent" -> the chart's rent account).
      4. Derive from the user's own wording when no chart account fits (e.g.
         "home rent" -> "6000-Home Rent"), preserving distinct sub-accounts
         instead of forcing everything into "Office Rent".
      5. Last resort: the keyword map for the category, else Miscellaneous.

    Uses the user's wording first, the seed chart second, the keyword map last.
    """
    desc_lower = description.lower()

    # Clean the description: drop leading verbs and stopwords so "paid home rent"
    # becomes the descriptor phrase "home rent".
    words = desc_lower.replace("paid", "").replace("purchase", "").replace("bought", "").split()
    content_words = [
        w for w in words
        if w.isalpha() and len(w) > 2
        and w not in ("the", "with", "for", "and", "cash", "bank", "today", "yesterday", "now")
    ]
    phrase = " ".join(content_words)

    # Find the category keyword (rent, salary, utilities, ...) present in description
    category = None
    for keyword in EXPENSE_ACCOUNTS:
        if keyword in desc_lower:
            category = keyword
            break

    chart_accounts = db.query(ChartOfAccount).filter(
        ChartOfAccount.account_type == "expense"
    ).all()

    if category:
        # 1. Exact chart-name match against the cleaned phrase (order-insensitive).
        for acc in chart_accounts:
            acc_words = set(acc.account_name.lower().split())
            if acc_words and acc_words.issubset(content_words):
                return acc.account_code

        # 2. Descriptor + category match in chart (e.g. "Home Rent" exists).
        for acc in chart_accounts:
            acc_lower = acc.account_name.lower()
            if category in acc_lower and any(d in acc_lower for d in content_words):
                return acc.account_code

        # 3. Category-only chart match ONLY when no descriptor word present.
        if not content_words:
            for acc in chart_accounts:
                if category in acc.account_name.lower():
                    return acc.account_code

        # 4. Derive the account from the user's own wording. Code prefix from
        #    the chart account for the category if one exists, else the keyword map.
        mapped = EXPENSE_ACCOUNTS.get(category)
        if mapped:
            prefix = mapped.split("-")[0]
            for acc in chart_accounts:
                if category in acc.account_name.lower():
                    prefix = acc.account_code.split("-")[0]
                    break
            if content_words:
                derived_name = " ".join(dict.fromkeys(content_words)).title()
                return f"{prefix}-{derived_name}"
            return mapped

    # 5. No category keyword: fall back to exact/first chart match on the phrase,
    #    else Miscellaneous.
    for acc in chart_accounts:
        acc_words = set(acc.account_name.lower().split())
        if acc_words and acc_words.issubset(content_words):
            return acc.account_code
    return "7200-Miscellaneous"


def _ensure_account_in_chart(db: Session, account_code: str, account_type: str = "expense") -> None:
    """Upsert an account into chart_of_accounts if it doesn't exist.

    Derived accounts (e.g. "6400-Travel") are created by dynamic
    categorization but were never registered in the chart, so the chart-driven
    expense/revenue filters (P&L, retained earnings, tax) could not classify
    them and they were silently excluded from expenses - producing wrong net
    income. Registering them keeps journal entries consistent with the chart.
    """
    code, name = account_code.split("-", 1) if "-" in account_code else (account_code, account_code)
    existing = db.query(ChartOfAccount).filter(
        ChartOfAccount.account_code == account_code
    ).first()
    if existing:
        return
    db.add(ChartOfAccount(
        account_code=account_code,
        account_name=name,
        account_type=account_type,
        is_active=1,
        created_at=date.today(),
    ))


def _generate_entry_id(db: Session) -> str:
    """Generate a unique journal entry ID like JE-YYYYMMDD-NNN."""
    today_str = date.today().strftime("%Y%m%d")
    existing = db.query(JournalEntry).filter(
        JournalEntry.entry_id.like(f"JE-{today_str}-%")
    ).count()
    seq = existing + 1
    return f"JE-{today_str}-{seq:03d}"


def _check_duplicate(description: str, posted_date: date, amount: Decimal, db: Session) -> JournalEntry | None:
    """Check for existing transaction with same amount, same description key, same date."""
    existing = db.execute(
        select(JournalEntry).where(
            JournalEntry.posted_date == posted_date,
            JournalEntry.debit_amount == amount,
            JournalEntry.status == "posted"
        )
    ).scalars().all()
    for e in existing:
        # Fuzzy match - same first 20 chars of description
        if e.description[:20] == description[:20]:
            return e
    return None


def record_transaction_nl(input: RecordTransactionNLInput, db: Session) -> RecordTransactionNLOutput:
    """Parse a plain-English transaction and create a journal entry."""
    description = input.description
    posted_date = input.posted_date

    # Step 1: Parse amount
    amount = _parse_amount(description)
    if amount is None or amount <= Decimal("0.00"):
        raise ValueError("No valid amount found in description")

    # Step 2: Categorize the expense - explicit override wins, else dynamic
    if input.debit_account:
        debit_account = input.debit_account
    else:
        debit_account = _categorize_description(description, db)

    # Register derived accounts in the chart so P&L/RE/tax classification works
    _ensure_account_in_chart(db, debit_account, account_type="expense")
    _ensure_account_in_chart(db, CASH_ACCOUNT, account_type="asset")

    # Step 3: Check for duplicate
    duplicate = _check_duplicate(description, posted_date, amount, db)
    if duplicate is not None:
        return RecordTransactionNLOutput(
            entry_id=duplicate.entry_id,
            description=duplicate.description,
            posted_date=duplicate.posted_date,
            reference=duplicate.reference,
            debit_account=duplicate.debit_account,
            debit_amount=duplicate.debit_amount,
            credit_account=duplicate.credit_account,
            credit_amount=duplicate.credit_amount,
            status="duplicate_ignored",
        )

    # Step 4: Create the journal entry
    entry_id = _generate_entry_id(db)
    journal_entry = JournalEntry(
        entry_id=entry_id,
        description=description,
        posted_date=posted_date,
        reference=input.reference,
        debit_account=debit_account,
        debit_amount=amount,
        credit_account=CASH_ACCOUNT,
        credit_amount=amount,
        status="posted",
    )
    db.add(journal_entry)
    db.commit()
    db.refresh(journal_entry)

    return RecordTransactionNLOutput(
        entry_id=journal_entry.entry_id,
        description=journal_entry.description,
        posted_date=journal_entry.posted_date,
        reference=journal_entry.reference,
        debit_account=journal_entry.debit_account,
        debit_amount=journal_entry.debit_amount,
        credit_account=journal_entry.credit_account,
        credit_amount=journal_entry.credit_amount,
        status=journal_entry.status,
    )
