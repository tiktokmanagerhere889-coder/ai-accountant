"""System Admin Agent - wraps 4 tools as an OpenAI Agent."""
import sys, os, json, typing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from decimal import Decimal

from agents import Agent, function_tool, Runner
from agents.run_config import RunConfig

from db.database import init_db, get_session
from tools.schemas import (
    CheckSystemStatusInput, CheckSystemStatusOutput,
    GetUsageStatisticsInput, GetUsageStatisticsOutput,
    ManageSystemPreferencesInput, ManageSystemPreferencesOutput,
    ScheduleSystemTaskInput, ScheduleSystemTaskOutput,
)
from tools.system_admin_tools import (
    check_system_status, get_usage_statistics,
    manage_system_preferences, schedule_system_task,
)
from agent_defs.model_providers import (
    create_groq_provider, create_gemini_provider,
    GROQ_MODEL, GROQ_FALLBACK_MODEL, GEMINI_MODEL,
)


def _get_session():
    init_db()
    return get_session()


def _to_json(obj):
    return json.dumps(json.loads(obj.model_dump_json()), indent=2, default=str)


# -- Tool 1: check_system_status --
@function_tool
def tool_check_system_status(check_type: str = "") -> str:
    """Run system health checks. No approval needed.

    Args:
        check_type: Optional comma-separated: database, providers, agents. Empty = all.
    """
    types = [t.strip() for t in check_type.split(",") if t.strip()] if check_type else None
    inp = CheckSystemStatusInput(check_type=types)
    db = _get_session()
    try:
        r = check_system_status(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 2: get_usage_statistics --
@function_tool
def tool_get_usage_statistics(from_date: str, to_date: str, group_by: str = "", include_detail: bool = False) -> str:
    """Get system usage analytics. No approval needed.

    Args:
        from_date: Start date YYYY-MM-DD.
        to_date: End date YYYY-MM-DD.
        group_by: Optional: provider, agent, day.
        include_detail: Include detailed breakdown.
    """
    inp = GetUsageStatisticsInput(
        from_date=date.fromisoformat(from_date),
        to_date=date.fromisoformat(to_date),
        group_by=group_by if group_by else None,
        include_detail=include_detail,
    )
    db = _get_session()
    try:
        r = get_usage_statistics(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 3: manage_system_preferences --
@function_tool
def tool_manage_system_preferences(action: str, settings_json: str = "", setting_key: str = "") -> str:
    """Manage company settings and system preferences. REQUIRES APPROVAL for writes.

    Args:
        action: view, update, reset.
        settings_json: JSON string of key-value settings (for update action).
        setting_key: Specific key to view or reset.
    """
    settings = json.loads(settings_json) if settings_json else None
    key = setting_key if setting_key else None
    inp = ManageSystemPreferencesInput(
        action=action.lower().strip(),
        settings=settings,
        setting_key=key,
    )
    db = _get_session()
    try:
        r = manage_system_preferences(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 4: schedule_system_task --
@function_tool
def tool_schedule_system_task(task_type: str, schedule_time: str = "", parameters_json: str = "", notes: str = "") -> str:
    """Schedule a system maintenance task. REQUIRES APPROVAL.

    Args:
        task_type: backup, export_data, maintenance, cleanup.
        schedule_time: Optional: now, off_peak, or datetime string.
        parameters_json: Optional JSON string of parameters.
        notes: Optional notes.
    """
    params = json.loads(parameters_json) if parameters_json else None
    n = notes if notes else None
    st = schedule_time if schedule_time else None
    inp = ScheduleSystemTaskInput(
        task_type=task_type.lower().strip(),
        schedule_time=st,
        parameters=params,
        notes=n,
    )
    db = _get_session()
    try:
        r = schedule_system_task(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


SYSTEM_ADMIN_AGENT = Agent(
    name="System Admin Agent",
    instructions="""You are the System Admin Agent for the AI Accountant.

You handle system health monitoring, usage stats, configuration management, and task scheduling. You have 4 tools.

Available tools:
1. tool_check_system_status - Run health checks on DB, providers, agents (no approval).
2. tool_get_usage_statistics - Analyze system usage and success rates (no approval).
3. tool_manage_system_preferences - View/update/reset company settings (REQUIRES APPROVAL for update/reset).
4. tool_schedule_system_task - Schedule backup/export/maintenance/cleanup tasks (REQUIRES APPROVAL).

Rules:
- Greetings, chit-chat, or general questions ('hi', 'hello', 'how are you',
  'what can you do', 'thanks'): answer conversationally. Do NOT call any tool.
- Call a tool ONLY when the user asks for specific accounting work (cash balance,
  record expense, reports, etc.).
- For tools 3-4: tell the user these require approval.
- For tool 3 (update): the user must provide settings as a JSON object.
- Explain results in plain English after tool calls.
""",
    tools=[
        tool_check_system_status,
        tool_get_usage_statistics,
        tool_manage_system_preferences,
        tool_schedule_system_task,
    ],
    model=GROQ_MODEL,
)


async def run_system_admin_agent(user_request: str) -> str:
    """Run the System Admin Agent. Groq -> Groq fallback -> Gemini."""
    for attempt_model, provider_fn, label in [
        (GROQ_MODEL, create_groq_provider, "Groq"),
        (GROQ_FALLBACK_MODEL, create_groq_provider, "Groq fallback"),
        (GEMINI_MODEL, create_gemini_provider, "Gemini"),
    ]:
        try:
            agent = SYSTEM_ADMIN_AGENT if attempt_model == GROQ_MODEL else Agent(
                name="System Admin Agent",
                instructions=SYSTEM_ADMIN_AGENT.instructions,
                tools=SYSTEM_ADMIN_AGENT.tools,
                model=attempt_model,
            )
            result = await Runner.run(agent, input=user_request, run_config=RunConfig(model_provider=provider_fn()))
            return result.final_output
        except Exception:
            last_error = f"{label}: failure"
    return f"Error: All providers unavailable.\n{last_error}"
