# AI Accountant — Agents & Tools Reference

**Workflow Diagram:** [View on Lucidchart](https://lucid.app/lucidchart/4fb7df8e-7bbd-4659-994b-14ab77174db9/edit?viewport_loc=-580%2C-136%2C2647%2C1309%2C0_0&invitationId=inv_4f89d381-8178-43e6-bf25-cc70b22a0aeb)

**Research Paper:** [AI_Accountant_Research_Paper.pdf](./AI_Accountant_Research_Paper.pdf)

---

## Architecture Pattern

**Orchestrator + Agents as Tools** (OpenAI Agents SDK)

```
User Request
     │
     ▼
┌─────────────────────┐
│   Orchestrator      │  ← Routes every /chat request
│   (1 agent)         │  ← Never talks to user directly
└─────────────────────┘
     │
     ├── agent_daily_entry        → Daily Entry Agent
     ├── agent_ledger             → Ledger & Master Data Agent
     ├── agent_reconciliation     → Reconciliation & Banking Agent
     ├── agent_month_end          → Month-End Reporting Agent
     ├── agent_year_end           → Year-End Close Agent
     ├── agent_cost_advanced      → Cost & Budgeting Agent
     ├── agent_tax                → Tax Agent
     ├── agent_audit              → Audit & Regulatory Agent
     ├── agent_advisory           → Advisory Agent
     └── agent_system_admin       → System Admin Agent
```

Each specialist agent is called as a **tool** by the Orchestrator. Specialist agents never communicate with the user directly — all output flows back through the Orchestrator which explains results in plain English.

**Total: 1 Orchestrator + 10 Specialist Agents + 71 Tools + 3 Direct-Backend Endpoints**

---

## 0. Orchestrator Agent

**File:** `backend/agent_defs/orchestrator.py`
**Role:** Receives every `/chat` request, determines which specialist agent to call based on user intent, calls it as a tool, and returns the combined result in plain English.

**Routing keywords:**
- `agent_daily_entry` — cash, balance, record expense, bank statement, petty cash
- `agent_ledger` — journal entries, ledger, chart of accounts, AP/AR, payroll, fixed assets, contacts
- `agent_reconciliation` — bank reconciliation, accrual, vendor/customer statement, cheque, LC/BG, bank charges
- `agent_month_end` — unpaid bills, prepaid, depreciation, amortization, payroll recon, aging reports, budget variance, loan schedule, cash flow forecast
- `agent_year_end` — trial balance, P&L, balance sheet, cash flow statement, retained earnings, carry forward, notes, close fiscal year
- `agent_cost_advanced` — breakeven, currency conversion, budget forecast, cost variance, overhead allocation, revenue recognition, provisions, related party
- `agent_tax` — withholding tax, WHT, tax planning, minimum tax, EOBI, sales tax, exemption flagging, income tax filing
- `agent_audit` — anomaly detection, fraud, suspicious transaction, internal audit, compliance deadline, filing deadline, statutory register
- `agent_advisory` — spending analysis, financial advice, financial health, cost cutting, financial ratios, custom report
- `agent_system_admin` — system status, health check, usage stats, system preferences, schedule backup, maintenance

---

## 1. Daily Entry Agent

**File:** `backend/agent_defs/daily_entry_agent.py`
**Tools file:** `backend/tools/cash_tools.py`, `backend/tools/transaction_tools.py`, `backend/tools/bank_tools.py`, `backend/tools/petty_cash_tools.py`, `backend/tools/receipt_tools.py`
**Role:** First point of contact for recording money movement — daily cash, transactions, receipts, petty cash.

| # | Tool | Approval | What it does |
|---|------|----------|--------------|
| 1 | `check_cash_position` | No | Live cash balance pulled from journal entries in DB, shown in plain language |
| 2 | `record_transaction_nl` | No | Parses a plain-English transaction description and stores it as a journal entry with correct debit/credit |
| 3 | `process_receipt_image` | **Yes** | Reads amount and vendor from an uploaded receipt photo; extracted details must be verified and approved before posting |
| 4 | `check_bank_transactions` | No | Queries stored bank transaction data for a date range |
| 5 | `manage_petty_cash` | No | Records small cash entries and sends replenishment reminders when balance is low |

**DB Tables:** `journal_entries`, `bank_transactions`, `petty_cash_entries`

---

## 2. Ledger & Master Data Agent

**File:** `backend/agent_defs/ledger_agent.py`
**Tools file:** `backend/tools/ledger_tools.py`, `backend/tools/asset_tools.py`, `backend/tools/contact_tools.py`
**Role:** Owns the chart of accounts, journal entries, all ledgers, and vendor/customer master records.

| # | Tool | Approval | What it does |
|---|------|----------|--------------|
| 1 | `create_journal_entry` | No | Converts a plain-language transaction into the correct debit/credit journal entry using fixed accounting rules |
| 2 | `get_general_ledger` | No | Aggregated ledger view grouped by account, filterable by date range and account prefix |
| 3 | `suggest_chart_of_accounts` | **Yes** | Suggests a starting chart of accounts structure for a given business type; owner adjusts and approves before saving |
| 4 | `get_ap_subledger` | No | Accounts payable sub-ledger — what the business owes vendors |
| 5 | `get_ar_subledger` | No | Accounts receivable sub-ledger — what customers owe the business |
| 6 | `get_payroll_ledger` | No | Payroll records for a period — salary minus deductions |
| 7 | `categorize_fixed_asset` | **Yes** | Categorizes a newly purchased asset and suggests depreciation method; requires approval before recording |
| 8 | `manage_contact` | No | Add, update, delete, or search vendor and customer contacts (shared tool) |

**DB Tables:** `journal_entries`, `chart_of_accounts`, `fixed_assets`, `contacts`

---

## 3. Reconciliation & Banking Agent

**File:** `backend/agent_defs/reconciliation_agent.py`
**Tools file:** `backend/tools/reconciliation_tools.py`
**Role:** Matches internal records against external statements (bank, vendor, customer) and tracks banking instruments. Heaviest concentration of approval gates.

| # | Tool | Approval | What it does |
|---|------|----------|--------------|
| 1 | `run_bank_reconciliation` | **Yes** | Matches bank statement lines to internal journal entries; uncertain matches go to a review queue |
| 2 | `post_accrual_entry` | **Yes** | Suggests an accrual entry based on past patterns; posts only after accountant approval |
| 3 | `reconcile_vendor_statement` | **Yes** | Compares a vendor's statement against internal AP records and flags differences |
| 4 | `reconcile_customer_statement` | **Yes** | Compares customer statement against internal AR records; receivable side |
| 5 | `track_cheque_clearing` | No | Tracks cheque issuance and clearing status through natural-language updates |
| 6 | `track_lc_bank_guarantee` | **Yes** | Tracks letter of credit and bank guarantee status; issuing the instrument is a bank/legal process |
| 7 | `reconcile_bank_charges` | No | Matches bank fee lines against the ledger |

**DB Tables:** `bank_transactions`, `journal_entries`, `reconciliation_items`, `bank_instruments`

---

## 4. Month-End Reporting Agent

**File:** `backend/agent_defs/month_end_reporting_agent.py`
**Tools file:** `backend/tools/month_end_tools.py`
**Role:** Period-end calculations — deterministic backend logic with the AI presenting and explaining results.

| # | Tool | Approval | What it does |
|---|------|----------|--------------|
| 1 | `review_unpaid_bills` | No | Returns a clear list of unpaid bills from AP records |
| 2 | `calculate_prepaid_adjustment` | No | Divides an advance payment across months — straightforward formula |
| 3 | `calculate_depreciation` | No | Fixed-formula depreciation (straight-line and reducing balance) |
| 4 | `calculate_amortization` | No | Fixed-formula amortization for intangible assets |
| 5 | `reconcile_payroll` | No | Matches payroll records against the general ledger |
| 6 | `get_ar_aging_report` | No | Accounts receivable grouped by overdue days (0-30, 31-60, 61-90, 90+) |
| 7 | `get_ap_aging_report` | No | Accounts payable aging — same grouping, vendor side |
| 8 | `analyze_budget_variance` | No | Compares budget vs actual figures and explains the gap in plain language |
| 9 | `get_loan_debt_schedule` | No | Amortization schedule split into principal and interest components |
| 10 | `forecast_cash_flow` | **Yes** | Projects near-term cash needs from historical data; owner treats as a guide, not a guarantee |

**DB Tables:** `journal_entries`, `fixed_assets`, `budgets`, `payroll_records`

---

## 5. Year-End Close & Financial Statements Agent

**File:** `backend/agent_defs/year_end_agent.py`
**Tools file:** `backend/tools/year_end_tools.py`
**Role:** Generates the four core financial statements and handles all year-end close operations.

| # | Tool | Approval | What it does |
|---|------|----------|--------------|
| 1 | `generate_trial_balance` | No | Aggregates all accounts — debits must equal credits; agent flags any mismatch |
| 2 | `generate_profit_loss` | No | Revenue minus expenses for a period; agent explains result in plain language |
| 3 | `generate_balance_sheet` | No | Assets must equal liabilities plus equity; agent checks and flags mismatches |
| 4 | `generate_cash_flow_statement` | No | Operating + investing + financing activity, explained by the agent |
| 5 | `close_fiscal_year` | **Yes** | **Irreversible.** Closes books for the fiscal year — requires explicit user confirmation |
| 6 | `transfer_retained_earnings` | No | Transfers net profit/loss to retained earnings — one-line formula |
| 7 | `carry_forward_balances` | No | Carries opening/closing balances to next period — system logic |
| 8 | `draft_notes_to_financials` | No | Drafts explanatory notes to financial statements from data; accountant reviews wording |

**DB Tables:** `journal_entries`, `retained_earnings`, `fiscal_years`

---

## 6. Cost, Advanced Accounting & Budgeting Agent

**File:** `backend/agent_defs/cost_advanced_agent.py`
**Tools file:** `backend/tools/cost_advanced_tools.py`
**Role:** Cost/management accounting, advanced accounting judgment calls, and forward-looking budget planning.

| # | Tool | Approval | What it does |
|---|------|----------|--------------|
| 1 | `calculate_breakeven` | No | CVP analysis — contribution margin, breakeven units and revenue (pure formula, no DB) |
| 2 | `convert_foreign_currency` | No | Currency conversion using live rates from `exchange_rates` table |
| 3 | `prepare_budget_forecast` | No | Budget forecast from historical average spend plus budget baseline |
| 4 | `calculate_standard_costing_variance` | **Yes** | Standard vs actual cost gap and quantity variance; owner supplies standard cost |
| 5 | `allocate_overhead_cost` | **Yes** | Overhead apportionment on owner-defined basis (e.g. per square foot) |
| 6 | `calculate_revenue_recognition` | **Yes** | Percentage-of-completion revenue recognition; owner provides completion percentage |
| 7 | `flag_provision_contingent_liability` | **Yes** | IAS 37 provision/contingency assessment — agent flags, accountant decides |
| 8 | `flag_related_party_transaction` | **Yes** | Flags transactions connected to insiders; accountant decides on disclosure |

**DB Tables:** `journal_entries`, `budgets`, `exchange_rates`, `contacts`

---

## 7. Tax Agent

**File:** `backend/agent_defs/tax_agent.py`
**Tools file:** `backend/tools/tax_tools.py`
**Role:** All tax calculation and filing-preparation tasks. Filing submission itself stays with a human — FBR portal requires personal credentials.

| # | Tool | Approval | What it does |
|---|------|----------|--------------|
| 1 | `calculate_withholding_tax` | No | WHT on payments — rate from `tax_rates` table or default rate |
| 2 | `get_tax_planning_advice` | No | Conversational tax guidance generated from stored financial data |
| 3 | `calculate_advance_minimum_tax` | No | AMT on turnover — rate from `tax_rates` by business type |
| 4 | `calculate_eobi_deductions` | No | EOBI employer and employee deductions — fixed percentages, ceiling capped |
| 5 | `adjust_sales_tax_input_output` | **Yes** | Sales tax input/output adjustment with override support |
| 6 | `flag_tax_exemption_zero_rating` | **Yes** | Flags zero-rated or exempt revenue entries for review |
| 7 | `prepare_sales_tax_filing` | **Yes** | Prepares FBR sales tax filing data; human submits via portal |
| 8 | `prepare_income_tax_filing` | **Yes** | Prepares FBR income tax filing data; human submits via portal |
| 9 | `list_tax_filings` | No | Lists all persisted tax filings with status and save dates |

**DB Tables:** `journal_entries`, `tax_rates`, `eobi_rates`, `tax_filings`

---

## 8. Audit & Regulatory Agent

**File:** `backend/agent_defs/audit_agent.py`
**Tools file:** `backend/tools/audit_tools.py`
**Role:** Anomaly detection, internal audit support, FBR audit risk scoring, statutory records, and compliance deadline tracking.

| # | Tool | Approval | What it does |
|---|------|----------|--------------|
| 1 | `detect_anomaly_transactions` | No | Pattern-based fraud and anomaly flagging — 4 detectors: duplicate amounts, round-number clustering, weekend/holiday postings, vendor concentration |
| 2 | `get_compliance_deadlines` | No | Tracks FBR, SECP, EOBI, and PESSI filing deadlines; reminds owner ahead of due dates |
| 3 | `support_internal_audit` | **Yes** | Flags unusual journal entries for accountant review — 5 patterns: large reversals, dormant accounts, missing references, late postings, imbalanced entries |
| 4 | `maintain_statutory_registers` | **Yes** | Keeps statutory register data current; legal accuracy checked by a person before confirming |
| 5 | `resolve_flagged_entry` | **Yes** | Confirms or waives an audit flag after human review — records who resolved it and why |
| 6 | `assess_fbr_audit_risk` | No | Scores FBR audit-selection risk from historically-disclosed parameters (TY2011/TY2017); FA 2025 immunity; read-only |

**DB Tables:** `journal_entries`, `flagged_entries`, `compliance_deadlines`, `statutory_registers`

---

## 9. Advisory Agent

**File:** `backend/agent_defs/advisory_agent.py`
**Tools file:** `backend/tools/advisory_tools.py`
**Role:** Open-ended financial insight and Q&A over the business's own data.

| # | Tool | Approval | What it does |
|---|------|----------|--------------|
| 1 | `analyze_spending_patterns` | No | Expense patterns grouped by category and month; keyword filter; concentration insights |
| 2 | `calculate_financial_ratios` | No | 4 categories: liquidity (current/quick), profitability (NPM/GP/ROA/ROE), leverage (D/E, debt ratio), efficiency (asset turnover, expense ratio) — plain-language interpretation |
| 3 | `assess_financial_health` | No | Weighted score 0–100: profitability 30%, liquidity 25%, leverage 20%, efficiency 15%, budget 10% — with strengths, weaknesses, and recommendations |
| 4 | `generate_cost_cutting_recommendations` | No | Top expense categories by spend, trend direction, savings estimates (10–20% discretionary), ranked by impact |
| 5 | `generate_custom_report` | **Yes** | 4 report types: summary, detailed, comparative, trend — section-based structured output |

**DB Tables:** `journal_entries`, `retained_earnings`, `budgets`, `chart_of_accounts`

---

## 10. System Admin Agent (Bonus Agent)

**File:** `backend/agent_defs/system_admin_agent.py`
**Tools file:** `backend/tools/system_admin_tools.py`
**Role:** System health monitoring, usage analytics, configuration management, and maintenance scheduling. Added as a bonus agent beyond the core 9.

| # | Tool | Approval | What it does |
|---|------|----------|--------------|
| 1 | `check_system_status` | No | DB health check, provider config verification, agent module import check — returns overall: healthy / degraded / unhealthy |
| 2 | `get_usage_statistics` | No | Backup log analysis with success/failure rates and recommendations |
| 3 | `manage_system_preferences` | **Yes** | CRUD for key-value config — view, update, reset. Auto-seeds defaults on first run |
| 4 | `schedule_system_task` | **Yes** | Schedule backup, export, maintenance, or cleanup tasks with status tracking |

**DB Tables:** `system_backup_log`, `system_config`

---

## Direct-Backend Features (No AI)

These go straight from API to the database. No agent, no tool, no LLM call.

| Feature | API Endpoints | Why No AI |
|---------|--------------|-----------|
| Audit Trail & Change Log | `POST /audit-trail`, `GET /audit-trail` | Timestamp + user-id logging — a DB design choice, not a reasoning task |
| User Roles & Permissions | `POST /roles`, `GET /roles`, `PUT /roles/{id}` | Standard access control — no language understanding needed |
| Data Backup & Scheduling | `POST /backup/trigger`, `GET /backup/history` | A scheduled operation — no language understanding needed |

---

## Approval-Required Tools — Full List (24 of 70)

Tools that pause and wait for explicit human confirmation before writing to the database:

| # | Tool | Agent |
|---|------|-------|
| 1 | `process_receipt_image` | Daily Entry |
| 2 | `categorize_fixed_asset` | Ledger & Master Data |
| 3 | `run_bank_reconciliation` | Reconciliation & Banking |
| 4 | `post_accrual_entry` | Reconciliation & Banking |
| 5 | `reconcile_vendor_statement` | Reconciliation & Banking |
| 6 | `reconcile_customer_statement` | Reconciliation & Banking |
| 7 | `track_lc_bank_guarantee` | Reconciliation & Banking |
| 8 | `forecast_cash_flow` | Month-End Reporting |
| 9 | `close_fiscal_year` | Year-End Close |
| 10 | `calculate_standard_costing_variance` | Cost & Budgeting |
| 11 | `allocate_overhead_cost` | Cost & Budgeting |
| 12 | `calculate_revenue_recognition` | Cost & Budgeting |
| 13 | `flag_provision_contingent_liability` | Cost & Budgeting |
| 14 | `flag_related_party_transaction` | Cost & Budgeting |
| 15 | `adjust_sales_tax_input_output` | Tax |
| 16 | `flag_tax_exemption_zero_rating` | Tax |
| 17 | `prepare_sales_tax_filing` | Tax |
| 18 | `prepare_income_tax_filing` | Tax |
| 19 | `support_internal_audit` | Audit & Regulatory |
| 20 | `maintain_statutory_registers` | Audit & Regulatory |
| 21 | `resolve_flagged_entry` | Audit & Regulatory |
| 25 | `assess_fbr_audit_risk` | Audit & Regulatory |
| 22 | `generate_custom_report` | Advisory |
| 23 | `manage_system_preferences` | System Admin |
| 24 | `schedule_system_task` | System Admin |

**24 approval-gated · 47 direct-execution · 71 total**

---

## Model & Provider Chain

```
Request → Groq (llama-4-scout-17b)  [primary]
              ↓ on 429 rate limit
          Groq (llama-3.3-70b-versatile)  [fallback]
              ↓ on 429 rate limit
          Gemini (gemini-1.5-flash)  [last resort]
              ↓ on 402 / failure
          Clean error message returned to user
```

All agents use this same three-tier provider chain via `backend/agent_defs/run_utils.py`.
