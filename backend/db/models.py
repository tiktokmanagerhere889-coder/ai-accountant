from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class CashPosition(Base):
    __tablename__ = "cash_position"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(String, nullable=False, index=True)
    account_name = Column(String, nullable=False)
    opening_balance = Column(Numeric, nullable=False)
    total_debits = Column(Numeric, nullable=False)
    total_credits = Column(Numeric, nullable=False)
    closing_balance = Column(Numeric, nullable=False)
    currency = Column(String, nullable=False)
    as_of_date = Column(Date, nullable=False)


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entry_id = Column(String, nullable=False, unique=True, index=True)
    description = Column(Text, nullable=False)
    posted_date = Column(Date, nullable=False)
    reference = Column(String)
    contact_id = Column(String, ForeignKey("contacts.contact_id"), nullable=True, index=True)
    debit_account = Column(String, nullable=False)
    debit_amount = Column(Numeric, nullable=False)
    credit_account = Column(String, nullable=False)
    credit_amount = Column(Numeric, nullable=False)
    status = Column(String, nullable=False)


class ReceiptExtraction(Base):
    __tablename__ = "receipt_extractions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    extraction_id = Column(String, nullable=False, unique=True, index=True)
    vendor_name = Column(String, nullable=True)
    total_amount = Column(Numeric, nullable=True)
    date = Column(Date, nullable=True)
    currency = Column(String, nullable=False)
    confidence = Column(Numeric, nullable=False)
    needs_approval = Column(Integer, nullable=False)
    status = Column(String, nullable=False)


class BankTransaction(Base):
    __tablename__ = "bank_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String, nullable=False, unique=True, index=True)
    date = Column(Date, nullable=False)
    description = Column(Text, nullable=False)
    amount = Column(Numeric, nullable=False)
    type = Column(String, nullable=False)
    status = Column(String, nullable=False)
    reference = Column(String)
    balance_after = Column(Numeric, nullable=False)
    account_id = Column(String, nullable=False, index=True)


class BankAccount(Base):
    __tablename__ = "bank_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(String, nullable=False, unique=True, index=True)
    account_name = Column(String, nullable=False)
    bank_name = Column(String, nullable=False)


class PettyCashFund(Base):
    __tablename__ = "petty_cash_funds"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fund_id = Column(String, nullable=False, unique=True, index=True)
    fund_name = Column(String, nullable=False)
    current_balance = Column(Numeric, nullable=False)


class PettyCashTransaction(Base):
    __tablename__ = "petty_cash_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String, nullable=False, unique=True, index=True)
    fund_id = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False)
    amount = Column(Numeric, nullable=False)
    description = Column(Text, nullable=False)
    paid_by = Column(String, nullable=False)
    date = Column(Date, nullable=False)
    remaining_balance = Column(Numeric, nullable=False)


class ChartOfAccount(Base):
    __tablename__ = "chart_of_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_code = Column(String, nullable=False, unique=True, index=True)
    account_name = Column(String, nullable=False)
    account_type = Column(String, nullable=False)
    is_active = Column(Integer, default=1)
    created_at = Column(Date)


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    contact_id = Column(String, nullable=False, unique=True, index=True)
    contact_name = Column(String, nullable=False)
    contact_type = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    address = Column(Text, nullable=True)
    tax_id = Column(String, nullable=True)
    related_party = Column(Boolean, nullable=False, default=False)
    created_at = Column(Date)


class FixedAsset(Base):
    __tablename__ = "fixed_assets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(String, nullable=False, unique=True, index=True)
    asset_name = Column(String, nullable=False)
    asset_category = Column(String, nullable=True)
    purchase_cost = Column(Numeric, nullable=False)
    purchase_date = Column(Date, nullable=False)
    useful_life_years = Column(Integer, nullable=False)
    depreciation_method = Column(String, nullable=False)
    residual_value = Column(Numeric, nullable=False)
    current_book_value = Column(Numeric, nullable=False)
    status = Column(String, default="pending_approval")


class PayrollEntry(Base):
    __tablename__ = "payroll_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entry_id = Column(String, nullable=False, unique=True, index=True)
    employee_name = Column(String, nullable=False)
    salary_amount = Column(Numeric, nullable=False)
    deductions = Column(Numeric, nullable=False)
    net_pay = Column(Numeric, nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    posted_date = Column(Date, nullable=False)


class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, nullable=False, unique=True, index=True)
    bank_account_id = Column(String, nullable=False, index=True)
    statement_date = Column(Date, nullable=False)
    run_date = Column(Date, nullable=False)
    status = Column(String, nullable=False, default="pending_approval")
    matched_count = Column(Integer, default=0)
    unmatched_count = Column(Integer, default=0)


