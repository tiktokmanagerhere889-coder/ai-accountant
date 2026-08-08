"""Audit & Regulatory Agent - wraps 5 tools as an OpenAI Agent."""
import sys, os, json, typing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from decimal import Decimal

from agents import Agent, function_tool, Runner
from agents.run_config import RunConfig

from db.database import init_db, get_session
from tools.schemas import (
    DetectAnomalyTransactionsInput, DetectAnomalyTransactionsOutput,
    GetComplianceDeadlinesInput, GetComplianceDeadlinesOutput,
    SupportInternalAuditInput, SupportInternalAuditOutput,
    ResolveFlaggedEntryInput, ResolveFlaggedEntryOutput,
    MaintainStatutoryRegistersInput, MaintainStatutoryRegistersOutput,
)
from tools.audit_tools import (
    detect_anomaly_transactions, get_compliance_deadlines,
    support_internal_audit, resolve_flagged_entry, maintain_statutory_registers,
)
from tools.fbr_risk_tools import assess_fbr_audit_risk, AssessFbrAuditRiskInput
from agent_defs.model_providers import (
    create_groq_provider, create_gemini_provider,
    GROQ_MODEL, GROQ_FALLBACK_MODEL, GEMINI_MODEL,
)


def _get_session():
    init_db()
    return get_session()


def _to_json(obj):
    return json.dumps(json.loads(obj.model_dump_json()), indent=2, default=str)


