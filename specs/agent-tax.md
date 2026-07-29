# Agent: Tax Agent

**Role:** All tax calculation and filing-preparation tasks. Filing submission itself always stays with a human (FBR portal requires personal credentials). 8 tools, 4 requiring human approval.

---

## Account Numbering Scheme

Consistent with Agents 2, 4, 5, 6:

| Prefix | Category |
|--------|----------|
| `1xxx` | **Assets** — cash (1000), receivables (1200), fixed assets |
| `2xxx` | **Liabilities** — payables (2000), tax payable (2200), WHT payable (2300), EOBI payable (2400), sales tax payable (2500) |
| `3xxx` | **Equity** — capital, retained earnings |
| `4xxx` | **Revenue** — sales, service income |
| `5xxx`, `6xxx`, `8xxx` | **Expenses** — operating costs, salaries, rent, tax expense |

**Agent 7 specific accounts (verification against Agents 2/5/6):**
- Withholding tax (WHT) deducted from payments → **2xxx** (liability: WHT payable until remitted to govt)
- Withholding tax expense → **5xxx/6xxx** (operating expense if borne by company)
- EOBI employer contribution → **6xxx** (payroll expense range)
- EOBI employee deduction payable → **2xxx** (liability until remitted)
- Sales tax collected → **2xxx** (sales tax payable liability)
- Sales tax input recoverable → **1xxx** (receivable from govt) or offset against output
- Advance minimum tax → **1xxx** (advance tax paid, receivable) or **5xxx** (tax expense)
- Income tax expense → **5xxx** (tax expense account)
- Income tax payable → **2xxx** (liability)

**Consistency confirmed:** All prefixes fall within the established 1xxx (Assets), 2xxx (Liabilities), 5xxx/6xxx (Expenses) ranges — matching Agents 2, 5, and 6.

---

## New DB Tables Needed

| Table | Purpose |
|-------|---------|
| `tax_rates` | Withholding tax rates, sales tax rates, AMT rates by type/category (tax_type, rate, effective_from, effective_to, description) |
| `eobi_rates` | EOBI deduction rates (rate_type, rate, effective_from, effective_to, description) |

---

## Tool: calculate_withholding_tax

- **Approval:** No — rule-based, fixed % from rate table
- **Input:** `amount` (Decimal), `withholding_type` (str — "salary", "contract", "supply", "service", "rent", "commission"), `transaction_date` (date)
- **Output:** `gross_amount` (Decimal), `withholding_type`, `rate_applied` (Decimal), `tax_amount` (Decimal), `net_amount` (Decimal), `rate_source` (str)
- **DB tables:** `tax_rates` (read) — query by tax_type + effective_from <= transaction_date <= effective_to
- **Edge cases:** No rate found for type → falls back to default 0% with warning. Amount ≤ 0 → Pydantic validation (gt=0). Multi-period rates → uses most recent effective rate.
- **Logic:** tax_amount = gross_amount × (rate / 100). net_amount = gross_amount − tax_amount. Rate looked up from `tax_rates` table by withholding_type and transaction_date.
- **New DB table needed:** `tax_rates` (id, tax_type, rate, effective_from, effective_to, description)
- **Example:** User: "Calculate withholding tax on 50000 for services" → 50000 × 8% = 4000 WHT, net 46000

## Tool: get_tax_planning_advice

- **Approval:** No — conversational guidance from stored data
- **Input:** `query` (str), `fiscal_year` (int)
- **Output:** `advice` (str), `fiscal_year`, `data_summary` (dict — e.g., total_revenue, total_expenses, estimated_tax_liability), `disclaimer` (str)
- **DB tables:** `journal_entries` (read — for revenue/expense patterns), `tax_rates` (read — for applicable rates)
- **Edge cases:** No data for the year → general advice only. Negative net income → loss carry-forward suggestion. Very large revenue → advance tax payment suggestion.
- **Logic:** Analyzes journal entries for the fiscal year. Revenue from prefix `4` accounts, expenses from `5`/`6`/`8` prefixes. Estimates approximate tax liability at corporate rate. Generates plain-English advice.
- **Example:** User: "Any tax planning tips for FY 2026?" → "Revenue 5M, expenses 3.5M, estimated tax ~450K. Consider advance tax payments to avoid interest."

