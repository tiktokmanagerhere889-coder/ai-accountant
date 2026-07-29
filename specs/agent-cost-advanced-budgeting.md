# Agent: Cost, Advanced Accounting & Budgeting

**Role:** Cost/management accounting (breakeven, variance, overhead allocation), advanced accounting (revenue recognition, provisions, foreign currency, related-party flagging), and forward-looking budget planning. 8 tools, 4 requiring human approval.

---

## Account Numbering Scheme

Consistent with Agents 2, 4, 5:

| Prefix | Category |
|--------|----------|
| `1xxx` | **Assets** — cash (1000), receivables (1200), fixed assets |
| `2xxx` | **Liabilities** — payables (2000), loans |
| `3xxx` | **Equity** — capital, retained earnings |
| `4xxx` | **Revenue** — sales, service income |
| `5xxx`, `6xxx`, `8xxx` | **Expenses** — operating costs, salaries, rent |

---

## Tool: calculate_breakeven

- **Approval:** No — pure formula, no AI reasoning
- **Input:** `fixed_cost` (Decimal), `variable_cost_per_unit` (Decimal), `selling_price_per_unit` (Decimal)
- **Output:** `breakeven_units` (Decimal), `breakeven_revenue` (Decimal), `contribution_margin_per_unit` (Decimal), `contribution_margin_ratio` (float), `formula_used` (str)
- **DB tables:** None (pure calculation)
- **Edge cases:** selling_price <= variable_cost → raises `ValueError` ("Price must exceed variable cost"), zero fixed_cost → breakeven = 0, negative inputs → Pydantic validation (gt=0)
- **Logic:** Contribution margin = price − variable cost. Breakeven units = fixed_cost / contribution_margin. Breakeven revenue = breakeven_units × price.
- **Example:** User: "Calculate breakeven: fixed cost 500000, variable cost 300 per unit, selling price 500" → 2500 units, $1,250,000 revenue

## Tool: convert_foreign_currency

- **Approval:** No — formula-based, rate from DB
- **Input:** `amount` (Decimal), `from_currency` (str), `to_currency` (str), `rate_date` (Optional[date])
- **Output:** `original_amount` (Decimal), `from_currency`, `to_currency`, `conversion_rate` (Decimal), `converted_amount` (Decimal), `rate_source` (str), `rate_date` (date)
- **DB tables:** `exchange_rates` (read) — stores currency pairs with rates
- **Edge cases:** Unknown currency pair → raises `ValueError` ("No rate found for pair"), rate older than 30 days → warning flag, same currency → rate=1, no change. Amount is zero → Pydantic validation (gt=0)
- **Logic:** converted = amount × rate. Rate looked up from `exchange_rates` table by currency pair + date (nearest available). If no `exchange_rates` table exists, falls back to 1:1 with warning.
- **New DB table needed:** `exchange_rates` (id, from_currency, to_currency, rate, rate_date, source)
- **Example:** User: "Convert 1000 USD to PKR at today's rate" → converted amount with rate used

## Tool: prepare_budget_forecast

- **Approval:** No — backend calculation from historical data
- **Input:** `fiscal_year` (int), `periods` (int, 1-12), `account_code_prefix` (Optional[str])
- **Output:** `forecast_items[]` (account_code, account_name, historical_avg, forecast_amount, basis), `total_forecast`, `data_months` (int), `confidence` (str)
- **DB tables:** `journal_entries` (read), `budgets` (read)
- **Edge cases:** No historical data → all zeros with "low" confidence, single month of history → "low" confidence, 3+ months → "medium", 12+ months → "high". Prefix filter narrows scope.
- **Logic:** Averages monthly actuals from journal_entries over available history, projects forward as budget forecast. If prior budget exists for same account, uses it as baseline with inflation adjustment.
- **Example:** User: "Prepare budget forecast for FY 2027" → per-account budget draft from spending patterns

## Tool: calculate_standard_costing_variance

- **Approval:** **Yes** — owner supplies standard cost, agent calculates gap
- **Input:** `account_code` (str), `period` (int), `fiscal_year` (int), `standard_cost` (Decimal), `standard_quantity` (Optional[Decimal])
- **Output:** `account_code`, `period`, `fiscal_year`, `standard_cost`, `actual_cost` (Decimal), `cost_variance` (Decimal), `variance_pct` (Decimal), `actual_quantity` (Optional[Decimal]), `quantity_variance` (Optional[Decimal]), `needs_approval` (bool), `explanation` (str)
- **DB tables:** `journal_entries` (read — for actual costs)
- **Edge cases:** No actual entries for account → actual_cost = 0, variance = full standard (flagged). Zero standard cost → raises ValueError. Negative variance (favorable/unfavorable) explained.
- **Logic:** actual_cost = sum of debit_amounts to account_code. cost_variance = actual − standard. variance_pct = variance / standard × 100. If quantity provided: quantity_variance = actual_qty − standard_qty.
- **Example:** User: "Calculate cost variance for account 6000, standard $50000 for period 7" → shows actual vs standard with explanation

## Tool: allocate_overhead_cost