# -- Tool 1: detect_anomaly_transactions --
@function_tool
def tool_detect_anomaly_transactions(from_date: str, to_date: str, anomaly_types: str = "", threshold: str = "") -> str:
    """Run pattern-based anomaly detection on journal entries. No approval needed.

    Args:
        from_date: Start date YYYY-MM-DD.
        to_date: End date YYYY-MM-DD.
        anomaly_types: Optional comma-separated: round_amount, weekend_posting, duplicate_amount, unusual_account.
        threshold: Optional minimum amount as string (e.g., '100000').
    """
    types = [t.strip() for t in anomaly_types.split(",") if t.strip()] if anomaly_types else None
    thresh = Decimal(threshold) if threshold else None
    inp = DetectAnomalyTransactionsInput(
        from_date=date.fromisoformat(from_date),
        to_date=date.fromisoformat(to_date),
        anomaly_types=types,
        threshold=thresh,
    )
    db = _get_session()
    try:
        r = detect_anomaly_transactions(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 2: get_compliance_deadlines --
@function_tool
def tool_get_compliance_deadlines(fiscal_year: int = 0, deadline_type: str = "", status: str = "", reminder_days: int = 0) -> str:
    """Query compliance deadlines with optional filters. Read-only, no approval.

    Args:
        fiscal_year: Optional fiscal year (e.g., 2026). 0 = no filter.
        deadline_type: Optional filter: tax_filing, statutory_filing, audit, annual_return, other.
        status: Optional filter: upcoming, overdue, completed.
        reminder_days: Show deadlines due within N days. 0 = no filter.
    """
    inp = GetComplianceDeadlinesInput(
        fiscal_year=fiscal_year if fiscal_year > 0 else None,
        deadline_type=deadline_type if deadline_type else None,
        status=status if status else None,
        reminder_days=reminder_days if reminder_days > 0 else None,
    )
    db = _get_session()
    try:
        r = get_compliance_deadlines(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 3: support_internal_audit --
@function_tool
def tool_support_internal_audit(fiscal_year: int, period: int = 0, min_severity: str = "", include_resolved: bool = False) -> str:
    """Run internal audit scan on journal entries. Flags 5 patterns. REQUIRES APPROVAL.

    Args:
        fiscal_year: Fiscal year (e.g., 2026).
        period: Optional period 1-12. 0 = full year.
        min_severity: Optional minimum severity: low, medium, high, critical.
        include_resolved: Include already-resolved flags. Default False.
    """
    inp = SupportInternalAuditInput(
        fiscal_year=fiscal_year,
        period=period if period > 0 else None,
        min_severity=min_severity if min_severity else None,
        include_resolved=include_resolved,
    )
    db = _get_session()
    try:
        r = support_internal_audit(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 4: resolve_flagged_entry --
@function_tool
def tool_resolve_flagged_entry(entry_id: str, flag_type: str, action: str, notes: str = "", resolved_by: str = "") -> str:
    """Mark a flagged audit entry as confirmed or waived. REQUIRES APPROVAL.

    Args:
        entry_id: Journal entry id of the flagged record (e.g. 'JE-2026-0001').
        flag_type: Flag type to resolve (e.g. missing_reference, weekend_posting).
        action: confirm (real issue) or waive (reviewed, not an issue).
        notes: Optional resolution notes.
        resolved_by: Reviewer name.
    """
    inp = ResolveFlaggedEntryInput(
        entry_id=entry_id,
        flag_type=flag_type,
        action=action.lower().strip(),
        notes=notes if notes else None,
        resolved_by=resolved_by if resolved_by else None,
    )
    db = _get_session()
    try:
        r = resolve_flagged_entry(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 5: maintain_statutory_registers --
@function_tool
def tool_maintain_statutory_registers(action: str, register_type: str, entry_date: str, description: str, reference_number: str = "", amount: str = "", register_id: str = "") -> str:
    """CRUD operations on statutory registers. REQUIRES APPROVAL for write actions.

    Args:
        action: add, update, delete, view.
        register_type: directors, members, charges, contracts, beneficial_owners.
        entry_date: Date YYYY-MM-DD.
        description: Register entry description.
        reference_number: Optional reference number.
        amount: Optional monetary amount as string.
        register_id: Required for update/delete actions.
    """
    amt = Decimal(amount) if amount else None
    reg_id = register_id if register_id else None
    inp = MaintainStatutoryRegistersInput(
        action=action.lower().strip(),
        register_type=register_type.lower().strip(),
        entry_date=date.fromisoformat(entry_date),
        description=description,
        reference_number=reference_number if reference_number else None,
        amount=amt,
        register_id=reg_id,
    )
    db = _get_session()
    try:
        r = maintain_statutory_registers(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 6: assess_fbr_audit_risk --
@function_tool
def tool_assess_fbr_audit_risk(fiscal_year: int, business_type: str = "non_corporate",
                               prior_3yr_audit_status: str = "unknown",
                               is_manufacturer: bool = False,
                               months_non_filing: int = 0,
                               customs_import_value: float = 0,
                               exempt_income: float = 0,
                               refund_claim: float = 0) -> str:
    """Score FBR audit-selection risk from historically-disclosed parameters. Read-only, no approval.

    Args:
        fiscal_year: Fiscal year (e.g., 2026).
        business_type: 'non_corporate' or 'corporate'.
        prior_3yr_audit_status: 'audited' (Finance Act 2025 immunity), 'not_audited', or 'unknown'.
        is_manufacturer: True if the business is a manufacturer.
        months_non_filing: Months of tax non-filing (if applicable).
        customs_import_value: Customs-import value in PKR (if known).
        exempt_income: Exempt income amount in PKR.
        refund_claim: Refund claim amount in PKR.
    """
    inp = AssessFbrAuditRiskInput(
        fiscal_year=fiscal_year,
        business_type=business_type,
        is_manufacturer=is_manufacturer,
        prior_3yr_audit_status=prior_3yr_audit_status,
        months_non_filing=months_non_filing if months_non_filing > 0 else None,
        customs_import_value=Decimal(str(customs_import_value)) if customs_import_value > 0 else None,
        exempt_income=Decimal(str(exempt_income)) if exempt_income > 0 else None,
        refund_claim=Decimal(str(refund_claim)) if refund_claim > 0 else None,
    )
    db = _get_session()
    try:
        r = assess_fbr_audit_risk(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


AUDIT_AGENT = Agent(
    name="Audit & Regulatory Agent",
    instructions="""You are the Audit & Regulatory Agent for the AI Accountant.

You handle anomaly detection, internal audit support, FBR audit risk scoring, statutory records, and compliance deadline tracking. You have 6 tools.

Available tools:
1. tool_detect_anomaly_transactions - Pattern-based fraud/anomaly detection (no approval).
2. tool_get_compliance_deadlines - Query compliance deadlines and due dates (no approval).
3. tool_support_internal_audit - Full internal audit scan with 5 patterns (REQUIRES APPROVAL).
4. tool_resolve_flagged_entry - Mark an audit flag as confirmed or waived (REQUIRES APPROVAL).
5. tool_maintain_statutory_registers - CRUD for directors/members/charges/contracts/beneficial_owners registers (REQUIRES APPROVAL for writes).
6. tool_assess_fbr_audit_risk - Score FBR audit-selection risk from historically-disclosed parameters (no approval).

Rules:
- Greetings, chit-chat, or general questions ('hi', 'hello', 'how are you',
  'what can you do', 'thanks'): answer conversationally. Do NOT call any tool.
- Call a tool ONLY when the user asks for specific accounting work (cash balance,
  record expense, reports, etc.).
- For tools 3-5: tell the user these require approval before writing.
- When the user asks to confirm/waive an audit flag, call tool_resolve_flagged_entry.
- Pass dates in YYYY-MM-DD format.
- Pass amounts as string numbers (e.g., '500000' not 500000).
- Explain results in plain English after tool calls.
""",
    tools=[
        tool_detect_anomaly_transactions,
        tool_get_compliance_deadlines,
        tool_support_internal_audit,
        tool_resolve_flagged_entry,
        tool_maintain_statutory_registers,
        tool_assess_fbr_audit_risk,
    ],
    model=GROQ_MODEL,
)


async def run_audit_agent(user_request: str) -> str:
    """Run the Audit & Regulatory Agent. Groq -> Groq fallback -> Gemini."""
    for attempt_model, provider_fn, label in [
        (GROQ_MODEL, create_groq_provider, "Groq"),
        (GROQ_FALLBACK_MODEL, create_groq_provider, "Groq fallback"),
        (GEMINI_MODEL, create_gemini_provider, "Gemini"),
    ]:
        try:
            agent = AUDIT_AGENT if attempt_model == GROQ_MODEL else Agent(
                name="Audit & Regulatory Agent",
                instructions=AUDIT_AGENT.instructions,
                tools=AUDIT_AGENT.tools,
                model=attempt_model,
            )
            result = await Runner.run(agent, input=user_request, run_config=RunConfig(model_provider=provider_fn()))
            return result.final_output
        except Exception:
            last_error = f"{label}: failure"
    return f"Error: All providers unavailable.\n{last_error}"
