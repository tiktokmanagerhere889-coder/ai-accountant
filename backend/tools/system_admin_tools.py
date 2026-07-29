"""Agent 10 — System Admin Tools.

4 tools: check_system_status, get_usage_statistics,
manage_system_preferences, schedule_system_task.
"""
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
import uuid
import sys, os, importlib

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from db.models import SystemConfig, SystemBackupLog
from tools.schemas import (
    SystemCheck,
    CheckSystemStatusInput, CheckSystemStatusOutput,
    UsageBreakdown,
    GetUsageStatisticsInput, GetUsageStatisticsOutput,
    ManageSystemPreferencesInput, ManageSystemPreferencesOutput,
    ScheduleSystemTaskInput, ScheduleSystemTaskOutput,
)


def _round(value: Decimal, places: int = 2) -> Decimal:
    return value.quantize(Decimal("0." + "0" * places), rounding=ROUND_HALF_UP)


_DEFAULT_SETTINGS = {
    "company_name": "My Company",
    "fiscal_year_end": "2026-12-31",
    "default_currency": "PKR",
    "default_timezone": "Asia/Karachi",
    "backup_enabled": "true",
    "retention_days": "90",
}


# ---------------------------------------------------------------------------
# Tool 1: Check System Status
# ---------------------------------------------------------------------------

