# Agent: Year-End Close & Financial Statements

**Role:** Generates the four core financial statements (trial balance, profit & loss, balance sheet, cash flow statement) and handles year-end closing, retained earnings transfer, balance carry-forward, and drafting notes to financial statements. 8 tools, 1 requiring human approval. *(Merged from two originally separate agents — Year-End Close and Financial Statements — since both are closely tied to period-end reporting.)*

---

## Account Numbering Scheme

The system uses the following prefix convention for accounts (defined in `chart_of_accounts` and used across all agents):

| Prefix | Category |
|--------|----------|
| `1xxx` | **Assets** — cash (1000), receivables (1200), fixed assets |
| `2xxx` | **Liabilities** — payables (2000), accruals |
| `3xxx` | **Equity** — capital, retained earnings |
| `4xxx` | **Revenue** — sales, service income |
| `5xxx`, `6xxx`, `8xxx` | **Expenses** — operating costs, salaries, rent |

Cash accounts specifically use prefixes: `1000`, `1001`, `1002`, `1100`.

---

## Tool: generate_trial_balance

- **Approval:** No
- **Input:** `as_of_date`
- **Output:** `accounts[]` (account_code, account_name, total_debits, total_credits, balance), `total_debits`, `total_credits`, `in_balance` (bool), `difference` (if not in balance)
- **DB tables:** `journal_entries` (read), `chart_of_accounts` (read)
- **Edge cases:** No entries for date range, all zero balances, out-of-balance detected, single-sided entries, empty database
- **Logic:** Aggregate `debit_amount` and `credit_amount` from `journal_entries` grouped by `debit_account`/`credit_account`. Sum debits and credits separately. If totals match → `in_balance=True`. Flag any account where debits != credits.
- **Example:** User: "Show trial balance as of July 2026" → list of accounts with debit/credit totals, balance status

## Tool: generate_profit_loss

- **Approval:** No
- **Input:** `from_date`, `to_date`
- **Output:** `revenue_items[]` (account, amount), `expense_items[]` (account, amount), `total_revenue`, `total_expenses`, `net_income`, `summary` (plain-language explanation)
- **DB tables:** `journal_entries` (read), `chart_of_accounts` (read)
- **Edge cases:** No revenue/expense entries, net loss (expenses > revenue), zero revenue, zero expenses
- **Logic:** Filter `journal_entries` by `credit_account.startswith("4")` for revenue (credit amounts), `debit_account.startswith(("5", "6", "8"))` for expenses (debit amounts). Group by account. Net = Revenue - Expenses.
- **Prefix verification:** Matches Agent 2's actual scheme — revenue is prefix `4`, expenses are prefixes `5`/`6`/`8` (same as used in Agent 4's `forecast_cash_flow` and Agent 2's ledger grouping).
- **Example:** User: "Generate P&L for July 2026" → revenue items, expense items, net income with explanation

## Tool: generate_balance_sheet

- **Approval:** No
- **Input:** `as_of_date`
- **Output:** `assets[]` (account, amount), `liabilities[]` (account, amount), `equity[]` (account, amount), `total_assets`, `total_liabilities`, `total_equity`, `balanced` (bool), `difference` (if not balanced)
- **DB tables:** `journal_entries` (read), `chart_of_accounts` (read), `retained_earnings` (read)
- **Edge cases:** No entries, not balanced (assets != liabilities + equity), zero equity, single account type missing
- **Logic:** Assets = accounts with prefix `1` (debit balances), Liabilities = prefix `2` (credit balances), Equity = prefix `3` (credit balances). Verify Assets = Liabilities + Equity.
- **Prefix verification:** Matches Agent 2's actual scheme — `1200` is AR (receivable/asset), `2000` is AP (payable/liability), `3000` is equity.
- **Example:** User: "Show balance sheet as of 31 July 2026" → assets, liabilities, equity with balance check

## Tool: generate_cash_flow_statement

- **Approval:** No
- **Input:** `from_date`, `to_date`
- **Output:** `operating_items[]` (description, amount), `investing_items[]` (description, amount), `financing_items[]` (description, amount), `net_operating`, `net_investing`, `net_financing`, `net_change_in_cash`, `opening_cash`, `closing_cash`
- **DB tables:** `journal_entries` (read)
- **Edge cases:** No cash entries, single activity type only, negative cash change, opening != closing + change
- **Logic:** 
  - **Operating:** Revenue entries (credit to prefix `4`) and expense entries (debit to prefixes `5`/`6`/`8`) that flow through cash accounts. Net = inflows - outflows from operations.
  - **Investing:** Entries involving fixed asset accounts (asset purchases/sales). Filter by `debit_account` or `credit_account` containing asset identifiers.
  - **Financing:** Entries involving loan accounts (prefix `2` for loans) or equity accounts (prefix `3`).
  - **Cash reconciliation:** `closing_cash = opening_cash + net_operating + net_investing + net_financing`
  - Opening/closing cash computed by aggregating `journal_entries` filtered by cash-account prefixes (`1000`, `1001`, `1002`, `1100`) — same aggregation pattern as Agent 1's `check_cash_position`. No separate `cash_position` table exists in the database.
- **Table verification:** Same pattern as Agent 1's `check_cash_position` — aggregates `journal_entries` filtered by cash-account prefixes (`1000`, `1001`, `1002`, `1100`). There is a `CashPosition` model in `db/models.py`, but Agent 1's actual tool implementation (`cash_tools.py`) queries `journal_entries` directly, not the model.
- **Example:** User: "Generate cash flow statement for July 2026" → operating/investing/financing sections with cash reconciliation

## Tool: close_fiscal_year

