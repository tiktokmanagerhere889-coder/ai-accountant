"""Agent 6 - Cost, Advanced Accounting & Budgeting Tools.

8 tools: calculate_breakeven, convert_foreign_currency, prepare_budget_forecast,
calculate_standard_costing_variance, allocate_overhead_cost,
calculate_revenue_recognition, flag_provision_contingent_liability,
flag_related_party_transaction.
"""
from datetime import date, timedelta, datetime
from decimal import Decimal, ROUND_HALF_UP
import uuid
import json
import urllib.request
import urllib.error

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from db.models import JournalEntry, Contact, ExchangeRate, Budget
from tools.schemas import (
    CalculateBreakevenInput, CalculateBreakevenOutput,
    ConvertForeignCurrencyInput, ConvertForeignCurrencyOutput,
    PrepareBudgetForecastInput, PrepareBudgetForecastOutput, BudgetForecastItem,
    CalculateStandardCostingVarianceInput, CalculateStandardCostingVarianceOutput,
    AllocateOverheadCostInput, AllocateOverheadCostOutput, AllocationResult,
    CalculateRevenueRecognitionInput, CalculateRevenueRecognitionOutput,
    FlagProvisionContingentLiabilityInput, FlagProvisionContingentLiabilityOutput,
    FlagRelatedPartyTransactionInput, FlagRelatedPartyTransactionOutput,
)
from decimal import Decimal


