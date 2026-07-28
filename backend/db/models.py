from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Column,
    Date,
    Integer,
    Numeric,
    String,
    Text,
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
