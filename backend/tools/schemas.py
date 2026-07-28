from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


# --- Cash Position ---

class CashPositionBase(BaseModel):
    account_id: str
    account_name: str
    opening_balance: Decimal
    total_debits: Decimal
    total_credits: Decimal
    closing_balance: Decimal
    currency: str
    as_of_date: date


class CashPositionCreate(CashPositionBase):
    pass


class CashPositionUpdate(BaseModel):
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    opening_balance: Optional[Decimal] = None
    total_debits: Optional[Decimal] = None
    total_credits: Optional[Decimal] = None
    closing_balance: Optional[Decimal] = None
    currency: Optional[str] = None
    as_of_date: Optional[date] = None


class CashPositionResponse(CashPositionBase):
    id: int
    model_config = {"from_attributes": True}


# --- Journal Entries ---

class JournalEntryBase(BaseModel):
    entry_id: str
    description: str
    posted_date: date
    reference: Optional[str] = None
    debit_account: str
    debit_amount: Decimal
    credit_account: str
    credit_amount: Decimal
    status: str


class JournalEntryCreate(JournalEntryBase):
    pass


class JournalEntryUpdate(BaseModel):
    entry_id: Optional[str] = None
    description: Optional[str] = None
    posted_date: Optional[date] = None
    reference: Optional[str] = None
    debit_account: Optional[str] = None
    debit_amount: Optional[Decimal] = None
    credit_account: Optional[str] = None
    credit_amount: Optional[Decimal] = None
    status: Optional[str] = None


class JournalEntryResponse(JournalEntryBase):
    id: int
    model_config = {"from_attributes": True}


# --- Receipt Extractions ---

class ReceiptExtractionBase(BaseModel):
    extraction_id: str
    vendor_name: Optional[str] = None
    total_amount: Optional[Decimal] = None
    date: Optional[date] = None
    currency: str = "PKR"
    confidence: Decimal
    needs_approval: int
    status: str


class ReceiptExtractionCreate(ReceiptExtractionBase):
    pass


class ReceiptExtractionUpdate(BaseModel):
    extraction_id: Optional[str] = None
    vendor_name: Optional[str] = None
    total_amount: Optional[Decimal] = None
    date: Optional[date] = None
    currency: Optional[str] = None
    confidence: Optional[Decimal] = None
    needs_approval: Optional[int] = None
    status: Optional[str] = None


class ReceiptExtractionResponse(ReceiptExtractionBase):
    id: int
    model_config = {"from_attributes": True}


# --- Bank Transactions ---

class BankTransactionBase(BaseModel):
    transaction_id: str
    date: date
    description: str
    amount: Decimal
    type: str
    status: str
    reference: Optional[str] = None
    balance_after: Decimal
    account_id: str


class BankTransactionCreate(BankTransactionBase):
    pass


class BankTransactionUpdate(BaseModel):
    transaction_id: Optional[str] = None
    date: Optional[date] = None
    description: Optional[str] = None
    amount: Optional[Decimal] = None
    type: Optional[str] = None
    status: Optional[str] = None
    reference: Optional[str] = None
    balance_after: Optional[Decimal] = None
    account_id: Optional[str] = None


class BankTransactionResponse(BankTransactionBase):
    id: int
    model_config = {"from_attributes": True}


# --- Bank Accounts ---

class BankAccountBase(BaseModel):
    account_id: str
    account_name: str
    bank_name: str


class BankAccountCreate(BankAccountBase):
    pass


class BankAccountUpdate(BaseModel):
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    bank_name: Optional[str] = None


class BankAccountResponse(BankAccountBase):
    id: int
    model_config = {"from_attributes": True}


# --- Petty Cash Funds ---

class PettyCashFundBase(BaseModel):
    fund_id: str
    fund_name: str
    current_balance: Decimal


class PettyCashFundCreate(PettyCashFundBase):
    pass


class PettyCashFundUpdate(BaseModel):
    fund_id: Optional[str] = None
    fund_name: Optional[str] = None
    current_balance: Optional[Decimal] = None


