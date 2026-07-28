# Agent: Ledger & Master Data

**Role:** Handles bookkeeping, journal entries, general ledger, master data (vendors/customers), payroll, fixed assets, and chart of accounts. The Orchestrator calls this agent as a tool (Agents-as-Tools pattern — not a handoff). It has 8 tools. 2 require human approval.

---

## Tool: create_journal_entry

- **What it does / how it works:** Creates a journal entry with specific debit and credit accounts. Unlike `record_transaction_nl` which parses NL, this tool takes exact account names and amounts. Validates that debits = credits before saving.
- **Approval required:** No
- **Input schema:**
```python
class CreateJournalEntryInput(BaseModel):
    entry_id: str | None = None
    description: str = Field(..., min_length=3, max_length=500)
    posted_date: date = Field(default_factory=date.today)
    reference: str | None = None
    debit_account: str = Field(..., description="Full account code+name e.g. '6000-Office Rent'")
    debit_amount: Decimal = Field(gt=0)
    credit_account: str = Field(..., description="Full account code+name e.g. '1000-Cash'")
    credit_amount: Decimal = Field(gt=0)
    status: str = "posted"
```
- **Output schema:**
```python
class CreateJournalEntryOutput(BaseModel):
    entry_id: str
    description: str
    posted_date: date
    reference: str | None
    debit_account: str
    debit_amount: Decimal
    credit_account: str
    credit_amount: Decimal
    status: str
```
- **DB tables touched:** `journal_entries` (write)
- **Edge cases:**
  1. Debits don't equal credits → raises `ValueError` with message "Debit and credit amounts must balance"
  2. Duplicate entry_id provided → raises `ValueError` with message "Entry ID already exists"
  3. Amount is zero or negative → Pydantic validation catches (gt=0)
  4. Description too short → Pydantic min_length validation catches
- **Example:**
  - User: "Create a journal entry debiting office rent 50000 and crediting cash"
  - Output: `{"entry_id": "JE-20260729-003", "description": "Office rent payment", "posted_date": "2026-07-29", "reference": null, "debit_account": "6000-Office Rent", "debit_amount": "50000.00", "credit_account": "1000-Cash", "credit_amount": "50000.00", "status": "posted"}`

---

## Tool: get_general_ledger

- **What it does / how it works:** Queries all posted journal entries, groups them by account (both debit and credit sides), and returns a ledger view showing opening balance, transactions, and closing balance per account.
- **Approval required:** No
- **Input schema:**
```python
class GetGeneralLedgerInput(BaseModel):
    from_date: date = Field(default_factory=lambda: date.today().replace(day=1))
    to_date: date = Field(default_factory=date.today)
    account_code_prefix: str | None = Field(default=None, description="Filter by account prefix e.g. '6000' for expenses")
```
- **Output schema:**
```python
class LedgerAccountEntry(BaseModel):
    account: str
    total_debits: Decimal
    total_credits: Decimal
    net_movement: Decimal

class GetGeneralLedgerOutput(BaseModel):
    from_date: date
    to_date: date
    accounts: list[LedgerAccountEntry]
    total_debits: Decimal
    total_credits: Decimal
```
- **DB tables touched:** `journal_entries` (read)
- **Edge cases:**
  1. No entries in date range → empty accounts list with zero totals
  2. `from_date` after `to_date` → raises ValueError
  3. Account prefix provided but no matches → empty list
- **Example:**
  - User: "Show me the general ledger for July"
  - Output: `{"from_date": "2026-07-01", "to_date": "2026-07-29", "accounts": [{"account": "1000-Cash", "total_debits": "500000.00", "total_credits": "120000.00", "net_movement": "380000.00"}], "total_debits": "500000.00", "total_credits": "120000.00"}`

---

## Tool: suggest_chart_of_accounts

- **What it does / how it works:** Uses LLM to suggest a chart of accounts structure based on business type (e.g., "retail shop", "freelance consultant"). Returns a suggestion that the user reviews and approves before saving. Nothing is written to DB until approved.
- **Approval required:** Yes
- **Input schema:**
```python
class SuggestChartOfAccountsInput(BaseModel):
    business_type: str = Field(..., min_length=3, max_length=100, description="Type of business e.g. 'retail', 'freelance', 'manufacturing'")
    description: str | None = Field(default=None, max_length=500, description="Additional context about the business")
```
- **Output schema:**
```python
class SuggestedAccountItem(BaseModel):
    account_code: str
    account_name: str
    account_type: str  # "asset", "liability", "equity", "revenue", "expense"
    description: str | None

class SuggestChartOfAccountsOutput(BaseModel):
    suggestion_id: str
    business_type: str
    accounts: list[SuggestedAccountItem]
    needs_approval: bool = True
    status: str = "suggested_pending_approval"
```
- **DB tables touched:** None (read-only suggestion until approved). On approval: `chart_of_accounts` (write)
- **Edge cases:**
  1. Business type too generic → returns standard default chart with note
  2. Business type unrecognized → returns generic chart with "review required" flag
  3. Same chart already exists and is approved → returns existing chart with `status: "already_exists"`
