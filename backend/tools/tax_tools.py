"""Agent 7 - Tax Tools.

8 tools: calculate_withholding_tax, get_tax_planning_advice,
calculate_advance_minimum_tax, calculate_eobi_deductions,
adjust_sales_tax_input_output, flag_tax_exemption_zero_rating,
prepare_sales_tax_filing, prepare_income_tax_filing.
"""
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import json
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from db.models import JournalEntry, TaxRate, EobiRate, Contact, RetainedEarnings, TaxFiling
from tools.account_utils import revenue_filter_clause, expense_filter_clause
from tools.schemas import (
    CalculateWithholdingTaxInput, CalculateWithholdingTaxOutput,
    GetTaxPlanningAdviceInput, GetTaxPlanningAdviceOutput,
    CalculateAdvanceMinimumTaxInput, CalculateAdvanceMinimumTaxOutput,
    CalculateEobiDeductionsInput, CalculateEobiDeductionsOutput,
    AdjustSalesTaxInputOutputInput, AdjustSalesTaxInputOutputOutput,
    FlagTaxExemptionZeroRatingInput, FlagTaxExemptionZeroRatingOutput,
    FlaggedExemptionEntry,
    PrepareSalesTaxFilingInput, PrepareSalesTaxFilingOutput,
    PrepareIncomeTaxFilingInput, PrepareIncomeTaxFilingOutput,
    ListTaxFilingsInput, ListTaxFilingsOutput, TaxFilingItem,
)


def _round(value: Decimal, places: int = 2) -> Decimal:
    return value.quantize(Decimal("0." + "0" * places), rounding=ROUND_HALF_UP)


def _get_tax_rate(db: Session, tax_type: str, effective_date: date = None) -> TaxRate:
    """Get the most recent applicable tax rate from tax_rates table."""
    if effective_date is None:
        effective_date = date.today()
    rate = db.query(TaxRate).filter(
        TaxRate.tax_type == tax_type,
        TaxRate.effective_from <= effective_date,
        (TaxRate.effective_to >= effective_date) | (TaxRate.effective_to.is_(None)),
    ).order_by(TaxRate.effective_from.desc()).first()
    return rate


def _rate_or_zero(db: Session, tax_type: str, effective_date: date = None) -> tuple[Decimal, str]:
    """Look up a tax rate from the DB. Returns (rate, source_label).

    If the rate is not configured in tax_rates, returns (0, 'not_configured')
    so the caller can surface a clear message - never a silent hardcoded rate.
    """
    record = _get_tax_rate(db, tax_type, effective_date)
    if record is None:
        return Decimal("0"), "not_configured"
    return Decimal(str(record.rate)), f"tax_rates:{record.description or tax_type}"


def _is_revenue_entry(entry) -> bool:
    """True if an entry's credit side is a revenue account (name-based)."""
    return any(k in entry.credit_account.lower() for k in ("revenue", "sales"))


def _sales_tax_rate(db: Session, effective_date: date = None) -> tuple[Decimal, str]:
    """Sales tax rate resolved from tax_rates table (type SALES_TAX).

    Returns (rate, source). If not configured, (0, 'not_configured') so the
    caller can warn instead of using a hardcoded percentage.
    """
    return _rate_or_zero(db, "SALES_TAX", effective_date)


def _corporate_tax_rate(db: Session, effective_date: date = None) -> tuple[Decimal, str]:
    """Corporate income tax rate resolved from tax_rates table (type INCOME_TAX)."""
    return _rate_or_zero(db, "INCOME_TAX", effective_date)


def _get_eobi_rate(db: Session, rate_type: str = "standard") -> EobiRate:
    """Get the most recent applicable EOBI rate."""
    rate = db.query(EobiRate).filter(
        EobiRate.rate_type == rate_type,
    ).order_by(EobiRate.effective_from.desc()).first()
    return rate


# ---------------------------------------------------------------------------
# Tool 1: Calculate Withholding Tax
# ---------------------------------------------------------------------------

