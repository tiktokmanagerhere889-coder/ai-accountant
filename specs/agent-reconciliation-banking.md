# Agent: Reconciliation & Banking

**Role:** Handles bank reconciliation, accrual entries, vendor/customer statement reconciliation, cheque clearing tracking, LC/bank guarantee tracking, and bank charges reconciliation. The Orchestrator calls this agent as a tool (Agents-as-Tools pattern). It has 7 tools. 5 require human approval.

---

## Tool: run_bank_reconciliation

- **What it does / how it works:** Takes bank statement lines from `bank_transactions` and matches them against internal `journal_entries`. Matching algorithm uses confidence scoring: exact amount+reference=95% confidence, amount+date proximity(3 days)=70%, amount only=50%. Unmatched items on either side are flagged for manual review. Returns suggested matches — nothing is saved until human approves.
- **Approval required:** Yes
- **Input schema:**
```python
class RunBankReconciliationInput(BaseModel):
    bank_account_id: str
    statement_date: date
    from_date: date
    to_date: date
```
- **Output schema:**
```python
class ReconciliationMatchItem(BaseModel):
    bank_txn_id: str
    journal_entry_id: str | None
    confidence: float  # 0.0 to 1.0
    match_type: str  # "exact", "amount_date", "amount_only", "unmatched"
    status: str  # "suggested", "confirmed"

class UnmatchedBankItem(BaseModel):
    bank_txn_id: str
    date: date
    description: str
    amount: Decimal
    reason: str  # "no_journal_match", "duplicate_journal"

class RunBankReconciliationOutput(BaseModel):
    run_id: str
    bank_account_id: str
    statement_date: date
    matches: list[ReconciliationMatchItem]
    unmatched_bank: list[UnmatchedBankItem]
    total_matched: int
    total_unmatched: int
    status: str = "pending_approval"
```
- **DB tables touched:** `bank_transactions` (read), `journal_entries` (read), `reconciliation_runs` (write), `reconciliation_matches` (write)
- **Edge cases:**
  1. Empty bank statement for period → returns empty match list with informative note
  2. No matching journal entries found → all bank items listed as unmatched with "no_journal_match"
  3. Multiple possible matches for one bank line → returns top 3 with descending confidence scores
  4. Amount match with 3+ day date gap → confidence drops to 50% flagged for human review
  5. Bank line amount differs from journal by <1% → suggests as potential match with "partial" flag
  6. Previous reconciliation already exists for this period+account → returns existing with message
- **Example:**
  - User: "Run bank reconciliation for HBL Current account for July 2026"
  - Output: `{"run_id": "REC-202607-001", "bank_account_id": "BA-001", "matches": [{"bank_txn_id": "BT-001", "journal_entry_id": "JE-20260725-001", "confidence": 0.95, "match_type": "exact", "status": "suggested"}], "unmatched_bank": [{"bank_txn_id": "BT-002", "description": "Unknown debit", "amount": "1500.00", "reason": "no_journal_match"}], "total_matched": 1, "total_unmatched": 1, "status": "pending_approval"}`

---

## Tool: post_accrual_entry

- **What it does / how it works:** Suggests month-end accrual entries based on accrual type (salary/utilities/rent). Calculates prorated amounts for partial periods. Returns a suggested journal entry — human must approve before posting to `journal_entries`.
- **Approval required:** Yes
- **Input schema:**
```python
class PostAccrualEntryInput(BaseModel):
    accrual_type: str = Field(..., description="'salary', 'utilities', 'rent', 'other'")
    amount: Decimal = Field(gt=0)
    description: str
    period_date: date
    debit_account: str | None = None
    credit_account: str | None = None
    partial_period_days: int | None = Field(default=None, ge=1, le=31)
```
- **Output schema:**
```python
class PostAccrualEntryOutput(BaseModel):
    accrual_id: str
    entry_id: str | None
    accrual_type: str
    amount: Decimal
    debit_account: str
    credit_account: str
    period_date: date
    needs_approval: bool = True
    status: str = "pending_approval"
    warning: str | None = None
```
- **DB tables touched:** `journal_entries` (write after approval)
- **Edge cases (minimum 6):**
  1. Accrual already posted for this period+type → warns with `accrual_id` and message: "already exists"
  2. Zero or negative amount → Pydantic gt=0 catches
  3. Back-dated accrual (period more than 30 days past) → warning: "confirm retroactive entry"
  4. Partial period (e.g., mid-month start) → prorates: `prorated = amount * partial_period_days / 30`
  5. Account type mismatch (e.g., salary credit to revenue account) → warning: "unusual account pairing"
  6. Duplicate same amount+type+period within 24h → warning: "possible duplicate entry"
- **Example:**
  - User: "Post accrual entry for salaries 150000 for July"
  - Output: `{"accrual_id": "ACR-202607-001", "entry_id": null, "accrual_type": "salary", "amount": "150000.00", "debit_account": "6100-Salary", "credit_account": "2000-Accrued Liabilities", "period_date": "2026-07-31", "needs_approval": true, "status": "pending_approval", "warning": null}`