- **Example:**
  - User: "Setup chart of accounts for my retail clothing store"
  - Output: `{"suggestion_id": "COA-20260729-001", "business_type": "retail clothing store", "accounts": [{"account_code": "1000", "account_name": "Cash", "account_type": "asset"}, ...], "needs_approval": true, "status": "suggested_pending_approval"}`

---

## Tool: get_ap_subledger

- **What it does / how it works:** Queries journal entries for accounts payable (AP) accounts (typically account codes starting with "2000" for liabilities). Shows what the business owes to vendors/suppliers.
- **Approval required:** No
- **Input schema:**
```python
class GetAPSubledgerInput(BaseModel):
    from_date: date = Field(default_factory=lambda: date.today().replace(day=1))
    to_date: date = Field(default_factory=date.today)
    vendor_contact_id: str | None = Field(default=None, description="Filter by specific vendor")
```
- **Output schema:**
```python
class APEntryItem(BaseModel):
    entry_id: str
    date: date
    description: str
    amount: Decimal
    vendor: str | None
    status: str

class GetAPSubledgerOutput(BaseModel):
    from_date: date
    to_date: date
    entries: list[APEntryItem]
    total_outstanding: Decimal
```
- **DB tables touched:** `journal_entries` (read), `contacts` (read for vendor names)
- **Edge cases:**
  1. No AP entries → empty list with zero total
  2. Vendor filter applied but no entries → empty list
  3. Date range has no AP activity → empty list
- **Example:**
  - User: "What do we owe to vendors this month?"
  - Output: `{"from_date": "2026-07-01", "to_date": "2026-07-29", "entries": [...], "total_outstanding": "125000.00"}`

---

## Tool: get_ar_subledger

- **What it does / how it works:** Queries journal entries for accounts receivable (AR) accounts (typically account codes starting with "1200"). Shows what customers owe the business.
- **Approval required:** No
- **Input schema:**
```python
class GetARSubledgerInput(BaseModel):
    from_date: date = Field(default_factory=lambda: date.today().replace(day=1))
    to_date: date = Field(default_factory=date.today)
    customer_contact_id: str | None = Field(default=None, description="Filter by specific customer")
```
- **Output schema:**
```python
class AREntryItem(BaseModel):
    entry_id: str
    date: date
    description: str
    amount: Decimal
    customer: str | None
    status: str

class GetARSubledgerOutput(BaseModel):
    from_date: date
    to_date: date
    entries: list[AREntryItem]
    total_outstanding: Decimal
```
- **DB tables touched:** `journal_entries` (read), `contacts` (read for customer names)
- **Edge cases:** Same pattern as AP subledger
- **Example:**
  - User: "Show me outstanding receivables"
  - Output: `{"from_date": "2026-07-01", "to_date": "2026-07-29", "entries": [...], "total_outstanding": "200000.00"}`

---

## Tool: get_payroll_ledger

- **What it does / how it works:** Queries payroll entries for a given period. Shows salary, deductions, and net pay for each employee.
- **Approval required:** No
- **Input schema:**
```python
class GetPayrollLedgerInput(BaseModel):
    from_date: date = Field(default_factory=lambda: date.today().replace(day=1))
    to_date: date = Field(default_factory=date.today)
    employee_name: str | None = Field(default=None, description="Filter by employee name")
```
- **Output schema:**
```python
class PayrollEntryItem(BaseModel):
    entry_id: str
    employee_name: str
    salary_amount: Decimal
    deductions: Decimal
    net_pay: Decimal
    period_start: date
    period_end: date

class GetPayrollLedgerOutput(BaseModel):
    from_date: date
    to_date: date
    entries: list[PayrollEntryItem]
    total_salary: Decimal
    total_deductions: Decimal
    total_net_pay: Decimal
```
- **DB tables touched:** `payroll_entries` (read)
- **Edge cases:**
  1. No payroll entries for period → empty list with zeros
  2. Employee filter no match → empty list
  3. Deductions exceed salary (invalid data) → returns data with warning flag
