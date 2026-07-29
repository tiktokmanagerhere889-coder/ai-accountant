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


# --- Reconciliation & Banking (Agent 3) ---

class RunBankReconciliationInput(BaseModel):
    bank_account_id: str = Field(..., description="Bank account ID to reconcile")
    statement_date: date = Field(..., description="Statement date")
    from_date: date = Field(..., description="Start date for transactions to match (inclusive)")
    to_date: date = Field(..., description="End date for transactions to match (inclusive)")


class ReconciliationMatchItem(BaseModel):
    bank_txn_id: str
    bank_date: date
    bank_description: str
    bank_amount: Decimal
    bank_type: str
    journal_entry_id: Optional[str] = None
    journal_date: Optional[date] = None
    journal_amount: Optional[Decimal] = None
    confidence: float
    match_type: str
    partial_match: bool = False
    status: str


class UnmatchedBankItem(BaseModel):
    bank_txn_id: str
    date: date
    description: str
    amount: Decimal
    reason: str


class RunBankReconciliationOutput(BaseModel):
    run_id: str
    bank_account_id: str
    statement_date: date
    period_from: date
    period_to: date
    matches: list[ReconciliationMatchItem]
    unmatched_bank: list[UnmatchedBankItem]
    total_matched: int
    total_unmatched: int
    total_amount_matched: Decimal = Decimal("0")
    total_amount_unmatched: Decimal = Decimal("0")
    status: str
    existing_run_note: Optional[str] = None


class PostAccrualEntryInput(BaseModel):
    accrual_type: str = Field(..., description="Type of accrual: e.g., salary, rent, utility")
    amount: Decimal = Field(..., gt=Decimal("0"), description="Accrual amount")
    description: str = Field(..., min_length=1, max_length=500, description="Description of the accrual entry")
    period_date: date = Field(..., description="Period end date for the accrual")
    debit_account: Optional[str] = Field(default=None, description="Override auto-detected debit account code")
    credit_account: Optional[str] = Field(default=None, description="Override auto-detected credit account code")
    partial_period_days: Optional[int] = Field(default=None, ge=1, le=365, description="Number of days in partial period")


class PostAccrualEntryOutput(BaseModel):
    accrual_id: str
    entry_id: Optional[str] = None
    accrual_type: str
    amount: Decimal
    debit_account: str
    debit_amount: Decimal
    credit_account: str
    credit_amount: Decimal
    period_date: date
    partial_period_days: Optional[int] = None
    prorated_amount: Optional[Decimal] = None
    needs_approval: bool = True
    status: str
    warnings: list[str] = []


class VendorStatementLine(BaseModel):
    reference: str
    date: date
    amount: Decimal
    description: Optional[str] = None


class ReconcileVendorStatementInput(BaseModel):
    vendor_contact_id: str = Field(..., description="Vendor contact ID")
    statement_date: date = Field(..., description="Date of the vendor statement")
    from_date: date = Field(..., description="Start date for matching (inclusive)")
    to_date: date = Field(..., description="End date for matching (inclusive)")
    statement_lines: list[VendorStatementLine] = Field(..., description="Lines from the vendor statement")


class StatementMatchItem(BaseModel):
    statement_ref: str
    journal_entry_id: str
    amount_match: bool
    date_match: bool
    status: str


class StatementDifferenceItem(BaseModel):
    reference: str
    statement_amount: Decimal
    internal_amount: Decimal
    difference: Decimal
    reason: Optional[str] = None


class ReconcileVendorStatementOutput(BaseModel):
    reconciliation_id: str
    vendor_contact_id: str
    matches: list[StatementMatchItem]
    differences: list[StatementDifferenceItem]
    total_difference: Decimal
    status: str


class ReconcileCustomerStatementInput(BaseModel):
    customer_contact_id: str = Field(..., description="Customer contact ID")
    statement_date: date = Field(..., description="Date of the customer statement")
    from_date: date = Field(..., description="Start date for matching (inclusive)")
    to_date: date = Field(..., description="End date for matching (inclusive)")
    statement_lines: list[VendorStatementLine] = Field(..., description="Lines from the customer statement")


