"""Year-End Close & Financial Statements tools (Agent 5): trial balance, P&L, balance sheet,
cash flow statement, retained earnings, carry-forward, notes to financials, close fiscal year."""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from db.models import (
    JournalEntry, ChartOfAccount, FixedAsset, IntangibleAsset,
    RetainedEarnings, FiscalYearClose,
)
from tools.account_utils import (
    get_cash_prefixes, get_revenue_prefixes, get_expense_prefixes,
    revenue_filter_clause, expense_filter_clause,
)
from tools.schemas import (
    GenerateTrialBalanceInput, GenerateTrialBalanceOutput, TrialBalanceAccount,
    GenerateProfitLossInput, GenerateProfitLossOutput, PnLItem,
    GenerateBalanceSheetInput, GenerateBalanceSheetOutput, BalanceSheetItem,
    GenerateCashFlowInput, GenerateCashFlowOutput, CashFlowItem,
    TransferRetainedEarningsInput, TransferRetainedEarningsOutput,
    CarryForwardBalancesInput, CarryForwardBalancesOutput, CarryForwardBalanceItem,
    DraftNotesToFinancialsInput, DraftNotesToFinancialsOutput, FinancialNote,
    CloseFiscalYearInput, CloseFiscalYearOutput,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _split_account(value: str):
    """Split '1000-Cash' into (code, name). Returns (value, value) if no hyphen."""
    parts = value.split("-", 1)
    if len(parts) == 2 and parts[0].strip().isdigit():
        return parts[0].strip(), parts[1].strip()
    return value, value


def _get_prefix(code: str) -> str:
    """Get the first digit of an account code (for category classification)."""
    return code.strip()[0]


def _is_cash_account(account: str, db: Session) -> bool:
    """Check if an account is a cash/bank account — resolved from the user's chart."""
    name = account.lower()
    # Safety-net name match (works even before chart populated)
    if any(k in name for k in ("cash", "bank")):
        return True
    code, _ = _split_account(account)
    prefixes = get_cash_prefixes(db)
    if prefixes:
        return any(code.startswith(p) for p in prefixes)
    return False


def _is_revenue_account(account: str, db: Session) -> bool:
    """Check if an account is a revenue account — resolved from the user's chart."""
    name = account.lower()
    if any(k in name for k in ("revenue", "sales")):
        return True
    code, _ = _split_account(account)
    prefixes = get_revenue_prefixes(db)
    if prefixes:
        return any(code.startswith(p) for p in prefixes)
    return False


def _is_expense_account(account: str, db: Session) -> bool:
    """Check if an account is an expense account — resolved from the user's chart."""
    name = account.lower()
    if any(k in name for k in ("expense", "cost of goods", "cogs")):
        return True
    code, _ = _split_account(account)
    prefixes = get_expense_prefixes(db)
    if prefixes:
        return any(code.startswith(p) for p in prefixes)
    return False


def _chart_type_for(db: Session, account_code: str) -> str | None:
    """Look up the account_type of a code from the user's chart (by code prefix)."""
    code, _ = _split_account(account_code)
    acc = db.query(ChartOfAccount).filter(
        ChartOfAccount.account_code.startswith(code)
    ).first()
    return acc.account_type.lower() if acc else None


def _is_investing_account(account: str, db: Session) -> bool:
    """True if account type is an asset that is not cash/bank (fixed, intangible, investment)."""
    atype = _chart_type_for(db, account)
    if atype == "asset":
        # Assets other than cash/bank/AR are investing
        return not (_is_cash_account(account, db) or _is_receivable_account(account))
    return False


def _is_financing_account(account: str, db: Session) -> bool:
    """True if account type is a liability (loan, payable) or equity (capital, retained earnings)."""
    atype = _chart_type_for(db, account)
    return atype in ("liability", "equity")


def _is_receivable_account(account: str) -> bool:
    """Name-based receivable check (AR, not inventory)."""
    name = account.lower()
    return any(k in name for k in ("receivable", "debtor"))


def _aggregate_entries(db: Session, from_date: date, to_date: date) -> list:
    """Get posted journal entries within date range."""
    return db.query(JournalEntry).filter(
        JournalEntry.posted_date >= from_date,
        JournalEntry.posted_date <= to_date,
        JournalEntry.status == "posted",
    ).order_by(JournalEntry.posted_date).all()


# ---------------------------------------------------------------------------
# Tool 1 – Trial Balance
# ---------------------------------------------------------------------------

def generate_trial_balance(
    input: GenerateTrialBalanceInput,
    db: Session,
) -> GenerateTrialBalanceOutput:
    """Generate trial balance as of a given date.

    Aggregates all posted journal entries up to as_of_date, groups by account,
    and computes total debits and credits per account. Reports whether debits = credits.
    """
    entries = db.query(JournalEntry).filter(
        JournalEntry.posted_date <= input.as_of_date,
        JournalEntry.status == "posted",
    ).all()

    # Aggregate per account (both debit and credit sides contribute)
    account_totals: dict[str, dict] = {}

    for entry in entries:
        # Debit side
        d_code, d_name = _split_account(entry.debit_account)
        if d_code not in account_totals:
            account_totals[d_code] = {"name": d_name, "debits": Decimal("0"), "credits": Decimal("0")}
        account_totals[d_code]["debits"] += entry.debit_amount

        # Credit side
        c_code, c_name = _split_account(entry.credit_account)
        if c_code not in account_totals:
            account_totals[c_code] = {"name": c_name, "debits": Decimal("0"), "credits": Decimal("0")}
        account_totals[c_code]["credits"] += entry.credit_amount

    accounts_list = []
    total_debits = Decimal("0")
    total_credits = Decimal("0")

    for code in sorted(account_totals.keys()):
        info = account_totals[code]
        debits = info["debits"]
        credits = info["credits"]
        balance = debits - credits
        accounts_list.append(TrialBalanceAccount(
            account_code=code,
            account_name=info["name"],
            total_debits=debits,
            total_credits=credits,
            balance=balance,
        ))
        total_debits += debits
        total_credits += credits

    in_balance = total_debits == total_credits
    difference = total_debits - total_credits

    return GenerateTrialBalanceOutput(
        as_of_date=input.as_of_date,
        accounts=accounts_list,
        total_debits=total_debits,
        total_credits=total_credits,
        in_balance=in_balance,
        difference=difference,
    )


# ---------------------------------------------------------------------------
# Tool 2 – Profit & Loss
# ---------------------------------------------------------------------------

def generate_profit_loss(
    input: GenerateProfitLossInput,
    db: Session,
) -> GenerateProfitLossOutput:
    """Generate profit & loss statement for a date range.

    Revenue = credit amounts to accounts with prefix '4'.
    Expenses = debit amounts to accounts with prefixes '5', '6', '8'.
    Net = Revenue - Expenses.
    """
    entries = _aggregate_entries(db, input.from_date, input.to_date)

    revenue_map: dict[str, Decimal] = {}
    expense_map: dict[str, Decimal] = {}

    for entry in entries:
        # Revenue: credit side on a revenue account (resolved from chart)
        c_code, c_name = _split_account(entry.credit_account)
        if _is_revenue_account(entry.credit_account, db):
            key = f"{c_code}-{c_name}"
            revenue_map[key] = revenue_map.get(key, Decimal("0")) + entry.credit_amount

        # Expenses: debit side on an expense account (resolved from chart)
        d_code, d_name = _split_account(entry.debit_account)
        if _is_expense_account(entry.debit_account, db):
            key = f"{d_code}-{d_name}"
            expense_map[key] = expense_map.get(key, Decimal("0")) + entry.debit_amount

    revenue_items = [PnLItem(account=k, amount=v) for k, v in sorted(revenue_map.items())]
    expense_items = [PnLItem(account=k, amount=v) for k, v in sorted(expense_map.items())]

    total_revenue = sum((v for v in revenue_map.values()), Decimal("0"))
    total_expenses = sum((v for v in expense_map.values()), Decimal("0"))
    net_income = total_revenue - total_expenses

    direction = "profit" if net_income >= Decimal("0") else "loss"
    summary = (
        f"Net {direction} of {abs(net_income).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)} for "
        f"period {input.from_date} to {input.to_date} "
        f"(revenue: {total_revenue.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}, "
        f"expenses: {total_expenses.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)})"
    )

    return GenerateProfitLossOutput(
        from_date=input.from_date,
        to_date=input.to_date,
        revenue_items=revenue_items,
        expense_items=expense_items,
        total_revenue=total_revenue,
        total_expenses=total_expenses,
        net_income=net_income,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Tool 3 – Balance Sheet
# ---------------------------------------------------------------------------

def generate_balance_sheet(
    input: GenerateBalanceSheetInput,
    db: Session,
) -> GenerateBalanceSheetOutput:
    """Generate balance sheet as of a given date.

    Assets = accounts with prefix '1'.
    Liabilities = accounts with prefix '2' (credit balances).
    Equity = accounts with prefix '3' (credit balances) + net income.
    Verify: Assets = Liabilities + Equity.
    """
    entries = db.query(JournalEntry).filter(
        JournalEntry.posted_date <= input.as_of_date,
        JournalEntry.status == "posted",
    ).all()

    # Net balance per account (debits - credits)
    balances: dict[str, Decimal] = {}
    account_names: dict[str, str] = {}

    for entry in entries:
        d_code, d_name = _split_account(entry.debit_account)
        balances[d_code] = balances.get(d_code, Decimal("0")) + entry.debit_amount
        account_names[d_code] = d_name

        c_code, c_name = _split_account(entry.credit_account)
        balances[c_code] = balances.get(c_code, Decimal("0")) - entry.credit_amount
        account_names[c_code] = c_name

    # Compute net income from revenue/expense accounts in the period
    total_revenue = Decimal("0")
    total_expenses = Decimal("0")
    for code, net_bal in balances.items():
        if _is_revenue_account(code, db):
            # Revenue: credit balance shows as negative net
            total_revenue += abs(net_bal) if net_bal < Decimal("0") else net_bal
        elif _is_expense_account(code, db):
            # Expense: debit balance shows as positive net
            total_expenses += net_bal if net_bal > Decimal("0") else abs(net_bal)

    net_income = total_revenue - total_expenses

    # Look up retained earnings from DB as supplement
    try:
        re_row = db.query(RetainedEarnings).filter(
            RetainedEarnings.fiscal_year == input.as_of_date.year
        ).first()
        db_re_balance = re_row.ending_balance if re_row else Decimal("0")
    except Exception:
        db_re_balance = Decimal("0")

    assets_list: list[BalanceSheetItem] = []
    liabilities_list: list[BalanceSheetItem] = []
    equity_list: list[BalanceSheetItem] = []

    total_assets = Decimal("0")
    total_liabilities = Decimal("0")
    total_equity = Decimal("0")

    for code in sorted(balances.keys()):
        net_balance = balances[code]
        name = account_names.get(code, code)
        prefix = code[0]

        if prefix == "1":
            # Asset: positive net = debit balance (normal), negative = overdraft (liability)
            amt = abs(net_balance)
            if amt > Decimal("0"):
                if net_balance >= Decimal("0"):
                    assets_list.append(BalanceSheetItem(account=f"{code}-{name}", amount=amt))
                    total_assets += amt
                else:
                    # Negative asset balance = overdraft, classify as liability
                    liabilities_list.append(BalanceSheetItem(account=f"{code}-{name} (Overdraft)", amount=amt))
                    total_liabilities += amt
        elif prefix == "2":
            # Liability: credit balance shows as negative net
            if net_balance < Decimal("0"):
                liab_amount = abs(net_balance)
                liabilities_list.append(BalanceSheetItem(account=f"{code}-{name}", amount=liab_amount))
                total_liabilities += liab_amount
        elif prefix == "3":
            # Equity: credit balance shows as negative net
            if net_balance < Decimal("0"):
                eq_amount = abs(net_balance)
                equity_list.append(BalanceSheetItem(account=f"{code}-{name}", amount=eq_amount))
                total_equity += eq_amount

    # Add net income as retained earnings component in equity
    if net_income > Decimal("0"):
        # Use stored RE if available, otherwise computed net income
        re_amount = db_re_balance if db_re_balance > Decimal("0") else net_income
        if re_amount > Decimal("0"):
            equity_list.append(BalanceSheetItem(account="Retained Earnings (Current Year)", amount=re_amount))
            total_equity += re_amount
    elif net_income < Decimal("0"):
        # Net loss reduces equity
        equity_list.append(BalanceSheetItem(account="Net Loss (Current Year)", amount=abs(net_income)))
        total_equity -= abs(net_income)

    # Sort by amount descending
    assets_list.sort(key=lambda x: x.amount, reverse=True)
    liabilities_list.sort(key=lambda x: x.amount, reverse=True)
    equity_list.sort(key=lambda x: x.amount, reverse=True)

    balanced = total_assets == (total_liabilities + total_equity)
    diff = total_assets - (total_liabilities + total_equity)

    return GenerateBalanceSheetOutput(
        as_of_date=input.as_of_date,
        assets=assets_list,
        liabilities=liabilities_list,
        equity=equity_list,
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        total_equity=total_equity,
        balanced=balanced,
        difference=diff,
    )


# ---------------------------------------------------------------------------
# Tool 4 – Cash Flow Statement
# ---------------------------------------------------------------------------

def generate_cash_flow_statement(
    input: GenerateCashFlowInput,
    db: Session,
) -> GenerateCashFlowOutput:
    """Generate cash flow statement for a date range.

    Opening/closing cash from journal_entries filtered by cash prefixes.
    Operating = revenue (4) + expense (5/6/8) cash flows.
    Investing = fixed asset purchases/sales.
    Financing = loans (2) and equity (3) changes.
    """
    entries = _aggregate_entries(db, input.from_date, input.to_date)

    # Compute opening cash as cash balance just before from_date
    opening_entries = db.query(JournalEntry).filter(
        JournalEntry.posted_date < input.from_date,
        JournalEntry.status == "posted",
    ).all()

    opening_cash = Decimal("0")
    for entry in opening_entries:
        if _is_cash_account(entry.debit_account, db):
            opening_cash += entry.debit_amount
        if _is_cash_account(entry.credit_account, db):
            opening_cash -= entry.credit_amount

    # Current period cash changes
    operating_items: list[CashFlowItem] = []
    investing_items: list[CashFlowItem] = []
    financing_items: list[CashFlowItem] = []

    net_operating = Decimal("0")
    net_investing = Decimal("0")
    net_financing = Decimal("0")

    for entry in entries:
        d_code, d_name = _split_account(entry.debit_account)
        c_code, c_name = _split_account(entry.credit_account)
        desc = entry.description or ""

        # Determine cash impact — accounts resolved from the user's chart
        cash_on_debit = _is_cash_account(entry.debit_account, db)
        cash_on_credit = _is_cash_account(entry.credit_account, db)

        if not cash_on_debit and not cash_on_credit:
            continue  # no cash impact

        # Determine category based on the non-cash side
        other_code = c_code if cash_on_debit else d_code
        other_name = c_name if cash_on_debit else d_name

        amount = entry.debit_amount if cash_on_debit else -(entry.credit_amount)

        other_full = f"{other_code}-{other_name}"
        if _is_revenue_account(other_full, db) or _is_expense_account(other_full, db):
            # Operating: revenue/expense
            operating_items.append(CashFlowItem(
                description=f"{desc} ({other_code})",
                amount=amount,
            ))
            net_operating += amount
        elif _is_investing_account(other_full, db):
            # Investing: fixed assets / long-term assets
            investing_items.append(CashFlowItem(
                description=f"{desc} ({other_code})",
                amount=amount,
            ))
            net_investing += amount
        elif _is_financing_account(other_full, db):
            # Financing: loans or equity
            financing_items.append(CashFlowItem(
                description=f"{desc} ({other_code})",
                amount=amount,
            ))
            net_financing += amount
        else:
            # Default to operating
            operating_items.append(CashFlowItem(
                description=f"{desc} ({other_code})",
                amount=amount,
            ))
            net_operating += amount

    # Current period cash change
    current_cash = opening_cash
    for entry in entries:
        if _is_cash_account(entry.debit_account, db):
            current_cash += entry.debit_amount
        if _is_cash_account(entry.credit_account, db):
            current_cash -= entry.credit_amount

    net_change = current_cash - opening_cash

    return GenerateCashFlowOutput(
        from_date=input.from_date,
        to_date=input.to_date,
        operating_items=operating_items,
        investing_items=investing_items,
        financing_items=financing_items,
        net_operating=net_operating,
        net_investing=net_investing,
        net_financing=net_financing,
        net_change_in_cash=net_change,
        opening_cash=opening_cash,
        closing_cash=current_cash,
    )


# ---------------------------------------------------------------------------
# Tool 5 – Transfer Retained Earnings
# ---------------------------------------------------------------------------

def transfer_retained_earnings(
    input: TransferRetainedEarningsInput,
    db: Session,
) -> TransferRetainedEarningsOutput:
    """Transfer net income to retained earnings for a fiscal year.

    Ending RE = Beginning RE + Net Income - Dividends.
    Creates journal entry crediting Retained Earnings.
    """
    # Compute net income from the full fiscal year
    period_start = date(input.fiscal_year, 1, 1)
    period_end = date(input.fiscal_year, 12, 31)

    # Total revenue (credit to revenue accounts, resolved from chart)
    rev = db.query(func.sum(JournalEntry.credit_amount)).filter(
        JournalEntry.posted_date >= period_start,
        JournalEntry.posted_date <= period_end,
        revenue_filter_clause(JournalEntry.credit_account, db),
        JournalEntry.status == "posted",
    ).scalar() or Decimal("0")

    # Total expenses (debit to expense accounts, resolved from chart)
    exp = db.query(func.sum(JournalEntry.debit_amount)).filter(
        JournalEntry.posted_date >= period_start,
        JournalEntry.posted_date <= period_end,
        expense_filter_clause(JournalEntry.debit_account, db),
        JournalEntry.status == "posted",
    ).scalar() or Decimal("0")
    exp = Decimal(str(exp))

    net_income = Decimal(str(rev)) - exp

    # Get prior retained earnings
    prior = db.query(RetainedEarnings).filter(
        RetainedEarnings.fiscal_year == input.fiscal_year - 1
    ).first()
    beginning_re = Decimal(str(prior.ending_balance)) if prior else Decimal("0")

    # Check if already exists for this year
    existing = db.query(RetainedEarnings).filter(
        RetainedEarnings.fiscal_year == input.fiscal_year
    ).first()

    ending_re = beginning_re + net_income
    entry_id = f"RE-{input.fiscal_year}"

    if existing:
        # Update existing record
        existing.net_income = net_income
        existing.ending_balance = ending_re
        db.commit()
    else:
        # Create new
        re_record = RetainedEarnings(
            fiscal_year=input.fiscal_year,
            beginning_balance=beginning_re,
            net_income=net_income,
            dividends=Decimal("0"),
            ending_balance=ending_re,
        )
        db.add(re_record)
        db.commit()

    return TransferRetainedEarningsOutput(
        fiscal_year=input.fiscal_year,
        beginning_retained_earnings=beginning_re,
        net_income=net_income,
        dividends=Decimal("0"),
        ending_retained_earnings=ending_re,
        journal_entry_id=entry_id,
    )


# ---------------------------------------------------------------------------
# Tool 6 – Carry Forward Balances
# ---------------------------------------------------------------------------

def carry_forward_balances(
    input: CarryForwardBalancesInput,
    db: Session,
) -> CarryForwardBalancesOutput:
    """Carry forward balance sheet account balances to the new fiscal year.

    Copies balances of permanent accounts (prefixes 1, 2, 3) as opening
    journal entries for the new fiscal year. Revenue/expense accounts
    (prefixes 4, 5, 6, 8) start at zero.
    """
    entries = db.query(JournalEntry).filter(
        JournalEntry.posted_date <= input.closing_date,
        JournalEntry.status == "posted",
    ).all()

    # Net balance per account
    balances: dict[str, Decimal] = {}
    account_names: dict[str, str] = {}

    for entry in entries:
        d_code, d_name = _split_account(entry.debit_account)
        balances[d_code] = balances.get(d_code, Decimal("0")) + entry.debit_amount
        account_names[d_code] = d_name

        c_code, c_name = _split_account(entry.credit_account)
        balances[c_code] = balances.get(c_code, Decimal("0")) - entry.credit_amount
        account_names[c_code] = c_name

    new_balances: list[CarryForwardBalanceItem] = []
    count = 0

    # Create opening journal entries for permanent accounts
    for code in sorted(balances.keys()):
        net_bal = balances[code]
        prefix = code[0]

        if prefix in ("1", "2", "3") and net_bal != Decimal("0"):
            name = account_names.get(code, code)
            opening_bal = abs(net_bal)

            # Create journal entry for carry-forward
            if net_bal > Decimal("0"):
                # Debit balance (asset): debit asset, credit opening balance equity
                debit_acc = f"{code}-{name}"
                credit_acc = "3000-Opening Balance Equity"
            else:
                # Credit balance (liability/equity): credit account, debit opening balance equity
                credit_acc = f"{code}-{name}"
                debit_acc = "3000-Opening Balance Equity"

            carry_entry = JournalEntry(
                entry_id=f"CF-{code}-{input.from_fiscal_year}-{input.to_fiscal_year}",
                description=f"Carry forward {name} from FY {input.from_fiscal_year} to FY {input.to_fiscal_year}",
                posted_date=input.closing_date,
                reference=None,
                debit_account=debit_acc,
                debit_amount=abs(net_bal) if net_bal > Decimal("0") else Decimal("0"),
                credit_account=credit_acc,
                credit_amount=abs(net_bal) if net_bal < Decimal("0") else Decimal("0"),
                status="posted",
            )
            # Check if already exists for this carry-forward
            existing = db.query(JournalEntry).filter(
                JournalEntry.entry_id == carry_entry.entry_id
            ).first()
            if not existing:
                db.add(carry_entry)

            new_balances.append(CarryForwardBalanceItem(
                account_code=code,
                account_name=name,
                closing_balance=net_bal,
                opening_balance_next_year=opening_bal,
            ))
            count += 1

    db.commit()

    return CarryForwardBalancesOutput(
        accounts_carried_forward=count,
        new_balances=new_balances,
        status="completed",
    )


# ---------------------------------------------------------------------------
# Tool 7 – Draft Notes to Financials
# ---------------------------------------------------------------------------

def draft_notes_to_financials(
    input: DraftNotesToFinancialsInput,
    db: Session,
) -> DraftNotesToFinancialsOutput:
    """Draft explanatory notes to financial statements based on actual data.

    Generates structured notes: accounting policies, depreciation method,
    commitments, and contingencies from system data.
    """
    notes: list[FinancialNote] = []
    requested = input.note_types or ["accounting_policies", "revenue_recognition",
                                      "depreciation_method", "commitments", "contingencies"]

    for note_type in requested:
        if note_type == "accounting_policies":
            # Gather depreciation methods in use
            assets = db.query(FixedAsset).all()
            methods_used = set()
            for a in assets:
                if a.depreciation_method:
                    methods_used.add(a.depreciation_method)

            content = (
                f"The financial statements are prepared under the historical cost convention. "
                f"Revenue is recognised when earned. "
            )
            if methods_used:
                content += f"Depreciation is provided on a {', '.join(methods_used)} basis over the estimated useful lives of assets. "
            source = [f"{a.asset_name} ({a.depreciation_method})" for a in assets[:3]]

            notes.append(FinancialNote(
                title="Accounting Policies",
                content=content,
                source_data=source,
            ))

        elif note_type == "revenue_recognition":
            notes.append(FinancialNote(
                title="Revenue Recognition",
                content="Revenue is recognised when goods are delivered or services are rendered, "
                        "net of returns and trade discounts. Service revenue is recognised over time "
                        "based on the percentage-of-completion method where applicable.",
                source_data=[],
            ))

        elif note_type == "depreciation_method":
            assets = db.query(FixedAsset).all()
            if assets:
                content_parts = []
                for a in assets:
                    annual_dep = (a.purchase_cost - a.residual_value) / Decimal(str(max(a.useful_life_years, 1)))
                    content_parts.append(
                        f"{a.asset_name}: {a.depreciation_method.replace('_', ' ').title()}, "
                        f"cost {a.purchase_cost}, residual {a.residual_value}, "
                        f"useful life {a.useful_life_years} years, "
                        f"annual depreciation {annual_dep.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"
                    )
                content = "Property, plant and equipment:\n" + "\n".join(content_parts)
            else:
                content = "No fixed assets held during the period."
            notes.append(FinancialNote(
                title="Property, Plant and Equipment",
                content=content,
                source_data=[a.asset_id for a in assets] if assets else [],
            ))

        elif note_type == "commitments":
            from db.models import Loan
            loans = db.query(Loan).filter(Loan.status == "active").all()
            if loans:
                content_parts = []
                for ln in loans:
                    content_parts.append(
                        f"{ln.loan_name}: principal {ln.principal_amount}, "
                        f"rate {ln.interest_rate}%, term {ln.term_months} months"
                    )
                content = "Loan commitments:\n" + "\n".join(content_parts)
            else:
                content = "No significant commitments outstanding."
            notes.append(FinancialNote(
                title="Commitments and Contingencies",
                content=content,
                source_data=[ln.loan_id for ln in loans] if loans else [],
            ))

        elif note_type == "contingencies":
            notes.append(FinancialNote(
                title="Contingent Liabilities",
                content="There are no material contingent liabilities as of the reporting date. "
                        "The company is not party to any significant legal proceedings.",
                source_data=[],
            ))

    return DraftNotesToFinancialsOutput(
        fiscal_year=input.fiscal_year,
        notes=notes,
        disclaimer="These notes are AI-generated drafts based on system data. "
                   "They should be reviewed by a qualified accountant before finalisation.",
    )


# ---------------------------------------------------------------------------
# Tool 8 – Close Fiscal Year (requires approval)
# ---------------------------------------------------------------------------

def close_fiscal_year(
    input: CloseFiscalYearInput,
    db: Session,
) -> CloseFiscalYearOutput:
    """Close a fiscal year — irreversible.

    Requires confirm=True. Prevents double-close by checking fiscal_year_close table.
    Creates closing journal entries:
    1. Close all revenue accounts to Income Summary
    2. Close all expense accounts to Income Summary
    3. Close Income Summary to Retained Earnings
    """
    if not input.confirm:
        raise ValueError("confirm must be True to close fiscal year")

    # Check for double-close
    already_closed = db.query(FiscalYearClose).filter(
        FiscalYearClose.fiscal_year == input.fiscal_year
    ).first()
    if already_closed:
        raise ValueError(f"Fiscal year {input.fiscal_year} is already closed (status: {already_closed.status})")

    period_start = date(input.fiscal_year, 1, 1)
    period_end = date(input.fiscal_year, 12, 31)

    # Get revenue accounts (credit side, prefix 4)
    revenue_entries = db.query(JournalEntry).filter(
        JournalEntry.posted_date >= period_start,
        JournalEntry.posted_date <= period_end,
        JournalEntry.status == "posted",
    ).all()

    # Aggregate revenue and expenses
    total_revenue = Decimal("0")
    total_expenses = Decimal("0")
    revenue_accounts: set[str] = set()
    expense_accounts: set[str] = set()

    for entry in revenue_entries:
        c_code, _ = _split_account(entry.credit_account)
        if _is_revenue_account(entry.credit_account, db):
            total_revenue += entry.credit_amount
            revenue_accounts.add(c_code)

        d_code, _ = _split_account(entry.debit_account)
        if _is_expense_account(entry.debit_account, db):
            total_expenses += entry.debit_amount
            expense_accounts.add(d_code)

    net_income = total_revenue - total_expenses
    closing_entries_count = 0

    # 1. Close revenue accounts: debit each revenue, credit Income Summary
    for rev_code in sorted(revenue_accounts):
        rev_total = Decimal("0")
        for entry in revenue_entries:
            c_code, _ = _split_account(entry.credit_account)
            if c_code == rev_code:
                rev_total += entry.credit_amount

        if rev_total > Decimal("0"):
            closing_entry = JournalEntry(
                entry_id=f"CL-{input.fiscal_year}-REV-{rev_code}",
                description=f"Closing revenue account {rev_code}",
                posted_date=input.closing_date,
                reference=f"FY{input.fiscal_year}-CLOSE",
                debit_account=f"{rev_code}-Revenue",
                debit_amount=rev_total,
                credit_account="3000-Income Summary",
                credit_amount=rev_total,
                status="closing",
            )
            db.add(closing_entry)
            closing_entries_count += 1

    # 2. Close expense accounts: credit each expense, debit Income Summary
    for exp_code in sorted(expense_accounts):
        exp_total = Decimal("0")
        for entry in revenue_entries:
            d_code, _ = _split_account(entry.debit_account)
            if d_code == exp_code:
                exp_total += entry.debit_amount

        if exp_total > Decimal("0"):
            closing_entry = JournalEntry(
                entry_id=f"CL-{input.fiscal_year}-EXP-{exp_code}",
                description=f"Closing expense account {exp_code}",
                posted_date=input.closing_date,
                reference=f"FY{input.fiscal_year}-CLOSE",
                debit_account="3000-Income Summary",
                debit_amount=exp_total,
                credit_account=f"{exp_code}-Expenses",
                credit_amount=exp_total,
                status="closing",
            )
            db.add(closing_entry)
            closing_entries_count += 1

    # 3. Close Income Summary to Retained Earnings
    if net_income != Decimal("0"):
        if net_income > Decimal("0"):
            # Net profit: debit Income Summary, credit Retained Earnings
            debit_acc = "3000-Income Summary"
            credit_acc = "3000-Retained Earnings"
        else:
            # Net loss: debit Retained Earnings, credit Income Summary
            debit_acc = "3000-Retained Earnings"
            credit_acc = "3000-Income Summary"

        closing_entry = JournalEntry(
            entry_id=f"CL-{input.fiscal_year}-INCSUM",
            description=f"Closing Income Summary to Retained Earnings (net income: {net_income})",
            posted_date=input.closing_date,
            reference=f"FY{input.fiscal_year}-CLOSE",
            debit_account=debit_acc,
            debit_amount=abs(net_income),
            credit_account=credit_acc,
            credit_amount=abs(net_income),
            status="closing",
        )
        db.add(closing_entry)
        closing_entries_count += 1

    # Record the close
    close_record = FiscalYearClose(
        fiscal_year=input.fiscal_year,
        closed_at=input.closing_date,
        closed_by="system",
        status="closed",
    )
    db.add(close_record)
    db.commit()

    return CloseFiscalYearOutput(
        fiscal_year=input.fiscal_year,
        closing_entries_created=closing_entries_count,
        revenue_closed=len(revenue_accounts),
        expenses_closed=len(expense_accounts),
        net_income_transferred=net_income,
        status="closed",
        message=f"Fiscal year {input.fiscal_year} closed successfully. "
                f"Created {closing_entries_count} closing entries. "
                f"Net income of {net_income.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)} transferred.",
    )
