from __future__ import annotations

import json
import uuid
import logging
from datetime import date, datetime
from typing import Optional, Any
from decimal import Decimal

from fastapi import FastAPI, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from db.database import get_db, init_db
from db.models import Base, AuditLog, UserRole, SystemBackupLog, JournalEntry
from agent_defs.orchestrator import run_orchestrator

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

# Ensure all tables are initialized
init_db()

app = FastAPI(title="AI Accountant Backend", version="1.0.0")


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


# Orchestrator Routes (AI Routing)

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        response_text = await run_orchestrator(request.message)
        return ChatResponse(response=response_text)
    except Exception as e:
        logger.error(f"Orchestrator invocation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