class ReconcileCustomerStatementOutput(BaseModel):
    reconciliation_id: str
    customer_contact_id: str
    matches: list[StatementMatchItem]
    differences: list[StatementDifferenceItem]
    total_difference: Decimal
    status: str


class TrackChequeClearingInput(BaseModel):
    action: str = Field(..., description="Action: 'issue', 'clear', 'bounce', 'reconcile', or 'status'")
    cheque_id: Optional[str] = Field(default=None, description="Cheque ID (required for 'clear', 'bounce', 'status')")
    vendor_name: Optional[str] = Field(default=None, description="Vendor name (for 'issue')")
    amount: Optional[Decimal] = Field(default=None, description="Cheque amount (for 'issue')")
    issue_date: Optional[date] = Field(default=None, description="Issue date (for 'issue')")
    bank_account_id: Optional[str] = Field(default=None, description="Bank account ID (for 'issue')")


class ChequeStatusItem(BaseModel):
    cheque_id: str
    vendor_name: Optional[str] = None
    amount: Optional[Decimal] = None
    status: str
    issue_date: Optional[date] = None
    clearing_date: Optional[date] = None
    days_outstanding: Optional[int] = None
    warning: Optional[str] = None


class TrackChequeClearingOutput(BaseModel):
    cheque_id: str
    action_performed: str
    current_state: ChequeStatusItem


class TrackLCBGInput(BaseModel):
    action: str = Field(..., description="Action: 'issue', 'amend', 'expire', 'close', or 'status'")
    lc_id: Optional[str] = Field(default=None, description="LC/BG ID (required for 'amend', 'expire', 'claim', 'status')")
    type: Optional[str] = Field(default=None, description="Type: 'LC' or 'BG' (for 'issue')")
    beneficiary: Optional[str] = Field(default=None, description="Beneficiary name (for 'issue')")
    amount: Optional[Decimal] = Field(default=None, description="LC/BG amount (for 'issue')")
    issue_date: Optional[date] = Field(default=None, description="Issue date (for 'issue')")
    expiry_date: Optional[date] = Field(default=None, description="Expiry date (for 'issue')")
    currency: str = Field(default="PKR", description="Currency code (for 'issue')")


class LCBGDetails(BaseModel):
    lc_id: str
    type: str
    beneficiary: str
    amount: Decimal
    currency: str
    issue_date: date
    expiry_date: date
    status: str
    days_to_expiry: Optional[int] = None


class TrackLCBGOutput(BaseModel):
    lc_id: str
    action_performed: str
    details: LCBGDetails
    needs_approval: bool = True
    warning: Optional[str] = None


class ReconcileBankChargesInput(BaseModel):
    bank_account_id: str = Field(..., description="Bank account ID")
    from_date: date = Field(..., description="Start date for charges (inclusive)")
    to_date: date = Field(..., description="End date for charges (inclusive)")
    charge_type: Optional[str] = Field(default=None, description="Filter by charge type (e.g., 'service', 'fee')")


class BankChargeItem(BaseModel):
    bank_txn_id: str
    date: date
    description: str
    amount: Decimal
    journal_match_id: Optional[str] = None
    match_status: str


class ReconcileBankChargesOutput(BaseModel):
    period_from: date
    period_to: date
    total_charges_found: int
    total_matched: int
    total_unmatched: int
    charges: list[BankChargeItem]
    warning: Optional[str] = None


# --- Month-End Reporting (Agent 4) ---

# Tool 7: AP Aging Report

class APAgingBucket(BaseModel):
    vendor_contact_id: str
    vendor_name: str
    current: Decimal = Decimal("0")
    aged_31_60: Decimal = Decimal("0")
    aged_61_90: Decimal = Decimal("0")
    aged_90_plus: Decimal = Decimal("0")
    total_outstanding: Decimal = Decimal("0")


class GetAPAgingReportInput(BaseModel):
    as_of_date: date = Field(default_factory=date.today, description="Date to calculate aging from")
    vendor_contact_id: Optional[str] = Field(default=None, description="Optional filter to a single vendor")


