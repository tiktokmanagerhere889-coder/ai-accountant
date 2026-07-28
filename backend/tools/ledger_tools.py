"""Ledger & Master Data tools for Agent 2: create_journal_entry, get_general_ledger, suggest_chart_of_accounts."""

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from db.models import JournalEntry, PayrollEntry
from tools.schemas import (
    APEntryItem,
    AREntryItem,
    CreateJournalEntryInput,
    CreateJournalEntryOutput,
    GetAPSubledgerInput,
    GetAPSubledgerOutput,
    GetARSubledgerInput,
    GetARSubledgerOutput,
    GetGeneralLedgerInput,
    GetGeneralLedgerOutput,
    GetPayrollLedgerInput,
    GetPayrollLedgerOutput,
    LedgerAccountEntry,
    PayrollEntryItem,
    SuggestChartOfAccountsInput,
    SuggestChartOfAccountsOutput,
    SuggestedAccountItem,
)


# ---------------------------------------------------------------------------
# Helper – infer account type from numeric account code prefix
# ---------------------------------------------------------------------------

def _infer_account_type(account_code: str) -> str:
    """Infer account type (Asset, Liability, Equity, Revenue, Expense) from code prefix."""
    prefix = account_code.split("-")[0].split()[0] if account_code else ""
    if prefix.isdigit():
        first_digit = prefix[0]
        mapping = {
            "1": "Asset",
            "2": "Liability",
            "3": "Equity",
            "4": "Revenue",
            "5": "Cost of Goods Sold",
            "6": "Expense",
            "7": "Other Income",
            "8": "Other Expense",
            "9": "Contra Account",
        }
        return mapping.get(first_digit, "Unknown")
    return "Unknown"


def _split_account(value: str):
    """Split '1000-Cash' into (code, name). Returns (value, value) if no hyphen."""
    parts = value.split("-", 1)
    if len(parts) == 2 and parts[0].strip().isdigit():
        return parts[0].strip(), parts[1].strip()
    return value, value


# ---------------------------------------------------------------------------
# Tool 1 – Create Journal Entry
# ---------------------------------------------------------------------------