def _round(value: Decimal, places: int = 2) -> Decimal:
    """Round a Decimal to the given number of places."""
    return value.quantize(Decimal("0." + "0" * places), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Tool 1: Calculate Breakeven (pure formula, no DB)
# ---------------------------------------------------------------------------

def calculate_breakeven(inp: CalculateBreakevenInput, db: Session) -> CalculateBreakevenOutput:
    """Calculate break-even point using CVP analysis.

    Contribution margin = price - variable cost.
    Breakeven units = fixed_cost / contribution_margin.
    Breakeven revenue = breakeven_units * price.
    """
    if inp.selling_price_per_unit <= inp.variable_cost_per_unit:
        raise ValueError(
            f"Selling price ({inp.selling_price_per_unit}) must exceed "
            f"variable cost ({inp.variable_cost_per_unit})"
        )

    cm = inp.selling_price_per_unit - inp.variable_cost_per_unit
    cm_ratio = float(cm / inp.selling_price_per_unit)

    if inp.fixed_cost == Decimal("0"):
        return CalculateBreakevenOutput(
            breakeven_units=Decimal("0"),
            breakeven_revenue=Decimal("0"),
            contribution_margin_per_unit=cm,
            contribution_margin_ratio=cm_ratio,
            formula_used="Fixed cost is zero; breakeven is 0 units (always profitable)",
        )

    be_units = _round(inp.fixed_cost / cm, 2)
    be_revenue = _round(be_units * inp.selling_price_per_unit, 2)

    return CalculateBreakevenOutput(
        breakeven_units=be_units,
        breakeven_revenue=be_revenue,
        contribution_margin_per_unit=cm,
        contribution_margin_ratio=cm_ratio,
        formula_used="Breakeven Units = Fixed Cost / (Price - Variable Cost)",
    )


# ---------------------------------------------------------------------------
# Tool 2: Convert Foreign Currency (reads exchange_rates table)
# ---------------------------------------------------------------------------

LIVE_EXCHANGE_API = "https://open.er-api.com/v6/latest/{base}"
FALLBACK_EXCHANGE_API = "https://api.exchangerate-api.com/v4/latest/{base}"
RATE_STALENESS_DAYS = 1  # rates older than 1 day are considered stale


def _fetch_live_rate(from_currency: str, to_currency: str) -> tuple[Decimal, date] | None:
    """Fetch a live exchange rate from open.er-api.com (free, no key).

    Tries primary (open.er-api.com) then fallback (exchangerate-api.com).
    Returns (rate, rate_date) or None if both API calls fail / currency missing.
    """
    rate = _fetch_live_rate_primary(from_currency, to_currency)
    if rate is not None:
        return rate
    return _fetch_live_rate_fallback(from_currency, to_currency)


def _fetch_live_rate_primary(from_currency: str, to_currency: str) -> tuple[Decimal, date] | None:
    """Fetch a live exchange rate from open.er-api.com (free, no key).

    Returns (rate, rate_date) or None if the API call fails / currency missing.
    """
    try:
        url = LIVE_EXCHANGE_API.format(base=from_currency)
        req = urllib.request.Request(url, headers={"User-Agent": "AI-Accountant/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if data.get("result") != "success":
            return None

        rates = data.get("rates", {})
        target = to_currency.upper()
        if target not in rates:
            return None

        rate = Decimal(str(rates[target]))
        rate_date = date.today()
        return rate, rate_date
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, json.JSONDecodeError, KeyError, ValueError):
        return None


def _fetch_live_rate_fallback(from_currency: str, to_currency: str) -> tuple[Decimal, date] | None:
    """Fetch a live exchange rate from exchangerate-api.com (free, no key).

    Fallback when open.er-api.com fails.
    Returns (rate, rate_date) or None if the API call fails / currency missing.
    """
    try:
        url = FALLBACK_EXCHANGE_API.format(base=from_currency)
        req = urllib.request.Request(url, headers={"User-Agent": "AI-Accountant/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        rates = data.get("rates", {})
        target = to_currency.upper()
        if target not in rates:
            return None

        rate = Decimal(str(rates[target]))
        rate_date = date.today()
        return rate, rate_date
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, json.JSONDecodeError, KeyError, ValueError):
        return None


def _find_cached_rate(db: Session, from_curr: str, to_curr: str, target_date: date | None) -> ExchangeRate | None:
    """Find a cached exchange rate.

    If target_date is None, returns the latest cached rate.
    If target_date is provided, returns the rate with rate_date on or before
    the target (for historical lookup), preferring exact date match.
    If no rate exists on or before target_date, returns the nearest after.
    """
    q = db.query(ExchangeRate).filter(
        ExchangeRate.from_currency == from_curr,
        ExchangeRate.to_currency == to_curr,
    )
    if target_date is None:
        return q.order_by(ExchangeRate.rate_date.desc(), ExchangeRate.fetched_at.desc()).first()
    # Prefer exact date match
    exact = q.filter(ExchangeRate.rate_date == target_date).first()
    if exact:
        return exact
    # Rates on or before target_date (for historical lookup), nearest first
    before = q.filter(ExchangeRate.rate_date <= target_date).order_by(ExchangeRate.rate_date.desc()).all()
    if before:
        return before[0]
    # No rate on/before — fall back to nearest after
    after = q.order_by(ExchangeRate.rate_date.asc()).all()
    return after[0] if after else None


def convert_foreign_currency(inp: ConvertForeignCurrencyInput, db: Session) -> ConvertForeignCurrencyOutput:
    """Convert amount between currencies.

    Rate resolution order:
      1. Cached rate from exchange_rates table (matching rate_date if provided).
         - Fresh if fetched within last 24h.
         - Stale (warning) if older.
      2. Live rate from open.er-api.com (primary) -> exchangerate-api.com (fallback).
         Saved to exchange_rates on fetch.
      3. Stale cached rate with a clear warning (if live fails).
      4. No rate available -> 1:1 fallback with a clear warning (never silent 1:1).
    """
    if inp.from_currency.upper() == inp.to_currency.upper():
        return ConvertForeignCurrencyOutput(
            original_amount=inp.amount,
            from_currency=inp.from_currency.upper(),
            to_currency=inp.to_currency.upper(),
            conversion_rate=Decimal("1.0"),
            converted_amount=inp.amount,
            rate_source="same_currency",
            rate_date=inp.rate_date or date.today(),
        )

    from_curr = inp.from_currency.upper()
    to_curr = inp.to_currency.upper()
    requested_date = inp.rate_date

    # Step 1: Look up cached rate (exact date or nearest)
    cached = _find_cached_rate(db, from_curr, to_curr, requested_date)

    # If a specific date was requested and we have a matching/neighbor cache, use it
    if requested_date is not None and cached:
        fetched = cached.fetched_at or datetime.combine(cached.rate_date, datetime.min.time())
        fresh_cutoff = datetime.utcnow() - timedelta(hours=24)
        cached_fresh = fetched >= fresh_cutoff
        if not cached_fresh:
            warning = (
                f"Live rate fetch failed for {from_curr}->{to_curr}. "
                f"Using stale cached rate from {cached.rate_date} "
                f"(requested date: {requested_date})."
            )
            converted = _round(inp.amount * cached.rate, 2)
            return ConvertForeignCurrencyOutput(
                original_amount=inp.amount,
                from_currency=from_curr,
                to_currency=to_curr,
                conversion_rate=cached.rate,
                converted_amount=converted,
                rate_source=f"{cached.source or 'exchange_rates'} (cached, stale)",
                rate_date=cached.rate_date,
                warning=warning,
            )
        converted = _round(inp.amount * cached.rate, 2)
        return ConvertForeignCurrencyOutput(
            original_amount=inp.amount,
            from_currency=from_curr,
            to_currency=to_curr,
            conversion_rate=cached.rate,
            converted_amount=converted,
            rate_source=cached.source or "exchange_rates",
            rate_date=cached.rate_date,
        )

    # No specific date or no cached match: check freshness of latest cached rate
    cached_fresh = False
    if cached:
        fetched = cached.fetched_at or datetime.combine(cached.rate_date, datetime.min.time())
        fresh_cutoff = datetime.utcnow() - timedelta(hours=24)
        cached_fresh = fetched >= fresh_cutoff

    # Step 2: Fresh cached rate available
    if cached and cached_fresh:
        converted = _round(inp.amount * cached.rate, 2)
        return ConvertForeignCurrencyOutput(
            original_amount=inp.amount,
            from_currency=from_curr,
            to_currency=to_curr,
            conversion_rate=cached.rate,
            converted_amount=converted,
            rate_source=cached.source or "exchange_rates",
            rate_date=cached.rate_date,
        )

    # Step 3: Try live API (primary then fallback)
    live = _fetch_live_rate(from_curr, to_curr)
    if live is not None:
        live_rate, live_date = live

        # Upsert the fresh rate into exchange_rates
        if cached:
            cached.rate = live_rate
            cached.rate_date = live_date
            cached.source = "open.er-api.com / exchangerate-api.com"
            cached.fetched_at = datetime.utcnow()
        else:
            db.add(ExchangeRate(
                from_currency=from_curr,
                to_currency=to_curr,
                rate=live_rate,
                rate_date=live_date,
                source="open.er-api.com / exchangerate-api.com",
                fetched_at=datetime.utcnow(),
            ))
        db.commit()

        converted = _round(inp.amount * live_rate, 2)
        return ConvertForeignCurrencyOutput(
            original_amount=inp.amount,
            from_currency=from_curr,
            to_currency=to_curr,
            conversion_rate=live_rate,
            converted_amount=converted,
            rate_source="open.er-api.com / exchangerate-api.com",
            rate_date=live_date,
        )

    # Step 4: Live fetch failed - use stale cached rate with a clear warning
    if cached:
        warning = (
            f"Live rate fetch failed for {from_curr}->{to_curr}. "
            f"Using stale cached rate from {cached.rate_date}."
        )
        converted = _round(inp.amount * cached.rate, 2)
        return ConvertForeignCurrencyOutput(
            original_amount=inp.amount,
            from_currency=from_curr,
            to_currency=to_curr,
            conversion_rate=cached.rate,
            converted_amount=converted,
            rate_source=f"{cached.source or 'exchange_rates'} (cached, stale)",
            rate_date=cached.rate_date,
            warning=warning,
        )

    # Step 5: Nothing available - 1:1 fallback with a clear warning, never silent 1:1
    warning = (
        f"No cached or live exchange rate available for {from_curr}->{to_curr}. "
        f"Using 1:1 rate (assumed parity). Verify manually."
    )
    converted = _round(inp.amount, 2)
    return ConvertForeignCurrencyOutput(
        original_amount=inp.amount,
        from_currency=from_curr,
        to_currency=to_curr,
        conversion_rate=Decimal("1.0"),
        converted_amount=converted,
        rate_source="assumed_parity",
        rate_date=date.today(),
        warning=warning,
    )


# ---------------------------------------------------------------------------
# Tool 3: Prepare Budget Forecast (reads journal_entries + budgets)
# ---------------------------------------------------------------------------

def prepare_budget_forecast(inp: PrepareBudgetForecastInput, db: Session) -> PrepareBudgetForecastOutput:
    """Prepare budget forecast from historical spending patterns.

    Averages monthly actuals from journal_entries over available history.
    Uses existing budget as baseline if available. Confidence scales with
    months of data: <3=low, 3-11=medium, 12+=high.
    """
    query = db.query(
        JournalEntry.debit_account,
        func.sum(JournalEntry.debit_amount).label("total_debit"),
        func.count(func.distinct(func.date_trunc("month", JournalEntry.posted_date))).label("months"),
    )

    if inp.account_code_prefix:
        query = query.filter(JournalEntry.debit_account.startswith(inp.account_code_prefix))

    # Aggregate grouping by debit account (expenses) and credit account (revenue)
    debit_data = query.filter(
        JournalEntry.status == "posted",
    ).group_by(JournalEntry.debit_account).all()

    credit_query = db.query(
        JournalEntry.credit_account,
        func.sum(JournalEntry.credit_amount).label("total_credit"),
        func.count(func.distinct(func.date_trunc("month", JournalEntry.posted_date))).label("months"),
    )
    if inp.account_code_prefix:
        credit_query = credit_query.filter(JournalEntry.credit_account.startswith(inp.account_code_prefix))

    credit_data = credit_query.filter(
        JournalEntry.status == "posted",
    ).group_by(JournalEntry.credit_account).all()

    # Also fetch existing budgets for same fiscal year as baseline
    budget_query = db.query(Budget).filter(Budget.fiscal_year == inp.fiscal_year)
    if inp.account_code_prefix:
        budget_query = budget_query.filter(Budget.account_code.startswith(inp.account_code_prefix))
    existing_budgets = {b.account_code: b.budget_amount for b in budget_query.all()}

    items = []
    total_forecast = Decimal("0")
    max_months = 0

    # Process debit-side accounts
    for row in debit_data:
        months = row.months if row.months else 0
        max_months = max(max_months, months)
        # Extract account code (before the dash if present)
        acct_code = row.debit_account.split("-")[0] if "-" in row.debit_account else row.debit_account
        total_amount = row.total_debit or Decimal("0")

        monthly_avg = _round(total_amount / Decimal(max(months, 1)), 2)
        forecast = monthly_avg * Decimal(inp.periods)

        # If budget exists, blend with inflation adjustment
        if acct_code in existing_budgets:
            budget_amt = existing_budgets[acct_code]
            # Weighted: 70% historical avg, 30% prior budget, with 5% inflation adjustment
            blended = monthly_avg * Decimal("0.7") + (budget_amt / Decimal(inp.periods)) * Decimal("0.3")
            forecast = _round(blended * Decimal("1.05") * Decimal(inp.periods), 2)
            basis = "historical_avg_budget_blended"
        else:
            basis = "historical_avg"

        items.append(BudgetForecastItem(
            account_code=acct_code,
            account_name=row.debit_account,
            historical_avg=monthly_avg,
            forecast_amount=forecast,
            basis=basis,
        ))
        total_forecast += forecast

    # Process credit-side accounts (revenue)
    for row in credit_data:
        months = row.months if row.months else 0
        if months == 0:
            continue
        max_months = max(max_months, months)
        acct_code = row.credit_account.split("-")[0] if "-" in row.credit_account else row.credit_account
        total_amount = row.total_credit or Decimal("0")

        monthly_avg = _round(total_amount / Decimal(months), 2)
        forecast = monthly_avg * Decimal(inp.periods)

        if acct_code in existing_budgets:
            budget_amt = existing_budgets[acct_code]
            blended = monthly_avg * Decimal("0.7") + (budget_amt / Decimal(inp.periods)) * Decimal("0.3")
            forecast = _round(blended * Decimal("1.05") * Decimal(inp.periods), 2)
            basis = "historical_avg_budget_blended"
        else:
            basis = "historical_avg"

        items.append(BudgetForecastItem(
            account_code=acct_code,
            account_name=row.credit_account,
            historical_avg=monthly_avg,
            forecast_amount=forecast,
            basis=basis,
        ))
        total_forecast += forecast

    if max_months >= 12:
        confidence = "high"
    elif max_months >= 3:
        confidence = "medium"
    else:
        confidence = "low"

    return PrepareBudgetForecastOutput(
        fiscal_year=inp.fiscal_year,
        periods=inp.periods,
        forecast_items=items,
        total_forecast=_round(total_forecast, 2),
        data_months=max_months,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Tool 4: Calculate Standard Costing Variance
# ---------------------------------------------------------------------------

def calculate_standard_costing_variance(
    inp: CalculateStandardCostingVarianceInput, db: Session
) -> CalculateStandardCostingVarianceOutput:
    """Compare standard cost to actual cost for an account.

    actual_cost = sum of debit amounts to the given account_code in the period.
    cost_variance = actual - standard. variance_pct = (variance / standard) * 100.
    """
    actual = db.query(func.sum(JournalEntry.debit_amount)).filter(
        JournalEntry.debit_account.startswith(inp.account_code),
        JournalEntry.status == "posted",
        func.extract("year", JournalEntry.posted_date) == inp.fiscal_year,
        func.extract("month", JournalEntry.posted_date) == inp.period,
    ).scalar() or Decimal("0")

    actual = _round(actual, 2)
    cost_variance = _round(actual - inp.standard_cost, 2)
    variance_pct = _round((cost_variance / inp.standard_cost) * Decimal("100"), 2)

    variance_type = "favorable" if cost_variance < 0 else "unfavorable"
    explanation = (
        f"Actual cost ({actual}) vs standard ({inp.standard_cost}): "
        f"{variance_type} variance of {cost_variance} ({variance_pct}%). "
    )

    quantity_variance = None
    if inp.standard_quantity is not None:
        # Approximate: each entry has a quantity of 1, count rows as proxy
        actual_qty = db.query(func.count(JournalEntry.id)).filter(
            JournalEntry.debit_account.startswith(inp.account_code),
            JournalEntry.status == "posted",
            func.extract("year", JournalEntry.posted_date) == inp.fiscal_year,
            func.extract("month", JournalEntry.posted_date) == inp.period,
        ).scalar() or 0
        quantity_variance = Decimal(actual_qty) - inp.standard_quantity
        explanation += f"Quantity variance: {quantity_variance} (standard: {inp.standard_quantity}, actual: {actual_qty})."

    return CalculateStandardCostingVarianceOutput(
        account_code=inp.account_code,
        period=inp.period,
        fiscal_year=inp.fiscal_year,
        standard_cost=inp.standard_cost,
        actual_cost=actual,
        cost_variance=cost_variance,
        variance_pct=variance_pct,
        actual_quantity=Decimal(actual_qty) if inp.standard_quantity is not None else None,
        quantity_variance=quantity_variance,
        needs_approval=True,
        explanation=explanation,
    )


# ---------------------------------------------------------------------------
# Tool 5: Allocate Overhead Cost (pure calculation)
# ---------------------------------------------------------------------------

def allocate_overhead_cost(inp: AllocateOverheadCostInput, db: Session) -> AllocateOverheadCostOutput:
    """Allocate overhead cost across departments based on allocation basis.

    Each department's allocation = (dept_basis / total_basis) * total_overhead.
    """
    total_basis = sum(item.value for item in inp.allocation_pool)

    if total_basis == Decimal("0"):
        raise ValueError("Allocation basis values sum to zero - cannot allocate.")

    allocations = []
    total_allocated = Decimal("0")

    for item in inp.allocation_pool:
        pct = float(item.value / total_basis) * 100.0
        amt = _round((item.value / total_basis) * inp.total_overhead, 2)
        allocations.append(AllocationResult(
            department_name=item.name,
            basis_value=item.value,
            percentage=pct,
            allocated_amount=amt,
        ))
        total_allocated += amt

    # Adjust rounding difference to ensure sum equals total_overhead
    diff = inp.total_overhead - total_allocated
    if diff != Decimal("0"):
        allocations[-1].allocated_amount = _round(allocations[-1].allocated_amount + diff, 2)
        total_allocated = inp.total_overhead

    return AllocateOverheadCostOutput(
        allocations=allocations,
        total_allocated=total_allocated,
        basis_used=inp.allocation_basis,
        period=inp.period,
        fiscal_year=inp.fiscal_year,
        needs_approval=True,
    )


# ---------------------------------------------------------------------------
# Tool 6: Calculate Revenue Recognition
# ---------------------------------------------------------------------------

def calculate_revenue_recognition(
    inp: CalculateRevenueRecognitionInput, db: Session
) -> CalculateRevenueRecognitionOutput:
    """Calculate revenue to recognize under percentage-of-completion method.

    total_recognizable = contract_value * (completion_pct / 100).
    current_period = total_recognizable - previously_recognized.
    """
    # Clamp completion to 100
    pct = min(inp.completion_percentage, Decimal("100"))
    total_rec = _round(inp.contract_value * (pct / Decimal("100")), 2)

    prev = inp.previous_recognized or Decimal("0")

    if pct <= Decimal("0"):
        raise ValueError(f"Completion percentage must be > 0, got {inp.completion_percentage}")

    if prev >= total_rec:
        raise ValueError(
            f"Previously recognized ({prev}) >= total recognizable ({total_rec}) - "
            f"over-recognized or fully recognized."
        )

    current_revenue = _round(total_rec - prev, 2)
    remaining = _round(inp.contract_value - total_rec, 2)

    explanation = (
        f"Contract {inp.contract_id}: {pct}% complete of {inp.contract_value}. "
        f"Total recognizable: {total_rec}, previously recognized: {prev}. "
        f"Current period revenue: {current_revenue}."
    )

    return CalculateRevenueRecognitionOutput(
        contract_id=inp.contract_id,
        contract_value=inp.contract_value,
        completion_percentage=pct,
        total_recognizable=total_rec,
        previously_recognized=prev,
        current_period_revenue=current_revenue,
        remaining_revenue=remaining,
        needs_approval=True,
        explanation=explanation,
    )


# ---------------------------------------------------------------------------
# Tool 7: Flag Provision / Contingent Liability
# ---------------------------------------------------------------------------

def flag_provision_contingent_liability(
    inp: FlagProvisionContingentLiabilityInput, db: Session
) -> FlagProvisionContingentLiabilityOutput:
    """Flag a provision or contingent liability per IAS 37.

    Probable (>50%) = recognize liability + expense.
    Possible = disclose in notes.
    Remote = no action.
    """
    prob = inp.probability.lower()

    if prob == "probable":
        treatment = "recognize"
        status = "pending_approval"
        reasoning = (
            f"IAS 37: Probability is '{prob}' - obligation is likely. "
            f"Recommend recognizing a liability of {inp.estimated_amount} "
            f"with corresponding expense. Debit: appropriate expense account, "
            f"Credit: Provision for {inp.description}."
        )
    elif prob == "possible":
        treatment = "disclose"
        status = "draft"
        reasoning = (
            f"IAS 37: Probability is 'possible' - obligation may arise. "
            f"Recommend disclosure in notes only. No journal entry needed."
        )
    elif prob == "remote":
        treatment = "ignore"
        status = "draft"
        reasoning = (
            f"IAS 37: Probability is 'remote' - obligation unlikely to arise. "
            f"No recognition or disclosure required."
        )
    else:
        raise ValueError(f"Invalid probability '{prob}'. Must be 'probable', 'possible', or 'remote'.")

    provision_id = f"PROV-{uuid.uuid4().hex[:6].upper()}"

    return FlagProvisionContingentLiabilityOutput(
        provision_id=provision_id,
        description=inp.description,
        estimated_amount=inp.estimated_amount,
        probability=inp.probability,
        accounting_treatment=treatment,
        needs_approval=True,
        reasoning=reasoning,
        status=status,
    )


# ---------------------------------------------------------------------------
# Tool 8: Flag Related Party Transaction (hybrid matching)
# ---------------------------------------------------------------------------

def flag_related_party_transaction(
    inp: FlagRelatedPartyTransactionInput, db: Session
) -> FlagRelatedPartyTransactionOutput:
    """Check if a transaction involves a related party.

    Matching (hybrid):
    1. If journal_entry.contact_id is set -> look up contact.related_party directly (reliable)
    2. Fallback: match journal_entry.reference against contacts.contact_id
       or contacts.contact_name (case-insensitive, trimmed)
    """
    flag_id = f"RPT-{uuid.uuid4().hex[:6].upper()}"
    entry = db.query(JournalEntry).filter(
        JournalEntry.entry_id == inp.entry_id
    ).first()

    if not entry:
        return FlagRelatedPartyTransactionOutput(
            flag_id=flag_id,
            entry_id=inp.entry_id,
            counterparty_name=inp.counterparty_name,
            related_party_status="not_related",
            confidence="low",
            disclosure_required=False,
            matched_via="no_match",
            reasoning=f"Journal entry '{inp.entry_id}' not found. No related-party match possible.",
            needs_approval=True,
        )

    matched_via = "no_match"
    related_party_status = "not_related"
    confidence = "low"
    matched_contact = None

    # Strategy 1: contact_id (reliable)
    if entry.contact_id:
        matched_contact = db.query(Contact).filter(
            Contact.contact_id == entry.contact_id
        ).first()
        if matched_contact:
            matched_via = "contact_id"
            confidence = "high"

    # Strategy 2: reference fallback (case-insensitive, trimmed)
    if not matched_contact and entry.reference:
        ref_trimmed = entry.reference.strip()
        # Match against contact_id first
        matched_contact = db.query(Contact).filter(
            func.lower(Contact.contact_id) == func.lower(ref_trimmed)
        ).first()
        # Fallback to contact_name
        if not matched_contact:
            matched_contact = db.query(Contact).filter(
                func.lower(Contact.contact_name) == func.lower(inp.counterparty_name.strip())
            ).first()
        if matched_contact:
            matched_via = "reference_fallback"
            confidence = "medium"

    if matched_contact:
        if matched_contact.related_party:
            related_party_status = "confirmed_related"
            disclosure_required = True
        else:
            related_party_status = "potential_related"
            disclosure_required = False

        reasoning = (
            f"Counterparty '{matched_contact.contact_name}' (ID: {matched_contact.contact_id}) "
            f"matched via {matched_via}."
        )
        if matched_contact.related_party:
            reasoning += f" Marked as related party per contacts database."
        else:
            reasoning += f" Not flagged as related party - contacts.related_party = False."
    else:
        # Counterparty not in contacts
        related_party_status = "not_related"
        disclosure_required = False
        confidence = "low"
        reasoning = (
            f"Counterparty '{inp.counterparty_name}' not found in contacts database. "
            f"No related-party relationship identified."
        )

    return FlagRelatedPartyTransactionOutput(
        flag_id=flag_id,
        entry_id=inp.entry_id,
        counterparty_name=inp.counterparty_name,
        related_party_status=related_party_status,
        confidence=confidence,
        disclosure_required=disclosure_required,
        matched_via=matched_via,
        reasoning=reasoning,
        needs_approval=True,
    )