class GetAPAgingReportOutput(BaseModel):
    as_of_date: date
    buckets: list[APAgingBucket]
    total_current: Decimal = Decimal("0")
    total_31_60: Decimal = Decimal("0")
    total_61_90: Decimal = Decimal("0")
    total_90_plus: Decimal = Decimal("0")
    grand_total: Decimal = Decimal("0")


# Tool 8: Budget Variance Analysis

class BudgetVarianceItem(BaseModel):
    account_code: str
    budget_amount: Decimal
    actual_amount: Decimal
    variance: Decimal
    variance_pct: Decimal
    flagged: bool = False
    explanation: str = ""


class AnalyzeBudgetVarianceInput(BaseModel):
    fiscal_year: int = Field(..., description="Fiscal year (e.g., 2026)")
    period: int = Field(..., ge=1, le=12, description="Period/month number (1-12)")
    account_code_prefix: Optional[str] = Field(default=None, description="Optional account filter prefix")


class AnalyzeBudgetVarianceOutput(BaseModel):
    fiscal_year: int
    period: int
    items: list[BudgetVarianceItem]
    total_budget: Decimal = Decimal("0")
    total_actual: Decimal = Decimal("0")
    total_variance: Decimal = Decimal("0")
    flagged_count: int = 0
    summary: str = ""


# Tool 9: Loan / Debt Schedule

class LoanPaymentScheduleItem(BaseModel):
    period_number: int
    payment_date: date
    payment_amount: Decimal
    principal_amount: Decimal
    interest_amount: Decimal
    remaining_balance: Decimal


class GetLoanDebtScheduleInput(BaseModel):
    loan_id: str = Field(..., description="Loan ID to generate or retrieve schedule for")
    as_of_date: Optional[date] = Field(default=None, description="Date to filter schedule from (shows only future payments)")


class GetLoanDebtScheduleOutput(BaseModel):
    loan_id: str
    loan_name: str
    principal_amount: Decimal
    interest_rate: Decimal
    term_months: int
    start_date: date
    monthly_payment: Decimal
    schedule: list[LoanPaymentScheduleItem]
    total_interest: Decimal = Decimal("0")
    source: str = "computed"


# Tool 10: Cash Flow Forecast

class CashFlowProjection(BaseModel):
    date: date
    projected_inflow: Decimal
    projected_outflow: Decimal
    net_flow: Decimal
    cumulative_balance: Decimal


class ForecastCashFlowInput(BaseModel):
    forecast_days: int = Field(default=30, ge=30, le=90, description="Forecast horizon: 30, 60, or 90 days")
    starting_balance: Decimal = Field(default=Decimal("0"), description="Opening cash balance")
    as_of_date: Optional[date] = Field(default=None, description="Base date for forecast; defaults to today")


class ForecastCashFlowOutput(BaseModel):
    forecast_days: int
    projections: list[CashFlowProjection]
    avg_monthly_inflow: Decimal = Decimal("0")
    avg_monthly_outflow: Decimal = Decimal("0")
    net_monthly_average: Decimal = Decimal("0")
    confidence: str = "low"
    needs_approval: bool = True


# --- Month-End Reporting (Agent 4) Tool 1-6 schemas ---

class UnpaidBillItem(BaseModel):
    entry_id: str
    vendor_name: str
    invoice_amount: Decimal
    outstanding_balance: Decimal
    due_date: date
    days_overdue: Optional[int] = None
    status: str


class ReviewUnpaidBillsInput(BaseModel):
    as_of_date: date = Field(default_factory=date.today, description="Date to check unpaid bills against")
    vendor_contact_id: Optional[str] = Field(default=None, description="Filter by specific vendor")
    min_days_overdue: Optional[int] = Field(default=None, ge=1, description="Minimum days overdue")


class ReviewUnpaidBillsOutput(BaseModel):
    items: list[UnpaidBillItem]
    total_unpaid: Decimal
    total_overdue: Decimal
    as_of_date: date


class PrepaidAdjustmentItem(BaseModel):
    prepaid_id: str
    description: str
    total_amount: Decimal
    start_date: date
    end_date: date
    monthly_amount: Decimal
    months_elapsed: int
    amount_amortized: Decimal
    remaining_balance: Decimal
    suggested_adjustment: Decimal


