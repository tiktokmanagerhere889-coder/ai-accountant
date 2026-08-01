"""Agent 8 - Audit & Regulatory Tools.

4 tools: detect_anomaly_transactions, get_compliance_deadlines,
support_internal_audit, maintain_statutory_registers.
"""
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import uuid

from sqlalchemy import func, extract
from sqlalchemy.orm import Session

from db.models import JournalEntry, FlaggedEntry, StatutoryRegister, ComplianceDeadline
from tools.schemas import (
    AnomalyEntry,
    DetectAnomalyTransactionsInput, DetectAnomalyTransactionsOutput,
    DeadlineItem,
    GetComplianceDeadlinesInput, GetComplianceDeadlinesOutput,
    FlaggedAuditEntry,
    SupportInternalAuditInput, SupportInternalAuditOutput,
    MaintainStatutoryRegistersInput, MaintainStatutoryRegistersOutput,
)


def _round(value: Decimal, places: int = 2) -> Decimal:
    return value.quantize(Decimal("0." + "0" * places), rounding=ROUND_HALF_UP)


# Standard account prefixes
_ASSET_PREFIXES = {"1"}
_LIABILITY_PREFIXES = {"2"}
_EQUITY_PREFIXES = {"3"}
_REVENUE_PREFIXES = {"4"}
_EXPENSE_PREFIXES = {"5", "6", "8"}


def _get_account_prefix(account: str) -> str:
    """Extract the first digit of an account code."""
    code = account.split("-")[0].strip()
    return code[0] if code else ""


def detect_anomaly_transactions(inp: DetectAnomalyTransactionsInput, db: Session) -> DetectAnomalyTransactionsOutput:
    """Run pattern-based anomaly detection on journal entries.

    Four detectors: round_amount, weekend_posting, duplicate_amount, unusual_account.
    """
    # Base query
    query = db.query(JournalEntry).filter(
        JournalEntry.posted_date >= inp.from_date,
        JournalEntry.posted_date <= inp.to_date,
    )
    if inp.threshold is not None and inp.threshold > 0:
        query = query.filter(
            (JournalEntry.debit_amount >= inp.threshold) |
            (JournalEntry.credit_amount >= inp.threshold)
        )

    entries = query.all()

    # Determine which detectors to run
    requested_types = set(inp.anomaly_types) if inp.anomaly_types else {"round_amount", "weekend_posting", "duplicate_amount", "unusual_account"}

    anomalies: list[AnomalyEntry] = []
    seen = set()  # (entry_id, anomaly_type) dedup

    def _add_anomaly(entry: JournalEntry, atype: str, confidence: str, reason: str, review: str):
        key = (entry.entry_id, atype)
        if key in seen:
            return
        seen.add(key)
        amount = max(entry.debit_amount, entry.credit_amount)
        anomalies.append(AnomalyEntry(
            entry_id=entry.entry_id,
            description=entry.description,
            amount=amount,
            anomaly_type=atype,
            confidence=confidence,
            reasoning=reason,
            suggested_review=review,
        ))

    for e in entries:
        amount = max(e.debit_amount, e.credit_amount)

        # 1. Round amount detector
        if "round_amount" in requested_types:
            if amount > 0 and amount % 1000 == 0:
                confidence = "high" if amount >= 100000 else "medium"
                _add_anomaly(
                    e, "round_amount", confidence,
                    f"Amount {amount} is a round number (multiple of 1000), possible round-tripping",
                    "Verify transaction substance and counterparty"
                )

        # 2. Weekend detector
        if "weekend_posting" in requested_types:
            if e.posted_date.weekday() >= 5:  # Saturday=5, Sunday=6
                _add_anomaly(
                    e, "weekend_posting", "high",
                    f"Posted on {e.posted_date.strftime('%A')} ({e.posted_date.isoformat()}) - unusual activity",
                    "Review weekend transactions for validity"
                )

        # 3. Duplicate amount detector
        if "duplicate_amount" in requested_types:
            dups = db.query(JournalEntry).filter(
                JournalEntry.posted_date == e.posted_date,
                JournalEntry.debit_amount == e.debit_amount,
                JournalEntry.credit_amount == e.credit_amount,
                JournalEntry.description.ilike(e.description.strip()),
                JournalEntry.entry_id != e.entry_id,
            ).count()
            if dups > 0:
                _add_anomaly(
                    e, "duplicate_amount", "medium",
                    f"Same amount ({amount}) on same date ({e.posted_date.isoformat()}) with similar description",
                    "Confirm this is not a duplicate entry"
                )

        # 4. Unusual account detector
        if "unusual_account" in requested_types:
            debit_prefix = _get_account_prefix(e.debit_account)
            credit_prefix = _get_account_prefix(e.credit_account)
            # Check for unusual patterns: expenses directly to equity, or revenue to assets
            if debit_prefix in _EQUITY_PREFIXES and credit_prefix not in _EQUITY_PREFIXES:
                _add_anomaly(
                    e, "unusual_account", "medium",
                    f"Unusual pairing: debit to {e.debit_account}, credit to {e.credit_account}",
                    "Verify account mapping is correct"
                )
            elif credit_prefix in _EXPENSE_PREFIXES and debit_prefix not in _EXPENSE_PREFIXES:
                _add_anomaly(
                    e, "unusual_account", "medium",
                    f"Credit to expense account {e.credit_account} - unusual direction",
                    "Verify entry direction is correct"
                )

    total_amount = sum(a.amount for a in anomalies)
    status = "clean" if not anomalies else "anomalies_detected"

    return DetectAnomalyTransactionsOutput(
        anomalies=anomalies,
        total_anomalies=len(anomalies),
        total_amount_flagged=_round(Decimal(str(total_amount))),
        period_from=inp.from_date,
        period_to=inp.to_date,
        status=status,
    )