def create_journal_entry(input: CreateJournalEntryInput, db: Session) -> CreateJournalEntryOutput:
    """Create a double-entry journal entry with auto-generated entry_id.

    Validates that total debits equal total credits, generates an entry_id
    in the format JE-YYYYMMDD-NNN, and persists to the database.
    """
    # Validate debits == credits
    if input.debit_amount != input.credit_amount:
        raise ValueError(
            f"Debits ({input.debit_amount}) must equal credits ({input.credit_amount})"
        )

    # Auto-generate entry_id: JE-YYYYMMDD-NNN
    posted = input.posted_date
    date_part = posted.strftime("%Y%m%d")
    prefix = f"JE-{date_part}-"

    # Find the highest existing sequence number for this date prefix
    existing = db.execute(
        select(JournalEntry.entry_id).where(JournalEntry.entry_id.like(prefix + "%"))
    ).scalars().all()

    max_seq = 0
    for eid in existing:
        suffix = eid[len(prefix):]
        if suffix.isdigit():
            seq = int(suffix)
            if seq > max_seq:
                max_seq = seq

    next_seq = max_seq + 1
    entry_id = f"{prefix}{next_seq:03d}"

    # Safety check: ensure the generated ID is truly unique (should be, but guard)
    existing_check = db.execute(
        select(JournalEntry).where(JournalEntry.entry_id == entry_id)
    ).scalar_one_or_none()
    if existing_check is not None:
        raise ValueError(f"Generated entry_id '{entry_id}' already exists after retry")

    # Create the journal entry
    entry = JournalEntry(
        entry_id=entry_id,
        description=input.description,
        posted_date=input.posted_date,
        reference=input.reference,
        debit_account=input.debit_account,
        debit_amount=input.debit_amount,
        credit_account=input.credit_account,
        credit_amount=input.credit_amount,
        status=input.status,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    return CreateJournalEntryOutput(
        entry_id=entry.entry_id,
        description=entry.description,
        posted_date=entry.posted_date,
        reference=entry.reference,
        debit_account=entry.debit_account,
        debit_amount=entry.debit_amount,
        credit_account=entry.credit_account,
        credit_amount=entry.credit_amount,
        status=entry.status,
    )


# ---------------------------------------------------------------------------
# Tool 2 – Get General Ledger
# ---------------------------------------------------------------------------

def get_general_ledger(input: GetGeneralLedgerInput, db: Session) -> GetGeneralLedgerOutput:
    """Query the general ledger aggregated by account over a date range.

    Groups all posted journal entries by account, sums debits and credits,
    and returns per-account totals. Optionally filters by account code prefix.
    """
    if input.from_date > input.to_date:
        raise ValueError(
            f"from_date ({input.from_date}) must not be after to_date ({input.to_date})"
        )

    # Fetch all entries in date range
    query = select(JournalEntry).where(
        JournalEntry.posted_date >= input.from_date,
        JournalEntry.posted_date <= input.to_date,
    )
    entries = db.execute(query).scalars().all()

    if not entries:
        return GetGeneralLedgerOutput(
            period_from=input.from_date,
            period_to=input.to_date,
            accounts=[],
            total_debits=Decimal("0.00"),
            total_credits=Decimal("0.00"),
        )

    # Aggregate by account
    account_data = {}  # account_code -> {name, type, debits, credits}

    def ensure_account(acc_value: str):
        code, name = _split_account(acc_value)
        if code not in account_data:
            account_data[code] = {
                "account_code": code,
                "account_name": name,
                "account_type": _infer_account_type(acc_value),
                "total_debits": Decimal("0.00"),
                "total_credits": Decimal("0.00"),
            }

    for entry in entries:
        ensure_account(entry.debit_account)
        ensure_account(entry.credit_account)
        account_data[_split_account(entry.debit_account)[0]]["total_debits"] += entry.debit_amount
        account_data[_split_account(entry.credit_account)[0]]["total_credits"] += entry.credit_amount

    # Build account entry list
    accounts = []
    for data in account_data.values():
        net = data["total_debits"] - data["total_credits"]
        accounts.append(LedgerAccountEntry(
            account_code=data["account_code"],
            account_name=data["account_name"],
            account_type=data["account_type"],
            opening_balance=Decimal("0.00"),
            total_debits=data["total_debits"],
            total_credits=data["total_credits"],
            net_movement=net,
            closing_balance=net,
        ))

    # Apply account_code_prefix filter if provided
    if input.account_code_prefix is not None:
        prefix = input.account_code_prefix.strip()
        if prefix:
            accounts = [a for a in accounts if a.account_code.startswith(prefix)]

    # Sort by account_code
    accounts.sort(key=lambda a: a.account_code)

    total_debits = sum(a.total_debits for a in accounts)
    total_credits = sum(a.total_credits for a in accounts)

    return GetGeneralLedgerOutput(
        period_from=input.from_date,
        period_to=input.to_date,
        accounts=accounts,
        total_debits=total_debits,
        total_credits=total_credits,
    )


# ---------------------------------------------------------------------------
# Tool 3 – Suggest Chart of Accounts
# ---------------------------------------------------------------------------

# Standard charts of accounts by business type
_CHARTS = {
    "retail": [
        ("1000", "Cash", "Asset", "Cash on hand and in bank accounts"),
        ("1100", "Accounts Receivable", "Asset", "Amounts owed by customers"),
        ("1200", "Inventory", "Asset", "Goods available for sale"),
        ("1300", "Prepaid Expenses", "Asset", "Prepaid rent, insurance, etc."),
        ("1400", "Equipment (Store)", "Asset", "Store fixtures and equipment"),
        ("2000", "Accounts Payable", "Liability", "Amounts owed to suppliers"),
        ("2100", "Short-term Loans", "Liability", "Loans due within 12 months"),
        ("3000", "Owner's Equity", "Equity", "Owner capital contribution"),
        ("4000", "Sales Revenue", "Revenue", "Revenue from goods sold"),
        ("4100", "Sales Returns & Allowances", "Revenue", "Refunds and adjustments"),
        ("5000", "Cost of Goods Sold", "Cost of Goods Sold", "Direct cost of merchandise sold"),
        ("6000", "Salaries & Wages", "Expense", "Employee compensation"),
        ("6100", "Rent Expense", "Expense", "Store and office rent"),
        ("6200", "Utilities Expense", "Expense", "Electricity, water, internet"),
        ("6300", "Marketing & Advertising", "Expense", "Promotional costs"),
        ("6400", "Office Supplies", "Expense", "Office consumables"),
    ],
    "freelance": [
        ("1000", "Cash", "Asset", "Cash on hand and in bank accounts"),
        ("1100", "Accounts Receivable", "Asset", "Outstanding client invoices"),
        ("2000", "Accounts Payable", "Liability", "Amounts owed to vendors"),
        ("3000", "Owner's Equity", "Equity", "Owner capital and retained earnings"),
        ("4000", "Service Revenue", "Revenue", "Income from services rendered"),
        ("6000", "Software & Subscriptions", "Expense", "SaaS tools and licenses"),
        ("6100", "Office Expense", "Expense", "Home office and supplies"),
        ("6200", "Marketing & Branding", "Expense", "Website, ads, portfolio"),
        ("6300", "Professional Development", "Expense", "Courses, certifications, events"),
        ("6400", "Travel & Meals", "Expense", "Client meetings and business travel"),
        ("6500", "Taxes & Licenses", "Expense", "Business taxes and permits"),
    ],
    "manufacturing": [
        ("1000", "Cash", "Asset", "Cash on hand and in bank accounts"),
        ("1100", "Accounts Receivable", "Asset", "Amounts owed by customers"),
        ("1200", "Raw Materials Inventory", "Asset", "Unprocessed materials"),
        ("1300", "Work in Progress", "Asset", "Partially finished goods"),
        ("1400", "Finished Goods Inventory", "Asset", "Completed goods ready for sale"),
        ("1500", "Property, Plant & Equipment", "Asset", "Factory buildings and machinery"),
        ("1600", "Accumulated Depreciation", "Asset", "Contra-asset for wear and tear"),
        ("2000", "Accounts Payable", "Liability", "Amounts owed to suppliers"),
        ("2100", "Short-term Loans", "Liability", "Loans due within 12 months"),
        ("2200", "Long-term Loans", "Liability", "Loans due beyond 12 months"),
        ("3000", "Owner's Equity", "Equity", "Owner capital"),
        ("3100", "Retained Earnings", "Equity", "Accumulated profits"),
        ("4000", "Sales Revenue", "Revenue", "Revenue from product sales"),
        ("5000", "Raw Materials Used", "Cost of Goods Sold", "Cost of direct materials"),
        ("5100", "Direct Labor", "Cost of Goods Sold", "Factory labor costs"),
        ("5200", "Manufacturing Overhead", "Cost of Goods Sold", "Indirect factory costs"),
        ("6000", "Salaries & Wages", "Expense", "Non-factory employee compensation"),
        ("6100", "Rent Expense", "Expense", "Office and facility rent"),
        ("6200", "Utilities Expense", "Expense", "Electricity, water, gas"),
        ("6300", "Depreciation Expense", "Expense", "Asset depreciation"),
        ("6400", "Maintenance & Repairs", "Expense", "Equipment upkeep"),
    ],
    "tech_startup": [
        ("1000", "Cash", "Asset", "Cash on hand and in bank accounts"),
        ("1100", "Accounts Receivable", "Asset", "Outstanding client invoices"),
        ("1200", "Prepaid Expenses", "Asset", "Prepaid SaaS and services"),
        ("1300", "Equipment & Computers", "Asset", "Laptops, servers, peripherals"),
        ("2000", "Accounts Payable", "Liability", "Amounts owed to vendors"),
        ("2100", "Deferred Revenue", "Liability", "Customer prepayments"),
        ("2200", "Accrued Salaries", "Liability", "Unpaid employee wages"),
        ("3000", "Investor Equity", "Equity", "Paid-in capital from investors"),
        ("3100", "Retained Earnings", "Equity", "Accumulated profits and losses"),
        ("4000", "Subscription Revenue", "Revenue", "Recurring SaaS revenue"),
        ("4100", "Service Revenue", "Revenue", "Consulting and implementation"),
        ("6000", "Salaries & Benefits", "Expense", "Employee compensation"),
        ("6100", "Cloud Infrastructure", "Expense", "AWS, GCP, Azure costs"),
        ("6200", "Software Licenses", "Expense", "Third-party SaaS tools"),
        ("6300", "Marketing & Sales", "Expense", "Ads, content, sales tools"),
        ("6400", "Office & Facilities", "Expense", "Rent, utilities, supplies"),
        ("6500", "Legal & Professional", "Expense", "Lawyers, accountants, consultants"),
    ],
    "restaurant": [
        ("1000", "Cash", "Asset", "Cash on hand and in bank"),
        ("1100", "Accounts Receivable", "Asset", "Catering and event receivables"),
        ("1200", "Food & Beverage Inventory", "Asset", "Ingredients and drinks"),
        ("1300", "Kitchen Equipment", "Asset", "Ovens, fryers, refrigerators"),
        ("1400", "Furniture & Fixtures", "Asset", "Tables, chairs, decor"),
        ("2000", "Accounts Payable", "Liability", "Supplier invoices"),
        ("2100", "Accrued Wages", "Liability", "Unpaid staff wages"),
        ("3000", "Owner's Equity", "Equity", "Owner investment"),
        ("4000", "Food Sales", "Revenue", "Dine-in and takeaway revenue"),
        ("4100", "Beverage Sales", "Revenue", "Drink sales revenue"),
        ("5000", "Cost of Food Sold", "Cost of Goods Sold", "Direct food cost"),
        ("5100", "Cost of Beverages", "Cost of Goods Sold", "Direct beverage cost"),
        ("6000", "Staff Wages", "Expense", "Kitchen and waitstaff pay"),
        ("6100", "Rent & Utilities", "Expense", "Lease and utilities"),
        ("6200", "Licenses & Permits", "Expense", "Liquor license, health permits"),
        ("6300", "Cleaning & Maintenance", "Expense", "Janitorial and repairs"),
    ],
    "non_profit": [
        ("1000", "Cash", "Asset", "Cash on hand and in bank"),
        ("1100", "Pledges Receivable", "Asset", "Donor pledges not yet received"),
        ("1200", "Prepaid Expenses", "Asset", "Prepaid program costs"),
        ("2000", "Accounts Payable", "Liability", "Amounts owed to vendors"),
        ("2100", "Deferred Revenue", "Liability", "Grant funds received in advance"),
        ("3000", "Net Assets Without Restrictions", "Equity", "Unrestricted fund balance"),
        ("3100", "Net Assets With Restrictions", "Equity", "Donor-restricted fund balance"),
        ("4000", "Donations & Contributions", "Revenue", "Individual and corporate donations"),
        ("4100", "Grant Revenue", "Revenue", "Foundation and government grants"),
        ("4200", "Program Service Revenue", "Revenue", "Fees from programs"),
        ("6000", "Program Expenses", "Expense", "Direct program costs"),
        ("6100", "Salaries & Benefits", "Expense", "Staff compensation"),
        ("6200", "Rent & Utilities", "Expense", "Facility costs"),
        ("6300", "Fundraising Expenses", "Expense", "Campaign and event costs"),
    ],
    "real_estate": [
        ("1000", "Cash", "Asset", "Cash on hand and in bank accounts"),
        ("1100", "Rental Properties", "Asset", "Residential and commercial properties"),
        ("1200", "Land Holdings", "Asset", "Land held for investment"),
        ("1300", "Accounts Receivable", "Asset", "Outstanding tenant rent payments"),
        ("1400", "Accumulated Depreciation", "Asset", "Contra-asset for property depreciation"),
        ("2000", "Accounts Payable", "Liability", "Contractor and vendor invoices"),
        ("2100", "Mortgage Payable", "Liability", "Property loans"),
        ("2200", "Security Deposits Held", "Liability", "Tenant security deposits"),
        ("3000", "Owner's Equity", "Equity", "Owner investment"),
        ("4000", "Rental Income", "Revenue", "Rental revenue from tenants"),
        ("4100", "Other Property Income", "Revenue", "Parking, laundry, late fees"),
        ("6000", "Property Maintenance", "Expense", "Repairs and upkeep"),
        ("6100", "Property Management Fees", "Expense", "Management company costs"),
        ("6200", "Insurance", "Expense", "Property insurance premiums"),
        ("6300", "Property Taxes", "Expense", "Real estate taxes"),
        ("6400", "Mortgage Interest", "Expense", "Interest on property loans"),
        ("6500", "Depreciation Expense", "Expense", "Property depreciation"),
    ],
    "service_based": [
        ("1000", "Cash", "Asset", "Cash on hand and in bank accounts"),
        ("1100", "Accounts Receivable", "Asset", "Outstanding client invoices"),
        ("1200", "Prepaid Expenses", "Asset", "Prepaid insurance and subscriptions"),
        ("2000", "Accounts Payable", "Liability", "Vendor invoices"),
        ("2100", "Unearned Revenue", "Liability", "Client prepayments"),
        ("3000", "Owner's Equity", "Equity", "Owner capital"),
        ("4000", "Service Revenue", "Revenue", "Revenue from client services"),
        ("4100", "Consulting Revenue", "Revenue", "Consulting and advisory fees"),
        ("6000", "Salaries & Wages", "Expense", "Employee compensation"),
        ("6100", "Rent & Utilities", "Expense", "Office costs"),
        ("6200", "Travel & Transportation", "Expense", "Client-site visits and travel"),
        ("6300", "Marketing & Advertising", "Expense", "Lead generation and branding"),
        ("6400", "Professional Fees", "Expense", "Subcontractors and legal"),
        ("6500", "Office Supplies", "Expense", "General office consumables"),
    ],
}

_UNKNOWN_TYPE_TEMPLATE = [
    ("1000", "Cash", "Asset", "Cash on hand and in bank accounts"),
    ("2000", "Accounts Payable", "Liability", "Amounts owed to vendors"),
    ("3000", "Owner's Equity", "Equity", "Owner capital contribution"),
    ("4000", "Revenue", "Revenue", "Business revenue"),
    ("6000", "Operating Expenses", "Expense", "General operating expenses"),
]


def suggest_chart_of_accounts(input: SuggestChartOfAccountsInput, db: Optional[Session] = None) -> SuggestChartOfAccountsOutput:
    """Suggest a standard chart of accounts for a given business type.

    Returns a predefined chart structure based on business category.
    Not LLM-based; uses a static mapping. Requires approval before use.
    """
    # Normalize business type key: lowercase, strip, replace spaces/special chars
    normalized = input.business_type.strip().lower()
    normalized = normalized.replace(" ", "_").replace("-", "_")

    # Map common variations
    alias_map = {
        "retail": "retail",
        "retail_store": "retail",
        "freelance": "freelance",
        "freelancer": "freelance",
        "independent_contractor": "freelance",
        "manufacturing": "manufacturing",
        "manufacturer": "manufacturing",
        "factory": "manufacturing",
        "tech_startup": "tech_startup",
        "technology": "tech_startup",
        "startup": "tech_startup",
        "saas": "tech_startup",
        "software": "tech_startup",
        "restaurant": "restaurant",
        "restaurant_and_catering": "restaurant",
        "cafe": "restaurant",
        "food_service": "restaurant",
        "non_profit": "non_profit",
        "nonprofit": "non_profit",
        "charity": "non_profit",
        "ngo": "non_profit",
        "real_estate": "real_estate",
        "realestate": "real_estate",
        "property": "real_estate",
        "property_management": "real_estate",
        "service_based": "service_based",
        "service": "service_based",
        "consulting": "service_based",
        "agency": "service_based",
    }

    resolved = alias_map.get(normalized)
    if resolved is None:
        raise ValueError(
            f"Unknown business type: '{input.business_type}'. "
            f"Supported types: {', '.join(sorted(_CHARTS.keys()))}"
        )

    chart = _CHARTS[resolved]
    accounts = [
        SuggestedAccountItem(account_code=code, account_name=name, account_type=atype, description=desc)
        for code, name, atype, desc in chart
    ]

    return SuggestChartOfAccountsOutput(
        business_type=resolved,
        accounts=accounts,
        total_count=len(accounts),
        needs_approval=True,
    )


# ---------------------------------------------------------------------------
# Tool 4 – Get AP Subledger
# ---------------------------------------------------------------------------

def get_ap_subledger(
    db: Session,
    inp: GetAPSubledgerInput,
) -> GetAPSubledgerOutput:
    """Retrieve AP (accounts payable) subledger grouped by vendor reference.

    Queries journal_entries where debit_account starts with "2000",
    groups by the reference field, and calculates outstanding totals.
    """
    query = db.query(
        JournalEntry.reference,
        func.sum(JournalEntry.debit_amount).label("total_amount"),
        func.count(JournalEntry.id).label("entry_count"),
        func.max(JournalEntry.posted_date).label("latest_date"),
        func.min(JournalEntry.entry_id).label("first_entry_id"),
    ).filter(
        JournalEntry.debit_account.startswith("2000"),
        JournalEntry.posted_date >= inp.from_date,
        JournalEntry.posted_date <= inp.to_date,
        JournalEntry.reference.isnot(None),
    )

    if inp.vendor_contact_id is not None:
        query = query.filter(JournalEntry.reference == inp.vendor_contact_id)

    rows = (
        query.group_by(JournalEntry.reference)
        .order_by(JournalEntry.reference)
        .all()
    )

    entries = []
    total_outstanding = Decimal("0.00")
    for row in rows:
        amt = (
            Decimal(str(row.total_amount))
            if row.total_amount is not None
            else Decimal("0.00")
        )
        entries.append(APEntryItem(
            entry_id=row.first_entry_id or "",
            vendor_name=row.reference or "",
            invoice_amount=amt,
            paid_amount=Decimal("0.00"),
            outstanding_balance=amt,
            due_date=row.latest_date,
            status="open",
        ))
        total_outstanding += amt

    return GetAPSubledgerOutput(
        entries=entries,
        total_outstanding=total_outstanding,
        total_paid=Decimal("0.00"),
        period_from=inp.from_date,
        period_to=inp.to_date,
    )


# ---------------------------------------------------------------------------
# Tool 5 – Get AR Subledger
# ---------------------------------------------------------------------------

def get_ar_subledger(
    db: Session,
    inp: GetARSubledgerInput,
) -> GetARSubledgerOutput:
    """Retrieve AR (accounts receivable) subledger grouped by customer reference.

    Queries journal_entries where debit_account starts with "1200",
    groups by the reference field, and calculates outstanding totals.
    """
    query = db.query(
        JournalEntry.reference,
        func.sum(JournalEntry.debit_amount).label("total_amount"),
        func.count(JournalEntry.id).label("entry_count"),
        func.max(JournalEntry.posted_date).label("latest_date"),
        func.min(JournalEntry.entry_id).label("first_entry_id"),
    ).filter(
        JournalEntry.debit_account.startswith("1200"),
        JournalEntry.posted_date >= inp.from_date,
        JournalEntry.posted_date <= inp.to_date,
        JournalEntry.reference.isnot(None),
    )

    if inp.customer_contact_id is not None:
        query = query.filter(JournalEntry.reference == inp.customer_contact_id)

    rows = (
        query.group_by(JournalEntry.reference)
        .order_by(JournalEntry.reference)
        .all()
    )

    entries = []
    total_outstanding = Decimal("0.00")
    for row in rows:
        amt = (
            Decimal(str(row.total_amount))
            if row.total_amount is not None
            else Decimal("0.00")
        )
        entries.append(AREntryItem(
            entry_id=row.first_entry_id or "",
            customer_name=row.reference or "",
            invoice_amount=amt,
            received_amount=Decimal("0.00"),
            outstanding_balance=amt,
            due_date=row.latest_date,
            status="open",
        ))
        total_outstanding += amt

    return GetARSubledgerOutput(
        entries=entries,
        total_outstanding=total_outstanding,
        total_received=Decimal("0.00"),
        period_from=inp.from_date,
        period_to=inp.to_date,
    )


# ---------------------------------------------------------------------------
# Tool 6 – Get Payroll Ledger
# ---------------------------------------------------------------------------

def get_payroll_ledger(
    db: Session,
    inp: GetPayrollLedgerInput,
) -> GetPayrollLedgerOutput:
    """Retrieve payroll ledger entries with totals and warning flags.

    Queries the payroll_entries table. Flags entries where deductions
    exceed salary with a warning. Returns per-employee entries along
    with aggregate totals.
    """
    query = db.query(PayrollEntry).filter(
        PayrollEntry.posted_date >= inp.from_date,
        PayrollEntry.posted_date <= inp.to_date,
    )

    if inp.employee_name is not None:
        query = query.filter(PayrollEntry.employee_name == inp.employee_name)

    rows = query.order_by(
        PayrollEntry.employee_name, PayrollEntry.posted_date
    ).all()

    entries = []
    total_salary = Decimal("0.00")
    total_deductions = Decimal("0.00")
    total_net_pay = Decimal("0.00")

    for row in rows:
        salary = Decimal(str(row.salary_amount))
        deductions = Decimal(str(row.deductions))
        net_pay = Decimal(str(row.net_pay))
        has_warning = deductions > salary

        entries.append(PayrollEntryItem(
            entry_id=row.entry_id,
            employee_name=row.employee_name,
            salary_amount=salary,
            deductions=deductions,
            net_pay=net_pay,
            period_start=row.period_start,
            period_end=row.period_end,
            posted_date=row.posted_date,
            warning=has_warning,
        ))
        total_salary += salary
        total_deductions += deductions
        total_net_pay += net_pay

    return GetPayrollLedgerOutput(
        entries=entries,
        total_salary=total_salary,
        total_deductions=total_deductions,
        total_net_pay=total_net_pay,
        period_from=inp.from_date,
        period_to=inp.to_date,
    )