- **Example:**
  - User: "Show payroll for July"
  - Output: `{"from_date": "2026-07-01", "to_date": "2026-07-29", "entries": [{"entry_id": "PR-001", "employee_name": "Ali", "salary_amount": "100000.00", "deductions": "15000.00", "net_pay": "85000.00", ...}], "total_salary": "100000.00", "total_deductions": "15000.00", "total_net_pay": "85000.00"}`

---

## Tool: categorize_fixed_asset

- **What it does / how it works:** User describes a new asset (e.g., "bought delivery truck for 2M"). LLM suggests a depreciation category, useful life, and method. The user reviews and approves before saving.
- **Approval required:** Yes
- **Input schema:**
```python
class CategorizeFixedAssetInput(BaseModel):
    asset_name: str = Field(..., min_length=2, max_length=200)
    purchase_cost: Decimal = Field(gt=0)
    purchase_date: date = Field(default_factory=date.today)
    asset_category: str | None = Field(default=None, description="Optional: 'vehicle', 'machinery', 'furniture', 'computer', 'building', 'other'")
```
- **Output schema:**
```python
class CategorizeFixedAssetOutput(BaseModel):
    asset_id: str
    asset_name: str
    purchase_cost: Decimal
    suggested_useful_life: int  # years
    suggested_depreciation_method: str  # "straight_line", "declining_balance", "sum_of_years"
    suggested_residual_value: Decimal
    needs_approval: bool = True
    status: str = "suggested_pending_approval"
```
- **DB tables touched:** `fixed_assets` (write after approval)
- **Edge cases:**
  1. Cost is less than residual value → raises ValueError
  2. Useful life suggested < 1 year → defaults to 1 year with note
  3. Same asset already exists (same name + cost) → returns existing with status
- **Example:**
  - User: "We bought a delivery truck for 2,000,000"
  - Output: `{"asset_id": "FA-20260729-001", "asset_name": "Delivery Truck", "purchase_cost": "2000000.00", "suggested_useful_life": 10, "suggested_depreciation_method": "straight_line", "suggested_residual_value": "200000.00", "needs_approval": true, "status": "suggested_pending_approval"}`

---

## Tool: manage_contact

- **What it does / how it works:** Adds, updates, or deletes vendor/customer contacts via natural language. Searches by name to avoid duplicates. Shared between Daily Entry and Ledger agents.
- **Approval required:** No
- **Input schema:**
```python
class ManageContactInput(BaseModel):
    action: str = Field(..., description="'add', 'update', 'delete', or 'search'")
    contact_type: str = Field(..., description="'vendor' or 'customer'")
    contact_name: str = Field(..., min_length=2, max_length=200)
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    tax_id: str | None = None
```
- **Output schema:**
```python
class ManageContactOutput(BaseModel):
    contact_id: str
    contact_name: str
    contact_type: str
    action_performed: str
    message: str | None
```
- **DB tables touched:** `contacts` (read/write)
- **Edge cases:**
  1. Adding duplicate contact name + type → returns existing with `message: "Contact already exists"`
  2. Deleting non-existent contact → raises ValueError
  3. Search with partial name → returns fuzzy matches sorted by relevance
  4. Email format invalid → Pydantic email validation catches
- **Example:**
  - User: "Add Abdullah General Store as a vendor, phone 0300-1234567"
  - Output: `{"contact_id": "CNT-001", "contact_name": "Abdullah General Store", "contact_type": "vendor", "action_performed": "added", "message": null}`

---

## Agent-Level Behavior

- **Routing:** Orchestrator routes to this agent when user mentions: "journal entry", "general ledger", "chart of accounts", "AP", "AR", "payroll", "payable", "receivable", "vendor", "customer", "contact", "fixed asset", "depreciation"
- **Downstream effects:**
  - `create_journal_entry` updates the general ledger and affects cash position (Agent 1's tool sees new journal entries)
  - `manage_contact` creates vendor/customer records that are used by Agent 1's `check_bank_transactions` and `manage_petty_cash`
  - `suggest_chart_of_accounts` (after approval) creates the account structure used by all other agents
- **Model fallback:** Same as Agent 1 — Groq qwen/qwen3.6-27b primary → llama-3.1-8b-instant fallback → Cerebras gemma-4-31b last resort
- **Shared tool:** `manage_contact` is shared between Daily Entry and Ledger agents — both can call it