def get_compliance_deadlines(inp: GetComplianceDeadlinesInput, db: Session) -> GetComplianceDeadlinesOutput:
    """Query compliance deadlines with optional filters."""
    query = db.query(ComplianceDeadline)

    if inp.fiscal_year:
        query = query.filter(ComplianceDeadline.fiscal_year == inp.fiscal_year)
    if inp.deadline_type:
        query = query.filter(ComplianceDeadline.deadline_type == inp.deadline_type)
    if inp.status:
        query = query.filter(ComplianceDeadline.status == inp.status)
    if inp.reminder_days is not None:
        reminder_date = date.today() + timedelta(days=inp.reminder_days)
        query = query.filter(ComplianceDeadline.due_date <= reminder_date)

    deadlines = query.order_by(ComplianceDeadline.due_date).all()

    items: list[DeadlineItem] = []
    today = date.today()
    for d in deadlines:
        days = (d.due_date - today).days
        items.append(DeadlineItem(
            deadline_id=d.deadline_id,
            deadline_type=d.deadline_type,
            description=d.description,
            due_date=d.due_date,
            days_remaining=days,
            status=d.status,
            responsible_person=d.responsible_person or "",
        ))

    overdue = [d for d in items if d.days_remaining < 0 and d.status != "completed"]
    upcoming = [d for d in items if d.days_remaining >= 0 and d.status != "completed"]

    if not items:
        summary = "No compliance deadlines configured. Add deadlines to track filing due dates."
    elif overdue and not upcoming:
        summary = f"{len(overdue)} deadline(s) overdue - immediate attention needed."
    elif not overdue and not upcoming:
        summary = "All compliance deadlines completed - up to date."
    else:
        parts = []
        if overdue:
            parts.append(f"{len(overdue)} overdue")
        if upcoming:
            parts.append(f"{len(upcoming)} upcoming")
        summary = f"{', '.join(parts)} compliance deadline(s)."

    return GetComplianceDeadlinesOutput(
        deadlines=items,
        overdue_count=len(overdue),
        upcoming_count=len(upcoming),
        summary=summary,
    )