class PettyCashFundResponse(PettyCashFundBase):
    id: int
    model_config = {"from_attributes": True}


# --- Petty Cash Transactions ---

class PettyCashTransactionBase(BaseModel):
    transaction_id: str
    fund_id: str
    action: str
    amount: Decimal
    description: str
    paid_by: str
    date: date
    remaining_balance: Decimal


class PettyCashTransactionCreate(PettyCashTransactionBase):
    pass


class PettyCashTransactionUpdate(BaseModel):
    transaction_id: Optional[str] = None
    fund_id: Optional[str] = None
    action: Optional[str] = None
    amount: Optional[Decimal] = None
    description: Optional[str] = None
    paid_by: Optional[str] = None
    date: Optional[date] = None
    remaining_balance: Optional[Decimal] = None


class PettyCashTransactionResponse(PettyCashTransactionBase):
    id: int
    model_config = {"from_attributes": True}


# --- Tool-specific Schemas ---

class CheckCashPositionInput(BaseModel):
    as_of_date: date = Field(default_factory=date.today, description="Date to check cash position for")
    account_id: Optional[str] = Field(default=None, description="Specific cash account ID; if None, sums all cash accounts")


class CheckCashPositionOutput(BaseModel):
    account_id: str
    account_name: str
    opening_balance: Decimal
    total_debits: Decimal
    total_credits: Decimal
    closing_balance: Decimal
    currency: str = "PKR"
    as_of_date: date
    warning: bool = False
    details: Optional[list[dict]] = None


class RecordTransactionNLInput(BaseModel):
    description: str = Field(..., min_length=5, max_length=500, description="Plain-English transaction description")
    posted_date: date = Field(default_factory=date.today, description="Transaction date")
    reference: Optional[str] = Field(default=None, description="Optional invoice/receipt reference number")


class RecordTransactionNLOutput(BaseModel):
    entry_id: str
    description: str
    posted_date: date
    reference: Optional[str]
    debit_account: str
    debit_amount: Decimal
    credit_account: str
    credit_amount: Decimal
    status: str = "posted"


class ProcessReceiptImageInput(BaseModel):
    image_data: str = Field(..., description="Base64-encoded receipt image")
    image_filename: str = Field(..., description="Original filename of the receipt image")
    suggested_account: Optional[str] = Field(default=None, description="Optional account to post to (e.g., 'Office Rent')")


class ProcessReceiptImageOutput(BaseModel):
    extraction_id: str
    vendor_name: Optional[str]
    total_amount: Optional[Decimal]
    date: Optional[date]
    currency: str = "PKR"
    confidence: float = Field(ge=0.0, le=1.0, description="Extraction confidence score")
    needs_approval: bool = True
    status: str = "extracted_pending_approval"


class BankTransactionItem(BaseModel):
    transaction_id: str
    date: date
    description: str
    amount: Decimal
    type: str
    status: str
    reference: Optional[str]
    balance_after: Decimal


class CheckBankTransactionsInput(BaseModel):
    account_id: Optional[str] = Field(default=None, description="Bank account ID to filter; if None, returns all bank accounts")
    from_date: date = Field(default_factory=lambda: date.today().replace(day=1), description="Start date (inclusive)")
    to_date: date = Field(default_factory=date.today, description="End date (inclusive)")
    status: Optional[str] = Field(default=None, description="Filter by transaction status: 'cleared', 'pending', or 'reconciled'")
    limit: int = Field(default=50, ge=1, le=500, description="Maximum number of transactions to return")


class CheckBankTransactionsOutput(BaseModel):
    account_id: Optional[str]
    account_name: Optional[str]
    transactions: list[BankTransactionItem]
    total_count: int
    total_debits: Decimal
    total_credits: Decimal
    period_from: date
    period_to: date
    truncated: bool = False
    actual_count: Optional[int] = None


