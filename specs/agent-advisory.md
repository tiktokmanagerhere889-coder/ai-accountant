# Agent: Advisory Agent

**Role:** Open-ended financial insight and Q&A over the business's own data. 5 tools, 1 requiring human approval.

---

## Account Numbering Scheme

Consistent with Agents 2, 4, 5, 6, 7, 8:

| Prefix | Category |
|--------|----------|
| `1xxx` | **Assets** — cash (1000), receivables (1200), fixed assets |
| `2xxx` | **Liabilities** — payables (2000), loans, tax payable |
| `3xxx` | **Equity** — capital, retained earnings |
| `4xxx` | **Revenue** — sales, service income |
| `5xxx`, `6xxx`, `8xxx` | **Expenses** — operating costs, salaries, rent |

**Agent 9 specific accounts:**
- No new accounts needed — reads from existing `journal_entries`, `chart_of_accounts`, `budgets`, `retained_earnings`
- All tools are query/analysis only — no write to journal_entries

---

## New DB Tables Needed

None. Agent 9 reads from existing tables only.

| Table | Purpose | Access |
|-------|---------|--------|
| `journal_entries` | All spending, revenue, and financial data | Read |
| `chart_of_accounts` | Account categorization for grouping | Read |
| `budgets` | Budget targets for variance/health analysis | Read |
| `retained_earnings` | Equity data for ratio calculations | Read |

---

## Tool: analyze_spending_patterns

- **Approval:** No — query-only, returns data analysis
- **Input:** `from_date` (date), `to_date` (date), `group_by` (Optional[str] — "month", "category", "vendor"), `account_prefixes` (Optional[list[str]] — filter to specific prefixes like ["5", "6"]), `description_keyword` (Optional[str] — filter entries whose description contains this)
- **Output:** `period` (str), `total_spending` (Decimal), `categories` (list: name, amount, percentage, count), `top_categories` (list: name, amount), `monthly_breakdown` (Optional[list: month, amount]), `insights` (list[str]), `entry_count` (int)
- **DB tables:** `journal_entries` (read — aggregate debit amounts by account, date, description)
- **Edge cases:** No entries in range → empty categories with message. Single category dominates (over 80%) → note in insights. group_by=month with single month → single-entry breakdown. description_keyword matches nothing → empty filtered result. Very large dataset → summary statistics only.
- **Logic:** Base query filters `posted_date` between from_date/to_date. Filters by `debit_account` prefix if `account_prefixes` provided. Filters by `description` ILIKE match if `description_keyword` provided. Groups by account prefix (category), month (extract year+month), or description pattern. Computes percentage of total for each category. Generates insights: highest category, month-over-month changes, concentration risk.
- **Example:** User: "Show me my spending patterns for Q2 2026" → 3 months analyzed, rent 50% (150000), salaries 33% (100000), utilities 17% (50000). Insight: "Rent is your largest expense at 50% of total spending."

## Tool: calculate_financial_ratios

- **Approval:** No — formula-based, deterministic calculation
- **Input:** `fiscal_year` (int), `period` (Optional[int] — month 1-12; if None, uses full year), `ratio_types` (Optional[list[str]] — "liquidity", "profitability", "leverage", "efficiency"; if None, computes all)
- **Output:** `fiscal_year` (int), `ratios` (list: name, value, benchmark, interpretation, category), `summary` (str)
- **DB tables:** `journal_entries` (read — aggregate by account prefix for assets/liabilities/revenue/expenses), `retained_earnings` (read — net_income, ending_balance)
- **Edge cases:** Zero or negative equity → divide-by-zero handled with "N/A (negative/zero equity)". No data for period → empty ratios with message. Zero revenue → profitability ratios return 0 or N/A. Very small denominators → ratios capped at reasonable bounds with note.
- **Logic:** Computes standard ratios by category:
  - **Liquidity:** Current Ratio = total_current_assets (1xxx) / total_current_liabilities (2xxx). Quick Ratio = (current_assets − inventory) / current_liabilities.
  - **Profitability:** Net Profit Margin = net_income / total_revenue × 100. Gross Profit Margin = (revenue − COGS) / revenue × 100. ROA = net_income / total_assets × 100. ROE = net_income / total_equity × 100.
  - **Leverage:** Debt-to-Equity = total_liabilities / total_equity. Debt Ratio = total_liabilities / total_assets.
  - **Efficiency:** Asset Turnover = total_revenue / total_assets. Expense Ratio = total_expenses / total_revenue.
  Each ratio includes a plain-language interpretation (e.g., "Above 1.0 indicates good short-term financial health").
- **New DB table needed:** None
- **Example:** User: "Calculate financial ratios for FY 2026" → Current Ratio 1.8 (healthy), Net Profit Margin 15% (strong), Debt-to-Equity 0.6 (low leverage), ROE 12% (moderate)

## Tool: assess_financial_health

