---
id: 001
title: implement-audit-regulatory-agent
stage: green
date: 2026-07-29
surface: agent
model: oc/big-pickle
feature: audit-regulatory
branch: main
user: hassan khan
command: Implement Agent 8 Audit & Regulatory — 4 tools, schemas, DB models (flagged_entries, statutory_registers, compliance_deadlines), agent def, orchestrator registration, 29 unit tests, 4 real Groq E2E
labels: [tools, schemas, agent-def, tests, db-models, audit, regulatory, compliance, agent8]
links:
  spec: specs/agent-audit-regulatory.md
  ticket: null
  adr: null
  pr: null
files:
  - backend/tools/audit_tools.py
  - backend/tools/schemas.py
  - backend/db/models.py
  - backend/agent_defs/audit_agent.py
  - backend/agent_defs/orchestrator.py
  - backend/migrate_agent8.py
  - backend/tests/test_audit_tools.py
  - backend/tests/test_agent8_e2e_real.py
  - specs/agent-audit-regulatory.md
  - docs/ph8.md
  - full-workflow.md
tests:
  - backend/tests/test_audit_tools.py (29/29 passed)
  - backend/tests/test_agent8_e2e_real.py (4/4 passed)
---

## Prompt

Implement Agent 8 (Audit & Regulatory) completely based on specs/agent-audit-regulatory.md. This includes:
1. New DB models: FlaggedEntry, StatutoryRegister, ComplianceDeadline in backend/db/models.py
2. 8 schema classes (4 input + 4 output) in backend/tools/schemas.py
3. 4 tool functions in backend/tools/audit_tools.py:
   - detect_anomaly_transactions (no approval, 4 detectors: round_amount, weekend_posting, duplicate_amount, unusual_account)
   - get_compliance_deadlines (no approval, filterable deadline queries)
   - support_internal_audit (approval, 5 patterns: missing_reference, weekend_posting, round_amount, large_amount 3σ, infrequent_account)
   - maintain_statutory_registers (approval, CRUD: add/update/delete/view)
4. Agent definition in audit_agent.py with 4 tool wrappers
5. Orchestrator registration (8th agent-tool)
6. 29 unit tests + 4 real Groq E2E tests = 33 total
7. Approval tools gated by needs_approval=True

## Response snapshot

All 4 tools implemented, all 29 unit tests pass against PostgreSQL. Full E2E sequence (4/4) confirmed through real Groq API. detect_anomaly_transactions runs 4 parallel detectors with dedup. support_internal_audit uses 3σ threshold for large entries and persistence to flagged_entries table. maintain_statutory_registers supports full CRUD with validation, duplicate reference detection, and approval gating for writes. 3 new DB tables added: flagged_entries, statutory_registers, compliance_deadlines.

## Outcome

- Impact: Agent 8 fully implemented — 4 tools covering anomaly detection, internal audit, statutory registers, compliance deadlines
- Tests: 29 unit + 4 real Groq E2E = 33 total
- Files: 11 files created/modified
- Next prompts: Agent 9 (Advisory — 5 tools pending)

## Evaluation notes

- Failure modes observed: Transient Groq failure on Tool 3 (Internal Audit), retry wrapper recovered it
- Graders run: 29/29 unit PASS, 4/4 Groq E2E PASS
- Prompt variant: Built in spec order (non-approval first, approval last)
- Next experiment: Add negative test cases for all approval gating tests
