# Agent Build Process — Complete Workflow (Agents 1-8)

Yeh document batata hai ke har naya agent kaise build karte hain — start se end tak, jo pattern Agents 1-7 mein follow kiya aur Agent 8 ke liye bhi wohi process rahega.

## 1. SPEC (Source of Truth)

**File:** `specs/agent-<name>.md`

- **Format:** Agent 5/6 jaisa — har tool ke liye: Input, Output, DB tables, Edge cases, Logic, Example
- **Account prefix consistency:** Agent 2 ke numbering scheme se verify (1=Assets, 2=Liabilities, 3=Equity, 4=Revenue, 5/6/8=Expenses)
- **New DB tables:** clearly mark karo — `**New DB table needed:** table_name`
- **Approval tools:** tool heading mein "(Approval: Yes)" ya "(Approval: No)"
- **Routing keywords:** agent-level routing list, orchestrator instructions ke liye
- **Tools order:** non-approval tools pehle, approval tools baad mein

## 2. DB MODELS

**File:** `backend/db/models.py`

- Har naye table ke liye `class TableName(Base):` append at end
- SQLAlchemy columns: Integer PK, String for IDs/indexes, Numeric for money, Date/Boolean/Text as needed
- `__tablename__`, `nullable`, `index`, `ForeignKey` properly set
- Migration: `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for existing tables. `table.create(bind=engine, checkfirst=True)` for new tables.

## 3. SCHEMAS

**File:** `backend/tools/schemas.py`

- Har tool ko 2 classes: `*Input(BaseModel)` + `*Output(BaseModel)`
- Fields: Decimal with `gt=0`/`ge=0` validation, Optional[X] for nullable, date for dates, str with min/max_length
- `needs_approval: bool = True` ONLY for approval tools
- Grouping comment: `# --- Agent N: Agent Name ---` before tool group

## 4. TOOL FUNCTIONS

**File:** `backend/tools/<agent>_tools.py`

- Pattern: `def tool_name(inp: InputModel, db: Session) -> OutputModel:`
- Pydantic input/output — kabhi raw dict nahi
- DB queries via SQLAlchemy: `session.query(...)`, `func.sum()`, `func.extract()`
- Helper: `_round(value, places=2)` — Decimal quantize
- Error handling: `raise ValueError(...)` for expected failures. Tool wrapper catches and returns `f"Error: {e}"`
- Pure calculation tools: no DB session needed (parameter accepted but unused)
- Filing tools: `confirm=False → raise ValueError("...requires confirm=True")`

## 5. AGENT DEFINITION

**File:** `backend/agent_defs/<agent>_agent.py`

- 8 tool wrappers with `@function_tool` decorator
- Har wrapper: parses string params → creates InputModel → calls tool function → `_to_json(result)`
- `_get_session()` → `init_db()` + `get_session()`
- `_to_json(obj)` → `json.dumps(json.loads(obj.model_dump_json()), indent=2, default=str)`
- Agent instructions: lists all 8 tools, marks approval tools, "ALWAYS call a tool"
- `run_<agent>_agent(user_request)` → Groq primary → Groq fallback → Cerebras last resort

## 6. ORCHESTRATOR REGISTRATION

**File:** `backend/agent_defs/orchestrator.py`

- Import: `from agent_defs.<agent_name>_agent import run_<agent_name>_agent`
- New function_tool: `async def agent_<name>(user_request: str) -> str: return await run_with_retry(run_<name>_agent, user_request)`
- Instructions: add routing line to ORCHESTRATOR_INSTRUCTIONS
- Tools list: append `agent_<name>` to ORCHESTRATOR_AGENT tools array
- Header comment update: add to "Currently registered" list

## 7. UNIT TESTS

**File:** `backend/tests/test_<agent>_tools.py`

- Har test class: `setup_method` (fresh schema) + `teardown_method` (close)
- Data seed helpers at module level: `_seed_rates()`, `_seed_journal_entries()`, etc.
- Har tool ke liye 2-5 test methods:
  - Normal case (exact values)
  - Edge case (empty, zero, boundary)
  - Error case (raises ValueError)
- Full E2E class: `TestE2E<Agent>Sequence` — calls all tools in order

## 8. REAL GROQ E2E

**File:** `backend/tests/test_agent<N>_e2e_real.py`

- Seeds production DB with test data (s.query all models → delete → add fresh)
- Har tool ke liye 1 orchestrator query
- `run_orchestrator(query)` → receives Groq response
- Reports: sequence number, tool name, latency, response preview, pass/fail
- 3s throttle between queries

## 9. DB MIGRATION

**File:** `backend/migrate_agent<N>.py`

- `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for existing table changes
- `TableName.__table__.create(bind=engine, checkfirst=True)` for new tables

## 10. DOCS & PHR

| File | Purpose |
|------|---------|
| `docs/ph<N>.md` | Completion report — tool table, test results, files, total system status |
| `history/prompts/<agent-name>/001-implement-<agent-name>-agent.green.prompt.md` | PHR record — id, title, prompt, response, outcome, evaluation |

PHR template: YAML frontmatter (id, title, stage, date, model, feature, files, tests) + body (Prompt with full requirements, Response snapshot, Outcome with impact/tests/reflection, Evaluation notes).

## 11. COMMIT

```bash
git add <all new/modified files>
git commit -m "feat: implement Agent N - Agent Name

N tools: tool1, tool2, ... (X approval, Y direct).

Infrastructure:
- list key DB changes
- schema count
- test count
- docs + PHR

Co-Authored-By: Claude <noreply@anthropic.com>"
```

## Per-Agent Summary (1-8)

| Agent | Tools | Approval | New Tables | Unit Tests | E2E Tests |
|-------|-------|----------|------------|-----------|-----------|
| 1. Daily Entry | 4 | 0 | — | 35+ | ✓ |
| 2. Ledger & Master Data | 8 | 2 | — | 46 | ✓ |
| 3. Reconciliation & Banking | 7 | 5 | 5 tables | 49 | ✓ |
| 4. Month-End Reporting | 10 | 1 | 5 tables | 44+ | ✓ |
| 5. Year-End Close & Financials | 8 | 1 | 2 tables | 16+ | ✓ |
| 6. Cost, Advanced Accounting | 8 | 5 | 1 table, 2 fields | 32 | ✓ |
| 7. Tax | 8 | 4 | 2 tables | 25 | ✓ |
| 8. Audit & Regulatory | 4 | 2 | 3 tables | 29 | ✓ |
| 9. Advisory | 5 | 1 | — | 25 | ✓ |
| 10. System Admin | 4 | 2 | 2 tables | 23 | ✓ |
