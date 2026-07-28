from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy import select

from db.models import JournalEntry
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


def _categorize_description(description: str) -> str:
    """Map a description to the most likely expense account."""
    desc_lower = description.lower()
    for keyword, account in EXPENSE_ACCOUNTS.items():
        if keyword in desc_lower:
            return account
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

    # Step 2: Categorize the expense
    debit_account = _categorize_description(description)

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