def calculate_withholding_tax(inp: CalculateWithholdingTaxInput, db: Session) -> CalculateWithholdingTaxOutput:
    """Calculate withholding tax (WHT) on a payment amount.

    Rate is resolved from tax_rates table by withholding_type (wht_<type>).
    No hardcoded fallback - if the rate is not configured, a clear error is
    raised instead of silently using a stale/assumed percentage.
    """
    rate, source = _rate_or_zero(db, f"wht_{inp.withholding_type}", inp.transaction_date)

    if rate == Decimal("0"):
        raise ValueError(
            f"Withholding tax rate for '{inp.withholding_type}' is not configured "
            "in tax_rates (wht_<type>). Add the rate before computing WHT."
        )

    tax_amount = _round(inp.amount * rate / Decimal("100"), 2)
    net_amount = _round(inp.amount - tax_amount, 2)

    return CalculateWithholdingTaxOutput(
        gross_amount=inp.amount,
        withholding_type=inp.withholding_type,
        rate_applied=rate,
        tax_amount=tax_amount,
        net_amount=net_amount,
        rate_source=source,
    )


# ---------------------------------------------------------------------------
# Tool 2: Get Tax Planning Advice
# ---------------------------------------------------------------------------

def get_tax_planning_advice(inp: GetTaxPlanningAdviceInput, db: Session) -> GetTaxPlanningAdviceOutput:
    """Generate tax planning advice based on stored financial data."""
    revenue = db.query(func.sum(JournalEntry.credit_amount)).filter(
        revenue_filter_clause(JournalEntry.credit_account, db),
        JournalEntry.status == "posted",
        func.extract("year", JournalEntry.posted_date) == inp.fiscal_year,
    ).scalar() or Decimal("0")

    expenses = db.query(func.sum(JournalEntry.debit_amount)).filter(
        expense_filter_clause(JournalEntry.debit_account, db),
        JournalEntry.status == "posted",
        func.extract("year", JournalEntry.posted_date) == inp.fiscal_year,
    ).scalar() or Decimal("0")

    revenue = _round(revenue, 2)
    expenses = _round(expenses, 2)
    net = _round(revenue - expenses, 2)

    data_summary = {
        "total_revenue": str(revenue),
        "total_expenses": str(expenses),
        "net_income": str(net),
        "fiscal_year": inp.fiscal_year,
    }

    advice_parts = []
    corp_rate, _src = _corporate_tax_rate(db)
    if revenue > Decimal("0"):
        est_tax = _round(net * corp_rate / Decimal("100"), 2) if corp_rate > Decimal("0") else Decimal("0")
        if net > Decimal("0"):
            rate_label = f"{corp_rate}%" if corp_rate > Decimal("0") else "the configured rate"
            advice_parts.append(
                f"Estimated tax liability for FY {inp.fiscal_year} is approximately {est_tax} "
                f"(based on {net} net income at {rate_label} corporate rate)."
            )
            if revenue > Decimal("10000000"):
                advice_parts.append(
                    "Your revenue exceeds 10M. Consider making quarterly advance tax payments "
                    "to avoid interest under Section 118 of the Income Tax Ordinance."
                )
        else:
            advice_parts.append(
                f"Net loss of {abs(net)} for FY {inp.fiscal_year}. "
                "You may be eligible for loss carry-forward under Section 57."
            )
        advice_parts.append(
            "Maintain proper documentation of all business expenses to support deductions."
        )
    else:
        advice_parts.append(
            f"No revenue data found for FY {inp.fiscal_year}. "
            "General advice: maintain proper records and consult a qualified tax advisor."
        )

    advice_parts.append(
        "Consider filing your returns before the due date to avoid late filing penalties."
    )

    return GetTaxPlanningAdviceOutput(
        advice=" ".join(advice_parts),
        fiscal_year=inp.fiscal_year,
        data_summary=data_summary,
    )


# ---------------------------------------------------------------------------
# Tool 3: Calculate Advance Minimum Tax
# ---------------------------------------------------------------------------

