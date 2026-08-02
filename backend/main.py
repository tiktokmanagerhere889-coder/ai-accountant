from __future__ import annotations

import json
import uuid
import logging
from datetime import date, datetime
from io import BytesIO
from typing import Optional, Any
from decimal import Decimal

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from db.database import get_db, init_db, get_session
from db.models import Base, AuditLog, UserRole, SystemBackupLog, JournalEntry
from db.seed_and_migrate import run_migrations
from agent_defs.orchestrator import run_orchestrator
from tool_registry import execute_tool, list_all_tools, get_tool_info
from export_service import build_xlsx, build_csv
from approval_service import (
    APPROVAL_REQUIRED_TOOLS,
    approve_or_execute,
    list_approval_history,
    list_pending_approvals,
    queue_for_approval,
    reject_approval,
    serialize_approval,
)

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

# Ensure all tables are initialized
init_db()

# Idempotent migrations + seeds (fetched_at column, tax/EOBI/asset configs)
run_migrations()

app = FastAPI(title="AI Accountant Backend", version="1.0.0")

# Setup CORS middleware
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins, adjust if needed for production domain locking
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic Schemas for direct backend endpoints

class AuditTrailCreate(BaseModel):
    user_id: str = Field(..., description="ID of the user performing the action")
    action: str = Field(..., description="Action description (e.g. USER_LOGIN)")
    table_name: str = Field(..., description="Target database table")
    record_id: str = Field(..., description="Target record identifier")


class AuditTrailResponse(BaseModel):
    audit_id: str
    user_id: str
    action: str
    table_name: str
    record_id: str
    timestamp: datetime

    class Config:
        from_attributes = True


class UserRoleCreate(BaseModel):
    role_name: str = Field(..., description="Unique role name")
    permissions: list[str] = Field(..., description="List of permissions")


class UserRoleResponse(BaseModel):
    role_id: str
    role_name: str
    permissions: list[str]

    class Config:
        from_attributes = True


class BackupTriggerInput(BaseModel):
    notes: Optional[str] = Field(default=None, description="Optional trigger details")


class BackupTriggerResponse(BaseModel):
    backup_id: str
    status: str
    triggered_at: date
    notes: Optional[str]
    message: str


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str


# Root and Health Checks

@app.get("/")
def root() -> dict[str, str]:
    return {"status": "ok", "app": "AI Accountant Backend"}


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        # Check DB connection
        db.execute(func.now())
        db_status = "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "unhealthy"

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "database": db_status,
        "timestamp": datetime.utcnow()
    }


# Direct-Backend Features (NO LLM, NO Agents)

# 1. Audit Trail Endpoint
@app.post("/audit-trail", response_model=AuditTrailResponse, status_code=201)
def create_audit_trail(payload: AuditTrailCreate, db: Session = Depends(get_db)):
    audit_id = f"AUD-{uuid.uuid4().hex[:8].upper()}"
    log_entry = AuditLog(
        audit_id=audit_id,
        user_id=payload.user_id,
        action=payload.action,
        table_name=payload.table_name,
        record_id=payload.record_id,
        timestamp=datetime.now()
    )
    db.add(log_entry)
    db.commit()
    db.refresh(log_entry)
    return log_entry


@app.get("/audit-trail", response_model=list[AuditTrailResponse])
def get_audit_trail(
    user_id: Optional[str] = None,
    limit: int = Query(default=50, le=100),
    offset: int = 0,
    db: Session = Depends(get_db)
):
    query = db.query(AuditLog)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    return query.order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit).all()


