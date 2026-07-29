# AI Accountant — Agents & Tools Reference

This file lists every agent in the system, every tool inside each agent, what each tool does, and whether it requires human approval before executing. Use this as the single source of truth when building, testing, or modifying any agent/tool.

**Framework:** OpenAI Agents SDK — Manager pattern (Orchestrator calls specialist agents as tools, specialist agents never talk to the user directly).

**Total: 1 Orchestrator + 7 Specialist Agents + 53 tools + 3 direct-backend (non-AI) features = 56 components.**

---

## 0. Orchestrator Agent

**Role:** Routes every `/chat` request to the correct specialist agent(s), combines their results into one natural-language reply. Owns the conversation. Has no tools of its own.

---

## 1. Daily Entry Agent

**Role:** Handles daily cash/transaction capture — the first point of contact for recording money movement.

| Tool | Approval | What it does |
|---|---|---|
| `check_cash_position` | No | Live cash balance from DB |
| `record_transaction_nl` | No | Parses a plain-English transaction and stores it |
| `process_receipt_image` | **Yes** | Reads amount/vendor from an uploaded receipt photo |
| `check_bank_transactions` | No | Queries stored bank transaction data |
| `manage_petty_cash` | No | Small cash entries + replenishment reminders |

---

## 2. Ledger & Master Data Agent

**Role:** Owns the chart of accounts, journal entries, ledgers, and vendor/customer records.

| Tool | Approval | What it does |
|---|---|---|
| `create_journal_entry` | No | Converts a plain-language transaction into correct debit/credit |
| `get_general_ledger` | No | Aggregated ledger view |
| `suggest_chart_of_accounts` | **Yes** | Suggests starting account structure |
| `get_ap_subledger` | No | Accounts payable sub-ledger view |
| `get_ar_subledger` | No | Accounts receivable sub-ledger view |
| `get_payroll_ledger` | No | Salary minus deductions |
| `categorize_fixed_asset` | **Yes** | Categorizes a newly added fixed asset |
| `manage_contact` | No | Add/update vendor or customer (shared tool) |

---

## 3. Reconciliation & Banking Agent

**Role:** Matches internal records against external statements (bank, vendor, customer) and tracks banking instruments. Heaviest concentration of approval gates.

| Tool | Approval | What it does |
|---|---|---|
| `run_bank_reconciliation` | **Yes** | Matches bank lines to internal records |
| `post_accrual_entry` | **Yes** | Suggests and posts an accrual after approval |
| `reconcile_vendor_statement` | **Yes** | Compares vendor statement to internal records |
| `reconcile_customer_statement` | **Yes** | Compares customer statement to internal records |
| `track_cheque_clearing` | No | Tracks cheque issuance/clearing |
| `track_lc_bank_guarantee` | **Yes** | Tracks letter of credit / bank guarantee status |
| `reconcile_bank_charges` | No | Matches bank fee lines to ledger |

---

## 4. Month-End Reporting Agent

**Role:** Period-end calculations that are deterministic (backend calculation), with the AI presenting/explaining the result.

| Tool | Approval | What it does |
|---|---|---|
| `review_unpaid_bills` | No | Returns list of unpaid bills |
| `calculate_prepaid_adjustment` | No | Divides advance payment across months |
| `calculate_depreciation` | No | Fixed-formula depreciation |
| `calculate_amortization` | No | Fixed-formula amortization |
| `reconcile_payroll` | No | Matches payroll records to general ledger |
| `get_ar_aging_report` | No | Grouped by overdue days |
| `get_ap_aging_report` | No | Grouped by overdue days, vendor side |
| `analyze_budget_variance` | No | Compares budget vs actual, explains gap |
| `get_loan_debt_schedule` | No | Amortization schedule (principal/interest) |
| `forecast_cash_flow` | **Yes** | Projects near-term cash needs |

---

## 5. Year-End Close & Financial Statements Agent

**Role:** Generates the four core financial statements and handles year-end closing, retained earnings, balance carry-forward, and notes to financials. *(Merged from two originally separate agents — Year-End Close and Financial Statements — into one, since both are closely tied to period-end reporting.)*

| Tool | Approval | What it does |
|---|---|---|
| `generate_trial_balance` | No | Debits = credits check |
| `generate_profit_loss` | No | Revenue − expenses |
| `generate_balance_sheet` | No | Assets = liabilities + equity check |
| `generate_cash_flow_statement` | No | Operating + investing + financing activity |
| `close_fiscal_year` | **Yes** | Irreversible year-end closing action |
| `transfer_retained_earnings` | No | One-line formula, system logic |
| `carry_forward_balances` | No | Opening/closing balance carry-forward, system logic — not an AI decision |
| `draft_notes_to_financials` | No | Drafts explanatory notes to statements (human reviews before attaching) |

---

## 6. Cost, Advanced Accounting & Budgeting Agent

**Role:** Cost/management accounting, advanced accounting judgment calls, and forward-looking budget planning.