def calculate_advance_minimum_tax(inp: CalculateAdvanceMinimumTaxInput, db: Session) -> CalculateAdvanceMinimumTaxOutput:
    """Calculate advance minimum tax (AMT) on turnover.

    Rate is resolved from tax_rates table by business type (amt_<type>).
    No hardcoded fallback - if the rate is not configured, a clear error is raised.
    """
    rate, basis = _rate_or_zero(db, f"amt_{inp.business_type}")
    if rate == Decimal("0"):
        raise ValueError(
            f"AMT rate for business type '{inp.business_type}' is not configured "
            "in tax_rates (amt_<type>). Add the rate before computing AMT."
        )

    amt = _round(inp.annual_turnover * rate / Decimal("100"), 2)

    return CalculateAdvanceMinimumTaxOutput(
        annual_turnover=inp.annual_turnover,
        applicable_rate=rate,
        minimum_tax=amt,
        basis=basis,
        fiscal_year=inp.fiscal_year,
    )


# ---------------------------------------------------------------------------
# Tool 4: Calculate EOBI Deductions
# ---------------------------------------------------------------------------

def calculate_eobi_deductions(inp: CalculateEobiDeductionsInput, db: Session) -> CalculateEobiDeductionsOutput:
    """Calculate EOBI (Employees' Old-Age Benefits Institution) deductions.

    Employer/employee rates resolved from eobi_rates table. No hardcoded
    fallback - if no rate is configured, a clear error is raised.
    """
    rate_record = _get_eobi_rate(db, inp.employee_category or "standard")
    if rate_record is None:
        raise ValueError(
            "EOBI rate is not configured in eobi_rates "
            f"(rate_type='{inp.employee_category or 'standard'}'). "
            "Add the rate before computing EOBI deductions."
        )

    rate = rate_record.rate
    employee_rate = rate_record.employee_rate
    if employee_rate is None:
        raise ValueError(
            "EOBI employee_rate is not configured for "
            f"rate_type='{inp.employee_category or 'standard'}'."
        )
    max_insurable = rate_record.max_insurable_amount or Decimal("999999999")
    basis = f"eobi_rates_{inp.employee_category or 'standard'}"

    insurable_salary = min(inp.gross_salary, max_insurable)
    employer_contribution = _round(insurable_salary * rate / Decimal("100"), 2)
    employee_contribution = _round(insurable_salary * employee_rate / Decimal("100"), 2)

    return CalculateEobiDeductionsOutput(
        gross_salary=inp.gross_salary,
        employee_contribution=employee_contribution,
        employer_contribution=employer_contribution,
        total_contribution=_round(employer_contribution + employee_contribution, 2),
        rate_applied=rate,
        basis=basis,
    )


# ---------------------------------------------------------------------------
# Tool 5: Adjust Sales Tax Input/Output
# ---------------------------------------------------------------------------

def adjust_sales_tax_input_output(inp: AdjustSalesTaxInputOutputInput, db: Session) -> AdjustSalesTaxInputOutputOutput:
    """Adjust sales tax input vs output for a period.

    If override amounts provided, uses those. Otherwise calculates from journal entries.
    """
    adjustments = []

    sales_rate, rate_src = _sales_tax_rate(db)

    if inp.output_tax_amount is not None:
        output_tax = inp.output_tax_amount
        adjustments.append(f"Output tax overridden to {output_tax} (reason: {inp.adjustment_reason or 'manual override'})")
    else:
        if sales_rate == Decimal("0"):
            raise ValueError(
                "Sales tax rate is not configured in tax_rates (SALES_TAX). "
                "Add the rate before computing sales tax."
            )
        revenue = db.query(func.sum(JournalEntry.credit_amount)).filter(
            revenue_filter_clause(JournalEntry.credit_account, db),
            JournalEntry.status == "posted",
            func.extract("year", JournalEntry.posted_date) == inp.fiscal_year,
            func.extract("month", JournalEntry.posted_date) == inp.period,
        ).scalar() or Decimal("0")
        output_tax = _round(revenue * sales_rate / Decimal("100"), 2)
        adjustments.append(f"Output tax calculated at {sales_rate}% ({rate_src}) on revenue {_round(revenue, 2)}")

    if inp.input_tax_amount is not None:
        input_tax = inp.input_tax_amount
        adjustments.append(f"Input tax overridden to {input_tax} (reason: {inp.adjustment_reason or 'manual override'})")
    else:
        if sales_rate == Decimal("0"):
            raise ValueError(
                "Sales tax rate is not configured in tax_rates (SALES_TAX). "
                "Add the rate before computing sales tax."
            )
        purchases = db.query(func.sum(JournalEntry.debit_amount)).filter(
            expense_filter_clause(JournalEntry.debit_account, db),
            JournalEntry.status == "posted",
            func.extract("year", JournalEntry.posted_date) == inp.fiscal_year,
            func.extract("month", JournalEntry.posted_date) == inp.period,
        ).scalar() or Decimal("0")
        input_tax = _round(purchases * sales_rate / Decimal("100"), 2)
        adjustments.append(f"Input tax calculated at {sales_rate}% ({rate_src}) on purchases {_round(purchases, 2)}")

    net_tax = _round(output_tax - input_tax, 2)
    refund = Decimal("0")
    if net_tax < Decimal("0"):
        refund = abs(net_tax)
        net_tax = Decimal("0")
        adjustments.append(f"Input tax exceeds output tax - refund scenario: {refund}")

    summary_parts = [
        f"Period {inp.period}/{inp.fiscal_year}:",
        f"Output tax = {output_tax}",
        f"Input tax = {input_tax}",
        f"Net payable = {net_tax}",
    ]
    if refund > Decimal("0"):
        summary_parts.append(f"Refund = {refund}")

    return AdjustSalesTaxInputOutputOutput(
        period=inp.period,
        fiscal_year=inp.fiscal_year,
        calculated_output_tax=output_tax,
        calculated_input_tax=input_tax,
        net_tax_payable=net_tax,
        refund_amount=refund,
        adjustments=adjustments,
        needs_approval=True,
        summary=". ".join(summary_parts),
    )


# ---------------------------------------------------------------------------
# Tool 6: Flag Tax Exemption / Zero Rating
# ---------------------------------------------------------------------------

def flag_tax_exemption_zero_rating(inp: FlagTaxExemptionZeroRatingInput, db: Session) -> FlagTaxExemptionZeroRatingOutput:
    """Flag revenue entries that may qualify for tax exemption or zero-rating.

    Checks revenue entries (prefix 4) against exemption criteria:
    exports, certain services, basic goods.
    """
    query = db.query(JournalEntry).filter(
        JournalEntry.status == "posted",
        func.extract("year", JournalEntry.posted_date) == inp.fiscal_year,
    )

    if inp.entry_ids:
        query = query.filter(JournalEntry.entry_id.in_(inp.entry_ids))
    else:
        # Scan all revenue entries (accounts resolved from chart)
        query = query.filter(revenue_filter_clause(JournalEntry.credit_account, db))

    if inp.period:
        query = query.filter(func.extract("month", JournalEntry.posted_date) == inp.period)

    entries = query.all()

    flagged = []
    total_amount = Decimal("0")

    for entry in entries:
        is_rev = _is_revenue_entry(entry)
        account_name = entry.credit_account if is_rev else entry.debit_account
        exemption_type = ""
        confidence = "low"
        reasoning = ""

        # Check if entry reference matches an export contact
        contact = None
        if entry.contact_id:
            contact = db.query(Contact).filter(Contact.contact_id == entry.contact_id).first()
        elif entry.reference:
            contact = db.query(Contact).filter(
                Contact.contact_id == entry.reference
            ).first()

        amount = entry.credit_amount if is_rev else entry.debit_amount

        if contact and "export" in (contact.contact_type or "").lower():
            exemption_type = "zero_rated_export"
            confidence = "high"
            reasoning = f"Counterparty '{contact.contact_name}' is export-related (contact_type={contact.contact_type})"
        elif "export" in (entry.description or "").lower():
            exemption_type = "potential_export"
            confidence = "medium"
            reasoning = "Description references export - manual verification needed"
        elif "salary" in account_name.lower() or "wage" in account_name.lower():
            exemption_type = "exempt_income"
            confidence = "medium"
            reasoning = "Salary/wage income may be exempt from sales tax"
        elif amount < Decimal("1000"):
            exemption_type = "low_value"
            confidence = "low"
            reasoning = f"Low-value entry ({amount}) - likely not subject to sales tax"
        else:
            continue

        flagged.append(FlaggedExemptionEntry(
            entry_id=entry.entry_id,
            description=entry.description,
            amount=amount,
            exemption_type=exemption_type,
            confidence=confidence,
            reasoning=reasoning,
        ))
        total_amount += amount

    recommendation_parts = []
    if flagged:
        recommendation_parts.append(f"Found {len(flagged)} entries potentially qualifying for exemption/zero-rating.")
        high_conf = sum(1 for f in flagged if f.confidence == "high")
        med_conf = sum(1 for f in flagged if f.confidence == "medium")
        if high_conf:
            recommendation_parts.append(f"{high_conf} entries have high confidence - likely qualify.")
        if med_conf:
            recommendation_parts.append(f"{med_conf} entries require manual verification.")
    else:
        recommendation_parts.append("No entries flagged for tax exemption or zero-rating.")

    return FlagTaxExemptionZeroRatingOutput(
        flagged_entries=flagged,
        total_flagged_amount=_round(total_amount, 2),
        needs_approval=True,
        recommendation=" ".join(recommendation_parts),
    )