---

## Tool: reconcile_vendor_statement

- **What it does / how it works:** Takes vendor statement lines and compares against internal AP records in `journal_entries`. Matches by reference number, amount, and date. Reports matched items, differences, and unmatched items on each side.
- **Approval required:** Yes
- **Input schema:**
```python
class VendorStatementLine(BaseModel):
    reference: str
    date: date
    amount: Decimal
    description: str | None = None

class ReconcileVendorStatementInput(BaseModel):
    vendor_contact_id: str
    statement_date: date
    from_date: date
    to_date: date
    statement_lines: list[VendorStatementLine]
```
- **Output schema:**
```python
class StatementMatchItem(BaseModel):
    statement_ref: str
    journal_entry_id: str
    amount_match: bool
    date_match: bool
    status: str  # "matched", "partial", "unmatched"

class StatementDifferenceItem(BaseModel):
    reference: str
    statement_amount: Decimal
    internal_amount: Decimal
    difference: Decimal
    reason: str | None

class ReconcileVendorStatementOutput(BaseModel):
    reconciliation_id: str
    vendor_contact_id: str
    matches: list[StatementMatchItem]
    differences: list[StatementDifferenceItem]
    total_difference: Decimal
    status: str = "pending_approval"
```
- **DB tables touched:** `journal_entries` (read), `contacts` (read)
- **Edge cases (minimum 6):**
  1. Statement line with no matching reference in internal records → flags as missing entry
  2. Internal record with no matching statement line → flags as unrecorded payment
  3. Same reference but different amounts → creates difference item with exact variance
  4. Vendor contact_id not found → raises ValueError with name suggestion
  5. Statement date outside from_date-to_date range → returns empty with date guidance
  6. Partial payment matches one statement line → matches partial, flags remainder
- **Example:**
  - User: "Reconcile statement from Abdullah General Store for July"
  - Output: `{"reconciliation_id": "VSR-202607-001", "vendor_contact_id": "CNT-001", "matches": [...], "differences": [...], "total_difference": "5000.00", "status": "pending_approval"}`

---

## Tool: reconcile_customer_statement

- **What it does / how it works:** Same as vendor reconciliation but for customers/AR side. Matches customer statement lines against internal AR records.
- **Approval required:** Yes
- **Input schema:** Same pattern as vendor with `customer_contact_id` instead of `vendor_contact_id`
- **Output schema:** Same structure as vendor
- **DB tables touched:** `journal_entries` (read), `contacts` (read)
- **Edge cases (minimum 6):** Same 6 as vendor but on AR side
- **Example:**
  - User: "Reconcile customer statement for ABC Trading for July"
  - Output: `{"reconciliation_id": "CSR-202607-001", "customer_contact_id": "CNT-002", "matches": [...], "differences": [...], "total_difference": "0.00", "status": "pending_approval"}`

---

## Tool: track_cheque_clearing

- **What it does / how it works:** Tracks cheque lifecycle: issue (record new cheque), clear (mark as cleared), bounce (mark as bounced), reconcile (mark as reconciled), status (check current state). Operates via natural-language updates.
- **Approval required:** No
- **Input schema:**
```python
class TrackChequeClearingInput(BaseModel):
    action: str = Field(..., description="'issue', 'clear', 'bounce', 'reconcile', 'status'")
    cheque_id: str | None = None
    vendor_name: str | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    issue_date: date | None = None
    bank_account_id: str | None = None
```
- **Output schema:**
```python
class ChequeStatusItem(BaseModel):
    cheque_id: str
    vendor_name: str | None
    amount: Decimal | None
    status: str  # "issued", "cleared", "bounced", "reconciled"
    issue_date: date | None
    clearing_date: date | None
    days_outstanding: int | None
    warning: str | None = None

class TrackChequeClearingOutput(BaseModel):
    cheque_id: str
    action_performed: str
    current_state: ChequeStatusItem
```
- **DB tables touched:** `cheque_registry` (read/write)
- **Edge cases (minimum 6):**
  1. Issue duplicate cheque_id → warns "cheque already issued", returns existing
  2. Clear cheque already cleared → no-op: returns current status with message
  3. Bounce cheque → status changes to "bounced", warning: "funds may need recovery"
  4. Status check on non-existent cheque → raises ValueError with valid IDs hint
  5. Cheque amount > bank account balance → warning flag "insufficient funds likely"
  6. Stale cheque (issued >180 days, not cleared) → auto-flag: "stale — confirm if still outstanding"
- **Example:**
  - User: "Issue cheque number 001234 for 50000 to Abdullah General Store"
  - Output: `{"cheque_id": "CHQ-001234", "action_performed": "issued", "current_state": {"cheque_id": "CHQ-001234", "vendor_name": "Abdullah General Store", "amount": "50000.00", "status": "issued", "issue_date": "2026-07-29", "clearing_date": null, "days_outstanding": 0, "warning": null}}`

