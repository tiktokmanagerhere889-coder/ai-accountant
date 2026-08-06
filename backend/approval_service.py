"""Approval service - queue, view, edit, approve/reject tool executions.

Direct-mode executions of sensitive tools are queued here instead of running
immediately. A human approves (optionally editing params) or rejects through
the REST endpoints in main.py.

Flow: queue -> view -> edit -> approve/reject -> execute/reject
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from db.models import ApprovalQueue
from tool_registry import execute_tool


def _post_accrual_to_journal(db, result: dict, params: dict) -> None:
    """Post an approved accrual suggestion as a real journal entry.

    post_accrual_entry returns a suggestion (debit/credit accounts + amounts)
    and never writes to the DB itself. On human approval we insert the JE here
    so it appears in the general ledger / cash position (like categorize_fixed_asset
    promotes its asset to approved on approval).

    The journal entry id is derived from the same scheme create_journal_entry
    uses (JE-YYYYMMDD-NNN), so it never collides.
    """
    from datetime import date
    from db.models import JournalEntry

    # Guard: never post twice (re-approval / edited re-run on same accrual).
    if result.get("status") == "posted":
        return

    debit_account = result.get("debit_account") or params.get("debit_account")
    credit_account = result.get("credit_account") or params.get("credit_account")
    debit_amount = result.get("debit_amount") or result.get("amount")
    credit_amount = result.get("credit_amount") or result.get("amount")
    period_date = result.get("period_date") or params.get("period_date") or date.today()
    description = params.get("description") or result.get("accrual_type") or "Accrual entry"
    prorated = result.get("prorated_amount")

    if not (debit_account and credit_account and debit_amount and credit_amount):
        return  # missing accounts/amounts — cannot post a balanced entry

    amount = prorated or debit_amount

    # Generate JE-YYYYMMDD-NNN entry id.
    if isinstance(period_date, str):
        try:
            period_date = date.fromisoformat(str(period_date)[:10])
        except ValueError:
            period_date = date.today()
    prefix = "JE-{}-".format(period_date.strftime("%Y%m%d"))
    existing = db.query(JournalEntry.entry_id).filter(
        JournalEntry.entry_id.like(prefix + "%")
    ).all()
    max_seq = 0
    for row in existing:
        # .all() on a column query returns SQLAlchemy Row objects (2.x), which
        # are NOT tuple subclasses — row[0] reads the id, str(row) does not.
        eid = row[0] if not isinstance(row, str) else row
        suffix = str(eid)[len(prefix):]
        if suffix.isdigit():
            max_seq = max(max_seq, int(suffix))
    # Collision-proof: the like-prefix scan can lag a concurrent writer (or a
    # stale max_seq), so bump until the generated id is actually free.
    entry_id = "{}{:03d}".format(prefix, max_seq + 1)
    while (
        db.query(JournalEntry.entry_id)
        .filter(JournalEntry.entry_id == entry_id)
        .first()
        is not None
    ):
        max_seq += 1
        entry_id = "{}{:03d}".format(prefix, max_seq + 1)

    entry = JournalEntry(
        entry_id=entry_id,
        description=str(description)[:500],
        posted_date=period_date,
        reference="ACCRUAL-{}".format(result.get("accrual_id", "")),
        debit_account=str(debit_account),
        debit_amount=amount,
        credit_account=str(credit_account),
        credit_amount=amount,
        status="posted",
    )
    db.add(entry)
    result["entry_id"] = entry_id
    result["status"] = "posted"

# Tools that ALWAYS require human approval before execution, even when the
# caller does not pass needs_approval=true. Mirrors the `approval: true` flags
# in frontend/src/components/agentsData.ts.
APPROVAL_REQUIRED_TOOLS = {
    "process_receipt_image",
    "run_bank_reconciliation",
    "post_accrual_entry",
    "reconcile_vendor_statement",
    "reconcile_customer_statement",
    "track_lc_bank_guarantee",
    "forecast_cash_flow",
    "close_fiscal_year",
    "categorize_fixed_asset",
    "calculate_standard_costing_variance",
    "allocate_overhead_cost",
    "calculate_revenue_recognition",
    "flag_provision_contingent_liability",
    "flag_related_party_transaction",
    "adjust_sales_tax_input_output",
    "flag_tax_exemption_zero_rating",
    "prepare_sales_tax_filing",
    "prepare_income_tax_filing",
    "support_internal_audit",
    "maintain_statutory_registers",
    "manage_system_preferences",
    "schedule_system_task",
    "generate_custom_report",
}

PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"
EDITED = "edited"

RESOLVED_STATUSES = (APPROVED, REJECTED, EDITED)


def queue_for_approval(
    tool_name: str,
    params: dict,
    db: Session,
    submitted_by: Optional[str] = None,
) -> ApprovalQueue:
    """Create a pending ApprovalQueue entry for a tool call."""
    entry = ApprovalQueue(
        approval_id=f"APR-{uuid.uuid4().hex[:8].upper()}",
        tool_name=tool_name,
        params=json.dumps(params, default=str),
        submitted_by=submitted_by,
        status=PENDING,
        created_at=datetime.utcnow(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def list_pending_approvals(db: Session) -> list[ApprovalQueue]:
    """Return all pending approval entries (newest first)."""
    return (
        db.query(ApprovalQueue)
        .filter(ApprovalQueue.status == PENDING)
        .order_by(ApprovalQueue.created_at.desc())
        .all()
    )


def list_approval_history(db: Session, limit: int = 50) -> list[ApprovalQueue]:
    """Return resolved approvals (approved/edited/rejected), newest first."""
    return (
        db.query(ApprovalQueue)
        .filter(ApprovalQueue.status.in_(RESOLVED_STATUSES))
        .order_by(ApprovalQueue.resolved_at.desc())
        .limit(limit)
        .all()
    )


def approve_or_execute(
    approval_id: str,
    db: Session,
    edited_params: Optional[dict] = None,
) -> tuple[ApprovalQueue, dict]:
    """Approve a queued tool call and execute it.

    If edited_params is provided (and differs from the original), the tool
    runs with the edited params and the entry is marked "edited"; otherwise
    the entry is marked "approved". The execution result is stored on the
    entry. Raises the original exception if execution fails (entry is still
    marked resolved so the failure is visible in history).
    """
    entry = db.query(ApprovalQueue).filter(ApprovalQueue.approval_id == approval_id).first()
    if entry is None:
        raise ValueError(f"Approval not found: {approval_id}")
    if entry.status != PENDING:
        raise ValueError(f"Approval {approval_id} already resolved (status={entry.status})")

    original_params = json.loads(entry.params)
    if edited_params is not None:
        entry.edited_params = json.dumps(edited_params, default=str)
    params_to_run = edited_params if edited_params is not None else original_params

    exc: Optional[Exception] = None
    result: Any = None
    try:
        result = execute_tool(entry.tool_name, params_to_run)
    except Exception as e:  # noqa: BLE001 - surface any execution error to the API layer
        exc = e
        result = {"error": str(e)}

    entry.status = EDITED if edited_params is not None and edited_params != original_params else APPROVED
    entry.resolved_at = datetime.utcnow()

    # categorize_fixed_asset saves the asset as "pending_approval" and returns
    # asset_id. On human approval, promote it to "approved" so downstream tools
    # (calculate_depreciation filters status in ["approved","active"]) can see it.
    if entry.tool_name == "categorize_fixed_asset" and isinstance(result, dict):
        asset_id = result.get("asset_id")
        if asset_id:
            from db.models import FixedAsset
            db.query(FixedAsset).filter(FixedAsset.asset_id == asset_id).update(
                {"status": "approved"}
            )

    # post_accrual_entry only RETURNS a suggested entry (needs_approval=True).
    # On human approval, actually post it as a journal entry so it shows up in
    # the general ledger / cash position. Mirrors the fixed-asset pattern above.
    if entry.tool_name == "post_accrual_entry" and isinstance(result, dict):
        _post_accrual_to_journal(db, result, params_to_run)

    entry.result = json.dumps(result, default=str)
    db.commit()
    db.refresh(entry)

    if exc is not None:
        raise RuntimeError(f"{entry.tool_name} execution failed after approval: {exc}") from exc
    return entry, result


def reject_approval(
    approval_id: str,
    db: Session,
    reason: Optional[str] = None,
) -> ApprovalQueue:
    """Mark a queued tool call as rejected with an optional reason."""
    entry = db.query(ApprovalQueue).filter(ApprovalQueue.approval_id == approval_id).first()
    if entry is None:
        raise ValueError(f"Approval not found: {approval_id}")
    if entry.status != PENDING:
        raise ValueError(f"Approval {approval_id} already resolved (status={entry.status})")

    entry.status = REJECTED
    entry.rejection_reason = reason
    entry.resolved_at = datetime.utcnow()
    db.commit()
    db.refresh(entry)
    return entry


def serialize_approval(entry: ApprovalQueue) -> dict:
    """Return a JSON-serializable dict for an ApprovalQueue row."""
    result = _safe_json(entry.result)
    formatted_result = None
    if result and isinstance(result, dict):
        try:
            from result_formatter import format_tool_result
            formatted_result = format_tool_result(entry.tool_name, result)
        except Exception:
            formatted_result = None

    return {
        "approval_id": entry.approval_id,
        "tool_name": entry.tool_name,
        "params": _safe_json(entry.params),
        "submitted_by": entry.submitted_by,
        "status": entry.status,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "resolved_at": entry.resolved_at.isoformat() if entry.resolved_at else None,
        "rejection_reason": entry.rejection_reason,
        "edited_params": _safe_json(entry.edited_params),
        "result": result,
        "formatted_result": formatted_result,
    }


def _safe_json(raw: Optional[str]) -> Any:
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw
