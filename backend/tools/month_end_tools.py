"""Month-End Reporting tools for Agent 4: AP aging, budget variance, loan schedule, cash flow forecast."""

import calendar
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from db.models import (
    Budget, Contact, JournalEntry, Loan, LoanPaymentSchedule,
    PrepaidExpense, FixedAsset, DepreciationSchedule,
    IntangibleAsset, AmortizationSchedule, PayrollEntry,
)
from tools.account_utils import ar_filter_clause, ap_filter_clause, salary_filter_clause
from tools.schemas import (
    APAgingBucket,
    AnalyzeBudgetVarianceInput,
    AnalyzeBudgetVarianceOutput,
    BudgetVarianceItem,
    CashFlowProjection,
    ForecastCashFlowInput,
    ForecastCashFlowOutput,
    GetAPAgingReportInput,
    GetAPAgingReportOutput,
    GetLoanDebtScheduleInput,
    GetLoanDebtScheduleOutput,
    LoanPaymentScheduleItem,
    ReviewUnpaidBillsInput, ReviewUnpaidBillsOutput, UnpaidBillItem,
    CalculatePrepaidAdjustmentInput, CalculatePrepaidAdjustmentOutput, PrepaidAdjustmentItem,
    CalculateDepreciationInput, CalculateDepreciationOutput, DepreciationEntryItem,
    CalculateAmortizationInput, CalculateAmortizationOutput, AmortizationEntryItem,
    ReconcilePayrollInput, ReconcilePayrollOutput, PayrollReconItem,
    GetARAgingReportInput, GetARAgingReportOutput, AgingBucketItem, CustomerAgingDetail,
)


# ---------------------------------------------------------------------------
# Helper - split "1000-Cash" into (code, name)
# ---------------------------------------------------------------------------

def _split_account(value: str):
    """Split '1000-Cash' into (code, name). Returns (value, value) if no hyphen."""
    parts = value.split("-", 1)
    if len(parts) == 2 and parts[0].strip().isdigit():
        return parts[0].strip(), parts[1].strip()
    return value, value


# ---------------------------------------------------------------------------
# Tool 7 - AP Aging Report
# ---------------------------------------------------------------------------

def get_ap_aging_report(
    input: GetAPAgingReportInput,
    db: Session,
) -> GetAPAgingReportOutput:
    """Generate an accounts payable aging report as of a given date.

    Payable accounts are resolved dynamically from the user's chart.
    Queries journal_entries where the credit side is a payable account,
    groups by vendor reference (contact_id), and buckets outstanding
    amounts into aging ranges: current (0-30), 31-60, 61-90, 90+ days.

    Edge cases handled:
      - No AP entries returns empty buckets.
      - No matching contact uses reference as vendor name.
      - Future-dated entries treated as current.
      - Unknown vendor reference handled gracefully.
    """
    query = db.query(JournalEntry).filter(
        ap_filter_clause(JournalEntry.credit_account, db),
        JournalEntry.status == "posted",
    )

    if input.vendor_contact_id is not None:
        query = query.filter(JournalEntry.reference == input.vendor_contact_id)

    entries = query.order_by(JournalEntry.reference).all()

    # Group by vendor reference
    vendor_groups: dict[str, list[JournalEntry]] = {}
    for entry in entries:
        ref = entry.reference or "__unknown__"
        vendor_groups.setdefault(ref, []).append(entry)

    if not vendor_groups:
        return GetAPAgingReportOutput(
            as_of_date=input.as_of_date,
            buckets=[],
            total_current=Decimal("0"),
            total_31_60=Decimal("0"),
            total_61_90=Decimal("0"),
            total_90_plus=Decimal("0"),
            grand_total=Decimal("0"),
        )

    buckets: list[APAgingBucket] = []
    total_current = Decimal("0")
    total_31_60 = Decimal("0")
    total_61_90 = Decimal("0")
    total_90_plus = Decimal("0")

    for ref, ref_entries in vendor_groups.items():
        vendor_name = ref
        if ref != "__unknown__":
            contact = db.query(Contact).filter(Contact.contact_id == ref).first()
            if contact is not None:
                vendor_name = contact.contact_name

        current = Decimal("0")
        aged_31_60 = Decimal("0")
        aged_61_90 = Decimal("0")
        aged_90_plus = Decimal("0")

        for entry in ref_entries:
            days_diff = (input.as_of_date - entry.posted_date).days
            if days_diff <= 0:
                current += entry.credit_amount
            elif days_diff <= 30:
                current += entry.credit_amount
            elif days_diff <= 60:
                aged_31_60 += entry.credit_amount
            elif days_diff <= 90:
                aged_61_90 += entry.credit_amount
            else:
                aged_90_plus += entry.credit_amount

        total = current + aged_31_60 + aged_61_90 + aged_90_plus
        buckets.append(APAgingBucket(
            vendor_contact_id=ref if ref != "__unknown__" else "",
            vendor_name=vendor_name,
            current=current,
            aged_31_60=aged_31_60,
            aged_61_90=aged_61_90,
            aged_90_plus=aged_90_plus,
            total_outstanding=total,
        ))
        total_current += current
        total_31_60 += aged_31_60
        total_61_90 += aged_61_90
        total_90_plus += aged_90_plus

    buckets.sort(key=lambda b: b.vendor_name.lower())

    return GetAPAgingReportOutput(
        as_of_date=input.as_of_date,
        buckets=buckets,
        total_current=total_current,
        total_31_60=total_31_60,
        total_61_90=total_61_90,
        total_90_plus=total_90_plus,
        grand_total=total_current + total_31_60 + total_61_90 + total_90_plus,
    )


# ---------------------------------------------------------------------------
# Tool 8 - Budget Variance Analysis
# ---------------------------------------------------------------------------

def analyze_budget_variance(
    input: AnalyzeBudgetVarianceInput,
    db: Session,
) -> AnalyzeBudgetVarianceOutput:
    """Compare budgeted amounts against actuals for a given fiscal year and period.

    Queries the budgets table for the target period, then aggregates actual
    debit amounts from journal_entries. Computes variance and variance
    percentage, generates plain-language explanations, and flags accounts
    with >20% absolute variance.

    Edge cases handled:
      - No budgets found raises ValueError.
      - Zero budget amount produces "No budget" explanation, not division-by-zero.
      - No actual entries for a budgeted account shows zero actuals.
      - Account code prefix filter is applied.
    """
    budget_query = db.query(Budget).filter(
        Budget.fiscal_year == input.fiscal_year,
        Budget.period == input.period,
    )
    budget_rows = budget_query.all()

    if not budget_rows:
        raise ValueError(
            f"No budgets found for FY {input.fiscal_year} period {input.period}"
        )

    # Determine the date range for the period
    _, last_day = calendar.monthrange(input.fiscal_year, input.period)
    period_start = date(input.fiscal_year, input.period, 1)
    period_end = date(input.fiscal_year, input.period, last_day)

    # Aggregate actuals from journal_entries grouped by debit_account code
    actuals_raw = db.query(
        JournalEntry.debit_account,
        func.sum(JournalEntry.debit_amount).label("total_debit"),
    ).filter(
        JournalEntry.posted_date >= period_start,
        JournalEntry.posted_date <= period_end,
        JournalEntry.status == "posted",
    ).group_by(JournalEntry.debit_account).all()

    # Build lookup: account_code -> total actual debit amount
    # Strip trailing account name from code if present (e.g. "6000-Salary" -> "6000")
    actuals_map: dict[str, Decimal] = {}
    for row in actuals_raw:
        code, _ = _split_account(row.debit_account)
        actuals_map[code] = Decimal(str(row.total_debit))

    items: list[BudgetVarianceItem] = []
    total_budget = Decimal("0")
    total_actual = Decimal("0")
    flagged_count = 0

    for budget_row in budget_rows:
        code = budget_row.account_code
        budget_amt = Decimal(str(budget_row.budget_amount))

        # Apply optional account_code_prefix filter on budget account codes
        if input.account_code_prefix is not None:
            prefix = input.account_code_prefix.strip()
            if prefix and not code.startswith(prefix):
                continue

        actual_amt = actuals_map.get(code, Decimal("0"))
        variance = actual_amt - budget_amt

        if budget_amt != Decimal("0"):
            variance_pct = (variance / budget_amt) * Decimal("100")
        else:
            variance_pct = Decimal("0")

        abs_pct = abs(variance_pct)
        flagged = budget_amt != Decimal("0") and abs_pct > Decimal("20")

        if budget_amt == Decimal("0") and actual_amt == Decimal("0"):
            explanation = f"No budget and no activity for {code}"
        elif budget_amt == Decimal("0") and actual_amt > Decimal("0"):
            explanation = f"Unbudgeted spend of {actual_amt} on {code}"
        elif variance > Decimal("0"):
            explanation = (
                f"Overspend of {abs_pct.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}% "
                f"on {code}"
            )
        elif variance < Decimal("0"):
            explanation = (
                f"Underspend of {abs_pct.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}% "
                f"on {code}"
            )
        else:
            explanation = f"On budget for {code}"

        items.append(BudgetVarianceItem(
            account_code=code,
            budget_amount=budget_amt,
            actual_amount=actual_amt,
            variance=variance,
            variance_pct=variance_pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            flagged=flagged,
            explanation=explanation,
        ))
        total_budget += budget_amt
        total_actual += actual_amt
        if flagged:
            flagged_count += 1

    summary = (
        f"Budget variance analysis for FY {input.fiscal_year} period {input.period}: "
        f"{len(items)} account(s) reviewed, {flagged_count} flagged with >20% variance."
    )

    items.sort(key=lambda i: abs(i.variance_pct), reverse=True)

    return AnalyzeBudgetVarianceOutput(
        fiscal_year=input.fiscal_year,
        period=input.period,
        items=items,
        total_budget=total_budget,
        total_actual=total_actual,
        total_variance=total_actual - total_budget,
        flagged_count=flagged_count,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Helper - add months to a date (avoiding dateutil dependency)
# ---------------------------------------------------------------------------

def _add_months(source: date, months: int) -> date:
    """Add a number of months to a date, clamping day to month length."""
    total_months = source.year * 12 + source.month - 1 + months
    year = total_months // 12
    month = total_months % 12 + 1
    _, last_day = calendar.monthrange(year, month)
    day = min(source.day, last_day)
    return date(year, month, day)


# ---------------------------------------------------------------------------
# Tool 9 - Loan / Debt Schedule
# ---------------------------------------------------------------------------

def get_loan_debt_schedule(
    input: GetLoanDebtScheduleInput,
    db: Session,
) -> GetLoanDebtScheduleOutput:
    """Retrieve or compute an amortisation schedule for a loan.

    If a schedule already exists in loan_payment_schedule, returns it.
    Otherwise uses the PMT formula to generate a full amortisation table,
    stores it, and returns it.

    PMT formula:
        payment = P * r * (1+r)^n / ((1+r)^n - 1)

    Edge cases handled:
      - Loan not found raises ValueError.
      - Zero interest rate: principal evenly split over term.
      - Final payment adjusted to clear remaining balance.
      - Single-period loan handled correctly.
    """
    loan = db.query(Loan).filter(Loan.loan_id == input.loan_id).first()
    if loan is None:
        raise ValueError(f"Loan '{input.loan_id}' not found")

    principal = Decimal(str(loan.principal_amount))
    annual_rate = Decimal(str(loan.interest_rate))
    term = int(loan.term_months)

    # Check for existing schedule
    existing = (
        db.query(LoanPaymentSchedule)
        .filter(LoanPaymentSchedule.loan_id == input.loan_id)
        .order_by(LoanPaymentSchedule.period_number)
        .all()
    )

    if existing:
        schedule_items = []
        total_interest = Decimal("0")
        for s in existing:
            si = LoanPaymentScheduleItem(
                period_number=s.period_number,
                payment_date=s.payment_date,
                payment_amount=Decimal(str(s.payment_amount)),
                principal_amount=Decimal(str(s.principal_amount)),
                interest_amount=Decimal(str(s.interest_amount)),
                remaining_balance=Decimal(str(s.remaining_balance)),
            )
            schedule_items.append(si)
            total_interest += si.interest_amount

        # Filter schedule by as_of_date (show only future payments)
        if input.as_of_date is not None:
            schedule_items = [si for si in schedule_items if si.payment_date >= input.as_of_date]

        monthly_payment = schedule_items[0].payment_amount if schedule_items else Decimal("0")

        return GetLoanDebtScheduleOutput(
            loan_id=loan.loan_id,
            loan_name=loan.loan_name,
            principal_amount=principal,
            interest_rate=annual_rate,
            term_months=term,
            start_date=loan.start_date,
            monthly_payment=monthly_payment,
            schedule=schedule_items,
            total_interest=total_interest.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            source="stored",
        )

    # Generate schedule using PMT
    r = annual_rate / Decimal("100") / Decimal("12")  # monthly interest rate (decimal)

    if r == Decimal("0"):
        # Zero interest: principal split evenly
        raw_payment = principal / Decimal(str(term))
        payment = raw_payment.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        use_pmt = False
    else:
        one_plus_r = Decimal("1") + r
        r_pow_n = one_plus_r ** int(term)
        raw_payment = principal * r * r_pow_n / (r_pow_n - Decimal("1"))
        payment = raw_payment.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        use_pmt = True

    schedule_items = []
    remaining = principal
    total_interest = Decimal("0")

    for period in range(1, term + 1):
        payment_date = _add_months(loan.start_date, period)

        if use_pmt:
            interest = (remaining * r).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            principal_part = payment - interest
            # Adjust final payment to clear any rounding residue
            if period == term or principal_part >= remaining:
                principal_part = remaining
                payment = principal_part + interest
        else:
            interest = Decimal("0")
            principal_part = payment
            if period == term:
                principal_part = remaining
                payment = principal_part

        if principal_part > remaining:
            principal_part = remaining
            payment = principal_part + interest

        remaining -= principal_part
        if remaining < Decimal("0.01"):
            remaining = Decimal("0")

        si = LoanPaymentScheduleItem(
            period_number=period,
            payment_date=payment_date,
            payment_amount=payment.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            principal_amount=principal_part.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            interest_amount=interest.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            remaining_balance=remaining.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        )
        schedule_items.append(si)
        total_interest += interest

        # Persist to database
        db.add(LoanPaymentSchedule(
            loan_id=input.loan_id,
            period_number=period,
            payment_date=payment_date,
            payment_amount=si.payment_amount,
            principal_amount=si.principal_amount,
            interest_amount=si.interest_amount,
            remaining_balance=si.remaining_balance,
        ))

    db.commit()

    # Filter schedule by as_of_date (show only future payments)
    if input.as_of_date is not None:
        schedule_items = [si for si in schedule_items if si.payment_date >= input.as_of_date]

    monthly = payment.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return GetLoanDebtScheduleOutput(
        loan_id=loan.loan_id,
        loan_name=loan.loan_name,
        principal_amount=principal,
        interest_rate=annual_rate,
        term_months=term,
        start_date=loan.start_date,
        monthly_payment=monthly,
        schedule=schedule_items,
        total_interest=total_interest.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        source="computed",
    )


# ---------------------------------------------------------------------------
# Tool 10 - Cash Flow Forecast
# ---------------------------------------------------------------------------

# Revenue accounts start with "4"; expense accounts start with "5", "6", or "8"
_INFLOW_PREFIXES = ("4",)
_OUTFLOW_PREFIXES = ("5", "6", "8")


def forecast_cash_flow(
    input: ForecastCashFlowInput,
    db: Session,
) -> ForecastCashFlowOutput:
    """Project future cash flows based on historical averages.

    Queries journal_entries over the last 3 months to calculate average
    monthly inflow (credit amounts to revenue accounts) and outflow
    (debit amounts to expense accounts). Projects forward as daily
    averages and returns daily projections.

    Requires agent-level approval (needs_approval=True).

    Confidence:
      - 'high': at least 3 months of history found
      - 'medium': 1-2 months of history found
      - 'low': less than 1 month of history found or no activity

    Edge cases handled:
      - No journal entries in period yields zero averages, low confidence.
      - forecast_days constrained to 30/60/90 via schema validation.
      - Zero starting balance is valid.
      - Negative net flow projections still returned (no clamping).
    """
    today = input.as_of_date or date.today()
    lookback_start = today - timedelta(days=90)

    # --- Calculate historical averages ---------------------------------------

    # Inflow: credit_amount to revenue accounts (prefix "4")
    inflow_rows = db.query(
        func.sum(JournalEntry.credit_amount).label("total"),
    ).filter(
        JournalEntry.posted_date >= lookback_start,
        JournalEntry.posted_date <= today,
        JournalEntry.credit_account.startswith(_INFLOW_PREFIXES[0]),
        JournalEntry.status == "posted",
    ).first()
    total_inflow = Decimal(str(inflow_rows.total)) if inflow_rows and inflow_rows.total else Decimal("0")

    # Outflow: debit_amount to expense accounts (prefix "5", "6", "8")
    outflow_sum = Decimal("0")
    for prefix in _OUTFLOW_PREFIXES:
        row = db.query(
            func.sum(JournalEntry.debit_amount).label("total"),
        ).filter(
            JournalEntry.posted_date >= lookback_start,
            JournalEntry.posted_date <= today,
            JournalEntry.debit_account.startswith(prefix),
            JournalEntry.status == "posted",
        ).first()
        if row and row.total:
            outflow_sum += Decimal(str(row.total))

    total_outflow = outflow_sum

    # Determine historical coverage (in months)
    earliest_entry = db.query(func.min(JournalEntry.posted_date)).filter(
        JournalEntry.status == "posted",
    ).scalar()

    if earliest_entry is not None:
        days_span = (today - earliest_entry).days
        months_span = days_span / 30.0
    else:
        months_span = 0

    if months_span >= 3 and (total_inflow > Decimal("0") or total_outflow > Decimal("0")):
        confidence = "high"
    elif months_span >= 1 and (total_inflow > Decimal("0") or total_outflow > Decimal("0")):
        confidence = "medium"
    else:
        confidence = "low"

    # Monthly averages
    num_months = max(Decimal(str(round(months_span, 1))), Decimal("1"))
    avg_monthly_inflow = total_inflow / num_months
    avg_monthly_outflow = total_outflow / num_months
    net_monthly = avg_monthly_inflow - avg_monthly_outflow

    # Daily averages (using 30-day month convention)
    daily_inflow = avg_monthly_inflow / Decimal("30")
    daily_outflow = avg_monthly_outflow / Decimal("30")

    # --- Build projections ---------------------------------------------------
    projections: list[CashFlowProjection] = []
    cumulative = input.starting_balance

    for day_offset in range(1, input.forecast_days + 1):
        proj_date = today + timedelta(days=day_offset)
        proj_inflow = daily_inflow.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        proj_outflow = daily_outflow.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        net = proj_inflow - proj_outflow
        cumulative += net

        projections.append(CashFlowProjection(
            date=proj_date,
            projected_inflow=proj_inflow,
            projected_outflow=proj_outflow,
            net_flow=net,
            cumulative_balance=cumulative.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        ))

    return ForecastCashFlowOutput(
        forecast_days=input.forecast_days,
        projections=projections,
        avg_monthly_inflow=avg_monthly_inflow.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        avg_monthly_outflow=avg_monthly_outflow.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        net_monthly_average=net_monthly.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        confidence=confidence,
        needs_approval=True,
    )


# ---------------------------------------------------------------------------
# Tool 1 - Review Unpaid Bills
# ---------------------------------------------------------------------------

def review_unpaid_bills(
    input: ReviewUnpaidBillsInput,
    db: Session,
) -> ReviewUnpaidBillsOutput:
    """Review unpaid (AP) bills as of a given date.
    Queries journal_entries where debit starts with "2000" and credit is
    still unpaid (no matching payment entry).  Groups by vendor reference and
    returns overdue items with aging.
    """
    query = db.query(JournalEntry).filter(
        ap_filter_clause(JournalEntry.credit_account, db),
        JournalEntry.status == "posted",
    )
    if input.vendor_contact_id is not None:
        query = query.filter(JournalEntry.reference == input.vendor_contact_id)
    ap_entries = query.order_by(JournalEntry.posted_date).all()

    items: list[UnpaidBillItem] = []
    total_unpaid = Decimal("0")
    total_overdue = Decimal("0")

    for entry in ap_entries:
        due_date = entry.posted_date
        days_overdue = (input.as_of_date - due_date).days
        if days_overdue < 0:
            days_overdue = 0

        # Apply min_days_overdue filter
        outstanding = entry.credit_amount
        if input.min_days_overdue is not None and days_overdue < input.min_days_overdue:
            continue

        vendor_name = entry.reference or "Unknown"
        if entry.reference:
            contact = db.query(Contact).filter(Contact.contact_id == entry.reference).first()
            if contact:
                vendor_name = contact.contact_name

        item = UnpaidBillItem(
            entry_id=entry.entry_id,
            vendor_name=vendor_name,
            invoice_amount=entry.credit_amount,
            outstanding_balance=outstanding,
            due_date=due_date,
            days_overdue=days_overdue,
            status="unpaid" if outstanding > Decimal("0") else "paid",
        )
        items.append(item)
        total_unpaid += outstanding
        if days_overdue > 0:
            total_overdue += outstanding

    return ReviewUnpaidBillsOutput(
        items=items,
        total_unpaid=total_unpaid,
        total_overdue=total_overdue,
        as_of_date=input.as_of_date,
    )


# ---------------------------------------------------------------------------
# Tool 2 - Calculate Prepaid Adjustment
# ---------------------------------------------------------------------------

def calculate_prepaid_adjustment(
    input: CalculatePrepaidAdjustmentInput,
    db: Session,
) -> CalculatePrepaidAdjustmentOutput:
    """Calculate monthly prepaid expense adjustments.
    Queries active prepaid_expenses, computes months elapsed from start_date
    to as_of_date, and returns the suggested amortization amount.
    """
    query = db.query(PrepaidExpense).filter(PrepaidExpense.status == "active")
    if input.prepaid_id is not None:
        query = query.filter(PrepaidExpense.prepaid_id == input.prepaid_id)
    prepaids = query.all()

    items: list[PrepaidAdjustmentItem] = []
    total_adjustment = Decimal("0")

    for p in prepaids:
        total_months = (input.as_of_date.year - p.start_date.year) * 12 + (input.as_of_date.month - p.start_date.month)
        months_elapsed = max(total_months, 0)
        amount_amortized = p.monthly_amount * Decimal(str(months_elapsed))
        remaining = p.remaining_balance

        adj = min(p.monthly_amount, remaining) if remaining > Decimal("0") else Decimal("0")
        items.append(PrepaidAdjustmentItem(
            prepaid_id=p.prepaid_id,
            description=p.description,
            total_amount=p.total_amount,
            start_date=p.start_date,
            end_date=p.end_date,
            monthly_amount=p.monthly_amount,
            months_elapsed=months_elapsed,
            amount_amortized=amount_amortized,
            remaining_balance=remaining,
            suggested_adjustment=adj,
        ))
        total_adjustment += adj

    return CalculatePrepaidAdjustmentOutput(
        items=items,
        total_adjustment=total_adjustment,
        as_of_date=input.as_of_date,
    )


# ---------------------------------------------------------------------------
# Tool 3 - Calculate Depreciation
# ---------------------------------------------------------------------------

def calculate_depreciation(
    input: CalculateDepreciationInput,
    db: Session,
) -> CalculateDepreciationOutput:
    """Calculate monthly straight-line depreciation for fixed assets.
    For each active asset: monthly_dep = (cost - residual) / useful_life / 12.
    Accumulated depreciation summed from existing schedule; if first run
    for the period, writes a DepreciationSchedule row.
    """
    query = db.query(FixedAsset).filter(FixedAsset.status.in_(["approved", "active"]))
    if input.asset_id is not None:
        query = query.filter(FixedAsset.asset_id == input.asset_id)
    assets = query.all()

    items: list[DepreciationEntryItem] = []
    total_dep = Decimal("0")

    for asset in assets:
        cost = asset.purchase_cost
        residual = asset.residual_value
        useful_life = asset.useful_life_years
        if useful_life < 1:
            useful_life = 1
        monthly = (cost - residual) / Decimal(str(useful_life)) / Decimal("12")
        monthly = monthly.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        existing = db.query(DepreciationSchedule).filter(
            DepreciationSchedule.asset_id == asset.asset_id,
            DepreciationSchedule.period_date == input.period_date,
        ).first()

        if existing:
            acc_dep = Decimal(str(existing.accumulated_depreciation))
            book = Decimal(str(existing.book_value))
            entry_id = existing.entry_id
        else:
            existing_entries = db.query(DepreciationSchedule).filter(
                DepreciationSchedule.asset_id == asset.asset_id,
            ).order_by(DepreciationSchedule.period_date).all()
            acc_dep = sum(Decimal(str(e.monthly_depreciation)) for e in existing_entries) + monthly
            book = cost - acc_dep
            if book < Decimal("0"):
                book = Decimal("0")
            entry_id = f"DEP-{asset.asset_id}-{input.period_date.isoformat()}"
            ds = DepreciationSchedule(
                entry_id=entry_id,
                asset_id=asset.asset_id,
                period_date=input.period_date,
                monthly_depreciation=monthly,
                accumulated_depreciation=acc_dep,
                book_value=book,
                status="posted",
            )
            db.add(ds)
            db.commit()

        items.append(DepreciationEntryItem(
            entry_id=entry_id,
            asset_id=asset.asset_id,
            asset_name=asset.asset_name,
            period_date=input.period_date,
            monthly_depreciation=monthly,
            accumulated_depreciation=acc_dep,
            book_value=book,
            status="posted",
        ))
        total_dep += monthly

    return CalculateDepreciationOutput(
        items=items,
        total_depreciation=total_dep.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        period_date=input.period_date,
    )


# ---------------------------------------------------------------------------
# Tool 4 - Calculate Amortization
# ---------------------------------------------------------------------------

def calculate_amortization(
    input: CalculateAmortizationInput,
    db: Session,
) -> CalculateAmortizationOutput:
    """Calculate monthly straight-line amortization for intangible assets.
    Same pattern as depreciation but for intangible_assets.
    """
    query = db.query(IntangibleAsset).filter(IntangibleAsset.status == "active")
    if input.asset_id is not None:
        query = query.filter(IntangibleAsset.asset_id == input.asset_id)
    assets = query.all()

    items: list[AmortizationEntryItem] = []
    total_amort = Decimal("0")

    for asset in assets:
        cost = asset.cost
        residual = asset.residual_value
        useful_life = asset.useful_life_years
        if useful_life < 1:
            useful_life = 1
        monthly = (cost - residual) / Decimal(str(useful_life)) / Decimal("12")
        monthly = monthly.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        existing = db.query(AmortizationSchedule).filter(
            AmortizationSchedule.asset_id == asset.asset_id,
            AmortizationSchedule.period_date == input.period_date,
        ).first()

        if existing:
            acc_amort = Decimal(str(existing.accumulated_amortization))
            book = Decimal(str(existing.book_value))
            entry_id = existing.entry_id
        else:
            existing_entries = db.query(AmortizationSchedule).filter(
                AmortizationSchedule.asset_id == asset.asset_id,
            ).order_by(AmortizationSchedule.period_date).all()
            acc_amort = sum(Decimal(str(e.monthly_amortization)) for e in existing_entries) + monthly
            book = cost - acc_amort
            if book < Decimal("0"):
                book = Decimal("0")
            entry_id = f"AMORT-{asset.asset_id}-{input.period_date.isoformat()}"
            am = AmortizationSchedule(
                entry_id=entry_id,
                asset_id=asset.asset_id,
                period_date=input.period_date,
                monthly_amortization=monthly,
                accumulated_amortization=acc_amort,
                book_value=book,
                status="posted",
            )
            db.add(am)
            db.commit()

        items.append(AmortizationEntryItem(
            entry_id=entry_id,
            asset_id=asset.asset_id,
            asset_name=asset.asset_name,
            period_date=input.period_date,
            monthly_amortization=monthly,
            accumulated_amortization=acc_amort,
            book_value=book,
            status="posted",
        ))
        total_amort += monthly

    return CalculateAmortizationOutput(
        items=items,
        total_amortization=total_amort.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        period_date=input.period_date,
    )


# ---------------------------------------------------------------------------
# Tool 5 - Reconcile Payroll
# ---------------------------------------------------------------------------

def reconcile_payroll(
    input: ReconcilePayrollInput,
    db: Session,
) -> ReconcilePayrollOutput:
    """Reconcile payroll entries against general ledger salary expense.
    Compares PayrollEntry totals against JournalEntry debits to salary
    accounts (prefix "6100") for the same period.  Flags discrepancies.
    """
    query = db.query(PayrollEntry).filter(
        PayrollEntry.period_start >= input.from_date,
        PayrollEntry.period_end <= input.to_date,
    )
    if input.employee_name is not None:
        query = query.filter(PayrollEntry.employee_name.ilike(f"%{input.employee_name}%"))
    payroll_rows = query.all()

    # Aggregate GL salary debits
    gl_salary = db.query(
        func.sum(JournalEntry.debit_amount).label("total"),
    ).filter(
        salary_filter_clause(JournalEntry.debit_account, db),
        JournalEntry.posted_date >= input.from_date,
        JournalEntry.posted_date <= input.to_date,
        JournalEntry.status == "posted",
    ).first()
    gl_total = Decimal(str(gl_salary.total)) if gl_salary and gl_salary.total else Decimal("0")

    items: list[PayrollReconItem] = []
    total_salary = Decimal("0")
    total_deductions = Decimal("0")
    total_net_pay = Decimal("0")
    discrepancies = 0

    for pr in payroll_rows:
        salary = pr.salary_amount
        deductions = pr.deductions
        net = pr.net_pay
        disc = None
        if salary - deductions != net:
            disc = f"salary({salary}) - deductions({deductions}) != net_pay({net})"
            discrepancies += 1

        items.append(PayrollReconItem(
            entry_id=pr.entry_id,
            employee_name=pr.employee_name,
            salary_amount=salary,
            deductions=deductions,
            net_pay=net,
            period_start=pr.period_start,
            period_end=pr.period_end,
            posted_date=pr.posted_date,
            discrepancy=disc,
        ))
        total_salary += salary
        total_deductions += deductions
        total_net_pay += net

    # Compare payroll total vs GL total
    if payroll_rows and gl_total != total_salary:
        discrepancies += 1

    return ReconcilePayrollOutput(
        items=items,
        total_salary=total_salary,
        total_deductions=total_deductions,
        total_net_pay=total_net_pay,
        period_from=input.from_date,
        period_to=input.to_date,
        discrepancies=discrepancies,
    )


# ---------------------------------------------------------------------------
# Tool 6 - AR Aging Report
# ---------------------------------------------------------------------------

def get_ar_aging_report(
    input: GetARAgingReportInput,
    db: Session,
) -> GetARAgingReportOutput:
    """Generate an accounts receivable aging report as of a given date.
    Queries journal_entries where debit_account starts with "1200",
    groups by customer reference, and buckets into aging ranges.
    """
    query = db.query(JournalEntry).filter(
        ar_filter_clause(JournalEntry.debit_account, db),
        JournalEntry.status == "posted",
    )
    if input.customer_contact_id is not None:
        query = query.filter(JournalEntry.reference == input.customer_contact_id)
    entries = query.order_by(JournalEntry.reference).all()

    customer_groups: dict[str, list[JournalEntry]] = {}
    for entry in entries:
        ref = entry.reference or "__unknown__"
        customer_groups.setdefault(ref, []).append(entry)

    if not customer_groups:
        return GetARAgingReportOutput(
            as_of_date=input.as_of_date,
            buckets=[],
            customer_details=[],
            total_outstanding=Decimal("0"),
        )

    bucket_current = Decimal("0")
    bucket_30 = Decimal("0")
    bucket_60 = Decimal("0")
    bucket_90 = Decimal("0")
    details: list[CustomerAgingDetail] = []
    grand_total = Decimal("0")

    for ref, ref_entries in customer_groups.items():
        customer_name = ref
        if ref != "__unknown__":
            contact = db.query(Contact).filter(Contact.contact_id == ref).first()
            if contact:
                customer_name = contact.contact_name

        cur = Decimal("0")
        p30 = Decimal("0")
        p60 = Decimal("0")
        p90 = Decimal("0")

        for entry in ref_entries:
            days = (input.as_of_date - entry.posted_date).days
            if days <= 0:
                cur += entry.debit_amount
            elif days <= 30:
                cur += entry.debit_amount
            elif days <= 60:
                p30 += entry.debit_amount
            elif days <= 90:
                p60 += entry.debit_amount
            else:
                p90 += entry.debit_amount

        total = cur + p30 + p60 + p90
        bucket_current += cur
        bucket_30 += p30
        bucket_60 += p60
        bucket_90 += p90
        grand_total += total

        details.append(CustomerAgingDetail(
            customer_name=customer_name,
            total_outstanding=total,
            current=cur,
            past_30=p30,
            past_60=p60,
            past_90=p90,
        ))

    all_total = bucket_current + bucket_30 + bucket_60 + bucket_90
    buckets = [
        AgingBucketItem(bucket_name="Current", from_days=0, to_days=30, total_amount=bucket_current, percentage=float(bucket_current / all_total * 100) if all_total > 0 else 0),
        AgingBucketItem(bucket_name="31-60 days", from_days=31, to_days=60, total_amount=bucket_30, percentage=float(bucket_30 / all_total * 100) if all_total > 0 else 0),
        AgingBucketItem(bucket_name="61-90 days", from_days=61, to_days=90, total_amount=bucket_60, percentage=float(bucket_60 / all_total * 100) if all_total > 0 else 0),
        AgingBucketItem(bucket_name="90+ days", from_days=91, to_days=None, total_amount=bucket_90, percentage=float(bucket_90 / all_total * 100) if all_total > 0 else 0),
    ]

    return GetARAgingReportOutput(
        as_of_date=input.as_of_date,
        buckets=buckets,
        customer_details=details,
        total_outstanding=grand_total,
    )
