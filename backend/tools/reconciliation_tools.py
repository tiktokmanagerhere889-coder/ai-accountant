"""Reconciliation & Banking tools for Agent 3: run_bank_reconciliation, post_accrual_entry, reconcile_vendor_statement, reconcile_customer_statement, track_cheque_clearing, track_lc_bank_guarantee, reconcile_bank_charges."""

import calendar
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select, or_
from sqlalchemy.orm import Session

from db.models import (
    BankTransaction,
    ChequeRegistry,
    Contact,
    JournalEntry,
    LCBGRegistry,
    ReconciliationRun,
    ReconciliationMatch,
)
from tools.account_utils import ar_filter_clause, ap_filter_clause
from tools.schemas import (
    BankChargeItem,
    ChequeStatusItem,
    LCBGDetails,
    PostAccrualEntryInput,
    PostAccrualEntryOutput,
    ReconcileBankChargesInput,
    ReconcileBankChargesOutput,
    ReconcileCustomerStatementInput,
    ReconcileCustomerStatementOutput,
    ReconcileVendorStatementInput,
    ReconcileVendorStatementOutput,
    ReconciliationMatchItem,
    RunBankReconciliationInput,
    RunBankReconciliationOutput,
    StatementDifferenceItem,
    StatementMatchItem,
    TrackChequeClearingInput,
    TrackChequeClearingOutput,
    TrackLCBGInput,
    TrackLCBGOutput,
    UnmatchedBankItem,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACCRUAL_MAP = {
    "salary": ("6100-Salary", "2000-Accrued Liabilities"),
    "utilities": ("6200-Utilities", "2000-Accrued Liabilities"),
    "rent": ("6000-Office Rent", "2000-Accrued Liabilities"),
}


# ---------------------------------------------------------------------------
# Helpers (Tools 1-2)
# ---------------------------------------------------------------------------


def _generate_run_id(db: Session) -> str:
    """Generate a run_id in the format REC-YYYYMM-NNN with next available sequence."""
    now = datetime.now()
    prefix = now.strftime("REC-%Y%m-")

    existing = db.execute(
        select(ReconciliationRun.run_id).where(
            ReconciliationRun.run_id.like(prefix + "%")
        )
    ).scalars().all()

    max_seq = 0
    for rid in existing:
        suffix = rid[len(prefix):]
        if suffix.isdigit():
            seq = int(suffix)
            if seq > max_seq:
                max_seq = seq

    return f"{prefix}{max_seq + 1:03d}"


def _generate_accrual_id() -> str:
    """Generate an accrual_id like ACC-YYYYMMDD-HHMMSS."""
    now = datetime.now()
    return now.strftime("ACC-%Y%m%d-%H%M%S")


def _compute_candidates(bank_txn, journal_entries):
    """Find up to 3 matching journal entries for a bank transaction, sorted by confidence.

    Confidence tiers:
      - 95% (exact): amount matches AND bank reference appears in JE description
      - 70% (amount_date): amount matches AND dates within 3 days
      - 50% (amount_only): amount matches but no date/reference match
    Partial matches (amount diff < 1%) use lower confidence tiers.
    """
    candidates = []

    for je in journal_entries:
        max_amt = max(abs(bank_txn.amount), Decimal("1"))
        amount_diff = abs(bank_txn.amount - je.debit_amount)

        if bank_txn.amount == je.debit_amount:
            amount_match = True
            partial_match = False
        elif amount_diff / max_amt < Decimal("0.01"):
            amount_match = True
            partial_match = True
        else:
            continue

        reference_match = False
        if bank_txn.reference and bank_txn.reference.lower() in je.description.lower():
            reference_match = True

        date_diff = abs((bank_txn.date - je.posted_date).days)

        if amount_match and not partial_match and reference_match:
            confidence = 95
            match_type = "exact"
        elif amount_match and not partial_match and date_diff <= 3:
            confidence = 70
            match_type = "amount_date"
        elif amount_match and not partial_match:
            confidence = 50
            match_type = "amount_only"
        elif partial_match and reference_match:
            confidence = 45
            match_type = "exact"
        elif partial_match and date_diff <= 3:
            confidence = 40
            match_type = "amount_date"
        else:
            confidence = 30
            match_type = "amount_only"

        candidates.append({
            "je": je,
            "confidence": confidence,
            "match_type": match_type,
            "partial_match": partial_match,
            "date_diff_days": date_diff,
        })

    candidates.sort(key=lambda c: c["confidence"], reverse=True)
    return candidates[:3]


# ---------------------------------------------------------------------------
# Tool 1: Run Bank Reconciliation
# ---------------------------------------------------------------------------


def run_bank_reconciliation(
    input: RunBankReconciliationInput,
    db: Session,
) -> RunBankReconciliationOutput:
    """Match bank transactions to journal entries for a given period.

    Uses a confidence-based algorithm:
      - 95% exact match (amount + reference in description)
      - 70% amount + date within 3 days
      - 50% amount only

    Persists the run and its matches to the database.
    Returns existing run data if the same period+account was already reconciled.
    """
    # --- Check for existing reconciliation ----------------------------------
    existing_run = db.execute(
        select(ReconciliationRun).where(
            ReconciliationRun.bank_account_id == input.bank_account_id,
            ReconciliationRun.statement_date == input.statement_date,
        )
    ).scalar_one_or_none()

    if existing_run is not None:
        existing_matches = db.execute(
            select(ReconciliationMatch).where(
                ReconciliationMatch.run_id == existing_run.run_id
            )
        ).scalars().all()

        match_items = []
        for m in existing_matches:
            bt = db.execute(
                select(BankTransaction).where(
                    BankTransaction.transaction_id == m.bank_txn_id
                )
            ).scalar_one_or_none()

            match_items.append(ReconciliationMatchItem(
                bank_txn_id=m.bank_txn_id,
                bank_date=bt.date if bt else input.from_date,
                bank_description=bt.description if bt else "",
                bank_amount=bt.amount if bt else Decimal("0"),
                bank_type=bt.type if bt else "",
                journal_entry_id=m.journal_entry_id,
                journal_date=None,
                journal_amount=None,
                confidence=float(m.confidence),
                match_type=m.match_type,
                status=m.status,
            ))

        return RunBankReconciliationOutput(
            run_id=existing_run.run_id,
            bank_account_id=input.bank_account_id,
            statement_date=input.statement_date,
            period_from=input.from_date,
            period_to=input.to_date,
            matches=match_items,
            unmatched_bank=[],
            total_matched=existing_run.matched_count or 0,
            total_unmatched=existing_run.unmatched_count or 0,
            total_amount_matched=Decimal("0"),
            total_amount_unmatched=Decimal("0"),
            status=existing_run.status,
            existing_run_note=(
                f"An existing reconciliation run '{existing_run.run_id}' "
                f"already exists for this period and account."
            ),
        )

    # --- Query data ---------------------------------------------------------
    bank_txns = db.execute(
        select(BankTransaction).where(
            BankTransaction.account_id == input.bank_account_id,
            BankTransaction.date >= input.from_date,
            BankTransaction.date <= input.to_date,
            BankTransaction.type.in_(["debit", "credit"]),
        )
    ).scalars().all()

    journal_entries = db.execute(
        select(JournalEntry).where(
            JournalEntry.posted_date >= input.from_date,
            JournalEntry.posted_date <= input.to_date,
            JournalEntry.status == "posted",
        )
    ).scalars().all()

    # --- Matching loop ------------------------------------------------------
    match_items = []
    unmatched_items = []
    matched_txn_ids = set()

    for bt in bank_txns:
        candidates = _compute_candidates(bt, journal_entries)

        if candidates:
            matched_txn_ids.add(bt.transaction_id)
            for c in candidates:
                match_items.append(ReconciliationMatchItem(
                    bank_txn_id=bt.transaction_id,
                    bank_date=bt.date,
                    bank_description=bt.description,
                    bank_amount=bt.amount,
                    bank_type=bt.type,
                    journal_entry_id=c["je"].entry_id,
                    journal_date=c["je"].posted_date,
                    journal_amount=c["je"].debit_amount,
                    confidence=float(c["confidence"]),
                    match_type=c["match_type"],
                    partial_match=c["partial_match"],
                    status="suggested",
                ))
        else:
            unmatched_items.append(UnmatchedBankItem(
                bank_txn_id=bt.transaction_id,
                date=bt.date,
                description=bt.description,
                amount=bt.amount,
                reason="no_journal_match",
            ))

    matched_count = len(matched_txn_ids)
    unmatched_count = len(unmatched_items)

    total_amount_matched = sum(
        bt.amount for bt in bank_txns if bt.transaction_id in matched_txn_ids
    )
    total_amount_unmatched = sum(
        bt.amount for bt in bank_txns if bt.transaction_id not in matched_txn_ids
    )

    # --- Persist run --------------------------------------------------------
    run_id = _generate_run_id(db)

    run_record = ReconciliationRun(
        run_id=run_id,
        bank_account_id=input.bank_account_id,
        statement_date=input.statement_date,
        run_date=date.today(),
        status="completed",
        matched_count=matched_count,
        unmatched_count=unmatched_count,
    )
    db.add(run_record)
    db.flush()

    for idx, mi in enumerate(match_items, start=1):
        match_record = ReconciliationMatch(
            match_id=f"RM-{run_id}-{mi.bank_txn_id}-{idx}",
            run_id=run_id,
            bank_txn_id=mi.bank_txn_id,
            journal_entry_id=mi.journal_entry_id,
            confidence=Decimal(str(mi.confidence)),
            match_type=mi.match_type,
            status=mi.status,
        )
        db.add(match_record)

    db.commit()

    return RunBankReconciliationOutput(
        run_id=run_id,
        bank_account_id=input.bank_account_id,
        statement_date=input.statement_date,
        period_from=input.from_date,
        period_to=input.to_date,
        matches=match_items,
        unmatched_bank=unmatched_items,
        total_matched=matched_count,
        total_unmatched=unmatched_count,
        total_amount_matched=total_amount_matched,
        total_amount_unmatched=total_amount_unmatched,
        status="completed",
    )


# ---------------------------------------------------------------------------
# Tool 2: Post Accrual Entry
# ---------------------------------------------------------------------------


def post_accrual_entry(
    input: PostAccrualEntryInput,
    db: Session,
) -> PostAccrualEntryOutput:
    """Prepare an accrual journal entry for approval.

    Does NOT write to the database; returns needs_approval=True with
    status = "pending_approval".  Runs several validation checks:
      - Duplicate accrual for same period + type
      - Back-dated (> 30 days)
      - Unusual account pairing
      - Duplicate within 24 hours
    """
    warnings_list = []

    # --- Resolve accounts ---------------------------------------------------
    if input.accrual_type in ACCRUAL_MAP:
        debit_account, credit_account = ACCRUAL_MAP[input.accrual_type]
    else:
        debit_account = "6000-Other Expenses"
        credit_account = "2000-Accrued Liabilities"

    if input.debit_account is not None:
        debit_account = input.debit_account
    if input.credit_account is not None:
        credit_account = input.credit_account

    # --- Proration ----------------------------------------------------------
    prorated_amount = None
    if input.partial_period_days is not None:
        prorated_amount = input.amount * Decimal(str(input.partial_period_days)) / Decimal("30")
        debit_amount = prorated_amount
        credit_amount = prorated_amount
    else:
        debit_amount = input.amount
        credit_amount = input.amount

    # --- Warnings -----------------------------------------------------------

    # 1. Unusual account pairing (salary credited to revenue)
    if input.accrual_type in ("salary", "utilities", "rent"):
        cred_prefix = credit_account.split("-")[0].strip()
        if cred_prefix and cred_prefix[0] == "4":
            warnings_list.append(
                f"Unusual account pairing: {input.accrual_type} accrual "
                f"credited to revenue account '{credit_account}'"
            )

    # 2. Duplicate accrual for same period + type
    _, last_day = calendar.monthrange(input.period_date.year, input.period_date.month)
    period_start = input.period_date.replace(day=1)
    period_end = input.period_date.replace(day=last_day)

    existing_in_period = db.execute(
        select(JournalEntry).where(
            JournalEntry.debit_account == debit_account,
            JournalEntry.posted_date >= period_start,
            JournalEntry.posted_date <= period_end,
            JournalEntry.status == "posted",
        )
    ).scalars().all()

    if existing_in_period:
        warnings_list.append(
            f"Duplicate accrual: an entry for '{input.accrual_type}' already "
            f"exists in {input.period_date.strftime('%Y-%m')}"
        )

    # 3. Back-dated (> 30 days)
    today = date.today()
    days_ago = (today - input.period_date).days
    if days_ago > 30:
        warnings_list.append(
            f"Back-dated entry: period_date ({input.period_date}) is "
            f"{days_ago} days in the past"
        )

    # 4. Duplicate within 24 hours
    yesterday = today - timedelta(days=1)
    recent_entries = db.execute(
        select(JournalEntry).where(
            JournalEntry.debit_account == debit_account,
            JournalEntry.posted_date >= yesterday,
            JournalEntry.status == "posted",
        )
    ).scalars().all()

    if recent_entries:
        warnings_list.append(
            f"Duplicate within 24h: a similar '{input.accrual_type}' entry "
            f"was already posted recently"
        )

    # --- Assemble output ----------------------------------------------------
    accrual_id = _generate_accrual_id()

    return PostAccrualEntryOutput(
        accrual_id=accrual_id,
        entry_id=None,
        accrual_type=input.accrual_type,
        amount=input.amount,
        debit_account=debit_account,
        debit_amount=debit_amount,
        credit_account=credit_account,
        credit_amount=credit_amount,
        period_date=input.period_date,
        partial_period_days=input.partial_period_days,
        prorated_amount=prorated_amount,
        needs_approval=True,
        status="pending_approval",
        warnings=warnings_list,
    )


# ---------------------------------------------------------------------------
# Helpers (Tools 5-6)
# ---------------------------------------------------------------------------


def _generate_cheque_id(db: Session) -> str:
    """Generate a new cheque_id like CHQ-{seq:06d}."""
    max_id = db.execute(select(func.max(ChequeRegistry.id))).scalar()
    seq = (max_id or 0) + 1
    return f"CHQ-{seq:06d}"


def _generate_lc_bg_id(db: Session, lc_type: str) -> str:
    """Generate a new LC/BG ID like LC-YYYYMM-NNN or BG-YYYYMM-NNN."""
    today = date.today()
    prefix = f"{lc_type}-{today.strftime('%Y%m')}-"
    count = db.execute(
        select(func.count()).select_from(LCBGRegistry).where(
            LCBGRegistry.lc_id.like(f"{prefix}%")
        )
    ).scalar()
    seq = (count or 0) + 1
    return f"{prefix}{seq:03d}"


def _compute_days_outstanding(issue_date: date, status: str) -> Optional[int]:
    """Compute days outstanding for an issued/bounced cheque."""
    if status in ("issued", "bounced"):
        return (date.today() - issue_date).days
    return None


def track_cheque_clearing(
    input: TrackChequeClearingInput, db: Session
) -> TrackChequeClearingOutput:
    """Handle cheque clearing lifecycle: issue, clear, bounce, reconcile, status.

    This tool requires no agent-level approval.
    """
    action = input.action
    cheque_id = input.cheque_id

    if action == "issue":
        # Generate or validate cheque_id
        if cheque_id:
            existing = db.execute(
                select(ChequeRegistry).where(ChequeRegistry.cheque_id == cheque_id)
            ).scalar_one_or_none()
            if existing:
                current = ChequeStatusItem(
                    cheque_id=existing.cheque_id,
                    vendor_name=existing.vendor_name,
                    amount=existing.amount,
                    status=existing.status,
                    issue_date=existing.issue_date,
                    clearing_date=existing.clearing_date,
                    days_outstanding=_compute_days_outstanding(
                        existing.issue_date, existing.status
                    ),
                    warning=f"Cheque {cheque_id} already issued (status: {existing.status})",
                )
                return TrackChequeClearingOutput(
                    cheque_id=cheque_id,
                    action_performed="issue",
                    current_state=current,
                )
        else:
            cheque_id = _generate_cheque_id(db)

        vendor_name = input.vendor_name or ""
        amount = input.amount or Decimal("0.00")
        issue_date = input.issue_date or date.today()
        bank_account_id = input.bank_account_id or ""

        warning = None
        if amount > Decimal("1000000.00"):
            warning = "High-value cheque - amount exceeds 1M"

        cheque = ChequeRegistry(
            cheque_id=cheque_id,
            vendor_name=vendor_name,
            amount=amount,
            issue_date=issue_date,
            clearing_date=None,
            status="issued",
            bank_account_id=bank_account_id,
            notes=warning,
        )
        db.add(cheque)
        db.commit()
        db.refresh(cheque)

        current = ChequeStatusItem(
            cheque_id=cheque.cheque_id,
            vendor_name=cheque.vendor_name,
            amount=cheque.amount,
            status=cheque.status,
            issue_date=cheque.issue_date,
            clearing_date=cheque.clearing_date,
            days_outstanding=_compute_days_outstanding(
                cheque.issue_date, cheque.status
            ),
            warning=warning,
        )
        return TrackChequeClearingOutput(
            cheque_id=cheque.cheque_id,
            action_performed="issue",
            current_state=current,
        )

    # All other actions require an existing cheque
    if not cheque_id:
        raise ValueError("cheque_id is required for this action")

    cheque = db.execute(
        select(ChequeRegistry).where(ChequeRegistry.cheque_id == cheque_id)
    ).scalar_one_or_none()

    if cheque is None:
        raise ValueError(f"Cheque {cheque_id} not found")

    warning = cheque.notes

    if action == "clear":
        if cheque.status == "cleared":
            current = ChequeStatusItem(
                cheque_id=cheque.cheque_id,
                vendor_name=cheque.vendor_name,
                amount=cheque.amount,
                status=cheque.status,
                issue_date=cheque.issue_date,
                clearing_date=cheque.clearing_date,
                days_outstanding=_compute_days_outstanding(
                    cheque.issue_date, cheque.status
                ),
                warning=warning or f"Cheque {cheque_id} already cleared",
            )
            return TrackChequeClearingOutput(
                cheque_id=cheque.cheque_id,
                action_performed="clear",
                current_state=current,
            )
        cheque.status = "cleared"
        cheque.clearing_date = date.today()
        db.commit()
        db.refresh(cheque)
        current = ChequeStatusItem(
            cheque_id=cheque.cheque_id,
            vendor_name=cheque.vendor_name,
            amount=cheque.amount,
            status=cheque.status,
            issue_date=cheque.issue_date,
            clearing_date=cheque.clearing_date,
            days_outstanding=None,
            warning=None,
        )
        return TrackChequeClearingOutput(
            cheque_id=cheque.cheque_id,
            action_performed="clear",
            current_state=current,
        )

    elif action == "bounce":
        cheque.status = "bounced"
        cheque.clearing_date = None
        warning = f"Cheque {cheque_id} bounced"
        cheque.notes = warning
        db.commit()
        db.refresh(cheque)
        current = ChequeStatusItem(
            cheque_id=cheque.cheque_id,
            vendor_name=cheque.vendor_name,
            amount=cheque.amount,
            status=cheque.status,
            issue_date=cheque.issue_date,
            clearing_date=cheque.clearing_date,
            days_outstanding=_compute_days_outstanding(
                cheque.issue_date, cheque.status
            ),
            warning=warning,
        )
        return TrackChequeClearingOutput(
            cheque_id=cheque.cheque_id,
            action_performed="bounce",
            current_state=current,
        )

    elif action == "reconcile":
        cheque.status = "reconciled"
        db.commit()
        db.refresh(cheque)
        current = ChequeStatusItem(
            cheque_id=cheque.cheque_id,
            vendor_name=cheque.vendor_name,
            amount=cheque.amount,
            status=cheque.status,
            issue_date=cheque.issue_date,
            clearing_date=cheque.clearing_date,
            days_outstanding=None,
            warning=None,
        )
        return TrackChequeClearingOutput(
            cheque_id=cheque.cheque_id,
            action_performed="reconcile",
            current_state=current,
        )

    elif action == "status":
        stale_warning = None
        if cheque.status == "issued":
            age = date.today() - cheque.issue_date
            if age > timedelta(days=180):
                stale_warning = (
                    f"Stale cheque - issued {age.days} days ago, not cleared"
                )
        all_warnings = [w for w in [warning, stale_warning] if w]
        combined_warning = "; ".join(all_warnings) if all_warnings else None

        current = ChequeStatusItem(
            cheque_id=cheque.cheque_id,
            vendor_name=cheque.vendor_name,
            amount=cheque.amount,
            status=cheque.status,
            issue_date=cheque.issue_date,
            clearing_date=cheque.clearing_date,
            days_outstanding=_compute_days_outstanding(
                cheque.issue_date, cheque.status
            ),
            warning=combined_warning,
        )
        return TrackChequeClearingOutput(
            cheque_id=cheque.cheque_id,
            action_performed="status",
            current_state=current,
        )

    else:
        raise ValueError(f"Unknown action: {action}")


def _compute_days_to_expiry(expiry_date: Optional[date], status: str) -> Optional[int]:
    if expiry_date is None or status in ("expired", "closed"):
        return None
    delta = (expiry_date - date.today()).days
    return max(delta, 0)


def track_lc_bank_guarantee(
    input: TrackLCBGInput, db: Session
) -> TrackLCBGOutput:
    """Handle LC/BG lifecycle: issue, amend, expire, close, status.

    This tool requires agent-level approval (needs_approval=True).
    """
    action = input.action
    lc_id = input.lc_id

    if action == "issue":
        lc_type = input.type
        if lc_type not in ("LC", "BG"):
            raise ValueError("type must be 'LC' or 'BG'")

        if lc_id:
            existing = db.execute(
                select(LCBGRegistry).where(LCBGRegistry.lc_id == lc_id)
            ).scalar_one_or_none()
            if existing:
                details = LCBGDetails(
                    lc_id=existing.lc_id,
                    type=existing.type,
                    beneficiary=existing.beneficiary,
                    amount=existing.amount,
                    currency=existing.currency,
                    issue_date=existing.issue_date,
                    expiry_date=existing.expiry_date,
                    days_to_expiry=_compute_days_to_expiry(
                        existing.expiry_date, existing.status
                    ),
                    status=existing.status,
                )
                return TrackLCBGOutput(
                    lc_id=lc_id,
                    action_performed="issue",
                    details=details,
                    needs_approval=True,
                    warning=f"LC/BG {lc_id} already exists (status: {existing.status})",
                )
        else:
            lc_id = _generate_lc_bg_id(db, lc_type)

        beneficiary = input.beneficiary or ""
        amount = input.amount or Decimal("0.00")
        issue_date = input.issue_date or date.today()
        expiry_date = input.expiry_date
        currency = input.currency or "PKR"

        if expiry_date is not None and expiry_date < date.today():
            raise ValueError(
                f"Expiry date {expiry_date} is in the past"
            )

        warning = None
        if expiry_date is not None and expiry_date <= date.today() + timedelta(days=30):
            warning = (
                f"LC/BG {lc_id} expiring within 30 days (expires: {expiry_date})"
            )

        # Check multiple LCs/BGs same beneficiary
        notes = None
        if beneficiary:
            same = db.execute(
                select(LCBGRegistry).where(
                    LCBGRegistry.beneficiary == beneficiary,
                    LCBGRegistry.status.in_(["active", "amended"]),
                )
            ).scalars().all()
            if same:
                ids = [r.lc_id for r in same]
                notes = (
                    f"Multiple active LC/BGs for same beneficiary: {', '.join(ids)}"
                )

        record = LCBGRegistry(
            lc_id=lc_id,
            type=lc_type,
            beneficiary=beneficiary,
            amount=amount,
            currency=currency,
            issue_date=issue_date,
            expiry_date=expiry_date or date.today(),
            status="active",
            notes=notes,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        details = LCBGDetails(
            lc_id=record.lc_id,
            type=record.type,
            beneficiary=record.beneficiary,
            amount=record.amount,
            currency=record.currency,
            issue_date=record.issue_date,
            expiry_date=record.expiry_date,
            days_to_expiry=_compute_days_to_expiry(
                record.expiry_date, record.status
            ),
            status=record.status,
        )
        return TrackLCBGOutput(
            lc_id=record.lc_id,
            action_performed="issue",
            details=details,
            needs_approval=True,
            warning=warning,
        )

    # All other actions require an existing record
    if not lc_id:
        raise ValueError("lc_id is required for this action")

    record = db.execute(
        select(LCBGRegistry).where(LCBGRegistry.lc_id == lc_id)
    ).scalar_one_or_none()

    if record is None:
        raise ValueError(f"LC/BG {lc_id} not found")

    if action == "amend":
        notes_parts = []
        if record.notes:
            notes_parts.append(record.notes)
        notes_parts.append(
            f"Previously: amount={record.amount}, beneficiary={record.beneficiary}"
        )
        record.notes = "; ".join(notes_parts)

        if input.amount is not None:
            record.amount = input.amount
        if input.beneficiary is not None:
            record.beneficiary = input.beneficiary
        record.status = "amended"
        db.commit()
        db.refresh(record)

        details = LCBGDetails(
            lc_id=record.lc_id,
            type=record.type,
            beneficiary=record.beneficiary,
            amount=record.amount,
            currency=record.currency,
            issue_date=record.issue_date,
            expiry_date=record.expiry_date,
            days_to_expiry=_compute_days_to_expiry(
                record.expiry_date, record.status
            ),
            status=record.status,
        )
        return TrackLCBGOutput(
            lc_id=record.lc_id,
            action_performed="amend",
            details=details,
            needs_approval=True,
            warning=None,
        )

    elif action == "expire":
        record.status = "expired"
        db.commit()
        db.refresh(record)

        details = LCBGDetails(
            lc_id=record.lc_id,
            type=record.type,
            beneficiary=record.beneficiary,
            amount=record.amount,
            currency=record.currency,
            issue_date=record.issue_date,
            expiry_date=record.expiry_date,
            days_to_expiry=None,
            status=record.status,
        )
        return TrackLCBGOutput(
            lc_id=record.lc_id,
            action_performed="expire",
            details=details,
            needs_approval=True,
            warning=None,
        )

    elif action == "close":
        close_notes = []
        if record.notes:
            close_notes.append(record.notes)
        if record.status not in ("expired", "closed") and (
            record.expiry_date is None or record.expiry_date > date.today()
        ):
            close_notes.append("Closed early before expiry date")
        if close_notes:
            record.notes = "; ".join(close_notes)
        record.status = "closed"
        db.commit()
        db.refresh(record)

        details = LCBGDetails(
            lc_id=record.lc_id,
            type=record.type,
            beneficiary=record.beneficiary,
            amount=record.amount,
            currency=record.currency,
            issue_date=record.issue_date,
            expiry_date=record.expiry_date,
            days_to_expiry=None,
            status=record.status,
        )
        return TrackLCBGOutput(
            lc_id=record.lc_id,
            action_performed="close",
            details=details,
            needs_approval=True,
            warning=None,
        )

    elif action == "status":
        details = LCBGDetails(
            lc_id=record.lc_id,
            type=record.type,
            beneficiary=record.beneficiary,
            amount=record.amount,
            currency=record.currency,
            issue_date=record.issue_date,
            expiry_date=record.expiry_date,
            days_to_expiry=_compute_days_to_expiry(
                record.expiry_date, record.status
            ),
            status=record.status,
        )
        return TrackLCBGOutput(
            lc_id=record.lc_id,
            action_performed="status",
            details=details,
            needs_approval=True,
            warning=record.notes,
        )

    else:
        raise ValueError(f"Unknown action: {action}")


# ---------------------------------------------------------------------------
# Helper -- generate reconciliation IDs for tools 3, 4, 7
# ---------------------------------------------------------------------------

def _generate_rec_id(prefix: str, statement_date: date) -> str:
    """Generate a reconciliation ID like VSR-20260729-001."""
    return f"{prefix}-{statement_date.strftime('%Y%m%d')}-001"


# ---------------------------------------------------------------------------
# Helper -- core matching logic shared by vendor and customer reconciliation
# ---------------------------------------------------------------------------

def _match_statement_lines(statement_lines, journal_entries):
    """Match statement lines against journal entries by reference, amount, and date.

    Returns (matches, matched_entry_ids) where matches is a list of
    StatementMatchItem and matched_entry_ids is a set of matched entry_ids.
    """
    matched_entry_ids = set()
    matches = []

    for line in statement_lines:
        best_entry = None
        best_score = -1  # 3=ref+amt+date, 2=ref+amt, 1=amt+date_prox, 0=ref_only

        for entry in journal_entries:
            if entry.entry_id in matched_entry_ids:
                continue

            ref_match = entry.reference is not None and entry.reference == line.reference
            amt_match = entry.debit_amount == line.amount
            date_diff = abs((entry.posted_date - line.date).days)
            date_exact = date_diff == 0
            date_prox = date_diff <= 3

            if ref_match and amt_match and date_exact:
                score = 3  # perfect match
            elif ref_match and amt_match:
                score = 2  # reference + amount, date differs
            elif amt_match and date_prox:
                score = 1  # amount + date proximity
            elif ref_match:
                score = 0  # reference only, amount differs
            else:
                continue

            if score > best_score:
                best_score = score
                best_entry = entry

        if best_entry is not None:
            matched_entry_ids.add(best_entry.entry_id)
            amount_match = best_entry.debit_amount == line.amount
            date_match = best_entry.posted_date == line.date
            status = "matched" if (amount_match and date_match) else "partial"
            matches.append(StatementMatchItem(
                statement_ref=line.reference,
                journal_entry_id=best_entry.entry_id,
                amount_match=amount_match,
                date_match=date_match,
                status=status,
            ))
        else:
            matches.append(StatementMatchItem(
                statement_ref=line.reference,
                journal_entry_id="",
                amount_match=False,
                date_match=False,
                status="unmatched",
            ))

    return matches, matched_entry_ids


# ---------------------------------------------------------------------------
# Tool 3 -- Reconcile Vendor Statement  (approval required at agent level)
# ---------------------------------------------------------------------------

def reconcile_vendor_statement(
    inp: ReconcileVendorStatementInput,
    db: Session,
) -> ReconcileVendorStatementOutput:
    """Match vendor statement lines against internal AP journal entries.

    Verifies the vendor contact exists, then attempts to match each
    statement line by reference (exact), amount (exact), or date proximity
    (within 3 days). Returns matched, partial, and unmatched items along
    with differences for internal entries not recorded on the statement.
    """
    # Verify vendor contact exists
    contact = db.query(Contact).filter(
        Contact.contact_id == inp.vendor_contact_id,
    ).first()
    if contact is None:
        raise ValueError(
            f"Vendor contact '{inp.vendor_contact_id}' not found in contacts table"
        )

    # Query AP journal entries (payable accounts resolved from chart, credit side)
    journal_entries = db.query(JournalEntry).filter(
        ap_filter_clause(JournalEntry.credit_account, db),
        JournalEntry.posted_date >= inp.from_date,
        JournalEntry.posted_date <= inp.to_date,
    ).order_by(JournalEntry.posted_date).all()

    # Match statement lines against journal entries
    matches, matched_entry_ids = _match_statement_lines(
        inp.statement_lines, journal_entries
    )

    # Journal entries not on statement become difference items
    differences = []
    for entry in journal_entries:
        if entry.entry_id not in matched_entry_ids:
            differences.append(StatementDifferenceItem(
                reference=entry.reference or "",
                statement_amount=Decimal("0.00"),
                internal_amount=entry.credit_amount,
                difference=-entry.credit_amount,
                reason="Recorded in internal books but not found on vendor statement",
            ))

    # Net difference between statement total and internal total
    statement_total = sum(line.amount for line in inp.statement_lines)
    internal_total = sum(entry.credit_amount for entry in journal_entries)
    total_difference = statement_total - internal_total

    return ReconcileVendorStatementOutput(
        reconciliation_id=_generate_rec_id("VSR", inp.statement_date),
        vendor_contact_id=inp.vendor_contact_id,
        matches=matches,
        differences=differences,
        total_difference=total_difference,
        status="pending_approval",
    )


# ---------------------------------------------------------------------------
# Tool 4 -- Reconcile Customer Statement  (approval required at agent level)
# ---------------------------------------------------------------------------

def reconcile_customer_statement(
    inp: ReconcileCustomerStatementInput,
    db: Session,
) -> ReconcileCustomerStatementOutput:
    """Match customer statement lines against internal AR journal entries.

    Verifies the customer contact exists, then attempts to match each
    statement line by reference (exact), amount (exact), or date proximity
    (within 3 days). Returns matched, partial, and unmatched items along
    with differences for internal entries not recorded on the statement.
    """
    # Verify customer contact exists
    contact = db.query(Contact).filter(
        Contact.contact_id == inp.customer_contact_id,
    ).first()
    if contact is None:
        raise ValueError(
            f"Customer contact '{inp.customer_contact_id}' not found in contacts table"
        )

    # Query AR journal entries (debit_account starts with "1200") in date range
    journal_entries = db.query(JournalEntry).filter(
        ar_filter_clause(JournalEntry.debit_account, db),
        JournalEntry.posted_date >= inp.from_date,
        JournalEntry.posted_date <= inp.to_date,
    ).order_by(JournalEntry.posted_date).all()

    # Match statement lines against journal entries
    matches, matched_entry_ids = _match_statement_lines(
        inp.statement_lines, journal_entries
    )

    # Journal entries not on statement become difference items
    differences = []
    for entry in journal_entries:
        if entry.entry_id not in matched_entry_ids:
            differences.append(StatementDifferenceItem(
                reference=entry.reference or "",
                statement_amount=Decimal("0.00"),
                internal_amount=entry.debit_amount,
                difference=-entry.debit_amount,
                reason="Recorded in internal books but not found on customer statement",
            ))

    # Net difference between statement total and internal total
    statement_total = sum(line.amount for line in inp.statement_lines)
    internal_total = sum(entry.debit_amount for entry in journal_entries)
    total_difference = statement_total - internal_total

    return ReconcileCustomerStatementOutput(
        reconciliation_id=_generate_rec_id("CSR", inp.statement_date),
        customer_contact_id=inp.customer_contact_id,
        matches=matches,
        differences=differences,
        total_difference=total_difference,
        status="pending_approval",
    )


# ---------------------------------------------------------------------------
# Tool 7 -- Reconcile Bank Charges  (no approval)
# ---------------------------------------------------------------------------

# Mapping from charge_type value to description keyword for ILIKE filter
_CHARGE_KEYWORD_MAP = {
    "service": "service",
    "maintenance": "maintenance",
    "transfer": "transfer",
    "fee": "fee",
    "commission": "commission",
    "other": "charge",
}


def reconcile_bank_charges(
    inp: ReconcileBankChargesInput,
    db: Session,
) -> ReconcileBankChargesOutput:
    """Match bank charge transactions against internal journal entries.

    Queries bank_transactions for debit-type negative amounts (fees/charges)
    within the given period, optionally filtered by a charge_type keyword
    in the description. Each charge is matched against journal_entries by
    amount and date proximity (within 3 days).
    """
    warning = None

    # Base query: bank charges are debits with negative amounts
    query = db.query(BankTransaction).filter(
        BankTransaction.account_id == inp.bank_account_id,
        BankTransaction.date >= inp.from_date,
        BankTransaction.date <= inp.to_date,
        BankTransaction.type == "debit",
        BankTransaction.amount < 0,
    )

    # Apply optional charge_type keyword filter on description
    if inp.charge_type is not None:
        keyword = _CHARGE_KEYWORD_MAP.get(inp.charge_type, inp.charge_type)
        query = query.filter(
            BankTransaction.description.ilike(f"%{keyword}%")
        )

    charges = query.order_by(BankTransaction.date).all()

    if not charges:
        if inp.charge_type is not None:
            warning = (
                f"No charges found for type '{inp.charge_type}' "
                f"in the specified period"
            )
        else:
            warning = "No bank charges found in the specified period"

        return ReconcileBankChargesOutput(
            period_from=inp.from_date,
            period_to=inp.to_date,
            total_charges_found=0,
            total_matched=0,
            total_unmatched=0,
            charges=[],
            warning=warning,
        )

    # Query journal entries with a 3-day buffer on both sides for date proximity
    journal_entries = db.query(JournalEntry).filter(
        JournalEntry.posted_date >= inp.from_date - timedelta(days=3),
        JournalEntry.posted_date <= inp.to_date + timedelta(days=3),
    ).all()

    # Track how many bank charges match each journal entry (duplicate detection)
    journal_match_count = {}
    charge_items = []

    for charge in charges:
        charge_abs = abs(charge.amount)
        best_match = None

        for entry in journal_entries:
            if entry.debit_amount == charge_abs:
                date_diff = abs((entry.posted_date - charge.date).days)
                if date_diff <= 3:
                    best_match = entry
                    break

        if best_match is not None:
            journal_match_count[best_match.entry_id] = (
                journal_match_count.get(best_match.entry_id, 0) + 1
            )
            charge_items.append(BankChargeItem(
                bank_txn_id=charge.transaction_id,
                date=charge.date,
                description=charge.description,
                amount=charge.amount,
                journal_match_id=best_match.entry_id,
                match_status="matched",
            ))
        else:
            charge_items.append(BankChargeItem(
                bank_txn_id=charge.transaction_id,
                date=charge.date,
                description=charge.description,
                amount=charge.amount,
                journal_match_id=None,
                match_status="unmatched",
            ))

    # Flag duplicate charges (same journal entry matched to multiple charges)
    duplicates = [eid for eid, cnt in journal_match_count.items() if cnt > 1]
    if duplicates:
        warning = (
            f"Duplicate charge detected: {len(duplicates)} journal entry(ies) "
            f"matched to multiple bank charges -- review recommended"
        )

    total_matched = sum(1 for c in charge_items if c.match_status == "matched")
    total_unmatched = sum(1 for c in charge_items if c.match_status == "unmatched")

    return ReconcileBankChargesOutput(
        period_from=inp.from_date,
        period_to=inp.to_date,
        total_charges_found=len(charge_items),
        total_matched=total_matched,
        total_unmatched=total_unmatched,
        charges=charge_items,
        warning=warning,
    )