class PettyCashTransactionItem(BaseModel):
    transaction_id: str
    fund_id: str
    action: str
    amount: Decimal
    description: Optional[str]
    paid_by: Optional[str]
    date: date
    remaining_balance: Decimal


class ManagePettyCashInput(BaseModel):
    action: str = Field(..., description="Action to perform: 'expense', 'add_fund', or 'check_replenishment'")
    fund_id: Optional[str] = Field(default=None, description="Petty cash fund ID; required for 'expense' and 'check_replenishment'")
    amount: Optional[Decimal] = Field(default=None, description="Amount for expense or add_fund actions; must be > 0")
    description: Optional[str] = Field(default=None, max_length=200, description="Description of the petty cash expense")
    paid_by: Optional[str] = Field(default=None, description="Person who paid or received the petty cash")
    replenishment_threshold: Decimal = Field(default=5000.00, ge=100.00, description="Minimum balance before triggering replenishment reminder")


class ManagePettyCashOutput(BaseModel):
    fund_id: str
    fund_name: str
    current_balance: Decimal
    threshold: Decimal
    needs_replenishment: bool
    transactions: list[PettyCashTransactionItem]
    message: Optional[str] = None


# --- Journal Entry (Agent 2 - Ledger) ---

class CreateJournalEntryInput(BaseModel):
    description: str = Field(..., min_length=1, max_length=500, description="Description of the journal entry")
    posted_date: date = Field(..., description="Date the entry was posted")
    reference: Optional[str] = Field(default=None, max_length=100, description="Optional invoice/receipt reference")
    debit_account: str = Field(..., min_length=1, description="Account code to debit")
    debit_amount: Decimal = Field(..., gt=Decimal("0"), description="Debit amount")
    credit_account: str = Field(..., min_length=1, description="Account code to credit")
    credit_amount: Decimal = Field(..., gt=Decimal("0"), description="Credit amount")
    status: str = Field(default="posted", description="Entry status: 'posted' or 'draft'")


class CreateJournalEntryOutput(BaseModel):
    entry_id: str
    description: str
    posted_date: date
    reference: Optional[str]
    debit_account: str
    debit_amount: Decimal
    credit_account: str
    credit_amount: Decimal
    status: str
    message: str = "Journal entry created successfully"


# --- General Ledger (Agent 2) ---

class LedgerAccountEntry(BaseModel):
    account_code: str
    account_name: str
    account_type: str
    opening_balance: Decimal
    total_debits: Decimal
    total_credits: Decimal
    net_movement: Decimal
    closing_balance: Decimal


class GetGeneralLedgerInput(BaseModel):
    from_date: date = Field(..., description="Start date (inclusive)")
    to_date: date = Field(..., description="End date (inclusive)")
    account_code_prefix: Optional[str] = Field(default=None, description="Filter accounts whose code starts with this prefix (e.g., '1000' for all cash accounts)")


class GetGeneralLedgerOutput(BaseModel):
    period_from: date
    period_to: date
    accounts: list[LedgerAccountEntry]
    total_debits: Decimal
    total_credits: Decimal


# --- AP Subledger (Agent 2) ---

class APEntryItem(BaseModel):
    entry_id: str
    vendor_name: str
    invoice_amount: Decimal
    paid_amount: Decimal
    outstanding_balance: Decimal
    due_date: date
    status: str


class GetAPSubledgerInput(BaseModel):
    vendor_contact_id: Optional[str] = Field(default=None, description="Filter by specific vendor contact ID")
    from_date: date = Field(default_factory=lambda: date.today().replace(day=1), description="Start date (inclusive)")
    to_date: date = Field(default_factory=date.today, description="End date (inclusive)")
    status: Optional[str] = Field(default=None, description="Filter by status: 'open', 'paid', 'overdue'")


class GetAPSubledgerOutput(BaseModel):
    entries: list[APEntryItem]
    total_outstanding: Decimal
    total_paid: Decimal
    period_from: date
    period_to: date


# --- AR Subledger (Agent 2) ---

