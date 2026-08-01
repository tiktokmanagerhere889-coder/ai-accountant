from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from db.models import BankTransaction, BankAccount
from tools.schemas import (
    CheckBankTransactionsInput,
    CheckBankTransactionsOutput,
    BankTransactionItem,
    RecordBankTransactionInput,
    RecordBankTransactionOutput,
)


def check_bank_transactions(input: CheckBankTransactionsInput, db: Session) -> CheckBankTransactionsOutput:
    """Query bank transactions with optional filters. Deterministic DB query — no AI reasoning."""
    from_date = input.from_date
    to_date = input.to_date
    account_id = input.account_id
    status = input.status
    limit = input.limit

    if from_date > to_date:
        raise ValueError("from_date must be before or equal to to_date")

    account_name = None
    if account_id is not None:
        account = db.execute(select(BankAccount).where(BankAccount.account_id == account_id)).scalar_one_or_none()
        if account is None:
            raise ValueError("Bank account not found")
        account_name = account.account_name

    query = select(BankTransaction)

    if account_id is not None:
        query = query.where(BankTransaction.account_id == account_id)
    query = query.where(BankTransaction.date >= from_date).where(BankTransaction.date <= to_date)
    if status is not None:
        query = query.where(BankTransaction.status == status)

    total_count_query = select(func.count()).select_from(query.subquery())
    total_count = db.execute(total_count_query).scalar() or 0

    query = query.order_by(BankTransaction.date, BankTransaction.transaction_id).limit(limit)
    results = db.execute(query).scalars().all()

    if len(results) == 0:
        return CheckBankTransactionsOutput(
            account_id=account_id,
            account_name=account_name,
            transactions=[],
            total_count=0,
            total_debits=Decimal("0.00"),
            total_credits=Decimal("0.00"),
            period_from=from_date,
            period_to=to_date,
            truncated=False,
        )

    transactions = []
    total_debits = Decimal("0.00")
    total_credits = Decimal("0.00")

    for r in results:
        item = BankTransactionItem(
            transaction_id=r.transaction_id,
            date=r.date,
            description=r.description,
            amount=r.amount,
            type=r.type,
            status=r.status,
            reference=r.reference,
            balance_after=r.balance_after,
        )
        transactions.append(item)
        if r.type == "debit":
            total_debits += r.amount
        else:
            total_credits += r.amount

    truncated = total_count > limit

    return CheckBankTransactionsOutput(
        account_id=account_id,
        account_name=account_name,
        transactions=transactions,
        total_count=total_count,
        total_debits=total_debits,
        total_credits=total_credits,
        period_from=from_date,
        period_to=to_date,
        truncated=truncated,
    )


def _generate_bank_txn_id(db: Session) -> str:
    """Generate a unique transaction ID like BNK-YYYYMMDD-NNN."""
    from datetime import date as _date
    today = _date.today()
    prefix = f"BNK-{today.strftime('%Y%m%d')}-"
    existing = db.execute(
        select(BankTransaction.transaction_id).where(
            BankTransaction.transaction_id.like(prefix + "%")
        )
    ).scalars().all()
    seq = 0
    for eid in existing:
        suffix = eid[len(prefix):]
        if suffix.isdigit():
            seq = max(seq, int(suffix))
    return f"{prefix}{seq + 1:03d}"


def record_bank_transaction(input: RecordBankTransactionInput, db: Session) -> RecordBankTransactionOutput:
    """Record a bank register transaction (bank statement line).

    Saves to bank_transactions table — this is the bank register, separate from
    journal entries. Bank charges, fees, interest, uncleared cheques all come here.
    """
    import json

    if input.type not in ("debit", "credit"):
        raise ValueError("type must be 'debit' or 'credit'")
    if input.status not in ("cleared", "pending"):
        raise ValueError("status must be 'cleared' or 'pending'")

    # Validate account exists
    account = db.execute(
        select(BankAccount).where(BankAccount.account_id == input.account_id)
    ).scalar_one_or_none()
    if account is None:
        raise ValueError(f"Bank account '{input.account_id}' not found in bank_accounts")

    txn_id = _generate_bank_txn_id(db)
    txn = BankTransaction(
        transaction_id=txn_id,
        date=input.date,
        description=input.description,
        amount=input.amount,
        type=input.type,
        status=input.status,
        reference=input.reference,
        balance_after=input.balance_after if input.balance_after is not None else Decimal("0"),
        account_id=input.account_id,
        custom_fields=json.dumps(input.custom_fields) if input.custom_fields else None,
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)

    return RecordBankTransactionOutput(
        transaction_id=txn.transaction_id,
        date=txn.date,
        description=txn.description,
        amount=txn.amount,
        type=txn.type,
        status=txn.status,
        reference=txn.reference,
        balance_after=txn.balance_after,
        account_id=txn.account_id,
        custom_fields=json.loads(txn.custom_fields) if txn.custom_fields else None,
        message=f"Bank transaction {txn.transaction_id} recorded.",
    )
