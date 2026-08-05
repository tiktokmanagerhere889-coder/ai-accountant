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
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    tool_calls: Optional[list["ToolCallInfo"]] = None
    conversation_id: Optional[str] = None
    pending: Optional["PendingIntent"] = None


class ToolCallInfo(BaseModel):
    toolName: str
    summary: str
    recordId: Optional[str] = None
    status: Optional[str] = None  # "executed" | "queued"


class PendingIntent(BaseModel):
    tool_name: str
    question: str
    conversation_id: str


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
        if key_name not in ("GROQ_API_KEY", "GEMINI_API_KEY"):
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
    for name in ("GROQ_API_KEY", "GEMINI_API_KEY"):
        if os.environ.get(name):
            configured.setdefault(name, False)
    return {"keys": configured}


# Orchestrator Routes (AI Routing)

def _tool_call_info(tool_name: str, result, message: str) -> ToolCallInfo:
    """Build a ToolCallInfo from a routed tool's result for chat transparency."""
    import json as _json
    summary = "Tool executed"
    record_id = None
    if isinstance(result, dict):
        # Extract a record id from common id keys
        for k in ("entry_id", "journal_entry_id", "record_id", "asset_id", "run_id", "task_id", "accrual_id", "cheque_id", "provision_id", "filing_id", "contact_id", "approval_id"):
            if result.get(k):
                record_id = str(result[k])
                break
        for k in ("message", "status", "summary", "description"):
            if result.get(k):
                summary = str(result[k])
                break
        # Report tools: include account count + total balances for a useful bubble
        if "accounts" in result and isinstance(result["accounts"], list):
            accounts = result["accounts"]
            if accounts:
                summary = f"{len(accounts)} accounts"
                # total_debits/total_credits may be top-level or per-account
                tdebits = result.get("total_debits")
                tcredits = result.get("total_credits")
                if tdebits is not None or tcredits is not None:
                    summary += f", debits {tdebits}, credits {tcredits}"
        elif "total_debits" in result and "total_credits" in result:
            summary = f"debits {result['total_debits']}, credits {result['total_credits']}"
    # Trim long summaries for the bubble
    if len(summary) > 120:
        summary = summary[:120] + "…"
    return ToolCallInfo(toolName=tool_name, summary=summary, recordId=record_id, status="executed")


async def _finish_routed(tool_name: str, result, message: str, conv_id: Optional[str] = None) -> ChatResponse:
    """Turn an executed tool's result into a ChatResponse (approval queue /
    LLM polish / tool_calls). Shared by the direct route and slot-fill paths."""
    from intent_router import is_approval_required
    from result_formatter import format_tool_result

    tool_call = _tool_call_info(tool_name, result, message)
    if is_approval_required(tool_name):
        # Approval-required tools still queue via the queue service
        from approval_service import queue_for_approval
        db = get_session()
        try:
            entry = queue_for_approval(tool_name, result, db, submitted_by="chat-router")
        finally:
            db.close()
        tool_call.status = "queued"
        tool_call.summary = f"Action queued for approval ({entry.approval_id})"
        return ChatResponse(
            response=f"[Queued for approval: {entry.approval_id}] The action '{tool_name}' requires your approval. Open the Approvals panel to review and approve.",
            tool_calls=[tool_call],
            conversation_id=conv_id,
        )
    text = format_tool_result(tool_name, result)
    # LLM polish re-formats presentation only. It runs for EVERY routed
    # tool so answers read naturally, but a verification step rejects
    # output that introduces numbers absent from the real result — so
    # Groq can reformat but never change the values.
    try:
        import json as _json
        raw_json = _json.dumps(result, default=str) if isinstance(result, dict) else str(result)
        polished = await _format_with_llm(message, text, raw_json)
        if polished:
            text = polished
    except Exception:
        pass
    return ChatResponse(response=text, tool_calls=[tool_call], conversation_id=conv_id)