def support_internal_audit(inp: SupportInternalAuditInput, db: Session) -> SupportInternalAuditOutput:
    """Run internal audit scan on journal entries.

    Flags 5 patterns: missing references, weekend postings, round amounts,
    unusually large entries (3sigma), and infrequent-account activity.
    Results persisted to flagged_entries table.
    """
    audit_id = f"AUD-{uuid.uuid4().hex[:8].upper()}"
    today = date.today()

    # Determine date range from fiscal_year and optional period
    if inp.period:
        from_date = date(inp.fiscal_year, inp.period, 1)
        # Last day of month
        if inp.period == 12:
            to_date = date(inp.fiscal_year, 12, 31)
        else:
            to_date = date(inp.fiscal_year, inp.period + 1, 1) - timedelta(days=1)
    else:
        from_date = date(inp.fiscal_year, 1, 1)
        to_date = date(inp.fiscal_year, 12, 31)

    entries = db.query(JournalEntry).filter(
        JournalEntry.posted_date >= from_date,
        JournalEntry.posted_date <= to_date,
    ).all()

    if not entries:
        return SupportInternalAuditOutput(
            audit_id=audit_id,
            flagged_entries=[],
            total_flagged=0,
            summary="No journal entries found for the specified period. No audit issues detected.",
            needs_approval=True,
        )

    # Mean and stddev for large-entry detection
    amounts = [float(max(e.debit_amount, e.credit_amount)) for e in entries]
    mean = sum(amounts) / len(amounts) if amounts else 0
    variance = sum((a - mean) ** 2 for a in amounts) / len(amounts) if amounts else 0
    stddev = variance ** 0.5
    threshold_3sigma = mean + 3 * stddev

    # Build account frequency map
    account_freq: dict[str, int] = {}
    for e in entries:
        account_freq[e.debit_account] = account_freq.get(e.debit_account, 0) + 1
        account_freq[e.credit_account] = account_freq.get(e.credit_account, 0) + 1

    flags: list[FlaggedAuditEntry] = []

    for e in entries:
        amount = max(e.debit_amount, e.credit_amount)
        severities = []

        # Pattern 1: Missing reference
        if not e.reference or not e.reference.strip():
            severities.append(("missing_reference", "medium", "Entry missing reference number"))

        # Pattern 2: Weekend posting
        if e.posted_date.weekday() >= 5:
            severities.append(("weekend_posting", "high", f"Posted on {e.posted_date.strftime('%A')}"))

        # Pattern 3: Round amount (ending in 000)
        if amount > 0 and amount % 1000 == 0 and amount >= 100000:
            severities.append(("round_amount", "medium", f"Round amount {amount} - possible round-tripping"))

        # Pattern 4: Unusually large (3 sigma)
        if amount > threshold_3sigma and threshold_3sigma > 0:
            severities.append(("large_amount", "high", f"Amount {amount} exceeds 3sigma threshold ({_round(Decimal(str(threshold_3sigma)))})"))

        # Pattern 5: Infrequent account
        for acc in [e.debit_account, e.credit_account]:
            freq = account_freq.get(acc, 0)
            if 1 <= freq <= 2 and len(entries) > 10:
                severities.append(("infrequent_account", "low", f"Account {acc} appears only {freq}x in period"))
                break

        for flag_type, severity, reason in severities:
            if inp.min_severity:
                sev_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
                if sev_order.get(severity, 0) < sev_order.get(inp.min_severity, 0):
                    continue
            flags.append(FlaggedAuditEntry(
                entry_id=e.entry_id,
                description=e.description,
                amount=amount,
                flag_type=flag_type,
                reason=reason,
                severity=severity,
                status="open",
            ))
            # Persist to flagged_entries table
            flagged = FlaggedEntry(
                entry_id=e.entry_id,
                flag_type=flag_type,
                reason=reason,
                severity=severity,
                flagged_by="system",
                flagged_at=today,
                status="open",
            )
            db.add(flagged)

    db.commit()

    # Summarize
    high = sum(1 for f in flags if f.severity == "high")
    medium = sum(1 for f in flags if f.severity == "medium")
    low = sum(1 for f in flags if f.severity == "low")

    if not flags:
        summary = f"No audit issues found for fiscal year {inp.fiscal_year}. All entries appear clean."
    else:
        summary = f"Audit complete. Found {len(flags)} issue(s): {high} high, {medium} medium, {low} low severity. Review flagged entries in the flagged_entries table."

    return SupportInternalAuditOutput(
        audit_id=audit_id,
        flagged_entries=flags,
        total_flagged=len(flags),
        summary=summary,
        needs_approval=True,
    )


