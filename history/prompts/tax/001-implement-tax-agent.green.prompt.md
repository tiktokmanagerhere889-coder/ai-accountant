---
id: 001
title: implement-tax-agent
stage: green
date: 2026-07-29
surface: agent
model: oc/big-pickle
feature: tax
branch: main
user: hassan khan
command: Implement Agent 7 Tax — 8 tools, schemas, DB models (tax_rates, eobi_rates), agent def, orchestrator registration, tests, E2E verification
labels: [tools, schemas, agent-def, tests, db-models, tax, agent7]
links:
  spec: specs/agent-tax.md
  ticket: null
  adr: null
  pr: null
files:
  - backend/tools/tax_tools.py
  - backend/tools/schemas.py
  - backend/db/models.py
  - backend/agent_defs/tax_agent.py
  - backend/agent_defs/orchestrator.py
  - backend/tests/test_tax_tools.py
  - backend/tests/test_agent7_e2e_real.py
  - specs/agent-tax.md
  - docs/ph7.md
tests:
  - backend/tests/test_tax_tools.py (25/25 passed)
  - backend/tests/test_agent7_e2e_real.py (8/8 passed)
---

## Prompt

Implement Agent 7 (Tax) completely based on specs/agent-tax.md. This includes:
1. New DB models: TaxRate, EobiRate in backend/db/models.py
2. 8 tool schema groups (16 classes) in backend/tools/schemas.py
3. 8 tool functions in backend/tools/tax_tools.py:
   - calculate_withholding_tax, get_tax_planning_advice, calculate_advance_minimum_tax,
     calculate_eobi_deductions, adjust_sales_tax_input_output,
     flag_tax_exemption_zero_rating, prepare_sales_tax_filing, prepare_income_tax_filing
4. Agent definition in tax_agent.py with 8 tool wrappers
5. Orchestrator registration (7th agent-tool)
6. 25 unit tests + 8 real Groq E2E tests = 33 total
7. Filing tools gated by confirm=True (sales tax + income tax)

## Response snapshot

All 8 tools implemented, all 25 unit tests pass against PostgreSQL. Full E2E sequence (8/8) confirmed through real Groq API. Tax rate tables (wht_service, wht_supply, wht_contract, wht_rent, amt_company) with effective-date-based lookup. EOBI with ceiling cap (50000 max insurable). Sales tax at 18% standard rate with override support. Zero-rating/exemption scanning with confidence levels. Both filing tools require confirm=True and never auto-submit.

## Outcome

- Impact: Agent 7 fully implemented — 8 tools covering all tax calculation and filing-preparation
- Tests: 25 unit + 8 real Groq E2E = 33 total
- Files: 9 files created/modified
- Next prompts: Agent 8 (Audit & Regulatory)

## Evaluation notes

- Failure modes observed: Transient Groq failures on Tools 4-6, retry wrapper recovered all
- Graders run: 25/25 unit PASS, 8/8 Groq E2E PASS
- Prompt variant: Built in spec order (non-approval first, approval last)
- Next experiment: Add negative test cases for all 4 filing gating tests