class CalculatePrepaidAdjustmentInput(BaseModel):
    prepaid_id: Optional[str] = Field(default=None, description="Specific prepaid ID; if None, processes all active")
    as_of_date: date = Field(default_factory=date.today, description="Date to calculate adjustments for")


class CalculatePrepaidAdjustmentOutput(BaseModel):
    items: list[PrepaidAdjustmentItem]
    total_adjustment: Decimal
    as_of_date: date


class DepreciationEntryItem(BaseModel):
    entry_id: str
    asset_id: str
    asset_name: str
    period_date: date
    monthly_depreciation: Decimal
    accumulated_depreciation: Decimal
    book_value: Decimal
    status: str


class CalculateDepreciationInput(BaseModel):
    asset_id: Optional[str] = Field(default=None, description="Specific asset ID; if None, processes all active")
    period_date: date = Field(default_factory=date.today, description="Period date")


class CalculateDepreciationOutput(BaseModel):
    items: list[DepreciationEntryItem]
    total_depreciation: Decimal
    period_date: date


class AmortizationEntryItem(BaseModel):
    entry_id: str
    asset_id: str
    asset_name: str
    period_date: date
    monthly_amortization: Decimal
    accumulated_amortization: Decimal
    book_value: Decimal
    status: str


class CalculateAmortizationInput(BaseModel):
    asset_id: Optional[str] = Field(default=None, description="Specific intangible asset ID; if None, processes all active")
    period_date: date = Field(default_factory=date.today, description="Period date")


class CalculateAmortizationOutput(BaseModel):
    items: list[AmortizationEntryItem]
    total_amortization: Decimal
    period_date: date


class PayrollReconItem(BaseModel):
    entry_id: str
    employee_name: str
    salary_amount: Decimal
    deductions: Decimal
    net_pay: Decimal
    period_start: date
    period_end: date
    posted_date: date
    discrepancy: Optional[str] = None


class ReconcilePayrollInput(BaseModel):
    from_date: date = Field(..., description="Start date")
    to_date: date = Field(..., description="End date")
    employee_name: Optional[str] = Field(default=None, description="Filter by employee")


class ReconcilePayrollOutput(BaseModel):
    items: list[PayrollReconItem]
    total_salary: Decimal
    total_deductions: Decimal
    total_net_pay: Decimal
    period_from: date
    period_to: date
    discrepancies: int = 0


class AgingBucketItem(BaseModel):
    bucket_name: str
    from_days: int
    to_days: Optional[int] = None
    total_amount: Decimal
    percentage: float


class CustomerAgingDetail(BaseModel):
    customer_name: str
    total_outstanding: Decimal
    current: Decimal
    past_30: Decimal
    past_60: Decimal
    past_90: Decimal


class GetARAgingReportInput(BaseModel):
    as_of_date: date = Field(default_factory=date.today, description="Date to calculate aging for")
    customer_contact_id: Optional[str] = Field(default=None, description="Filter by specific customer")


class GetARAgingReportOutput(BaseModel):
    buckets: list[AgingBucketItem]
    customer_details: list[CustomerAgingDetail]
    total_outstanding: Decimal
    as_of_date: date


# --- Month-End Reporting (Agent 4) supplementary schemas ---

# --- Year-End Close & Financial Statements (Agent 5) ---

# Tool 1: Trial Balance
class TrialBalanceAccount(BaseModel):
    account_code: str
    account_name: str
    total_debits: Decimal = Decimal("0")
    total_credits: Decimal = Decimal("0")
    balance: Decimal = Decimal("0")


class GenerateTrialBalanceInput(BaseModel):
    as_of_date: date = Field(default_factory=date.today, description="Date to generate trial balance for")


class GenerateTrialBalanceOutput(BaseModel):
    as_of_date: date
    accounts: list[TrialBalanceAccount]
    total_debits: Decimal = Decimal("0")
    total_credits: Decimal = Decimal("0")
    in_balance: bool = True
    difference: Decimal = Decimal("0")


# Tool 2: Profit & Loss
class PnLItem(BaseModel):
    account: str
    amount: Decimal


class GenerateProfitLossInput(BaseModel):
    from_date: date = Field(..., description="Start date (inclusive)")
    to_date: date = Field(..., description="End date (inclusive)")