class AREntryItem(BaseModel):
    entry_id: str
    customer_name: str
    invoice_amount: Decimal
    received_amount: Decimal
    outstanding_balance: Decimal
    due_date: date
    status: str


class GetARSubledgerInput(BaseModel):
    customer_contact_id: Optional[str] = Field(default=None, description="Filter by specific customer contact ID")
    from_date: date = Field(default_factory=lambda: date.today().replace(day=1), description="Start date (inclusive)")
    to_date: date = Field(default_factory=date.today, description="End date (inclusive)")
    status: Optional[str] = Field(default=None, description="Filter by status: 'open', 'paid', 'overdue'")


class GetARSubledgerOutput(BaseModel):
    entries: list[AREntryItem]
    total_outstanding: Decimal
    total_received: Decimal
    period_from: date
    period_to: date


# --- Payroll Ledger (Agent 2) ---

class PayrollEntryItem(BaseModel):
    entry_id: str
    employee_name: str
    salary_amount: Decimal
    deductions: Decimal
    net_pay: Decimal
    period_start: date
    period_end: date
    posted_date: date
    warning: bool = False


class GetPayrollLedgerInput(BaseModel):
    employee_name: Optional[str] = Field(default=None, description="Filter by specific employee name")
    from_date: date = Field(default_factory=lambda: date.today().replace(day=1), description="Start date (inclusive)")
    to_date: date = Field(default_factory=date.today, description="End date (inclusive)")


class GetPayrollLedgerOutput(BaseModel):
    entries: list[PayrollEntryItem]
    total_salary: Decimal
    total_deductions: Decimal
    total_net_pay: Decimal
    period_from: date
    period_to: date


# --- Chart of Accounts (Agent 2) ---

class SuggestedAccountItem(BaseModel):
    account_code: str
    account_name: str
    account_type: str
    description: Optional[str] = None


class SuggestChartOfAccountsInput(BaseModel):
    business_type: str = Field(..., min_length=1, max_length=200, description="Type of business (e.g., 'retail', 'manufacturing', 'freelance')")
    description: Optional[str] = Field(default=None, max_length=500, description="Optional description of business for more tailored suggestions")


class SuggestChartOfAccountsOutput(BaseModel):
    business_type: str
    accounts: list[SuggestedAccountItem]
    total_count: int
    needs_approval: bool = True


# --- Fixed Asset (Agent 2) ---

class CategorizeFixedAssetInput(BaseModel):
    asset_name: str = Field(..., min_length=1, max_length=200, description="Name of the fixed asset")
    purchase_cost: Decimal = Field(..., gt=Decimal("0"), description="Purchase cost of the asset")
    purchase_date: date = Field(..., description="Date of purchase")
    asset_category: Optional[str] = Field(default=None, max_length=100, description="Optional asset category override (e.g., 'Vehicle', 'Computer')")


class CategorizeFixedAssetOutput(BaseModel):
    asset_id: str
    asset_name: str
    purchase_cost: Decimal
    suggested_useful_life: int
    suggested_depreciation_method: str
    suggested_residual_value: Decimal
    needs_approval: bool = True
    status: str


# --- Contact Management (Agent 2) ---

class ManageContactInput(BaseModel):
    action: str = Field(..., description="Action: add, update, delete, or search")
    contact_type: str = Field(..., description="Contact type: 'vendor' or 'customer'")
    contact_name: str = Field(..., min_length=1, max_length=200, description="Contact name")
    contact_id: Optional[str] = Field(default=None, max_length=100, description="Contact ID (needed for update/delete by ID)")
    phone: Optional[str] = Field(default=None, max_length=50, description="Phone number")
    email: Optional[str] = Field(default=None, max_length=200, description="Email address")
    address: Optional[str] = Field(default=None, max_length=500, description="Physical address")
    tax_id: Optional[str] = Field(default=None, max_length=100, description="Tax identification number")


class ManageContactOutput(BaseModel):
    contact_id: str
    contact_name: str
    contact_type: str
    action_performed: str
    message: str
