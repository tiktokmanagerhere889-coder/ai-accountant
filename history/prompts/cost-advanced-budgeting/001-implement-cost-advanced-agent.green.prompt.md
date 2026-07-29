---
id: 001
title: implement-cost-advanced-budgeting-agent
stage: green
date: 2026-07-29
surface: agent
model: oc/big-pickle
feature: cost-advanced-budgeting
branch: main
user: hassan khan
command: Implement Agent 6 Cost, Advanced Accounting & Budgeting — 8 tools, schemas, DB models, agent def, orchestrator registration, tests, E2E verification
labels: [tools, schemas, agent-def, tests, db-models, cost-advanced-budgeting, agent6]
links:
  spec: specs/agent-cost-advanced-budgeting.md
  ticket: null
  adr: null
  pr: null
files:
  - backend/tools/cost_advanced_tools.py
  - backend/tools/schemas.py
  - backend/db/models.py
  - backend/agent_defs/cost_advanced_agent.py
  - backend/agent_defs/orchestrator.py
  - backend/agent_defs/run_utils.py
  - backend/tests/test_cost_advanced_tools.py
  - backend/tests/test_agent6_e2e_real.py
  - backend/migrate_agent6.py
  - specs/agent-cost-advanced-budgeting.md
  - docs/ph6.md
tests:
  - backend/tests/test_cost_advanced_tools.py (32/32 passed)
  - backend/tests/test_agent6_e2e_real.py (8/8 passed)
---

## Prompt

Implement Agent 6 (Cost, Advanced Accounting & Budgeting) completely based on specs/agent-cost-advanced-budgeting.md. This includes:
1. New DB model: ExchangeRate, new field contacts.related_party, new column journal_entries.contact_id (FK)
2. 16 new Pydantic schema classes in backend/tools/schemas.py
3. 8 tool functions in backend/tools/cost_advanced_tools.py:
   - calculate_breakeven, convert_foreign_currency, prepare_budget_forecast,
     calculate_standard_costing_variance, allocate_overhead_cost,
     calculate_revenue_recognition, flag_provision_contingent_liability,
     flag_related_party_transaction
4. Agent definition in cost_advanced_agent.py with 8 tool wrappers
5. Orchestrator registration (6th agent-tool)
6. 32 unit tests + 8 real Groq E2E tests
7. Centralized retry wrapper in run_utils.py (applied to all 6 agents)
8. verification of needs_approval flags (5 approval, 3 non-approval)
9. Revenue Recognition 3x consecutive real API test (confirmed transient Groq issue, not schema bug)
10. docs/ph6.md completion report

## Response snapshot

All 8 tools implemented, all 32 unit tests pass against PostgreSQL. Full E2E sequence (8/8) confirmed through real Groq orchestrator. Hybrid contact_id + reference fallback matching for related party transactions. Approval flow verified: all 5 approval tools correctly gate. Centralized retry wrapper ensures resilience against transient Groq outages. DB migration executed (contacts.related_party, journal_entries.contact_id, exchange_rates table).

## Outcome

- ✅ Impact: Agent 6 fully implemented — 8 tools covering cost/management accounting, advanced accounting, and budgeting
- 🧪 Tests: 32 unit + 8 real Groq E2E = 40 total
- 📁 Files: 11 files created/modified
- 🔁 Next prompts: Agent 7 (Tax Agent)
- 🧠 Reflection: The hybrid contact matching approach (contact_id FK + reference fallback) future-proofs related party detection while maintaining backward compatibility with existing data. The centralized retry wrapper is essential for real-world Groq free-tier reliability. Revenue Recognition empty output was a transient Groq API issue, not a code bug — 3x retry test confirmed.

## Evaluation notes (flywheel)

- Failure modes observed: Revenue Recognition returned empty via orchestrator twice due to Groq transient outage; Related Party tool returned "specialist unavailable" once due to rate limit — both recovered with centralized retry
- Graders run and results (PASS/FAIL): 32/32 unit PASS, 8/8 Groq E2E PASS, approval verification PASS
- Prompt variant (if applicable): All 8 tools built together rather than sequentially (consistent with Agent 5 pattern)
- Next experiment (smallest change to try): Add negative test cases for all 5 approval tools (testing rejection flows)