class ReconciliationMatch(Base):
    __tablename__ = "reconciliation_matches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String, nullable=False, unique=True, index=True)
    run_id = Column(String, nullable=False, index=True)
    bank_txn_id = Column(String, nullable=False)
    journal_entry_id = Column(String, nullable=True)
    confidence = Column(Numeric, nullable=False)
    match_type = Column(String, nullable=False)
    status = Column(String, nullable=False, default="suggested")


class ChequeRegistry(Base):
    __tablename__ = "cheque_registry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cheque_id = Column(String, nullable=False, unique=True, index=True)
    vendor_name = Column(String, nullable=True)
    amount = Column(Numeric, nullable=False)
    issue_date = Column(Date, nullable=False)
    clearing_date = Column(Date, nullable=True)
    status = Column(String, nullable=False, default="issued")
    bank_account_id = Column(String, nullable=False, index=True)
    notes = Column(Text, nullable=True)


class LCBGRegistry(Base):
    __tablename__ = "lc_bg_registry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    lc_id = Column(String, nullable=False, unique=True, index=True)
    type = Column(String, nullable=False)
    beneficiary = Column(String, nullable=False)
    amount = Column(Numeric, nullable=False)
    currency = Column(String, nullable=False, default="PKR")
    issue_date = Column(Date, nullable=False)
    expiry_date = Column(Date, nullable=False)
    status = Column(String, nullable=False, default="active")
    notes = Column(Text, nullable=True)


class Budget(Base):
    __tablename__ = "budgets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    budget_id = Column(String, nullable=False, unique=True, index=True)
    fiscal_year = Column(Integer, nullable=False)
    period = Column(Integer, nullable=False)
    account_code = Column(String, nullable=False)
    budget_amount = Column(Numeric, nullable=False)
    created_at = Column(Date)


class Loan(Base):
    __tablename__ = "loans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    loan_id = Column(String, nullable=False, unique=True, index=True)
    loan_name = Column(String, nullable=False)
    principal_amount = Column(Numeric, nullable=False)
    interest_rate = Column(Numeric, nullable=False)
    term_months = Column(Integer, nullable=False)
    start_date = Column(Date, nullable=False)
    status = Column(String, nullable=False, default="active")


class LoanPaymentSchedule(Base):
    __tablename__ = "loan_payment_schedule"

    id = Column(Integer, primary_key=True, autoincrement=True)
    loan_id = Column(String, nullable=False, index=True)
    period_number = Column(Integer, nullable=False)
    payment_date = Column(Date, nullable=False)
    payment_amount = Column(Numeric, nullable=False)
    principal_amount = Column(Numeric, nullable=False)
    interest_amount = Column(Numeric, nullable=False)
    remaining_balance = Column(Numeric, nullable=False)


