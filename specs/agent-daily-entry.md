# Agent: Daily Entry

**Role:** Handles the user's daily cash and transaction operations. The Orchestrator calls this agent as a tool (Agents-as-Tools pattern — not a handoff). It has 5 tools.

---

## Tool: check_cash_position

- **What it does / how it works:** Queries the `cash_position` table (or `journal_entries` aggregated by account) for the current date's opening balance plus all posted transactions up to now. Returns the live cash balance as a deterministic sum — no AI reasoning, just a DB query wrapped in Pydantic output.
- **Approval required:** No
- **Input schema:**

```python
class CheckCashPositionInput(BaseModel):
    as_of_date: date = Field(default_factory=date.today, description="Date to check cash position for")
    account_id: str | None = Field(default=None, description="Specific cash account ID; if None, sums all cash accounts")
```

- **Output schema:**



```python
class CheckCashPositionOutput(BaseModel):
    account_id: str
    account_name: str
    opening_balance: Decimal
    total_debits: Decimal
    total_credits: Decimal
    closing_balance: Decimal
    currency: str = "PKR"
    as_of_date: date
```

- **DB tables touched:** `cash_position` (read), `journal_entries` (read)
- **Edge cases:**
  1. No transactions exist for the date → returns opening balance only, zero debits/credits
  2. Account ID provided but does not exist in DB → raises `ValueError` with message "Account not found"
  3. Opening balance is negative (overdrawn) → returns the negative value with a `warning` flag set to true
  4. Multiple cash accounts exist and no account_id given → sums all cash accounts and returns a consolidated result with per-account breakdown in `details`
- **Example:**
  - User: "What's our cash position right now?"
  - Output: `{"account_id": "CA-001", "account_name": "Main Cash", "opening_balance": "500000.00", "total_debits": "120000.00", "total_credits": "45000.00", "closing_balance": "575000.00", "currency": "PKR", "as_of_date": "2026-07-28"}`

---

## Tool: record_transaction_nl

- **What it does / how it works:** Accepts a plain-English transaction string (e.g., "Paid office rent 50000 for July"), parses it to extract amount, description, date, and account mappings, then creates a journal entry with matching debit and credit sides using fixed accounting rules (expense accounts debit, cash/bank accounts credit). Stores the entry in `journal_entries` and returns the created entry ID.
- **Approval required:** No
- **Input schema:**

```python
class RecordTransactionNLInput(BaseModel):
    description: str = Field(..., min_length=5, max_length=500, description="Plain-English transaction description")
    posted_date: date = Field(default_factory=date.today, description="Transaction date")
    reference: str | None = Field(default=None, description="Optional invoice/receipt reference number")
```

- **Output schema:**

```python
class RecordTransactionNLOutput(BaseModel):
    entry_id: str
    description: str
    posted_date: date
    reference: str | None
    debit_account: str
    debit_amount: Decimal
    credit_account: str
    credit_amount: Decimal
    status: str = "posted"
```

- **DB tables touched:** `journal_entries` (write), `accounts` (read — to resolve account IDs from names)
- **Edge cases:**
  1. Description mentions an account name not in the chart of accounts → returns error with `unknown_account` field listing the unrecognized term
  2. Amount cannot be parsed from the description → raises `ValueError` with message "No valid amount found in description"
  3. Debit and credit amounts don't balance after parsing → raises `ValueError` with message "Transaction does not balance"
  4. Same transaction (same amount, same description, same date) already exists → returns the existing entry_id with `status: "duplicate_ignored"`
- **Example:**
  - User: "Add office rent 50000 for July"
  - Output: `{"entry_id": "JE-20260728-001", "description": "Office rent for July", "posted_date": "2026-07-28", "reference": null, "debit_account": "6000-Office Rent", "debit_amount": "50000.00", "credit_account": "1000-Cash", "credit_amount": "50000.00", "status": "posted"}`

---

## Tool: process_receipt_image

- **What it does / how it works:** Accepts an uploaded receipt image, extracts the vendor name, total amount, and date using the LLM's vision capability, then returns a structured extraction result. The amount is validated against a minimum threshold (e.g., > 0). The result is returned as a suggestion — it does NOT write to the database until approved.
- **Approval required:** Yes
- **Input schema:**