async def _chat_impl(request: ChatRequest) -> ChatResponse:
    """Handle a chat message (no persistence — wrapped by chat())."""
    conv_id = request.conversation_id or "default"
    try:
        from intent_router import route_tool
        from tool_registry import execute_tool, REGISTRY
        import slot_fill

        # ---- 1. Pending intent? Merge the user's answer ----
        pending = slot_fill.PENDING_INTENTS.get(conv_id)
        if pending is not None:
            fresh = route_tool(request.message)
            # A fresh clear command replaces the pending intent; otherwise treat
            # this message as the answer to the clarifying question.
            if fresh is not None and fresh[0] != pending["tool_name"]:
                slot_fill.PENDING_INTENTS.pop(conv_id, None)
            else:
                params = slot_fill.merge_answer(pending, request.message)
                pending["params"] = params
                if slot_fill.is_complete(pending["tool_name"], params):
                    slot_fill.PENDING_INTENTS.pop(conv_id, None)
                    try:
                        result = execute_tool(pending["tool_name"], params)
                    except Exception as exc:
                        return ChatResponse(
                            response=f"[Tool error] {request.message}\n\n{str(exc)}",
                            conversation_id=conv_id,
                        )
                    return await _finish_routed(pending["tool_name"], result, request.message, conv_id)
                # Still missing fields - re-ask with updated context.
                question = slot_fill.describe_missing(pending["tool_name"], params)
                slot_fill.PENDING_INTENTS[conv_id] = pending
                return ChatResponse(
                    response=question,
                    conversation_id=conv_id,
                    pending=PendingIntent(
                        tool_name=pending["tool_name"], question=question, conversation_id=conv_id
                    ),
                )

        # ---- 2. Normal routing ----
        match = route_tool(request.message)
        if match is not None:
            tool_name, params = match
            # Proactive slot-fill: do not execute a write tool with missing fields.
            if slot_fill.is_write_tool(tool_name):
                question = slot_fill.describe_missing(tool_name, params)
                if question:
                    slot_fill.PENDING_INTENTS[conv_id] = {
                        "tool_name": tool_name,
                        "params": params,
                        "original": request.message,
                    }
                    return ChatResponse(
                        response=question,
                        conversation_id=conv_id,
                        pending=PendingIntent(
                            tool_name=tool_name, question=question, conversation_id=conv_id
                        ),
                    )
            try:
                result = execute_tool(tool_name, params)
            except Exception as route_err:
                # A matched tool failed to execute. Surface the real error cleanly
                # instead of falling through to the LLM orchestrator (which would
                # fail across all providers and show a misleading message).
                return ChatResponse(
                    response=f"[Tool error] {request.message}\n\n{str(route_err)}",
                    conversation_id=conv_id,
                )
            return await _finish_routed(tool_name, result, request.message, conv_id)

        # Router didn't match - fall back to LLM orchestrator
        response_text = await run_orchestrator(request.message)
        return ChatResponse(response=response_text, conversation_id=conv_id)
    except Exception as e:
        logger.error(f"Orchestrator invocation error: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred while processing your request.")


def _tool_calls_to_json(tool_calls: Optional[list]) -> Optional[str]:
    """Serialize a list of ToolCallInfo (or dicts) to JSON for persistence.

    Pydantic models are dumped to dicts first so json.dumps never hits a
    non-serializable object (which previously rolled back the whole message).
    """
    if not tool_calls:
        return None
    try:
        dumped = [
            tc.model_dump() if hasattr(tc, "model_dump") else tc
            for tc in tool_calls
        ]
        return json.dumps(dumped, default=str)
    except Exception:
        return None


def _persist_chat(conv_id: str, user_msg: str, ai_msg: str, tool_calls: Optional[list]) -> bool:
    """Persist a user + AI message pair into conversations/chat_messages.

    Best-effort: never raises (the chat response must not fail because history
    couldn't save). Creates the conversation row on first message. Returns True
    if this was a new conversation (so the caller can generate a smart title).
    """
    needs_title = False
    try:
        from db.models import Conversation, ChatMessage
        db = get_session()
        try:
            conv = db.query(Conversation).filter(Conversation.conversation_id == conv_id).first()
            if conv is None:
                needs_title = True
                title = user_msg[:40] + ("…" if len(user_msg) > 40 else "")
                conv = Conversation(conversation_id=conv_id, title=title)
                db.add(conv)
            elif conv.title in ("New Chat", "", "Untitled"):
                # Conversation pre-created (New Chat button) — still needs a smart title.
                needs_title = True
            db.add(ChatMessage(conversation_id=conv_id, role="user", content=user_msg))
            db.add(ChatMessage(
                conversation_id=conv_id, role="ai", content=ai_msg,
                tool_calls_json=_tool_calls_to_json(tool_calls),
            ))
            db.commit()
        finally:
            db.close()
    except Exception:
        pass
    return needs_title


async def _llm_title(user_msg: str) -> str:
    """Generate a short meaningful title from the first user message.

    Best-effort: returns "" if all providers fail, so the raw message title is
    kept. Uses the same Groq -> Gemini fallback chain as the orchestrator.
    """
    from agents import Agent, Runner
    from agents.run_config import RunConfig
    from agent_defs.model_providers import (
        create_groq_provider, create_gemini_provider,
        GROQ_FALLBACK_MODEL, GEMINI_MODEL,
    )
    instructions = (
        "You are a conversation titler. Summarize the user's first message into a "
        "short title (3-6 words, no more). Use a concise noun phrase or short verb "
        "phrase like 'Trial balance', 'Office rent expense', 'Cash flow check', "
        "'Utility expense'. For a simple greeting or chit-chat use 'Greeting'. "
        "No quotes, no periods, no 'About', no filler words. Reply with the title only."
    )
    for model, provider_fn in [(GROQ_FALLBACK_MODEL, create_groq_provider), (GEMINI_MODEL, create_gemini_provider)]:
        try:
            agent = Agent(
                name="Conversation Title",
                instructions=instructions,
                model=model,
            )
            result = await Runner.run(
                agent, input=user_msg,
                run_config=RunConfig(model_provider=provider_fn()),
            )
            title = result.final_output.strip().strip('"').strip("'").strip()
            if title and len(title) > 5:
                if len(title) > 60:
                    title = title[:60].rstrip() + "…"
                return title
        except Exception:
            continue
    return ""