## Tool: calculate_advance_minimum_tax

- **Approval:** No — deterministic formula
- **Input:** `annual_turnover` (Decimal), `fiscal_year` (int), `business_type` (str — "company", "individual", "aop")
- **Output:** `annual_turnover`, `applicable_rate` (Decimal), `minimum_tax` (Decimal), `basis` (str), `fiscal_year`
- **DB tables:** `tax_rates` (read — for AMT rate by business type)
- **Edge cases:** Turnover ≤ 0 → Pydantic validation (gt=0). Business type not found → defaults to company rate with warning. Below AMT threshold → returns 0 with note.
- **Logic:** AMT = turnover × (rate / 100). Under Pakistan tax law: companies ~1.5%, individuals/AOP vary. Rate from `tax_rates` table with type='advance_minimum_tax'.
- **Example:** User: "Calculate minimum tax for 10M turnover (company)" → 10M × 1.5% = 150,000 AMT

## Tool: calculate_eobi_deductions

- **Approval:** No — fixed % payroll deductions
- **Input:** `gross_salary` (Decimal), `period` (int), `fiscal_year` (int), `employee_category` (Optional[str] — "worker", "staff", "executive")
- **Output:** `gross_salary`, `employee_contribution` (Decimal), `employer_contribution` (Decimal), `total_contribution` (Decimal), `rate_applied` (Decimal), `basis` (str)
- **DB tables:** `eobi_rates` (read) — query rate by employee_category + effective date
- **Edge cases:** No rate found → defaults to standard EOBI rate with warning. Salary ≤ 0 → Pydantic validation (gt=0). Ceiling applies if salary exceeds max insurable amount.
- **Logic:** EOBI employer contribution = gross_salary × (rate / 100). Ceiling: max insurable salary (e.g., 50000/month under Pakistan rules). Employee contribution = employer_contribution × 0.5 (or same rate depending on category).
- **New DB table needed:** `eobi_rates` (id, rate_type, rate, effective_from, effective_to, description, max_insurable_amount)
- **Example:** User: "Calculate EOBI on gross salary 45000" → Employer 2250 (5%), Employee 1125 (2.5%), Total 3375

## Tool: adjust_sales_tax_input_output

- **Approval:** **Yes** — refund calculation requires accountant review
- **Input:** `period` (int), `fiscal_year` (int), `output_tax_amount` (Optional[Decimal] — override), `input_tax_amount` (Optional[Decimal] — override), `adjustment_reason` (Optional[str])
- **Output:** `period`, `fiscal_year`, `calculated_output_tax` (Decimal), `calculated_input_tax` (Decimal), `net_tax_payable` (Decimal), `refund_amount` (Decimal), `adjustments` (list[str]), `needs_approval` (bool), `summary` (str)
- **DB tables:** `journal_entries` (read — for sales/revenue and expense entries), `tax_rates` (read — for applicable sales tax rate)
- **Edge cases:** No entries for period → zeros. Input tax > output tax → refund scenario. Override amounts provided → skip DB calculation. Negative adjustments → explained.
- **Logic:** output_tax = sum of revenue (prefix `4`) × sales_tax_rate. input_tax = sum of applicable expenses (prefix `5`/`6`) × sales_tax_rate. net = output − input. If input > output: refund = difference.
- **Example:** User: "Adjust sales tax for July 2026" → output 45000, input 28000, net payable 17000

## Tool: flag_tax_exemption_zero_rating