- **Approval:** No — synthesis of existing data into narrative
- **Input:** `fiscal_year` (int), `period` (Optional[int] — if None, full year)
- **Output:** `health_assessment` (str — "strong", "moderate", "weak", "critical"), `score` (int — 0-100), `key_metrics` (list: name, value, rating), `strengths` (list[str]), `weaknesses` (list[str]), `recommendations` (list[str]), `summary` (str)
- **DB tables:** `journal_entries` (read — all prefixes for ratio computation), `retained_earnings` (read — net_income trend), `budgets` (read — actual vs budget variance)
- **Edge cases:** No financial data → "insufficient data" assessment with 0 score. Only one side of balance sheet (assets but no liabilities) → note partial data. Negative retained earnings → flagged as weakness. Budget table empty → budget variance skipped with note.
- **Logic:** Computes core ratios (delegates to calculate_financial_ratios logic inlined or shared), scores each ratio against fixed thresholds, computes weighted health score (0-100). Categories:
  1. Profitability (30% weight): net profit margin ≥10% = strong, ≥5% = moderate, <5% = weak, negative = critical
  2. Liquidity (25% weight): current ratio ≥1.5 = strong, ≥1.0 = moderate, <1.0 = weak
  3. Leverage (20% weight): debt-to-equity ≤1.0 = strong, ≤2.0 = moderate, >2.0 = weak
  4. Efficiency (15% weight): expense ratio ≤80% = strong, ≤90% = moderate, >90% = weak
  5. Budget variance (10% weight): within ±5% = strong, ±10% = moderate, beyond = weak (if budgets exist)
  Generates strengths (top 2 highest-scoring categories), weaknesses (bottom 2), and actionable recommendations.
- **Example:** User: "Assess financial health for FY 2026" → Score 72/100 (moderate). Strengths: liquidity (current ratio 2.1), low leverage (D/E 0.4). Weaknesses: profitability margin 4% (below target), expenses 10% over budget.

## Tool: generate_cost_cutting_recommendations

- **Approval:** No — analytical, no writes
- **Input:** `fiscal_year` (int), `period` (Optional[int]), `target_account_prefixes` (Optional[list[str]] — limit analysis to specific expense areas), `min_savings_threshold` (Optional[Decimal] — only recommend savings above this amount)
- **Output:** `total_expenses` (Decimal), `top_expense_categories` (list: name, amount, percentage, trend), `recommendations` (list: area, current_spend, potential_savings, suggestion, priority), `estimated_total_savings` (Decimal), `summary` (str)
- **DB tables:** `journal_entries` (read — expense prefixes 5/6/8), `chart_of_accounts` (read — account names for categories)
- **Edge cases:** No expenses found → empty recommendations. All expenses are essential (rent, salaries) → note limited cutting opportunities. Very small operation → savings estimates may be minimal. target_account_prefixes filters to only those categories.
- **Logic:** Identifies top expense categories by aggregating debit amounts for expense prefixes (5/6/8). For each category, computes:
  - Total spend and percentage of total expenses
  - Month-over-month trend (increasing/stable/decreasing based on variance)
  - Potential savings estimate (10-20% of discretionary categories like office expenses, travel; 0% for essential like rent, salaries)
  - Specific suggestion based on category (e.g., "Negotiate bulk discount with suppliers" for COGS, "Review subscription services" for office expenses)
  Ranks recommendations by potential_savings descending. Filters by min_savings_threshold if provided.
- **Example:** User: "Give me cost cutting ideas for 2026" → Top category: COGS 200000 (40%, stable). Savings: negotiate supplier contracts → save ~20000 (10%). Second: Office expenses 50000 (10%, increasing 15% MoM). Savings: review subscriptions → save ~7500 (15%).

## Tool: generate_custom_report

- **Approval:** **Yes** — creates structured output that may be shared externally
- **Input:** `report_title` (str), `fiscal_year` (int), `period_from` (Optional[int]), `period_to` (Optional[int]), `report_type` (str — "summary", "detailed", "comparative", "trend"), `include_sections` (Optional[list[str]] — "revenue", "expenses", "ratios", "budget_variance", "trends"), `notes` (Optional[str])
- **Output:** `report_id` (str), `report_title` (str), `report_type`, `generated_at` (date), `sections` (list: title, content, data), `summary` (str), `needs_approval` (bool)
- **DB tables:** `journal_entries` (read — all data), `budgets` (read — for variance), `chart_of_accounts` (read — account names), `retained_earnings` (read — equity data)
- **Edge cases:** No data for specified period → report with empty sections. include_sections empty → includes all sections by default. period_from > period_to → raises ValueError. comparative type with single period → single period shown with note.
- **Logic:** Builds a structured report based on report_type:
  - **summary:** Top-level figures only: total revenue, total expenses, net income, key ratios
  - **detailed:** Full breakdown by account prefix with sub-totals, transaction count
  - **comparative:** Side-by-side comparison of two periods (period_from vs period_to), shows absolute and % change
  - **trend:** Month-by-month breakdown of key metrics across all months in range
  Each section includes a title, narrative content, and structured data dict. Report_id generated as `RPT-{uuid[:8]}`.
- **Example:** User: "Generate a comparative report for H1 2026 vs H2 2026" → Report RPT-A1B2C3D4: Revenue up 12% (2.5M vs 2.8M), Expenses up 8% (1.8M vs 1.94M), Net Income up 22% (700K vs 860K).

---

## Agent-Level Behavior

- **Routing:** "advisory", "financial advice", "spending analysis", "spending pattern", "where is my money going", "financial health", "health assessment", "company health", "cost cutting", "reduce expenses", "save money", "financial ratios", "ratio analysis", "current ratio", "profit margin", "custom report", "financial report", "report generation"
- **1 human-approval tool:** `generate_custom_report`
- **4 non-approval tools:** `analyze_spending_patterns`, `calculate_financial_ratios`, `assess_financial_health`, `generate_cost_cutting_recommendations`
- **All analysis tools:** read-only from existing tables, no data mutation