class GenerateProfitLossOutput(BaseModel):
    from_date: date
    to_date: date
    revenue_items: list[PnLItem]
    expense_items: list[PnLItem]
    total_revenue: Decimal = Decimal("0")
    total_expenses: Decimal = Decimal("0")
    net_income: Decimal = Decimal("0")
    summary: str = ""


# Tool 3: Balance Sheet
class BalanceSheetItem(BaseModel):
    account: str
    amount: Decimal


class GenerateBalanceSheetInput(BaseModel):
    as_of_date: date = Field(default_factory=date.today, description="Date to generate balance sheet for")


class GenerateBalanceSheetOutput(BaseModel):
    as_of_date: date
    assets: list[BalanceSheetItem]
    liabilities: list[BalanceSheetItem]
    equity: list[BalanceSheetItem]
    total_assets: Decimal = Decimal("0")
    total_liabilities: Decimal = Decimal("0")
    total_equity: Decimal = Decimal("0")
    balanced: bool = True
    difference: Decimal = Decimal("0")


# Tool 4: Cash Flow Statement
class CashFlowItem(BaseModel):
    description: str
    amount: Decimal


class GenerateCashFlowInput(BaseModel):
    from_date: date = Field(..., description="Start date (inclusive)")
    to_date: date = Field(..., description="End date (inclusive)")


class GenerateCashFlowOutput(BaseModel):
    from_date: date
    to_date: date
    operating_items: list[CashFlowItem]
    investing_items: list[CashFlowItem]
    financing_items: list[CashFlowItem]
    net_operating: Decimal = Decimal("0")
    net_investing: Decimal = Decimal("0")
    net_financing: Decimal = Decimal("0")
    net_change_in_cash: Decimal = Decimal("0")
    opening_cash: Decimal = Decimal("0")
    closing_cash: Decimal = Decimal("0")


# Tool 5: Transfer Retained Earnings
class TransferRetainedEarningsInput(BaseModel):
    fiscal_year: int = Field(..., description="Fiscal year to transfer earnings for")


class TransferRetainedEarningsOutput(BaseModel):
    fiscal_year: int
    beginning_retained_earnings: Decimal = Decimal("0")
    net_income: Decimal = Decimal("0")
    dividends: Decimal = Decimal("0")
    ending_retained_earnings: Decimal = Decimal("0")
    journal_entry_id: str = ""


# Tool 6: Carry Forward Balances
class CarryForwardBalanceItem(BaseModel):
    account_code: str
    account_name: str
    closing_balance: Decimal
    opening_balance_next_year: Decimal


class CarryForwardBalancesInput(BaseModel):
    from_fiscal_year: int = Field(..., description="Fiscal year to close")
    to_fiscal_year: int = Field(..., description="Next fiscal year")
    closing_date: date = Field(default_factory=date.today, description="Date of carry-forward")


class CarryForwardBalancesOutput(BaseModel):
    accounts_carried_forward: int = 0
    new_balances: list[CarryForwardBalanceItem]
    status: str = "completed"


# Tool 7: Draft Notes to Financials
class FinancialNote(BaseModel):
    title: str
    content: str
    source_data: list[str] = []


class DraftNotesToFinancialsInput(BaseModel):
    fiscal_year: int = Field(..., description="Fiscal year for notes")
    note_types: Optional[list[str]] = Field(default=None, description="Types: accounting_policies, revenue_recognition, depreciation_method, commitments, contingencies")


class DraftNotesToFinancialsOutput(BaseModel):
    fiscal_year: int
    notes: list[FinancialNote]
    disclaimer: str = ""


# Tool 8: Close Fiscal Year
class CloseFiscalYearInput(BaseModel):
    fiscal_year: int = Field(..., description="Fiscal year to close")
    closing_date: date = Field(default_factory=date.today, description="Closing date")
    confirm: bool = Field(default=False, description="Must be true to execute close")


class CloseFiscalYearOutput(BaseModel):
    fiscal_year: int
    closing_entries_created: int = 0
    revenue_closed: int = 0
    expenses_closed: int = 0
    net_income_transferred: Decimal = Decimal("0")
    status: str = "closed"
    message: str = ""