- **Approval:** **Yes** — accountant confirms qualifying sales
- **Input:** `entry_ids` (list[str] — specific journal entry IDs to review), `fiscal_year` (int), `period` (Optional[int])
- **Output:** `flagged_entries` (list of dict: entry_id, description, amount, exemption_type, confidence, reasoning), `total_flagged_amount` (Decimal), `needs_approval` (bool), `recommendation` (str)
- **DB tables:** `journal_entries` (read — for revenue entries), `chart_of_accounts` (read — for account categorization), `contacts` (read — for export/related-party checks)
- **Edge cases:** No entries provided → scans all revenue entries for the period. Zero-confidence items flagged for manual review. Duplicate entry IDs → deduplicated.
- **Logic:** Revenue entries (prefix `4`) are checked against known zero-rated/exempt categories: exports (contact check), basic food items (account name), certain services. Entries matching exemption criteria flagged.
- **Example:** User: "Flag zero-rated transactions for July 2026" → flags export sales as zero-rated with recommendation

## Tool: prepare_sales_tax_filing

- **Approval:** **Yes** — prepares numbers; human submits via FBR portal
- **Input:** `period` (int), `fiscal_year` (int), `confirm` (bool — must be True to proceed)
- **Output:** `filing_id` (str), `period`, `fiscal_year`, `sales_tax_payable` (Decimal), `input_tax_adjustments` (Decimal), `net_amount_payable` (Decimal), `filing_data` (dict — structured for FBR form), `needs_approval` (bool), `status` (str), `message` (str)
- **DB tables:** `journal_entries` (read), `tax_rates` (read), `contacts` (read)
- **Edge cases:** confirm=False → raises ValueError. Already filed for period → returns existing with warning. No entries for period → zero filing with note. Previous adjustments not finalized → warning.
- **Logic:** Aggregates revenue (prefix `4`), applies standard sales tax rate (e.g., 18%), subtracts input tax adjustments. Formats output as FBR-compatible structure.
- **Example:** User: "Prepare sales tax filing for July 2026" → structured filing data with net payable

## Tool: prepare_income_tax_filing

- **Approval:** **Yes** — prepares numbers; human submits via FBR portal
- **Input:** `fiscal_year` (int), `confirm` (bool — must be True to proceed)
- **Output:** `filing_id` (str), `fiscal_year`, `total_income` (Decimal), `total_expenses` (Decimal), `taxable_income` (Decimal), `tax_liability` (Decimal), `advance_tax_paid` (Decimal), `net_tax_due` (Decimal), `filing_data` (dict — structured for FBR form), `needs_approval` (bool), `status` (str), `message` (str)
- **DB tables:** `journal_entries` (read), `tax_rates` (read), `retained_earnings` (read)
- **Edge cases:** confirm=False → raises ValueError. Already filed → returns existing with warning. Net loss → zero tax liability with loss carry-forward note. No data → zero filing.
- **Logic:** Total income from revenue accounts (prefix `4`). Total expenses from expense accounts (prefixes `5`/`6`/`8`). Taxable = income − expenses. Tax liability computed from progressive/company rates. Advance tax paid from retained_earnings or specific entries.
- **Example:** User: "Prepare income tax filing for FY 2026" → structured filing data with net tax due

---

## Agent-Level Behavior

- **Routing:** "withholding tax", "WHT", "withholding", "tax planning", "tax advice", "minimum tax", "AMT", "advance minimum tax", "EOBI", "social security", "payroll deduction", "sales tax", "input tax", "output tax", "sales tax adjustment", "tax exemption", "zero-rated", "tax exempt", "sales tax filing", "income tax filing", "tax filing", "FBR", "tax return"
- **4 human-approval tools:** `adjust_sales_tax_input_output`, `flag_tax_exemption_zero_rating`, `prepare_sales_tax_filing` (needs confirm=True), `prepare_income_tax_filing` (needs confirm=True)
- **4 non-approval tools:** `calculate_withholding_tax`, `get_tax_planning_advice`, `calculate_advance_minimum_tax`, `calculate_eobi_deductions`
- **All filing tools:** confirm=False raises ValueError (never auto-submit)