class PrepaidExpense(Base):
    __tablename__ = "prepaid_expenses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    prepaid_id = Column(String, nullable=False, unique=True, index=True)
    description = Column(String, nullable=False)
    total_amount = Column(Numeric, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    monthly_amount = Column(Numeric, nullable=False)
    remaining_balance = Column(Numeric, nullable=False)
    status = Column(String, default="active")


class DepreciationSchedule(Base):
    __tablename__ = "depreciation_schedule"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entry_id = Column(String, nullable=False, unique=True, index=True)
    asset_id = Column(String, nullable=False, index=True)
    period_date = Column(Date, nullable=False)
    monthly_depreciation = Column(Numeric, nullable=False)
    accumulated_depreciation = Column(Numeric, nullable=False)
    book_value = Column(Numeric, nullable=False)
    status = Column(String, default="posted")


class IntangibleAsset(Base):
    __tablename__ = "intangible_assets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(String, nullable=False, unique=True, index=True)
    asset_name = Column(String, nullable=False)
    cost = Column(Numeric, nullable=False)
    acquisition_date = Column(Date, nullable=False)
    useful_life_years = Column(Integer, nullable=False)
    residual_value = Column(Numeric, nullable=False)
    current_book_value = Column(Numeric, nullable=False)
    status = Column(String, default="active")


class AmortizationSchedule(Base):
    __tablename__ = "amortization_schedule"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entry_id = Column(String, nullable=False, unique=True, index=True)
    asset_id = Column(String, nullable=False, index=True)
    period_date = Column(Date, nullable=False)
    monthly_amortization = Column(Numeric, nullable=False)
    accumulated_amortization = Column(Numeric, nullable=False)
    book_value = Column(Numeric, nullable=False)
    status = Column(String, default="posted")


class CashFlowProjection(Base):
    __tablename__ = "cash_flow_projections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    projection_id = Column(String, nullable=False, unique=True, index=True)
    projected_date = Column(Date, nullable=False)
    projected_inflow = Column(Numeric, nullable=False)
    projected_outflow = Column(Numeric, nullable=False)
    net_cash_flow = Column(Numeric, nullable=False)
    confidence_level = Column(Numeric, nullable=False)
    generated_date = Column(Date, nullable=False)
    status = Column(String, default="pending_approval")


class RetainedEarnings(Base):
    __tablename__ = "retained_earnings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fiscal_year = Column(Integer, nullable=False, unique=True, index=True)
    beginning_balance = Column(Numeric, nullable=False, default=0)
    net_income = Column(Numeric, nullable=False, default=0)
    dividends = Column(Numeric, nullable=False, default=0)
    ending_balance = Column(Numeric, nullable=False, default=0)


class FiscalYearClose(Base):
    __tablename__ = "fiscal_year_close"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fiscal_year = Column(Integer, nullable=False, unique=True, index=True)
    closed_at = Column(Date, nullable=False)
    closed_by = Column(String, nullable=False, default="system")
    status = Column(String, nullable=False, default="closed")


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    from_currency = Column(String, nullable=False)
    to_currency = Column(String, nullable=False)
    rate = Column(Numeric, nullable=False)
    rate_date = Column(Date, nullable=False)
    source = Column(String, nullable=True)


class TaxRate(Base):
    __tablename__ = "tax_rates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tax_type = Column(String, nullable=False, index=True)
    rate = Column(Numeric, nullable=False)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    description = Column(String, nullable=True)


class EobiRate(Base):
    __tablename__ = "eobi_rates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rate_type = Column(String, nullable=False, index=True)
    rate = Column(Numeric, nullable=False)
    employee_rate = Column(Numeric, nullable=True)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    description = Column(String, nullable=True)
    max_insurable_amount = Column(Numeric, nullable=True)


class FlaggedEntry(Base):
    __tablename__ = "flagged_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entry_id = Column(String, ForeignKey("journal_entries.entry_id"), nullable=False, index=True)
    flag_type = Column(String, nullable=False)
    reason = Column(Text, nullable=False)
    severity = Column(String, nullable=False)
    flagged_by = Column(String, nullable=False, default="system")
    flagged_at = Column(Date, nullable=False)
    resolved_at = Column(Date, nullable=True)
    status = Column(String, nullable=False, default="open")


class StatutoryRegister(Base):
    __tablename__ = "statutory_registers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    register_id = Column(String, nullable=False, unique=True, index=True)
    register_type = Column(String, nullable=False)
    entry_date = Column(Date, nullable=False)
    description = Column(Text, nullable=False)
    reference_number = Column(String, nullable=True)
    amount = Column(Numeric, nullable=True)
    status = Column(String, nullable=False, default="pending_approval")
    filed_date = Column(Date, nullable=True)
    created_at = Column(Date, nullable=False)
    updated_at = Column(Date, nullable=False)


class ComplianceDeadline(Base):
    __tablename__ = "compliance_deadlines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    deadline_id = Column(String, nullable=False, unique=True, index=True)
    deadline_type = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=False)
    due_date = Column(Date, nullable=False)
    responsible_person = Column(String, nullable=True)
    status = Column(String, nullable=False, default="upcoming")
    reminder_days = Column(Integer, nullable=True)
    fiscal_year = Column(Integer, nullable=True)


class SystemConfig(Base):
    __tablename__ = "system_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_key = Column(String, nullable=False, unique=True, index=True)
    config_value = Column(String, nullable=False)
    description = Column(String, nullable=True)
    updated_at = Column(Date, nullable=False)


class SystemBackupLog(Base):
    __tablename__ = "system_backup_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    backup_id = Column(String, nullable=False, unique=True, index=True)
    backup_type = Column(String, nullable=False)
    status = Column(String, nullable=False, default="scheduled")
    triggered_by = Column(String, nullable=True)
    triggered_at = Column(Date, nullable=False)
    completed_at = Column(Date, nullable=True)
    size_bytes = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    parameters = Column(Text, nullable=True)


class UserApiKey(Base):
    __tablename__ = "user_api_keys"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    key_name = Column(String, unique=True, nullable=False)
    key_value = Column(String, nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    audit_id = Column(String, nullable=False, unique=True, index=True)
    user_id = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False)
    table_name = Column(String, nullable=False)
    record_id = Column(String, nullable=False)
    timestamp = Column(DateTime, nullable=False, default=func.now())


class UserRole(Base):
    __tablename__ = "user_roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    role_id = Column(String, nullable=False, unique=True, index=True)
    role_name = Column(String, nullable=False, unique=True, index=True)
    permissions = Column(Text, nullable=False)  # JSON-serialized list of permissions