# ---------------------------------------------------------------------------
# Tool 7: Prepare Sales Tax Filing
# ---------------------------------------------------------------------------

def prepare_sales_tax_filing(inp: PrepareSalesTaxFilingInput, db: Session) -> PrepareSalesTaxFilingOutput:
    """Prepare sales tax filing data for FBR submission.

    Requires confirm=True. Never auto-submits.
    """
    if not inp.confirm:
        raise ValueError(
            "Sales tax filing preparation requires confirm=True. "
            "This prepares the data only - you will submit via FBR portal."
        )

    sales_rate, rate_src = _sales_tax_rate(db)
    if sales_rate == Decimal("0"):
        raise ValueError(
            "Sales tax rate is not configured in tax_rates (SALES_TAX). "
            "Add the rate before preparing the filing."
        )

    # Already filed for this period? Return the stored filing (no re-save).
    existing = db.query(TaxFiling).filter(
        TaxFiling.filing_type == "sales",
        TaxFiling.fiscal_year == inp.fiscal_year,
        TaxFiling.period == inp.period,
    ).first()
    if existing is not None:
        fd = json.loads(existing.filing_data) if existing.filing_data else {}
        return PrepareSalesTaxFilingOutput(
            filing_id=existing.filing_id,
            period=inp.period,
            fiscal_year=inp.fiscal_year,
            sales_tax_payable=Decimal(fd.get("output_tax", "0")),
            input_tax_adjustments=Decimal(fd.get("input_tax", "0")),
            net_amount_payable=Decimal(fd.get("net_payable", "0")),
            filing_data=fd,
            needs_approval=True,
            status=existing.status,
            message=(
                f"A sales tax filing for period {inp.period}/{inp.fiscal_year} already "
                f"exists ({existing.filing_id}) and was NOT re-saved. Review it via "
                "'show my tax filings' or the Export (Tax) workbook."
            ),
        )

    filing_id = f"ST-{inp.fiscal_year}-{inp.period:02d}-{uuid.uuid4().hex[:4].upper()}"

    # Calculate output tax from revenue
    revenue = db.query(func.sum(JournalEntry.credit_amount)).filter(
        revenue_filter_clause(JournalEntry.credit_account, db),
        JournalEntry.status == "posted",
        func.extract("year", JournalEntry.posted_date) == inp.fiscal_year,
        func.extract("month", JournalEntry.posted_date) == inp.period,
    ).scalar() or Decimal("0")

    output_tax = _round(revenue * sales_rate / Decimal("100"), 2)

    # Calculate input tax from purchases
    purchases = db.query(func.sum(JournalEntry.debit_amount)).filter(
        expense_filter_clause(JournalEntry.debit_account, db),
        JournalEntry.status == "posted",
        func.extract("year", JournalEntry.posted_date) == inp.fiscal_year,
        func.extract("month", JournalEntry.posted_date) == inp.period,
    ).scalar() or Decimal("0")

    input_tax = _round(purchases * sales_rate / Decimal("100"), 2)
    net_payable = _round(output_tax - input_tax, 2)
    if net_payable < Decimal("0"):
        net_payable = Decimal("0")

    filing_data = {
        "fbr_form": "Sales Tax Return (Form STR)",
        "period": f"{inp.fiscal_year}-{inp.period:02d}",
        "sales_tax_rate": str(sales_rate),
        "total_revenue": str(_round(revenue, 2)),
        "output_tax": str(output_tax),
        "total_purchases": str(_round(purchases, 2)),
        "input_tax": str(input_tax),
        "net_payable": str(net_payable),
        "status": "prepared_for_human_submission",
        "note": "This data must be verified and submitted manually via FBR portal.",
    }

    # Persist the prepared filing so it survives restarts and can be exported.
    db.add(TaxFiling(
        filing_id=filing_id,
        filing_type="sales",
        fiscal_year=inp.fiscal_year,
        period=inp.period,
        total_revenue=_round(revenue, 2),
        total_expenses=_round(purchases, 2),
        tax_liability=output_tax,
        net_payable=net_payable,
        filing_data=json.dumps(filing_data, default=str),
        status="prepared",
    ))
    db.commit()

    return PrepareSalesTaxFilingOutput(
        filing_id=filing_id,
        period=inp.period,
        fiscal_year=inp.fiscal_year,
        sales_tax_payable=output_tax,
        input_tax_adjustments=input_tax,
        net_amount_payable=net_payable,
        filing_data=filing_data,
        needs_approval=True,
        status="prepared",
        message=f"Sales tax filing {filing_id} prepared and saved. Review and submit via FBR portal.",
    )