def maintain_statutory_registers(inp: MaintainStatutoryRegistersInput, db: Session) -> MaintainStatutoryRegistersOutput:
    """CRUD operations on statutory registers.

    Actions: add, update, delete, view.
    Requires approval for all write actions.
    """
    today = date.today()
    valid_actions = {"add", "update", "delete", "view"}
    valid_types = {"directors", "members", "charges", "contracts", "beneficial_owners"}

    if inp.action not in valid_actions:
        raise ValueError(f"Invalid action '{inp.action}'. Must be one of: {', '.join(sorted(valid_actions))}")
    if inp.register_type not in valid_types:
        raise ValueError(f"Invalid register_type '{inp.register_type}'. Must be one of: {', '.join(sorted(valid_types))}")

    # -- VIEW --
    if inp.action == "view":
        query = db.query(StatutoryRegister).filter(
            StatutoryRegister.register_type == inp.register_type
        )
        entries = query.order_by(StatutoryRegister.entry_date.desc()).all()
        if not entries:
            msg = f"No entries found in the '{inp.register_type}' register."
            return MaintainStatutoryRegistersOutput(
                register_id="",
                action_performed="view",
                register_type=inp.register_type,
                entry_date=inp.entry_date,
                description=msg,
                status="empty",
                message=msg,
                needs_approval=False,
            )
        # Return count of entries found
        entry = entries[0]
        return MaintainStatutoryRegistersOutput(
            register_id=entry.register_id,
            action_performed="view",
            register_type=inp.register_type,
            entry_date=entry.entry_date,
            description=entry.description,
            reference_number=entry.reference_number or "",
            amount=entry.amount or Decimal("0"),
            status=entry.status,
            message=f"Found {len(entries)} entry(ies) in '{inp.register_type}' register.",
            needs_approval=False,
        )

    # -- DELETE --
    if inp.action == "delete":
        if not inp.register_id:
            raise ValueError("register_id is required for delete action")
        entry = db.query(StatutoryRegister).filter(
            StatutoryRegister.register_id == inp.register_id
        ).first()
        if not entry:
            raise ValueError(f"Register entry with register_id '{inp.register_id}' not found")
        db.delete(entry)
        db.commit()
        return MaintainStatutoryRegistersOutput(
            register_id=inp.register_id,
            action_performed="delete",
            register_type=inp.register_type,
            entry_date=inp.entry_date,
            description=f"Deleted entry from '{inp.register_type}' register",
            status="deleted",
            message=f"Register entry '{inp.register_id}' deleted successfully. Requires approval.",
            needs_approval=True,
        )

    # -- UPDATE --
    if inp.action == "update":
        if not inp.register_id:
            raise ValueError("register_id is required for update action")
        entry = db.query(StatutoryRegister).filter(
            StatutoryRegister.register_id == inp.register_id
        ).first()
        if not entry:
            raise ValueError(f"Register entry with register_id '{inp.register_id}' not found")
        entry.description = inp.description
        entry.reference_number = inp.reference_number or entry.reference_number
        if inp.amount is not None:
            entry.amount = inp.amount
        entry.updated_at = today
        entry.status = "pending_approval"
        db.commit()
        return MaintainStatutoryRegistersOutput(
            register_id=inp.register_id,
            action_performed="update",
            register_type=inp.register_type,
            entry_date=entry.entry_date,
            description=entry.description,
            reference_number=entry.reference_number or "",
            amount=entry.amount or Decimal("0"),
            status="pending_approval",
            message=f"Register entry '{inp.register_id}' updated. Requires approval.",
            needs_approval=True,
        )

    # -- ADD --
    if inp.action == "add":
        # Generate register_id
        reg_id = f"REG-{inp.register_type[:3].upper()}-{uuid.uuid4().hex[:8].upper()}"

        # Check duplicate reference
        if inp.reference_number:
            existing = db.query(StatutoryRegister).filter(
                StatutoryRegister.reference_number == inp.reference_number
            ).first()
            ref_note = f" (note: reference '{inp.reference_number}' already exists)" if existing else ""
        else:
            ref_note = ""

        db_entry = StatutoryRegister(
            register_id=reg_id,
            register_type=inp.register_type,
            entry_date=inp.entry_date,
            description=inp.description,
            reference_number=inp.reference_number,
            amount=inp.amount,
            status="pending_approval",
            created_at=today,
            updated_at=today,
        )
        db.add(db_entry)
        db.commit()

        message = f"Register entry '{reg_id}' added to '{inp.register_type}' register.{ref_note} Requires approval."

        return MaintainStatutoryRegistersOutput(
            register_id=reg_id,
            action_performed="add",
            register_type=inp.register_type,
            entry_date=inp.entry_date,
            description=inp.description,
            reference_number=inp.reference_number or "",
            amount=inp.amount or Decimal("0"),
            status="pending_approval",
            message=message,
            needs_approval=True,
        )
