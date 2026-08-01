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
      1. Look up the user's chart_of_accounts for an expense account whose name
         contains a keyword from the description (e.g. "home" + "rent" -> an
         account named "Home Rent" if present).
      2. Fall back to the keyword map.
      3. Derive the account name from the description itself (e.g. "laptop rent"
         -> "Laptop Rent"), preferring the user's own wording over a hardcoded
         "Office Rent".
    """
    desc_lower = description.lower()

    # Find the category keyword (rent, salary, utilities, ...) present in description
    category = None
    for keyword in EXPENSE_ACCOUNTS:
        if keyword in desc_lower:
            category = keyword
            break

    if category:
        descriptor_words = [
            w for w in desc_lower
            .replace("paid", "").replace("purchase", "").replace("bought", "").split()
            if w.isalpha() and len(w) > 2
            and w not in (category, "the", "with", "for", "and", "cash", "bank")
        ]
        chart_accounts = db.query(ChartOfAccount).filter(
            ChartOfAccount.account_type == "expense"
        ).all()

        # 1. Descriptor + category exact match in chart (e.g. "Home Rent" exists)
        for acc in chart_accounts:
            acc_lower = acc.account_name.lower()
            if category in acc_lower and any(d in acc_lower for d in descriptor_words):
                return acc.account_code

        # 2. Category-only chart match ONLY when no descriptor word present
        #    (e.g. plain "rent" -> the chart's rent account)
        if not descriptor_words:
            for acc in chart_accounts:
                if category in acc.account_name.lower():
                    return acc.account_code

        # 3. Derive the account from the user's own wording — this preserves
        #    "home rent" / "laptop rent" as distinct sub-accounts instead of
        #    forcing everything into "Office Rent". Code prefix from the chart
        #    account for the category if one exists, else the keyword map.
        mapped = EXPENSE_ACCOUNTS.get(category)
        if mapped:
            prefix = mapped.split("-")[0]
            # Use chart account code if a category account exists
            for acc in chart_accounts:
                if category in acc.account_name.lower():
                    prefix = acc.account_code.split("-")[0]
                    break
            if descriptor_words:
                derived_name = " ".join(descriptor_words).title()
                return f"{prefix}-{derived_name}"
            return mapped

    return "7200-Miscellaneous"


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
        # Fuzzy match — same first 20 chars of description
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

    # Step 2: Categorize the expense — explicit override wins, else dynamic
    if input.debit_account:
        debit_account = input.debit_account
    else:
        debit_account = _categorize_description(description, db)

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