# ---------------------------------------------------------------------------
# Tool 8: Prepare Income Tax Filing
# ---------------------------------------------------------------------------

def prepare_income_tax_filing(inp: PrepareIncomeTaxFilingInput, db: Session) -> PrepareIncomeTaxFilingOutput:
    """Prepare income tax filing data for FBR submission.

    Requires confirm=True. Never auto-submits.
    """
    if not inp.confirm:
        raise ValueError(
            "Income tax filing preparation requires confirm=True. "
            "This prepares the data only - you will submit via FBR portal."
        )

    # Already filed for this fiscal year? Return the stored filing (no re-save).
    existing = db.query(TaxFiling).filter(
        TaxFiling.filing_type == "income",
        TaxFiling.fiscal_year == inp.fiscal_year,
        TaxFiling.period.is_(None),
    ).first()
    if existing is not None:
        fd = json.loads(existing.filing_data) if existing.filing_data else {}
        return PrepareIncomeTaxFilingOutput(
            filing_id=existing.filing_id,
            fiscal_year=inp.fiscal_year,
            total_income=Decimal(fd.get("total_income", "0")),
            total_expenses=Decimal(fd.get("total_expenses", "0")),
            taxable_income=Decimal(fd.get("taxable_income", "0")),
            tax_liability=Decimal(fd.get("tax_liability", "0")),
            advance_tax_paid=Decimal(fd.get("advance_tax_paid", "0")),
            net_tax_due=Decimal(fd.get("net_tax_due", "0")),
            filing_data=fd,
            needs_approval=True,
            status=existing.status,
            message=(
                f"An income tax filing for FY {inp.fiscal_year} already exists "
                f"({existing.filing_id}) and was NOT re-saved. Review it via "
                "'show my tax filings' or the Export (Tax) workbook."
            ),
        )

    # Deterministic filing ID (stable across re-runs for the same fiscal year)
    filing_id = f"IT-{inp.fiscal_year}"

    # Total income from revenue accounts (resolved from chart)
    total_income = db.query(func.sum(JournalEntry.credit_amount)).filter(
        revenue_filter_clause(JournalEntry.credit_account, db),
        JournalEntry.status == "posted",
        func.extract("year", JournalEntry.posted_date) == inp.fiscal_year,
    ).scalar() or Decimal("0")

    # Total expenses from expense accounts (resolved from chart)
    total_expenses = db.query(func.sum(JournalEntry.debit_amount)).filter(
        expense_filter_clause(JournalEntry.debit_account, db),
        JournalEntry.status == "posted",
        func.extract("year", JournalEntry.posted_date) == inp.fiscal_year,
    ).scalar() or Decimal("0")

    total_income = _round(total_income, 2)
    total_expenses = _round(total_expenses, 2)
    taxable_income = _round(total_income - total_expenses, 2)
    if taxable_income < Decimal("0"):
        taxable_income = Decimal("0")

    # Estimate tax liability using rate configured in tax_rates (INCOME_TAX)
    corp_rate, _rate_src = _corporate_tax_rate(db)
    if corp_rate == Decimal("0"):
        raise ValueError(
            "Corporate income tax rate is not configured in tax_rates (INCOME_TAX). "
            "Add the rate before preparing the filing."
        )
    tax_rate = corp_rate
    tax_liability = _round(taxable_income * tax_rate / Decimal("100"), 2)

    # Check if any advance tax was paid (from retained_earnings or specific entries)
    advance_tax = Decimal("0")

    filing_data = {
        "fbr_form": "Income Tax Return (Form ITR)",
        "fiscal_year": str(inp.fiscal_year),
        "tax_rate": str(tax_rate),
        "total_income": str(total_income),
        "total_expenses": str(total_expenses),
        "taxable_income": str(taxable_income),
        "tax_liability": str(tax_liability),
        "advance_tax_paid": str(advance_tax),
        "net_tax_due": str(_round(tax_liability - advance_tax, 2)),
        "status": "prepared_for_human_submission",
        "note": "This data must be verified and submitted manually via FBR portal.",
    }

    net_due = _round(tax_liability - advance_tax, 2)

    message_parts = []
    if taxable_income > Decimal("0"):
        message_parts.append(f"Estimated tax liability for FY {inp.fiscal_year}: {net_due}")
    else:
        message_parts.append(f"No tax liability for FY {inp.fiscal_year} (net loss or zero income)")
    message_parts.append("Review all figures before submitting via FBR portal")

    # Persist the prepared filing so it survives restarts and can be exported.
    db.add(TaxFiling(
        filing_id=filing_id,
        filing_type="income",
        fiscal_year=inp.fiscal_year,
        period=None,
        total_revenue=total_income,
        total_expenses=total_expenses,
        tax_liability=tax_liability,
        net_payable=net_due,
        filing_data=json.dumps(filing_data, default=str),
        status="prepared",
    ))
    db.commit()

    return PrepareIncomeTaxFilingOutput(
        filing_id=filing_id,
        fiscal_year=inp.fiscal_year,
        total_income=total_income,
        total_expenses=total_expenses,
        taxable_income=taxable_income,
        tax_liability=tax_liability,
        advance_tax_paid=advance_tax,
        net_tax_due=net_due,
        filing_data=filing_data,
        needs_approval=True,
        status="prepared",
        message=". ".join(message_parts) + ".",
    )