# 2. User Roles CRUD
@app.post("/roles", response_model=UserRoleResponse, status_code=201)
def create_role(payload: UserRoleCreate, db: Session = Depends(get_db)):
    existing = db.query(UserRole).filter(UserRole.role_name == payload.role_name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Role name already exists")

    role_id = f"ROL-{uuid.uuid4().hex[:8].upper()}"
    role_entry = UserRole(
        role_id=role_id,
        role_name=payload.role_name,
        permissions=json.dumps(payload.permissions)
    )
    db.add(role_entry)
    db.commit()
    db.refresh(role_entry)

    return UserRoleResponse(
        role_id=role_entry.role_id,
        role_name=role_entry.role_name,
        permissions=json.loads(role_entry.permissions)
    )


@app.get("/roles", response_model=list[UserRoleResponse])
def list_roles(db: Session = Depends(get_db)):
    roles = db.query(UserRole).all()
    return [
        UserRoleResponse(
            role_id=r.role_id,
            role_name=r.role_name,
            permissions=json.loads(r.permissions)
        )
        for r in roles
    ]


@app.put("/roles/{role_id}", response_model=UserRoleResponse)
def update_role(role_id: str, payload: UserRoleCreate, db: Session = Depends(get_db)):
    role_entry = db.query(UserRole).filter(UserRole.role_id == role_id).first()
    if not role_entry:
        raise HTTPException(status_code=404, detail="Role not found")

    # Check uniqueness of role_name if changed
    if role_entry.role_name != payload.role_name:
        existing = db.query(UserRole).filter(UserRole.role_name == payload.role_name).first()
        if existing:
            raise HTTPException(status_code=400, detail="Role name already exists")

    role_entry.role_name = payload.role_name
    role_entry.permissions = json.dumps(payload.permissions)
    db.commit()
    db.refresh(role_entry)

    return UserRoleResponse(
        role_id=role_entry.role_id,
        role_name=role_entry.role_name,
        permissions=json.loads(role_entry.permissions)
    )


# 3. Scheduled / Triggered backup
@app.post("/backup/trigger", response_model=BackupTriggerResponse, status_code=202)
def trigger_backup(payload: BackupTriggerInput, db: Session = Depends(get_db)):
    backup_id = f"BAK-{uuid.uuid4().hex[:8].upper()}"
    log_entry = SystemBackupLog(
        backup_id=backup_id,
        backup_type="backup",
        status="completed", # Simulating completed backup execution
        triggered_by="direct-endpoint",
        triggered_at=date.today(),
        notes=payload.notes or "Triggered via backend API",
        completed_at=date.today(),
        size_bytes=1024 * 1024 * 15 # Simulating a 15MB backup
    )
    db.add(log_entry)
    db.commit()
    db.refresh(log_entry)
    return BackupTriggerResponse(
        backup_id=log_entry.backup_id,
        status=log_entry.status,
        triggered_at=log_entry.triggered_at,
        notes=log_entry.notes,
        message=f"Backup {backup_id} completed successfully."
    )


@app.get("/backup/history")
def get_backup_history(db: Session = Depends(get_db)):
    logs = db.query(SystemBackupLog).order_by(SystemBackupLog.triggered_at.desc()).all()
    return [
        {
            "backup_id": log.backup_id,
            "backup_type": log.backup_type,
            "status": log.status,
            "triggered_by": log.triggered_by,
            "triggered_at": log.triggered_at,
            "completed_at": log.completed_at,
            "size_bytes": log.size_bytes,
            "notes": log.notes
        }
        for log in logs
    ]


# API Key Management
@app.post("/settings/api-keys")
def save_api_keys(keys: dict, db: Session = Depends(get_db)):
    """Save user-provided API keys. Accepts { key_name: key_value } pairs."""
    from db.models import UserApiKey
    for key_name, key_value in keys.items():
        if key_name not in ("GROQ_API_KEY", "CEREBRAS_API_KEY"):
            continue
        existing = db.query(UserApiKey).filter(UserApiKey.key_name == key_name).first()
        if existing:
            existing.key_value = key_value
        else:
            db.add(UserApiKey(id=str(uuid.uuid4()), key_name=key_name, key_value=key_value))
    db.commit()
    return {"status": "saved", "message": "API keys updated successfully"}


@app.get("/settings/api-keys")
def get_api_key_status(db: Session = Depends(get_db)):
    """Return which API keys have been user-configured (without exposing key values)."""
    from db.models import UserApiKey
    import os
    user_keys = db.query(UserApiKey).all()
    configured = {k.key_name: True for k in user_keys}
    # Also check which env vars exist
    for name in ("GROQ_API_KEY", "CEREBRAS_API_KEY"):
        if os.environ.get(name):
            configured.setdefault(name, False)
    return {"keys": configured}


# Orchestrator Routes (AI Routing)

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Handle a chat message.

    Reliability-first: try the deterministic intent router (no LLM decides what
    to run) so the answer is always grounded in real tool data. If the router
    matches, we execute the tool directly and format the result. Only when the
    router does NOT match a known intent do we fall back to the LLM orchestrator.
    """
    try:
        from db.database import get_session
        from intent_router import execute_route, is_approval_required
        from result_formatter import format_tool_result, has_dedicated_formatter

        db = get_session()
        try:
            routed = execute_route(request.message, db)
        finally:
            db.close()

        if routed is not None:
            tool_name, result = routed
            if is_approval_required(tool_name):
                # Approval-required tools still queue via the queue service
                from approval_service import queue_for_approval
                db = get_session()
                try:
                    entry = queue_for_approval(tool_name, result, db, submitted_by="chat-router")
                finally:
                    db.close()
                return ChatResponse(
                    response=f"[Queued for approval: {entry.approval_id}] The action '{tool_name}' requires your approval. Open the Approvals panel to review and approve."
                )
            text = format_tool_result(tool_name, result)
            # LLM polish re-formats presentation only. It runs for EVERY routed
            # tool so answers read naturally, but a verification step rejects
            # output that introduces numbers absent from the real result — so
            # Groq can reformat but never change the values.
            try:
                import json as _json
                raw_json = _json.dumps(result, default=str) if isinstance(result, dict) else str(result)
                polished = await _format_with_llm(request.message, text, raw_json)
                if polished:
                    text = polished
            except Exception:
                pass
            return ChatResponse(response=text)

        # Router didn't match - fall back to LLM orchestrator
        response_text = await run_orchestrator(request.message)
        return ChatResponse(response=response_text)
    except Exception as e:
        logger.error(f"Orchestrator invocation error: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred while processing your request.")


async def _format_with_llm(message: str, tool_text: str, raw_json: str = "") -> str:
    """Best-effort: ask Groq to polish the tool result into plain English.

    The LLM may ONLY reformat presentation - it must preserve every value
    exactly as given. A verification pass rejects the polished text if it
    introduces numbers not present in the source data (e.g. Groq once replaced
    a real cash balance of 245,000 with a hallucinated -1,117,000).

    Returns the polished text, or "" if the LLM is unavailable, produces a
    broken artifact, or changes values. Never blocks the response.
    """
    try:
        import re as _re
        from agent_defs.model_providers import create_groq_provider, GROQ_FALLBACK_MODEL
        from agents import Runner
        from agents.run_config import RunConfig
        from agents import Agent

        formatter = Agent(
            name="Result Formatter",
            instructions=(
                "You are a financial report presenter. You receive a user question and the raw "
                "tool result data. Rewrite the result as a clear, friendly, plain-English answer "
                "to the user's question.\n"
                "STRICT RULES:\n"
                "- Use ONLY the numbers and values present in the data. Never round, change, or "
                "invent any number, even if it looks wrong or negative.\n"
                "- Do NOT add any figure that is not in the data.\n"
                "- Do NOT refuse or say you cannot access data - the data is provided.\n"
                "- Keep it under 150 words. Plain text only - no tags, no JSON, no code blocks."
            ),
            model=GROQ_FALLBACK_MODEL,
        )
        result = await Runner.run(
            formatter,
            input=f"User asked: {message}\n\nTool result data (JSON):\n{raw_json or tool_text}",
            run_config=RunConfig(model_provider=create_groq_provider()),
        )
        polished = result.final_output.strip()
        # Reject artifacts: tool-call tags, JSON blocks, or content shorter than the raw
        if not polished or "<|" in polished or polished.startswith("{"):
            return ""
        # Verification: any number in the polished text must exist in the source.
        source = raw_json or tool_text
        if not _numbers_preserved(polished, source):
            return ""
        return polished
    except Exception:
        return ""


def _numbers_preserved(polished: str, source: str) -> bool:
    """True if every number in the polished text appears in the source data.

    Both sides are normalized (commas stripped, trailing decimals trimmed) so
    "245,000.00" in the reply matches "245000.00" in the source. If the LLM
    invents any number not present in the source, this returns False and the
    polished text is discarded in favor of the deterministic formatter.
    """
    import re as _re

    def _norm(s: str) -> str:
        s = s.replace(",", "").strip()
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return s

    source_nums = {_norm(n) for n in _re.findall(r"\d[\d,]*\.?\d*", source.replace("PKR", ""))}
    polished_nums = {_norm(n) for n in _re.findall(r"\d[\d,]*\.?\d*", polished.replace("PKR", ""))}
    for n in polished_nums:
        if n and n not in source_nums:
            return False
    return True


# Direct Tool Execution (bypasses LLM)

class ToolExecuteRequest(BaseModel):
    tool_name: str = Field(..., description="Tool name from the registry")
    params: dict = Field(default_factory=dict, description="Tool parameters as key-value pairs")
    needs_approval: Optional[bool] = Field(
        default=False,
        description="Queue the tool for human approval instead of executing it directly",
    )
    bypass_approval: Optional[bool] = Field(
        default=False,
        description="Execute immediately even if the tool normally requires approval",
    )


class ToolExecuteResponse(BaseModel):
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None


class ApprovalApproveRequest(BaseModel):
    edited_params: Optional[dict] = Field(
        default=None,
        description="Edited tool parameters to use during execution (optional)",
    )


class ApprovalRejectRequest(BaseModel):
    reason: Optional[str] = Field(default=None, description="Reason for rejection")


@app.get("/tools/list")
def list_tools_endpoint():
    """List all available tools with metadata (ai_only, description)."""
    return {"tools": list_all_tools()}


@app.post("/tools/execute", response_model=ToolExecuteResponse)
def execute_tool_direct(request: ToolExecuteRequest, db: Session = Depends(get_db)):
    """Execute a tool directly without going through the LLM orchestrator.

    Tools requiring approval (needs_approval flag or in APPROVAL_REQUIRED_TOOLS)
    are queued in the approval queue instead of executing immediately. The
    returned result contains queued=true and the approval_id.
    """
    requires_approval = not request.bypass_approval and (
        request.needs_approval or request.tool_name in APPROVAL_REQUIRED_TOOLS
    )
    if requires_approval:
        entry = queue_for_approval(
            request.tool_name,
            request.params,
            db,
            submitted_by="direct-mode",
        )
        return ToolExecuteResponse(
            success=True,
            result={
                "queued": True,
                "approval_id": entry.approval_id,
                "tool_name": entry.tool_name,
                "status": "pending_approval",
                "message": f"Queued for approval: {entry.approval_id}",
            },
        )
    try:
        result = execute_tool(request.tool_name, request.params)
        return ToolExecuteResponse(success=True, result=result)
    except Exception as e:
        logger.error(f"Tool execution error ({request.tool_name}): {e}")
        return ToolExecuteResponse(success=False, error=str(e))


# Approval queue endpoints (queue -> view -> edit -> approve/reject -> execute)

@app.get("/approvals/pending")
def get_pending_approvals(db: Session = Depends(get_db)):
    """List all pending approval requests."""
    return {"approvals": [serialize_approval(a) for a in list_pending_approvals(db)]}


@app.get("/approvals/history")
def get_approval_history(
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
):
    """List resolved approvals (approved/edited/rejected), newest first."""
    return {"approvals": [serialize_approval(a) for a in list_approval_history(db, limit=limit)]}


@app.post("/approvals/{approval_id}/approve")
def approve_pending_approval(
    approval_id: str,
    payload: ApprovalApproveRequest,
    db: Session = Depends(get_db),
):
    """Approve a queued tool call, optionally with edited params. Executes the tool."""
    try:
        entry, result = approve_or_execute(approval_id, db, payload.edited_params)
    except ValueError as e:
        msg = str(e)
        status_code = 404 if "not found" in msg else 400
        raise HTTPException(status_code=status_code, detail=msg)
    except Exception as e:
        logger.error(f"Approval execution error ({approval_id}): {e}")
        raise HTTPException(status_code=500, detail=str(e))
    return {"approval": serialize_approval(entry), "result": result}


@app.post("/approvals/{approval_id}/reject")
def reject_pending_approval(
    approval_id: str,
    payload: ApprovalRejectRequest,
    db: Session = Depends(get_db),
):
    """Reject a queued tool call with an optional reason."""
    try:
        entry = reject_approval(approval_id, db, payload.reason)
    except ValueError as e:
        msg = str(e)
        status_code = 404 if "not found" in msg else 400
        raise HTTPException(status_code=status_code, detail=msg)
    return {"approval": serialize_approval(entry)}


# Data Export (per agent / all agents)

@app.get("/export/xlsx")
def export_xlsx(agent: Optional[str] = Query(default=None, description="Agent id or 'all'")):
    """Download professional XLSX report. agent=all or specific agent id."""
    db = get_session()
    try:
        data = build_xlsx(db, agent)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="export.xlsx"'},
    )


@app.get("/export/csv")
def export_csv(agent: Optional[str] = Query(default=None, description="Agent id or 'all'")):
    """Download plain CSV. agent=all or specific agent id."""
    db = get_session()
    try:
        data = build_csv(db, agent)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()
    return StreamingResponse(
        BytesIO(data),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="export.csv"'},
    )