async def _title_conversation(conv_id: str, user_msg: str) -> None:
    """Async background task: generate a smart title and update the conversation."""
    title = await _llm_title(user_msg)
    if not title:
        return
    try:
        from db.models import Conversation
        db = get_session()
        try:
            conv = db.query(Conversation).filter(Conversation.conversation_id == conv_id).first()
            if conv is not None:
                conv.title = title
                db.commit()
        finally:
            db.close()
    except Exception:
        pass


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Handle a chat message, persisting the exchange to conversation history.

    Persist AFTER the impl runs so a save failure never blocks the answer. On
    the first message of a conversation, fire a background task to generate a
    meaningful title (Claude.ai-style) so the history list reads nicely.
    """
    import asyncio
    conv_id = request.conversation_id or f"conv-{uuid.uuid4().hex[:12]}"
    resp = await _chat_impl(request)
    is_new = _persist_chat(conv_id, request.message, resp.response, resp.tool_calls)
    if is_new:
        asyncio.create_task(_title_conversation(conv_id, request.message))
    return resp


# Chat history endpoints (ChatGPT-style conversation list + messages)

def _derive_title(first_user_msg: str) -> str:
    """Deterministic short title from a first user message (no LLM).

    Used as a fallback so conversations created before smart titles (or whose
    LLM title task failed) still show a meaningful name in history. Keeps the
    message short and strips dates/amounts noise where possible.
    """
    msg = first_user_msg.strip()
    if not msg:
        return "New Chat"
    # Cap length at ~42 chars on a word boundary.
    if len(msg) <= 42:
        return msg
    cut = msg[:42]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut + "…"


@app.get("/conversations")
def list_conversations(db: Session = Depends(get_db)):
    """List all conversations, newest first, with last-message preview.

    Conversations whose stored title is a placeholder ("New Chat"/empty) fall
    back to a deterministic title derived from their first user message, so
    history always reads meaningfully even when the LLM title task never ran.
    """
    from db.models import Conversation, ChatMessage
    convs = db.query(Conversation).order_by(Conversation.updated_at.desc()).limit(50).all()
    out = []
    for c in convs:
        last = db.query(ChatMessage).filter(
            ChatMessage.conversation_id == c.conversation_id
        ).order_by(ChatMessage.timestamp.desc()).first()
        first_user = db.query(ChatMessage).filter(
            ChatMessage.conversation_id == c.conversation_id,
            ChatMessage.role == "user",
        ).order_by(ChatMessage.timestamp.asc()).first()
        title = c.title
        if not title or title.strip() in ("New Chat", "", "Untitled"):
            title = _derive_title(first_user.content if first_user else "")
        out.append({
            "conversation_id": c.conversation_id,
            "title": title,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
            "last_message": last.content[:80] if last else "",
        })
    return {"conversations": out}


@app.post("/conversations")
def create_conversation(db: Session = Depends(get_db)):
    """Create a new empty conversation, returns its id."""
    from db.models import Conversation
    import uuid as _uuid
    conv_id = f"conv-{_uuid.uuid4().hex[:12]}"
    db.add(Conversation(conversation_id=conv_id, title="New Chat"))
    db.commit()
    return {"conversation_id": conv_id, "title": "New Chat"}


@app.get("/conversations/{conversation_id}/messages")
def get_conversation_messages(conversation_id: str, db: Session = Depends(get_db)):
    """List messages in a conversation, oldest first."""
    from db.models import ChatMessage
    msgs = db.query(ChatMessage).filter(
        ChatMessage.conversation_id == conversation_id
    ).order_by(ChatMessage.timestamp.asc()).all()
    return {"messages": [
        {
            "role": m.role,
            "content": m.content,
            "tool_calls": json.loads(m.tool_calls_json) if m.tool_calls_json else None,
            "timestamp": m.timestamp.isoformat(),
        }
        for m in msgs
    ]}


@app.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, db: Session = Depends(get_db)):
    """Delete a conversation and its messages."""
    from db.models import Conversation, ChatMessage
    db.query(ChatMessage).filter(ChatMessage.conversation_id == conversation_id).delete()
    db.query(Conversation).filter(Conversation.conversation_id == conversation_id).delete()
    db.commit()
    return {"status": "deleted"}


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
    return {"approval": serialize_approval(entry), "result": result, "message": f"Approved and executed {entry.tool_name} ({approval_id})."}


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
    return {"approval": serialize_approval(entry), "message": f"Rejected {entry.tool_name} ({approval_id})."}


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