| Tool | Approval | What it does | DB Tables |
|---|---|---|---|
| `calculate_breakeven` | No | CVP analysis — contribution margin, breakeven units/revenue | None (pure formula) |
| `convert_foreign_currency` | No | Currency conversion using `exchange_rates` table | `exchange_rates` |
| `prepare_budget_forecast` | No | Budget forecast from historical avg + budget baseline | `journal_entries`, `budgets` |
| `calculate_standard_costing_variance` | **Yes** | Standard vs actual cost gap + quantity variance | `journal_entries` |
| `allocate_overhead_cost` | **Yes** | Overhead apportionment on owner-defined basis | None (pure calculation) |
| `calculate_revenue_recognition` | **Yes** | Percentage-of-completion revenue recognition | `journal_entries` |
| `flag_provision_contingent_liability` | **Yes** | IAS 37 provision/contingency assessment | `journal_entries`, `contacts` |
| `flag_related_party_transaction` | **Yes** | Insider-connected transaction check (contact_id + reference hybrid) | `journal_entries`, `contacts` |

---

## 7. Tax Agent

**Role:** All tax calculation and filing-preparation tasks. Filing submission itself always stays with a human (FBR portal requires personal credentials).

| Tool | Approval | What it does |
|---|---|---|
| Tool | Approval | What it does | DB Tables |
|---|---|---|---|
| `calculate_withholding_tax` | No | WHT on payments — rate from `tax_rates` table or default | `tax_rates` |
| `get_tax_planning_advice` | No | Conversational tax guidance from stored financial data | `journal_entries` |
| `calculate_advance_minimum_tax` | No | AMT on turnover — rate from `tax_rates` by business type | `tax_rates` |
| `calculate_eobi_deductions` | No | EOBI employer + employee deductions, ceiling capped | `eobi_rates` |
| `adjust_sales_tax_input_output` | **Yes** | Sales tax input/output adjustment with override support | `journal_entries` |
| `flag_tax_exemption_zero_rating` | **Yes** | Flags zero-rated/exempt revenue entries | `journal_entries`, `contacts` |
| `prepare_sales_tax_filing` | **Yes** | Prepares FBR sales tax filing data (confirm=True req) | `journal_entries` |
| `prepare_income_tax_filing` | **Yes** | Prepares FBR income tax filing data (confirm=True req) | `journal_entries` |

---

## 8. Audit & Regulatory Agent

**Role:** Anomaly detection, internal audit support, statutory records, and compliance deadline tracking.

| Tool | Approval | What it does |
|---|---|---|
| `support_internal_audit` | **Yes** | Flags unusual entries for accountant review |
| `detect_anomaly_transactions` | No | Pattern-based fraud/anomaly flagging |
| `maintain_statutory_registers` | **Yes** | Keeps statutory register data current |
| `get_compliance_deadlines` | No | Tracks and reminds of filing deadlines |

---

## 9. Advisory Agent

**Role:** Open-ended financial insight and Q&A over the business's own data.

| Tool | Approval | What it does |
|---|---|---|
| `analyze_spending_patterns` | No | Answers spending questions (e.g. utilities in March) |
| `assess_financial_health` | No | Combines ratios/trends into a plain-language summary |
| `generate_cost_cutting_recommendations` | No | Suggestions from spending patterns already in the system |
| `generate_custom_report` | **Yes** | Builds a custom query from a plain-language ask |
| `calculate_financial_ratios` | No | Standard ratios, explained |

---

## Direct-Backend Features (NOT agent tools — no AI involved)

These go straight from UI/API to the database. No agent, no tool, no LLM call.

| Feature | Why no AI |
|---|---|
| `audit_trail_change_log` | Timestamp + user-id logging — a DB design choice |
| `user_roles_permissions` | Standard access-control feature |
| `data_backup_scheduling` | A scheduled script — no language understanding needed |

---

## Quick Reference — Approval-Required Tools (across all agents)

These are the tools that must pause and wait for human confirmation before writing to the database:

1. `process_receipt_image` (Daily Entry)
2. `suggest_chart_of_accounts` (Ledger & Master Data)
3. `categorize_fixed_asset` (Ledger & Master Data)
4. `run_bank_reconciliation` (Reconciliation & Banking)
5. `post_accrual_entry` (Reconciliation & Banking)
6. `reconcile_vendor_statement` (Reconciliation & Banking)
7. `reconcile_customer_statement` (Reconciliation & Banking)
8. `track_lc_bank_guarantee` (Reconciliation & Banking)
9. `forecast_cash_flow` (Month-End Reporting)
10. `close_fiscal_year` (Year-End Close & Financial Statements)
11. `calculate_standard_costing_variance` (Cost, Advanced & Budgeting)
12. `allocate_overhead_cost` (Cost, Advanced & Budgeting)
13. `calculate_revenue_recognition` (Cost, Advanced & Budgeting)
14. `flag_provision_contingent_liability` (Cost, Advanced & Budgeting)
15. `flag_related_party_transaction` (Cost, Advanced & Budgeting)
16. `prepare_sales_tax_filing` (Tax)
17. `prepare_income_tax_filing` (Tax)
18. `adjust_sales_tax_input_output` (Tax)
19. `flag_tax_exemption_zero_rating` (Tax)
20. `support_internal_audit` (Audit & Regulatory)
21. `maintain_statutory_registers` (Audit & Regulatory)
22. `generate_custom_report` (Advisory)

**18 tools require approval, 35 do not, out of 53 total (Agents 1-7 implemented).**