- **Approval:** **Yes** — irreversible, closes books permanently
- **Input:** `fiscal_year`, `closing_date`, `confirm` (bool, must be true)
- **Output:** `status`, `closing_entries_created` (count), `revenue_closed`, `expenses_closed`, `net_income_transferred`, `message`
- **DB tables:** `journal_entries` (write), `fiscal_year_close` (write)
- **Edge cases:** Year already closed (`ValueError`), no revenue/expense entries to close, zero net income, partial-year close rejected
- **Logic:** Create closing journal entries: (1) Close all revenue accounts to Income Summary, (2) Close all expense accounts to Income Summary, (3) Close Income Summary to Retained Earnings. Mark all entries with status "closing". Prevent double-closing by checking `fiscal_year_close` table.
- **Example:** User: "Close fiscal year 2026" → creates closing entries, transfers net income, locks year

## Tool: transfer_retained_earnings

- **Approval:** No — one-line formula, system logic, not an AI decision
- **Input:** `fiscal_year`
- **Output:** `fiscal_year`, `beginning_retained_earnings`, `net_income`, `dividends` (if any), `ending_retained_earnings`, `journal_entry_id`
- **DB tables:** `journal_entries` (read/write), `retained_earnings` (read/write)
- **Edge cases:** No prior retained earnings, net loss instead of income, negative retained earnings, first year of operations
- **Logic:** Ending RE = Beginning RE + Net Income − Dividends. Create journal entry debiting Income Summary, crediting Retained Earnings.
- **Example:** User: "Calculate retained earnings for FY 2026" → shows retained earnings movement

## Tool: carry_forward_balances

- **Approval:** No — backend calculation, system logic, not an AI decision
- **Input:** `from_fiscal_year`, `to_fiscal_year`, `closing_date`
- **Output:** `accounts_carried_forward` (count), `new_balances[]` (account_code, account_name, closing_balance, opening_balance_next_year), `status`
- **DB tables:** `journal_entries` (read), `chart_of_accounts` (read)
- **Edge cases:** No balance sheet accounts, all zero balances, first-time carry-forward, permanent accounts only
- **Logic:** Copy balance sheet account balances (assets, liabilities, equity — prefixes `1`, `2`, `3`) as opening entries for new fiscal year. Revenue/expense accounts (prefixes `4`, `5`, `6`, `8`) start at zero.
- **Example:** User: "Carry forward balances from 2026 to 2027" → opening balances created for new year

## Tool: draft_notes_to_financials

- **Approval:** No — AI-generated draft, human reviews before attaching to final statements
- **Input:** `fiscal_year`, `note_types[]` optional (accounting_policies, revenue_recognition, depreciation_method, commitments, contingencies)
- **Output:** `notes[]` (title, content, source_data references), `disclaimer`
- **DB tables:** `journal_entries` (read), `fixed_assets` (read), `chart_of_accounts` (read), `contacts` (read)
- **Edge cases:** No data for requested note type, first-year notes, missing accounting policy info, multiple depreciation methods in use
- **Logic:** Generate structured note content from actual data. Accounting policies note describes depreciation methods, revenue recognition, etc. from actual system settings. Commitments note pulls from loan data. Contingencies note flags provision-like entries.
- **Example:** User: "Draft notes to financial statements for FY 2026" → structured notes with data references

---

## Agent-Level Behavior

- **Routing:** "trial balance", "profit and loss", "P&L", "income statement", "balance sheet", "financial position", "cash flow", "cash flow statement", "year-end close", "close fiscal year", "retained earnings", "carry forward", "notes to financials", "financial statements", "closing entries"
- **1 human-approval tool:** `close_fiscal_year` — irreversible book closure, must be confirmed
- **7 backend-calculation / AI-review tools:** trial balance, P&L, balance sheet, cash flow statement, retained earnings, carry forward, notes to financials — pure queries with AI explanation
- **Dependencies:**
  - Requires `chart_of_accounts` table with proper account prefix categorization (1=assets, 2=liabilities, 3=equity, 4=revenue, 5/6/8=expenses)
  - Requires `journal_entries` with proper debit/credit account coding
  - `generate_cash_flow_statement` uses same aggregation as Agent 1's `check_cash_position` — queries `journal_entries` filtered by cash-account prefixes (`1000`, `1001`, `1002`, `1100`). No separate `cash_position` table in the database.
  - Requires Agents 1-4 to be fully operational (this is the final period-end agent before statements)
- **Statement order:** Trial balance → P&L → Balance Sheet → Cash Flow (trial balance must balance before statements can be generated)

## New DB Tables Needed

| Table | Purpose |
|-------|---------|
| `retained_earnings` | Track retained earnings balance per fiscal year |
| `fiscal_year_close` | Track which fiscal years have been closed (prevent double-close) |

## Spec Verification Summary

The following checks were performed against existing Agent 1/2 specs and implementation:

| Check | Result |
|-------|--------|
| Prefix scheme (1=assets, 2=liabilities, 3=equity, 4=revenue, 5/6/8=expenses) | ✅ Matches Agent 2's actual usage: `2000` for AP (liabilities), `1200` for AR (assets), `4` for revenue, `5`/`6`/`8` for expenses |
| Cash source — `check_cash_position` in `cash_tools.py` | ✅ Both use aggregated `journal_entries` filtered by cash prefixes (`1000`, `1001`, `1002`, `1100`). No separate `cash_position` table. |
| Equity accounts (prefix `3xxx`) exist in Agent 2's data | ✅ Every business type in `_CHARTS` has `3000` (Owner's Equity) or `3000`/`3100` (Retained Earnings). Test data uses `3000-Equity` in journal entries. |
| `carry_forward_balances` approval = No | ✅ Fixed (was incorrectly marked Yes) |
| Approval count = 1 (`close_fiscal_year` only) | ✅ Fixed (was incorrectly 2) |