```python
class ProcessReceiptImageInput(BaseModel):
    image_data: str = Field(..., description="Base64-encoded receipt image")
    image_filename: str = Field(..., description="Original filename of the receipt image")
    suggested_account: str | None = Field(default=None, description="Optional account to post to (e.g., 'Office Rent')")
```

- **Output schema:**

```python
class ProcessReceiptImageOutput(BaseModel):
    extraction_id: str
    vendor_name: str | None
    total_amount: Decimal | None
    date: date | None
    currency: str = "PKR"
    confidence: float = Field(ge=0.0, le=1.0, description="Extraction confidence score")
    needs_approval: bool = True
    status: str = "extracted_pending_approval"
```

- **DB tables touched:** `receipt_extractions` (write — stores the extraction result for audit trail)
- **Edge cases:**
  1. Image is not a receipt (e.g., a photo of a person) → `confidence` below 0.3, returns `status: "unrecognized_image"` with `vendor_name: null`
  2. Receipt is blurry or partially cropped → `confidence` between 0.3–0.6, returns partial extraction with `vendor_name` and `total_amount` marked as `uncertain`
  3. Amount is zero or negative → raises `ValueError` with message "Invalid receipt amount"
  4. Image file is too large (>10MB) or wrong format (not PNG/JPEG) → raises `ValueError` with message "Unsupported image format or size"
- **Example:**
  - User uploads a receipt photo of a grocery store purchase
  - Output: `{"extraction_id": "REC-20260728-001", "vendor_name": "Abdullah Super Market", "total_amount": "3500.00", "date": "2026-07-27", "currency": "PKR", "confidence": 0.92, "needs_approval": true, "status": "extracted_pending_approval"}`

---

## Tool: check_bank_transactions

- **What it does / how it works:** Queries the `bank_transactions` table for transactions matching optional filters (date range, bank account ID, transaction type). Returns a list of matching bank transactions with their status (cleared, pending, reconciled). Uses deterministic DB queries — no AI reasoning.
- **Approval required:** No
- **Input schema:**

```python
class CheckBankTransactionsInput(BaseModel):
    account_id: str | None = Field(default=None, description="Bank account ID to filter; if None, returns all bank accounts")
    from_date: date = Field(default_factory=lambda: date.today().replace(day=1), description="Start date (inclusive)")
    to_date: date = Field(default_factory=date.today, description="End date (inclusive)")
    status: str | None = Field(default=None, description="Filter by transaction status: 'cleared', 'pending', or 'reconciled'")
    limit: int = Field(default=50, ge=1, le=500, description="Maximum number of transactions to return")
```

- **Output schema:**

```python
class BankTransactionItem(BaseModel):
    transaction_id: str
    date: date
    description: str
    amount: Decimal
    type: str  # "debit" or "credit"
    status: str  # "cleared", "pending", "reconciled"
    reference: str | None
    balance_after: Decimal

class CheckBankTransactionsOutput(BaseModel):
    account_id: str | None
    account_name: str | None
    transactions: list[BankTransactionItem]
    total_count: int
    total_debits: Decimal
    total_credits: Decimal
    period_from: date
    period_to: date
```

- **DB tables touched:** `bank_transactions` (read), `bank_accounts` (read)
- **Edge cases:**
  1. No transactions found for the date range → returns empty list with `total_count: 0` and zero totals
  2. Account ID provided but does not exist → raises `ValueError` with message "Bank account not found"
  3. `from_date` is after `to_date` → raises `ValueError` with message "from_date must be before or equal to to_date"
  4. `limit` is reached before all transactions are returned → includes `truncated: true` in output with the actual count available
- **Example:**
  - User: "Show me bank transactions for the last week"
  - Output: `{"account_id": "BA-001", "account_name": "HBL Business Account", "transactions": [{"transaction_id": "BT-001", "date": "2026-07-25", "description": "Customer payment - Invoice INV-045", "amount": "150000.00", "type": "credit", "status": "cleared", "reference": "INV-045", "balance_after": "2350000.00"}], "total_count": 1, "total_debits": "0.00", "total_credits": "150000.00", "period_from": "2026-07-21", "period_to": "2026-07-28"}`