- **Approval:** **Yes** — owner defines allocation basis
- **Input:** `total_overhead` (Decimal), `allocation_basis` (str — "sq_ft", "headcount", "revenue_pct", "custom"), `allocation_pool[]` (name: str, value: Decimal — each department/center's basis value), `period` (int), `fiscal_year` (int)
- **Output:** `allocations[]` (department_name, basis_value, percentage, allocated_amount), `total_allocated`, `basis_used`, `period`, `fiscal_year`, `needs_approval` (bool)
- **DB tables:** None (pure calculation)
- **Edge cases:** Allocation values sum to zero → raises ValueError. Single department → 100% allocation. Custom basis allows weighted distribution.
- **Logic:** Each department's allocation = (dept_basis_value / total_basis_values) × total_overhead. Verify sum of allocations = total_overhead.
- **Example:** User: "Allocate $100,000 overhead by headcount: Sales 10, Engineering 25, Support 15" → percentage split and dollar allocation per team

## Tool: calculate_revenue_recognition

- **Approval:** **Yes** — contract completion requires judgement
- **Input:** `contract_id` (str), `contract_value` (Decimal), `completion_percentage` (Decimal, 0-100), `previous_recognized` (Optional[Decimal]), `period` (int), `fiscal_year` (int)
- **Output:** `contract_id`, `contract_value`, `completion_percentage`, `total_recognizable` (Decimal), `previously_recognized` (Decimal), `current_period_revenue` (Decimal), `remaining_revenue` (Decimal), `needs_approval` (bool), `explanation` (str)
- **DB tables:** `journal_entries` (read — for previously recognized amounts)
- **Edge cases:** completion% > 100 → clamped to 100, completion% ≤ 0 → raises ValueError, previous_recognized > total_recognizable → raises ValueError (over-recognized), 100% complete → all remaining recognized
- **Logic:** total_recognizable = contract_value × (completion_pct / 100). current_period = total_recognizable − previously_recognized. remaining = contract_value − total_recognizable.
- **Example:** User: "Recognize revenue for contract C-001, $500K, 60% complete, $200K already recognized" → $100K current period revenue

## Tool: flag_provision_contingent_liability

- **Approval:** **Yes** — final decision by accountant
- **Input:** `description` (str), `estimated_amount` (Decimal), `probability` (str — "probable", "possible", "remote"), `fiscal_year` (int), `related_party` (Optional[str])
- **Output:** `provision_id` (str), `description`, `estimated_amount`, `probability`, `accounting_treatment` (str — "recognize", "disclose", "ignore"), `needs_approval` (bool), `reasoning` (str), `status` (str)
- **DB tables:** `journal_entries` (read — for similar past provisions), `contacts` (read — for related party check)
- **Edge cases:** probable → "recognize" (accrue in statements), possible → "disclose" (note only), remote → "ignore". Amount is zero → Pydantic validation (gt=0). Previously flagged same item → returns existing with status.
- **Logic:** IFRS/IAS 37-based: probable (>50%) = recognize liability + expense. Possible = disclose in notes. Remote = no action. Generates journal entry suggestion if recognize.
- **Example:** User: "Flag potential lawsuit provision: $200K, probable" → recommends recognition with supporting reasoning

## Tool: flag_related_party_transaction

- **Approval:** **Yes** — insider-connected transaction flagging
- **Input:** `entry_id` (str), `transaction_description` (str), `amount` (Decimal), `counterparty_name` (str), `fiscal_year` (int)
- **Output:** `flag_id` (str), `entry_id`, `counterparty_name`, `related_party_status` (str — "confirmed_related", "potential_related", "not_related"), `confidence` (str), `disclosure_required` (bool), `reasoning` (str), `needs_approval` (bool)
- **DB tables:** `contacts` (read — check if counterparty matches any contact with related-party flag), `journal_entries` (read — for the specific entry)
- **Edge cases:** Counterparty not in contacts → "not_related" with low confidence. Same counterparty flagged before → returns previous status. Amount unusually high/low relative to normal → additional flag "review_amount".
- **Logic:** Checks contacts table for counterparty name match. If found with `contact_type` matching patterns or a `related_party` flag field, marks as related. Requires human approval before disclosure.
- **New DB field needed:** `contacts.related_party` (boolean, default False) or separate `related_parties` table
- **Example:** User: "Flag transaction JE-123 with Abdullah Traders for $50K" → checks contacts, returns related-party assessment

---

## Agent-Level Behavior

- **Routing:** "breakeven", "cost-volume-profit", "CVP", "break-even", "currency conversion", "forex", "exchange rate", "budget forecast", "budgeting", "standard cost", "cost variance", "overhead allocation", "cost allocation", "revenue recognition", "contract revenue", "provision", "contingent liability", "provision booking", "related party", "insider transaction", "related party disclosure"
- **4 human-approval tools:** `calculate_standard_costing_variance`, `allocate_overhead_cost`, `calculate_revenue_recognition`, `flag_provision_contingent_liability`, `flag_related_party_transaction`
- **3 direct-calculation tools:** `calculate_breakeven`, `convert_foreign_currency`, `prepare_budget_forecast`

## New DB Tables Needed

| Table | Purpose |
|-------|---------|
| `exchange_rates` | Currency conversion rates (from_currency, to_currency, rate, rate_date, source) |

## New DB Fields Needed

| Table | Field | Purpose |
|-------|-------|---------|
| `contacts` | `related_party` (Boolean, default False) | Flag vendors/customers as related parties |
