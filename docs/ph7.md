# AI Accountant — Phase 7: Tax Agent Completion Report

## Overview

Phase 7 implements the Tax Agent (Agent 7) following Spec-Driven Development (SDD). The agent handles all tax calculation and filing-preparation tasks — withholding tax, tax planning advice, advance minimum tax, EOBI deductions, sales tax adjustment, exemption flagging, sales tax filing, and income tax filing — across 8 tools, 4 requiring human approval.

All tools use PostgreSQL persistence, Pydantic v2 validation, and real Groq API integration via the OpenAI Agents SDK.

## Agent 7: Tax Agent (8 tools)

**Spec:** `specs/agent-tax.md`
**Tools:** `backend/tools/tax_tools.py`
**Agent def:** `backend/agent_defs/tax_agent.py`
**Schemas:** `backend/tools/schemas.py` (lines 1358+)
**Tests:** `backend/tests/test_tax_tools.py`

| # | Tool | Approval | Logic | DB Tables |
|---|------|----------|-------|-----------|
| 1 | `calculate_withholding_tax` | No | tax_amount = gross × (rate/100). Rate from `tax_rates` by type + date, fallback to defaults (service 8%, salary 5%, etc.) | `tax_rates` |
| 2 | `get_tax_planning_advice` | No | Analyzes revenue (prefix 4) / expenses (prefix 5/6/8). Generates advice with estimated tax liability, loss carry-forward, or general guidance | `journal_entries` |
| 3 | `calculate_advance_minimum_tax` | No | AMT = turnover × (rate/100). Company 1.5%, individual 1.0%, AOP 1.25%. Rate from `tax_rates` table | `tax_rates` |
| 4 | `calculate_eobi_deductions` | No | Employer = insurable_salary × rate%. Employee = insurable_salary × employee_rate%. Capped at max_insurable_amount | `eobi_rates` |
| 5 | `adjust_sales_tax_input_output` | **Yes** | output_tax = revenue×18%, input_tax = purchases×18%. Supports override amounts. Refund if input > output | `journal_entries` |
| 6 | `flag_tax_exemption_zero_rating` | **Yes** | Checks revenue entries against exemption criteria: exports (contact check), salary, low-value. Reports confidence | `journal_entries`, `contacts` |
| 7 | `prepare_sales_tax_filing` | **Yes** | FBR-compatible data: output tax, input tax, net payable. Requires confirm=True. Never auto-submits | `journal_entries` |
| 8 | `prepare_income_tax_filing` | **Yes** | FBR-compatible data: income, expenses, taxable income, liability. Requires confirm=True. Never auto-submits | `journal_entries` |

## DB Changes

| Change | Type | Purpose |
|--------|------|---------|
| `tax_rates` | **New table** | Tax rates by type (wht_*, amt_*) with effective dates |
| `eobi_rates` | **New table** | EOBI deduction rates with max_insurable_amount |

## Test Suite

| Suite | Tests | Type |
|-------|-------|------|
| WHT | 3 | PostgreSQL |
| Tax Planning | 2 | PostgreSQL |
| AMT | 3 | PostgreSQL |
| EOBI | 3 | PostgreSQL |
| Sales Tax Adj | 3 | PostgreSQL |
| Exemption Flag | 3 | PostgreSQL |
| Sales Tax Filing | 3 | PostgreSQL |
| Income Tax Filing | 4 | PostgreSQL |
| Full E2E sequence | 1 | PostgreSQL |
| **Unit total** | **25** | |
| Real Groq E2E (orchestrator) | **8** | Groq API |
| **Grand total** | **33** | |

## Total System Status

| Agent | Tools | Approval | Tests | Status |
|-------|-------|----------|-------|--------|
| Agent 1: Daily Entry | 4 | 0 | 35+ | ✅ |
| Agent 2: Ledger & Master Data | 8 | 2 | 46 | ✅ |
| Agent 3: Reconciliation & Banking | 7 | 5 | 49 | ✅ |
| Agent 4: Month-End Reporting | 10 | 1 | 44+ | ✅ |
| Agent 5: Year-End Close & Financials | 8 | 1 | 16+ | ✅ |
| Agent 6: Cost, Advanced Accounting | 8 | 5 | 40 | ✅ |
| Agent 7: Tax | **8** | **4** | **25+8** | ✅ |
| **Total** | **53** | **18** | **250+** | |