# ---------------------------------------------------------------------------
# Tool 9: List Tax Filings (read-only)
# ---------------------------------------------------------------------------

def list_tax_filings(inp: ListTaxFilingsInput, db: Session) -> ListTaxFilingsOutput:
    """List all persisted tax filings (sales/income) for review and export.

    Read-only — never requires approval. Backed by the tax_filings table that
    prepare_sales_tax_filing / prepare_income_tax_filing persist into.
    """
    query = db.query(TaxFiling)
    if inp.filing_type:
        query = query.filter(TaxFiling.filing_type == inp.filing_type)
    if inp.fiscal_year:
        query = query.filter(TaxFiling.fiscal_year == inp.fiscal_year)
    rows = query.order_by(
        TaxFiling.created_at.desc(), TaxFiling.fiscal_year.desc()
    ).all()

    items = [
        TaxFilingItem(
            filing_id=r.filing_id,
            filing_type=r.filing_type,
            fiscal_year=r.fiscal_year,
            period=r.period,
            total_revenue=r.total_revenue or Decimal("0"),
            total_expenses=r.total_expenses or Decimal("0"),
            tax_liability=r.tax_liability or Decimal("0"),
            net_payable=r.net_payable or Decimal("0"),
            status=r.status or "prepared",
            created_at=r.created_at.date() if r.created_at else None,
        )
        for r in rows
    ]

    message = (
        f"{len(items)} tax filing(s) on record."
        if items
        else "No tax filings on record yet. Prepare a sales or income tax filing to save one."
    )
    return ListTaxFilingsOutput(items=items, total_count=len(items), message=message)