---

## Tool: track_lc_bank_guarantee

- **What it does / how it works:** Tracks Letters of Credit and Bank Guarantees. Supports: issue, amend, expire, close actions. LC/BG issuance involves bank process — the tool only tracks it after bank confirmation.
- **Approval required:** Yes
- **Input schema:**
```python
class TrackLCBGInput(BaseModel):
    action: str = Field(..., description="'issue', 'amend', 'expire', 'close', 'status'")
    lc_id: str | None = None
    type: str | None = Field(default=None, description="'LC' or 'BG'")
    beneficiary: str | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    issue_date: date | None = None
    expiry_date: date | None = None
    currency: str = "PKR"
```
- **Output schema:**
```python
class LCBGDetails(BaseModel):
    lc_id: str
    type: str
    beneficiary: str
    amount: Decimal
    currency: str
    issue_date: date
    expiry_date: date
    status: str  # "active", "amended", "expired", "closed"
    days_to_expiry: int | None

class TrackLCBGOutput(BaseModel):
    lc_id: str
    action_performed: str
    details: LCBGDetails
    needs_approval: bool = True
    warning: str | None = None
```
- **DB tables touched:** `lc_bg_registry` (read/write)
- **Edge cases (minimum 6):**
  1. Issue LC with expiry_date in past → raises ValueError "expiry date must be in future"
  2. Amend LC/BG amount → creates new version, preserves original in history field
  3. Close LC before expiry → records early closure with reason required
  4. Duplicate lc_id → error with existing details for reference
  5. LC/BG expiring within 30 days → warning: "expiring soon — renewal recommended"
  6. Multiple LCs for same beneficiary → summary with count and total exposure
- **Example:**
  - User: "Issue LC for 5,000,000 to ABC Trading, expiring 2026-12-31"
  - Output: `{"lc_id": "LC-202607-001", "action_performed": "issued", "details": {"lc_id": "LC-202607-001", "type": "LC", "beneficiary": "ABC Trading", "amount": "5000000.00", "currency": "PKR", "issue_date": "2026-07-29", "expiry_date": "2026-12-31", "status": "active", "days_to_expiry": 155}, "needs_approval": true, "warning": null}`

---

## Tool: reconcile_bank_charges

- **What it does / how it works:** Matches bank fee/charge lines from `bank_transactions` against internal `journal_entries` by amount and approximate date. Fixed formula — no AI reasoning. Reports matched and unmatched charges.
- **Approval required:** No
- **Input schema:**
```python
class ReconcileBankChargesInput(BaseModel):
    bank_account_id: str
    from_date: date
    to_date: date
    charge_type: str | None = Field(default=None, description="'service', 'maintenance', 'transfer', 'other'")
```
- **Output schema:**
```python
class BankChargeItem(BaseModel):
    bank_txn_id: str
    date: date
    description: str
    amount: Decimal
    journal_match_id: str | None
    match_status: str  # "matched", "unmatched"

class ReconcileBankChargesOutput(BaseModel):
    period_from: date
    period_to: date
    total_charges_found: int
    total_matched: int
    total_unmatched: int
    charges: list[BankChargeItem]
    warning: str | None = None
```
- **DB tables touched:** `bank_transactions` (read), `journal_entries` (read)
- **Edge cases (minimum 5):**
  1. No bank charges in period → empty list with zero totals
  2. Charges not recorded in journal → all items show unmatched with reason
  3. Charge type filter provided but no matches → empty with supported types hint
  4. Duplicate charge (one bank line matched to multiple journal entries) → flags as "over_recorded"
  5. Negative charge amount (refund/adjustment) → listed as "credit_charge" type
- **Example:**
  - User: "Reconcile bank charges for HBL Current for July"
  - Output: `{"period_from": "2026-07-01", "period_to": "2026-07-31", "total_charges_found": 3, "total_matched": 2, "total_unmatched": 1, "charges": [...], "warning": null}`

---

## Agent-Level Behavior

- **Routing:** Orchestrator routes to this agent when user mentions: "reconcile", "bank reconciliation", "bank match", "accrual", "vendor statement", "customer statement", "cheque", "check", "LC", "letter of credit", "bank guarantee", "BG", "bank charges", "bank fees", "statement matching", "outstanding items"
- **Downstream effects:**
  - `run_bank_reconciliation` (after approval) updates reconciliation status in `reconciliation_runs` and `reconciliation_matches` tables
  - `post_accrual_entry` (after approval) creates a journal entry visible to Agent 1's `check_cash_position` and Agent 2's `get_general_ledger`
  - `track_cheque_clearing` status changes affect Agent 1's `check_bank_transactions` results
- **Model fallback:** Same as Agents 1+2 — Groq qwen/qwen3.6-27b primary → llama-3.1-8b-instant fallback → Cerebras gemma-4-31b last resort
- **Approval-heavy agent:** 5 of 7 tools require human confirmation — the highest ratio of any agent due to financial risk