def check_system_status(inp: CheckSystemStatusInput, db: Session) -> CheckSystemStatusOutput:
    """Run system health checks: database, providers, agents."""
    check_types = set(inp.check_type or ["all"])
    run_all = "all" in check_types

    checks: list[SystemCheck] = []

    # 1. Database check
    if run_all or "database" in check_types:
        import time
        start = time.time()
        try:
            result = db.execute(text("SELECT 1")).scalar()
            latency = _round(Decimal(str((time.time() - start) * 1000)), 1)
            if result == 1:
                checks.append(SystemCheck(
                    name="database", status="healthy",
                    detail="PostgreSQL connection OK",
                    latency_ms=latency,
                ))
            else:
                checks.append(SystemCheck(
                    name="database", status="degraded",
                    detail=f"Unexpected result: {result}",
                    latency_ms=latency,
                ))
        except Exception as e:
            checks.append(SystemCheck(
                name="database", status="unhealthy",
                detail=f"Database connection failed: {e}",
                latency_ms=Decimal("0"),
            ))

    # 2. Providers check
    if run_all or "providers" in check_types:
        groq_key = os.environ.get("GROQ_API_KEY", "")
        cerebras_key = os.environ.get("CEREBRAS_API_KEY", "")
        groq_model = os.environ.get("GROQ_MODEL", "not set")
        cerebras_model = os.environ.get("CEREBRAS_MODEL", "not set")

        providers_available = 0
        providers_total = 2
        provider_details = []

        if groq_key:
            providers_available += 1
            provider_details.append(f"Groq: configured (model: {groq_model})")
        else:
            provider_details.append("Groq: not configured")

        if cerebras_key:
            providers_available += 1
            provider_details.append(f"Cerebras: configured (model: {cerebras_model})")
        else:
            provider_details.append("Cerebras: not configured")

        provider_status = "healthy" if providers_available == providers_total else "degraded" if providers_available > 0 else "unhealthy"
        checks.append(SystemCheck(
            name="providers", status=provider_status,
            detail="; ".join(provider_details),
            latency_ms=Decimal("0"),
        ))

    # 3. Agents check
    if run_all or "agents" in check_types:
        agent_modules = [
            "daily_entry_agent", "ledger_agent", "reconciliation_agent",
            "month_end_reporting_agent", "year_end_agent", "cost_advanced_agent",
            "tax_agent", "audit_agent", "advisory_agent",
        ]
        loaded = 0
        failed = []
        for mod in agent_modules:
            try:
                importlib.import_module(f"agent_defs.{mod}")
                loaded += 1
            except ImportError:
                failed.append(mod)

        total = len(agent_modules)
        agent_status = "healthy" if loaded == total else "degraded" if loaded > 0 else "unhealthy"
        detail = f"{loaded}/{total} agents loaded"
        if failed:
            detail += f"; failed: {', '.join(failed)}"
        checks.append(SystemCheck(
            name="agents", status=agent_status,
            detail=detail,
            latency_ms=Decimal("0"),
        ))

    # Overall status
    has_unhealthy = any(c.status == "unhealthy" for c in checks)
    has_degraded = any(c.status == "degraded" for c in checks)
    db_healthy = any(c.name == "database" and c.status == "healthy" for c in checks)

    if has_unhealthy and not db_healthy:
        overall = "unhealthy"
    elif has_unhealthy or has_degraded:
        overall = "degraded"
    else:
        overall = "healthy"

    count = len(checks)
    healthy_count = sum(1 for c in checks if c.status == "healthy")
    summary = f"System status: {overall.upper()}. {healthy_count}/{count} checks passed."

    return CheckSystemStatusOutput(
        overall_status=overall,
        checks=checks,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Tool 2: Get Usage Statistics
# ---------------------------------------------------------------------------

def get_usage_statistics(inp: GetUsageStatisticsInput, db: Session) -> GetUsageStatisticsOutput:
    """Analyze system usage from backup logs and request patterns."""
    period_str = f"{inp.from_date.isoformat()} to {inp.to_date.isoformat()}"

    backup_logs = db.query(SystemBackupLog).filter(
        SystemBackupLog.triggered_at >= inp.from_date,
        SystemBackupLog.triggered_at <= inp.to_date,
    ).all()

    total = len(backup_logs)
    successes = sum(1 for b in backup_logs if b.status == "completed")
    failures = sum(1 for b in backup_logs if b.status == "failed")

    # Build breakdown by backup_type
    type_map: dict[str, dict] = {}
    for b in backup_logs:
        t = b.backup_type
        if t not in type_map:
            type_map[t] = {"requests": 0, "successes": 0, "failures": 0, "latency_sum": Decimal("0")}
        type_map[t]["requests"] += 1
        if b.status == "completed":
            type_map[t]["successes"] += 1
        elif b.status == "failed":
            type_map[t]["failures"] += 1

    breakdown = [
        UsageBreakdown(
            dimension=t,
            requests=v["requests"],
            successes=v["successes"],
            failures=v["failures"],
            avg_latency=Decimal("0"),
        )
        for t, v in sorted(type_map.items())
    ]

    # Recommendations
    recommendations = []
    if total == 0:
        recommendations.append("No usage data recorded for this period — logs may be empty.")
    if total > 0 and failures / total > 0.1:
        recommendations.append("High failure rate detected — review system configuration.")
    if not breakdown:
        breakdown = []
    if not recommendations:
        healthy_pct = _round(Decimal(str(successes)) / Decimal(str(total)) * 100) if total > 0 else Decimal("0")
        recommendations.append(f"System healthy — {healthy_pct}% success rate across {total} operations.")

    avg_latency = Decimal("0")
    summary = f"Usage summary: {total} operations, {successes} successes, {failures} failures."

    return GetUsageStatisticsOutput(
        period=period_str,
        total_requests=total,
        success_count=successes,
        failure_count=failures,
        avg_latency_ms=avg_latency,
        breakdown=breakdown,
        recommendations=recommendations,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Tool 3: Manage System Preferences
# ---------------------------------------------------------------------------

def _seed_defaults(db: Session):
    """Seed default settings if system_config table is empty."""
    count = db.query(func.count(SystemConfig.id)).scalar()
    if count == 0:
        today = date.today()
        for key, value in _DEFAULT_SETTINGS.items():
            db.add(SystemConfig(
                config_key=key,
                config_value=value,
                description=_DEFAULT_DESCRIPTIONS.get(key, ""),
                updated_at=today,
            ))
        db.commit()


_DEFAULT_DESCRIPTIONS = {
    "company_name": "Company legal name for reports",
    "fiscal_year_end": "Fiscal year end date (YYYY-MM-DD)",
    "default_currency": "Default currency code",
    "default_timezone": "System timezone",
    "backup_enabled": "Enable automatic backups (true/false)",
    "retention_days": "Data retention period in days",
}


def manage_system_preferences(inp: ManageSystemPreferencesInput, db: Session) -> ManageSystemPreferencesOutput:
    """CRUD for system configuration settings.

    Actions: view, update, reset.
    Requires approval for write actions.
    """
    _seed_defaults(db)
    today = date.today()

    valid_actions = {"view", "update", "reset"}
    if inp.action not in valid_actions:
        raise ValueError(f"Invalid action '{inp.action}'. Must be one of: {', '.join(sorted(valid_actions))}")

    # -- VIEW --
    if inp.action == "view":
        if inp.setting_key:
            entry = db.query(SystemConfig).filter(SystemConfig.config_key == inp.setting_key).first()
            if not entry:
                return ManageSystemPreferencesOutput(
                    action_performed="view",
                    settings={},
                    changed_keys=[],
                    message=f"Setting '{inp.setting_key}' not found.",
                    needs_approval=False,
                )
            return ManageSystemPreferencesOutput(
                action_performed="view",
                settings={entry.config_key: entry.config_value},
                changed_keys=[],
                message=f"Retrieved setting '{inp.setting_key}'.",
                needs_approval=False,
            )
        else:
            entries = db.query(SystemConfig).all()
            settings = {e.config_key: e.config_value for e in entries}
            return ManageSystemPreferencesOutput(
                action_performed="view",
                settings=settings,
                changed_keys=[],
                message=f"Retrieved {len(entries)} setting(s).",
                needs_approval=False,
            )

    # -- UPDATE --
    if inp.action == "update":
        if not inp.settings:
            entries = db.query(SystemConfig).all()
            current = {e.config_key: e.config_value for e in entries}
            return ManageSystemPreferencesOutput(
                action_performed="update",
                settings=current,
                changed_keys=[],
                message="No settings provided to update. Current configuration returned.",
                needs_approval=True,
            )

        changed = []
        warnings = []
        for key, value in inp.settings.items():
            existing = db.query(SystemConfig).filter(SystemConfig.config_key == key).first()
            if existing:
                existing.config_value = str(value)
                existing.updated_at = today
                changed.append(key)
            else:
                db.add(SystemConfig(
                    config_key=key,
                    config_value=str(value),
                    description="Newly created — verify",
                    updated_at=today,
                ))
                changed.append(key)
                warnings.append(f"'{key}' is new — please verify")

        db.commit()

        # Return updated state
        entries = db.query(SystemConfig).all()
        current = {e.config_key: e.config_value for e in entries}

        msg = f"Updated {len(changed)} setting(s): {', '.join(changed)}."
        if warnings:
            msg += " " + "; ".join(warnings)

        return ManageSystemPreferencesOutput(
            action_performed="update",
            settings=current,
            changed_keys=changed,
            message=msg,
            needs_approval=True,
        )

    # -- RESET --
    if inp.action == "reset":
        if not inp.setting_key:
            raise ValueError("setting_key is required for reset action")

        entry = db.query(SystemConfig).filter(SystemConfig.config_key == inp.setting_key).first()
        if not entry:
            raise ValueError(f"Setting '{inp.setting_key}' not found — cannot reset")

        db.delete(entry)
        db.commit()

        return ManageSystemPreferencesOutput(
            action_performed="reset",
            settings={},
            changed_keys=[inp.setting_key],
            message=f"Setting '{inp.setting_key}' has been reset (removed).",
            needs_approval=True,
        )


# ---------------------------------------------------------------------------
# Tool 4: Schedule System Task
# ---------------------------------------------------------------------------

def schedule_system_task(inp: ScheduleSystemTaskInput, db: Session) -> ScheduleSystemTaskOutput:
    """Schedule a system maintenance task (backup, export, maintenance, cleanup)."""
    task_id = f"TASK-{uuid.uuid4().hex[:8].upper()}"
    today = date.today()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    valid_types = {"backup", "export_data", "maintenance", "cleanup"}
    if inp.task_type not in valid_types:
        raise ValueError(f"Invalid task_type '{inp.task_type}'. Must be one of: {', '.join(sorted(valid_types))}")

    # Determine schedule time
    if not inp.schedule_time or inp.schedule_time == "now":
        scheduled_for = now_str
        time_note = "immediately"
    elif inp.schedule_time == "off_peak":
        scheduled_for = f"{today.isoformat()} 02:00"
        time_note = "next off-peak window (02:00)"
    else:
        scheduled_for = inp.schedule_time
        time_note = inp.schedule_time

    # Generate description based on task type
    params = inp.parameters or {}
    type_details = {
        "backup": "Full database backup",
        "export_data": f"Data export ({params.get('scope', 'all')})",
        "maintenance": "System maintenance — expected brief downtime",
        "cleanup": f"Cleanup ({params.get('scope', 'old backups and temp data')})",
    }

    description = type_details.get(inp.task_type, inp.task_type)

    # Estimate completion
    estimates = {
        "backup": "2 minutes",
        "export_data": "5 minutes",
        "maintenance": "10 minutes",
        "cleanup": "3 minutes",
    }
    estimated = estimates.get(inp.task_type, "5 minutes")

    # Record in backup log
    log_entry = SystemBackupLog(
        backup_id=task_id,
        backup_type=inp.task_type,
        status="scheduled",
        triggered_by="system",
        triggered_at=today,
        notes=inp.notes or description,
        parameters=str(params) if params else None,
    )
    db.add(log_entry)
    db.commit()

    msg = f"Task {task_id}: {description} scheduled for {time_note}. Estimated completion: {estimated}."

    return ScheduleSystemTaskOutput(
        task_id=task_id,
        task_type=inp.task_type,
        status="scheduled",
        scheduled_for=scheduled_for,
        estimated_completion=estimated,
        message=msg,
        needs_approval=True,
    )
