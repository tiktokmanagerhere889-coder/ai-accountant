---
id: "002"
title: "Implement ledger tools 4-6"
stage: green
date: 2026-07-29
surface: agent
model: oc/big-pickle
feature: ledger-master-data
branch: main
user: hassan khan
command: Implement tools 4-6 for Agent 2 (Ledger & Master Data) — get_ap_subledger, get_ar_subledger, get_payroll_ledger with PostgreSQL tests
labels: ["ap-subledger", "ar-subledger", "payroll-ledger", "sqlalchemy", "tools", "testing"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
  - backend/tools/ledger_tools.py
  - backend/tools/schemas.py
  - backend/tests/test_ledger_tools_456.py
tests:
  - test_ap_with_entries
  - test_ap_empty
  - test_ap_vendor_filter
  - test_ar_with_entries
  - test_ar_empty
  - test_payroll_with_entries
  - test_payroll_empty
  - test_payroll_employee_filter
  - test_payroll_deduction_warning
---

## Prompt

You are implementing tools 4-6 for Agent 2 (Ledger & Master Data) of the AI Accountant project.

Project: C:\Users\Hassan\ai-accountant
PostgreSQL: postgresql://postgres:postgres@localhost:5432/ai_accountant (prod), ai_accountant_test (test)
DB models: backend/db/models.py (read it first — already has JournalEntry, Contact, PayrollEntry)
Schemas: backend/tools/schemas.py (read it first — schemas for these tools should already exist)
Test helper: backend/tests/test_helpers.py - use TEST_DATABASE_URL

**IMPORTANT**: Tests must use PostgreSQL not SQLite. Import Base from db.models, engine with TEST_DATABASE_URL, drop_all + create_all.

**Tool 4: get_ap_subledger** (no approval)
- Input: GetAPSubledgerInput (from_date, to_date, vendor_contact_id optional)
- Output: GetAPSubledgerOutput (entries list, total_outstanding)
- Logic: Query journal_entries where debit_account starts with "2000" (liability/AP range). Group by vendor reference. Calculate total outstanding.
- If vendor_contact_id provided, filter by reference field matching contact_id pattern.
- Write in: backend/tools/ledger_tools.py (append to file created by another agent, or create if not exists)

**Tool 5: get_ar_subledger** (no approval)
- Input: GetARSubledgerInput (from_date, to_date, customer_contact_id optional)
- Output: GetARSubledgerOutput (entries list, total_outstanding)
- Logic: Query journal_entries where debit_account starts with "1200" (AR range). Same pattern as AP.

**Tool 6: get_payroll_ledger** (no approval)
- Input: GetPayrollLedgerInput (from_date, to_date, employee_name optional)
- Output: GetPayrollLedgerOutput (entries list, total_salary, total_deductions, total_net_pay)
- Logic: Query payroll_entries table. Filter by employee_name if provided.
- Edge cases: deductions > salary -> warning flag, no entries -> empty list

**Tests**: Create backend/tests/test_ledger_tools_456.py
- Test AP with entries, test empty AP, test vendor filter
- Test AR with entries, test empty AR
- Test payroll with entries, test employee filter, test no entries
- 4-5 tests minimum, all passing

Write ALL files completely. Use Optional[X] not X|None syntax. No `__future__` annotations.

## Response snapshot

Implemented 3 ledger tools (get_ap_subledger, get_ar_subledger, get_payroll_ledger) by appending to existing backend/tools/ledger_tools.py. Added `warning: bool = False` field to PayrollEntryItem schema. Created test file backend/tests/test_ledger_tools_456.py with 9 tests across 3 test classes — all pass against PostgreSQL. AP and AR tools query journal_entries grouped by reference with debit_account prefix filtering (2000/1200). Payroll tool queries payroll_entries with per-entry warning flag when deductions exceed salary.

## Outcome

- ✅ Impact: Added 3 fully tested ledger tools to Agent 2. AP/AR subledger tools query journal entries grouped by vendor/customer reference with contact ID filtering. Payroll ledger tool queries payroll entries with warning flags for anomalous deductions. All tools handle empty results and optional filters.
- 🧪 Tests: 9/9 passing — test_ap_with_entries, test_ap_empty, test_ap_vendor_filter, test_ar_with_entries, test_ar_empty, test_payroll_with_entries, test_payroll_empty, test_payroll_employee_filter, test_payroll_deduction_warning
- 📁 Files: backend/tools/ledger_tools.py (appended 3 functions), backend/tools/schemas.py (added warning field), backend/tests/test_ledger_tools_456.py (new test file)
- 🔁 Next prompts: Create orchestration layer or integration tests combining tools from multiple agents.
- 🧠 Reflection: The existing schemas from a prior agent already defined APEntryItem, AREntryItem, and PayrollEntryItem with detailed fields (entry_id, vendor_name, invoice_amount, etc.). The tools map flat journal_entry data to these structured output models. The ledger_tools.py file already existed with tools 1-3 (create_journal_entry, get_general_ledger, suggest_chart_of_accounts) so tools 4-6 were appended.

## Evaluation notes (flywheel)

- Failure modes observed: Initial import error due to missing sys.path setup — resolved by adding sys.path.insert at top of test file following existing test convention.
- Graders run and results (PASS/FAIL): PASS - all 9 tests passing against PostgreSQL
- Prompt variant (if applicable): agent-native implementation with pytest test classes
- Next experiment (smallest change to try): None — all tests passing