---

## Tool: manage_petty_cash

- **What it does / how it works:** Handles small cash transactions — recording a petty cash expenditure, adding a new petty cash fund, or triggering a replenishment reminder when the fund balance drops below a threshold. Uses the `petty_cash_funds` and `petty_cash_transactions` tables. Returns the updated fund balance and any replenishment alerts.
- **Approval required:** No
- **Input schema:**

```python
class ManagePettyCashInput(BaseModel):
    action: str = Field(..., description="Action to perform: 'expense', 'add_fund', or 'check_replenishment'")
    fund_id: str | None = Field(default=None, description="Petty cash fund ID; required for 'expense' and 'check_replenishment'")
    amount: Decimal | None = Field(default=None, ge=0.01, description="Amount for expense or add_fund actions")
    description: str | None = Field(default=None, max_length=200, description="Description of the petty cash expense")
    paid_by: str | None = Field(default=None, description="Person who paid or received the petty cash")
    replenishment_threshold: Decimal = Field(default=5000.00, ge=100.00, description="Minimum balance before triggering replenishment reminder")
```

- **Output schema:**

```python
class PettyCashTransactionItem(BaseModel):
    transaction_id: str
    fund_id: str
    action: str  # "expense" or "add_fund"
    amount: Decimal
    description: str | None
    paid_by: str | None
    date: date
    remaining_balance: Decimal

class ManagePettyCashOutput(BaseModel):
    fund_id: str
    fund_name: str
    current_balance: Decimal
    threshold: Decimal
    needs_replenishment: bool
    transactions: list[PettyCashTransactionItem]
    message: str | None  # e.g., "Replenishment recommended — balance below threshold"
```

- **DB tables touched:** `petty_cash_funds` (read/write), `petty_cash_transactions` (write)
- **Edge cases:**
  1. Expense amount exceeds current fund balance → `needs_replenishment` set to true, transaction still recorded with `warning: "Balance is now negative — replenish immediately"`
  2. `action` is "check_replenishment" but fund balance is above threshold → `needs_replenishment: false` with `message: "Balance is sufficient"`
  3. `fund_id` does not exist → raises `ValueError` with message "Petty cash fund not found"
  4. `action` is "add_fund" but amount is zero → raises `ValueError` with message "Add amount must be greater than zero"
- **Example:**
  - User: "Record a petty cash expense of 2000 for office supplies paid by Ali"
  - Output: `{"fund_id": "PC-001", "fund_name": "Main Petty Cash", "current_balance": "3000.00", "threshold": "5000.00", "needs_replenishment": true, "transactions": [{"transaction_id": "PCT-001", "fund_id": "PC-001", "action": "expense", "amount": "2000.00", "description": "Office supplies", "paid_by": "Ali", "date": "2026-07-28", "remaining_balance": "3000.00"}], "message": "Replenishment recommended — balance below threshold"}`

---

## Agent-Level Behavior

- **Routing:** The Orchestrator routes to this agent when the user's intent matches any of these patterns: "cash position", "check cash", "record transaction", "add expense", "upload receipt", "bank transactions", "petty cash", "small cash", "replenish petty cash"
- **Downstream effects:**
  - `record_transaction_nl` triggers the Ledger & Master Data agent's `create_journal_entry` tool to post the entry to the general ledger
  - `process_receipt_image` (after approval) triggers `record_transaction_nl` to create a journal entry from the extracted data
  - `manage_petty_cash` (when balance goes negative) triggers a notification to the Advisory agent's `assess_financial_health` tool
- **Model fallback:** If Cerebras's daily token quota is exhausted mid-conversation with this agent, the Orchestrator transparently switches to Groq (Llama 4 Scout) for the remainder of the session. The user sees no interruption — the agent continues processing with the fallback model. If both providers are unavailable, the agent returns a `model_unavailable` error with a retry suggestion.
