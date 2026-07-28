# Agent: Month-End Reporting

**Role:** Handles all month-end close tasks — unpaid bills, prepaid adjustments, depreciation, amortization, payroll reconciliation, AR/AP aging reports, budget variance analysis, loan/debt schedule tracking, and cash flow forecasting. 10 tools, 1 requiring human approval.

---

## Tool: review_unpaid_bills

- **Approval:** No
- **Input:** `from_date`, `to_date`, `vendor_contact_id` optional, `min_days_overdue` optional
- **Output:** `bills[]` (entry_id, vendor, amount, posted_date, days_overdue, status), `total_unpaid`
- **DB tables:** `journal_entries` (read), `contacts` (read)
- **Edge cases:** No unpaid bills, vendor filter no match, all bills paid, overdue > 90 days flagged
- **Example:** User: "Show me unpaid bills for July" → list of AP items with vendor names

## Tool: calculate_prepaid_adjustment

- **Approval:** No
- **Input:** `prepaid_id` optional, `as_of_date`
- **Output:** `adjustments[]` (prepaid_id, description, monthly_amount, months_remaining, total_adjustment)
- **DB tables:** `prepaid_expenses` (read/write)
- **Edge cases:** Fully amortized, zero remaining months, negative balance
- **Example:** User: "Calculate prepaid adjustment for July" → monthly amortization of advance payments

## Tool: calculate_depreciation

- **Approval:** No
- **Input:** `asset_id` optional, `period_date`
- **Output:** `entries[]` (asset_id, asset_name, monthly_depreciation, accumulated_depreciation, book_value)
- **DB tables:** `fixed_assets` (read), `depreciation_schedule` (write)
- **Edge cases:** Fully depreciated, asset not found, residual > cost, mid-period acquisition
- **Example:** User: "Run depreciation for July 2026" → straight-line calculation per active asset

## Tool: calculate_amortization

- **Approval:** No
- **Input:** `asset_id` optional, `period_date`
- **Output:** Same structure as depreciation
- **DB tables:** `intangible_assets` (read), `amortization_schedule` (write)
- **Edge cases:** Same as depreciation

## Tool: reconcile_payroll

- **Approval:** No
- **Input:** `period_start`, `period_end`
- **Output:** `payroll_total`, `gl_total`, `difference`, `matched`, `unmatched_entries[]`
- **DB tables:** `payroll_entries` (read), `journal_entries` (read)
- **Edge cases:** No payroll, no GL entries, perfect match, partial match

## Tool: get_ar_aging_report

- **Approval:** No
- **Input:** `as_of_date`, `customer_contact_id` optional
- **Output:** `aging_buckets[]` (bucket_name, total, count), `customer_details[]`
- **DB tables:** `journal_entries` (read), `contacts` (read)
- **Edge cases:** No AR, all current, all overdue, customer filter

## Tool: get_ap_aging_report

- **Approval:** No
- **Input:** Same pattern as AR
- **Output:** Same structure
- **DB tables:** Same as AR but AP side

## Tool: analyze_budget_variance

- **Approval:** No
- **Input:** `fiscal_year`, `period`, `account_code` optional
- **Output:** `variances[]` (account, budget, actual, variance, variance_pct, explanation)
- **DB tables:** `budgets` (read), `journal_entries` (read)
- **Edge cases:** No budget, no actuals, overspend > 20% flagged

## Tool: get_loan_debt_schedule

- **Approval:** No
- **Input:** `loan_id`, `as_of_date`
- **Output:** `schedule[]` (payment_date, principal, interest, total, balance), `loan_summary`
- **DB tables:** `loans` (read), `loan_payment_schedule` (read)
- **Edge cases:** Loan paid, not found, 0% interest

## Tool: forecast_cash_flow

- **Approval:** Yes
- **Input:** `forecast_days` (30/60/90), `as_of_date`
- **Output:** `projections[]` (date, inflow, outflow, net, confidence), `current_balance`
- **DB tables:** `journal_entries` (read), `bank_transactions` (read), `cash_flow_projections` (write)
- **Edge cases:** No history, negative projection, low confidence

## Agent-Level Behavior

- **Routing:** "month-end", "unpaid bills", "prepaid", "depreciation", "amortization", "payroll reconciliation", "aging report", "AR aging", "AP aging", "budget variance", "loan schedule", "debt schedule", "cash flow forecast"
- **Only 1 approval tool:** `forecast_cash_flow` — projections are inherently uncertain
- **8 backend-calculation tools:** pure formulas, no AI needed
- **2 AI-assisted tools:** `review_unpaid_bills` (query+present), `analyze_budget_variance` (compare+explain)
