"""Agent 9 - Advisory Tools.

5 tools: analyze_spending_patterns, calculate_financial_ratios,
assess_financial_health, generate_cost_cutting_recommendations,
generate_custom_report.
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import uuid

from sqlalchemy import func, extract, or_
from sqlalchemy.orm import Session

from db.models import JournalEntry, Budget, RetainedEarnings
from tools.account_utils import get_expense_prefixes, get_revenue_prefixes, expense_filter_clause
from tools.schemas import (
    CategorySpend, MonthlySpend,
    AnalyzeSpendingPatternsInput, AnalyzeSpendingPatternsOutput,
    RatioResult,
    CalculateFinancialRatiosInput, CalculateFinancialRatiosOutput,
    MetricRating,
    AssessFinancialHealthInput, AssessFinancialHealthOutput,
    Recommendation,
    GenerateCostCuttingInput, GenerateCostCuttingOutput,
    ReportSection,
    GenerateCustomReportInput, GenerateCustomReportOutput,
)


def _round(value: Decimal, places: int = 2) -> Decimal:
    return value.quantize(Decimal("0." + "0" * places), rounding=ROUND_HALF_UP)


def _get_prefix(code: str) -> str:
    """Get first digit of account code."""
    parts = code.split("-", 1)
    return parts[0].strip()[0] if parts[0].strip() else ""


def _aggregate_expenses(db: Session, from_date: date, to_date: date, account_prefixes: list[str] | None = None) -> list[JournalEntry]:
    """Aggregate expense entries in a date range.

    Prefixes resolved from the user's chart_of_accounts when not supplied.
    """
    prefixes = account_prefixes or get_expense_prefixes(db)
    query = db.query(JournalEntry).filter(
        JournalEntry.posted_date >= from_date,
        JournalEntry.posted_date <= to_date,
        JournalEntry.status == "posted",
    )
    if prefixes:
        # Filter by debit account prefix
        prefix_filters = [JournalEntry.debit_account.startswith(p) for p in prefixes]
        query = query.filter(prefix_filters[0] if len(prefix_filters) == 1 else or_(*prefix_filters))
    else:
        # Safety net: name-based expense match when chart not populated
        query = query.filter(expense_filter_clause(JournalEntry.debit_account, db))
    return query.all()


def _sum_by_prefix(db: Session, prefix: str, from_date: date | None = None, to_date: date | None = None) -> Decimal:
    """Sum debit amounts for accounts starting with a prefix."""
    query = db.query(func.sum(JournalEntry.debit_amount)).filter(
        JournalEntry.debit_account.startswith(prefix),
        JournalEntry.status == "posted",
    )
    if from_date:
        query = query.filter(JournalEntry.posted_date >= from_date)
    if to_date:
        query = query.filter(JournalEntry.posted_date <= to_date)
    return _round(Decimal(str(query.scalar() or "0")))


def _sum_credit_by_prefix(db: Session, prefix: str, from_date: date | None = None, to_date: date | None = None) -> Decimal:
    """Sum credit amounts for accounts starting with a prefix."""
    query = db.query(func.sum(JournalEntry.credit_amount)).filter(
        JournalEntry.credit_account.startswith(prefix),
        JournalEntry.status == "posted",
    )
    if from_date:
        query = query.filter(JournalEntry.posted_date >= from_date)
    if to_date:
        query = query.filter(JournalEntry.posted_date <= to_date)
    return _round(Decimal(str(query.scalar() or "0")))


# ---------------------------------------------------------------------------
# Tool 1: Analyze Spending Patterns
# ---------------------------------------------------------------------------

def analyze_spending_patterns(inp: AnalyzeSpendingPatternsInput, db: Session) -> AnalyzeSpendingPatternsOutput:
    """Analyze expense patterns over a date range. Groups by account prefix, month, or keyword."""
    entries = _aggregate_expenses(db, inp.from_date, inp.to_date, inp.account_prefixes)

    if inp.description_keyword:
        keyword = inp.description_keyword.lower()
        entries = [e for e in entries if keyword in e.description.lower()]

    if not entries:
        period_str = f"{inp.from_date.isoformat()} to {inp.to_date.isoformat()}"
        return AnalyzeSpendingPatternsOutput(
            period=period_str,
            total_spending=Decimal("0"),
            categories=[],
            top_categories=[],
            insights=["No spending data found for the selected period."],
            entry_count=0,
        )

    total_spending = sum(max(e.debit_amount, e.credit_amount) for e in entries)

    # Group by account category (prefix level)
    cat_map: dict[str, dict] = {}
    for e in entries:
        amt = max(e.debit_amount, e.credit_amount)
        prefix = _get_prefix(e.debit_account)
        cat_name = _prefix_label(prefix)
        if cat_name not in cat_map:
            cat_map[cat_name] = {"amount": Decimal("0"), "count": 0}
        cat_map[cat_name]["amount"] += amt
        cat_map[cat_name]["count"] += 1

    categories = [
        CategorySpend(
            name=name,
            amount=_round(v["amount"]),
            percentage=_round(v["amount"] / Decimal(str(total_spending)) * 100 if total_spending else Decimal("0")),
            count=v["count"],
        )
        for name, v in sorted(cat_map.items(), key=lambda x: -x[1]["amount"])
    ]

    top_categories = categories[:3] if len(categories) >= 3 else categories[:]

    # Monthly breakdown
    month_map: dict[str, Decimal] = {}
    for e in entries:
        amt = max(e.debit_amount, e.credit_amount)
        month_key = e.posted_date.strftime("%Y-%m")
        month_map[month_key] = month_map.get(month_key, Decimal("0")) + amt

    monthly = [
        MonthlySpend(month=m, amount=_round(a))
        for m, a in sorted(month_map.items())
    ]

    # Insights
    insights = []
    if categories:
        top = categories[0]
        insights.append(f"'{top.name}' is the largest expense category at {top.percentage}% of total spending ({top.amount}).")
    if len(categories) >= 2 and categories[0].percentage > 80:
        insights.append(f"Concentration risk: '{categories[0].name}' dominates at over 80% of total spending.")
    if len(monthly) >= 2:
        first, last = monthly[0], monthly[-1]
        if last.amount > first.amount:
            pct = _round((last.amount - first.amount) / first.amount * 100) if first.amount else Decimal("0")
            if pct > 20:
                insights.append(f"Spending trend: month-over-month increase of {pct}% from {first.month} to {last.month}.")
    ncats = len(categories)
    insights.append(f"Total of {len(entries)} transactions analyzed across {ncats} categor{'y' if ncats == 1 else 'ies'}.")

    period_str = f"{inp.from_date.isoformat()} to {inp.to_date.isoformat()}"

    return AnalyzeSpendingPatternsOutput(
        period=period_str,
        total_spending=_round(Decimal(str(total_spending))),
        categories=categories,
        top_categories=top_categories,
        monthly_breakdown=monthly if monthly else None,
        insights=insights,
        entry_count=len(entries),
    )


def _prefix_label(prefix: str) -> str:
    """Map account prefix to human-readable label."""
    labels = {
        "1": "Assets", "2": "Liabilities", "3": "Equity",
        "4": "Revenue", "5": "COGS", "6": "Operating Expenses", "7": "Tax", "8": "Other Expenses",
    }
    return labels.get(prefix, f"Prefix {prefix}")


# ---------------------------------------------------------------------------
# Tool 2: Calculate Financial Ratios
# ---------------------------------------------------------------------------

def calculate_financial_ratios(inp: CalculateFinancialRatiosInput, db: Session) -> CalculateFinancialRatiosOutput:
    """Calculate standard financial ratios for a fiscal year/period."""
    if inp.period:
        from_date = date(inp.fiscal_year, inp.period, 1)
        if inp.period == 12:
            to_date = date(inp.fiscal_year, 12, 31)
        else:
            to_date = date(inp.fiscal_year, inp.period + 1, 1) - __import__("datetime").timedelta(days=1)
    else:
        from_date = date(inp.fiscal_year, 1, 1)
        to_date = date(inp.fiscal_year, 12, 31)

    ratios: list[RatioResult] = []
    requested = set(inp.ratio_types) if inp.ratio_types else {"liquidity", "profitability", "leverage", "efficiency"}

    # Aggregate account balances
    total_assets = _sum_by_prefix(db, "1", from_date, to_date)
    total_liabilities = _sum_by_prefix(db, "2", from_date, to_date)
    total_equity = _sum_by_prefix(db, "3", from_date, to_date)
    total_revenue = _sum_credit_by_prefix(db, "4", from_date, to_date)
    total_cogs = _sum_by_prefix(db, "5", from_date, to_date)
    total_expenses = _sum_by_prefix(db, "5", from_date, to_date) + _sum_by_prefix(db, "6", from_date, to_date) + _sum_by_prefix(db, "8", from_date, to_date)

    net_income = total_revenue - total_expenses

    # --- Liquidity Ratios ---
    if "liquidity" in requested:
        # Current ratio
        if total_liabilities > 0:
            cr = _round(total_assets / total_liabilities)
            cr_interp = "Above 1.0 indicates sufficient short-term assets to cover liabilities." if cr >= Decimal("1") else "Below 1.0 suggests potential liquidity concerns."
        else:
            cr = Decimal("0")
            cr_interp = "No liabilities recorded - unable to compute ratio."
        ratios.append(RatioResult(name="Current Ratio", value=str(cr), benchmark="> 1.0", interpretation=cr_interp, category="liquidity"))

        # Quick ratio (assumes ~50% of assets are liquid for approximation)
        quick_assets = total_assets - _round(total_assets * Decimal("0.5"))
        if total_liabilities > 0:
            qr = _round(quick_assets / total_liabilities)
            qr_interp = "Above 0.5 suggests adequate immediate liquidity." if qr >= Decimal("0.5") else "Below 0.5 indicates potential near-term cash issues."
        else:
            qr = Decimal("0")
            qr_interp = "No liabilities recorded."
        ratios.append(RatioResult(name="Quick Ratio", value=str(qr), benchmark="> 0.5", interpretation=qr_interp, category="liquidity"))

    # --- Profitability Ratios ---
    if "profitability" in requested:
        if total_revenue > 0:
            npm = _round(net_income / total_revenue * 100)
            npm_interp = "Healthy profit margin." if npm >= Decimal("10") else "Thin profit margin - consider cost optimization." if npm >= Decimal("0") else "Negative profit margin - company is operating at a loss."
        else:
            npm = Decimal("0")
            npm_interp = "No revenue recorded."
        ratios.append(RatioResult(name="Net Profit Margin (%)", value=str(npm), benchmark="> 10%", interpretation=npm_interp, category="profitability"))

        if total_revenue > 0:
            gp = _round((total_revenue - total_cogs) / total_revenue * 100)
            gp_interp = "Strong gross margin." if gp >= Decimal("40") else "Moderate gross margin." if gp >= Decimal("20") else "Low gross margin."
        else:
            gp = Decimal("0")
            gp_interp = "No revenue recorded."
        ratios.append(RatioResult(name="Gross Profit Margin (%)", value=str(gp), benchmark="> 40%", interpretation=gp_interp, category="profitability"))

        if total_assets > 0:
            roa = _round(net_income / total_assets * 100)
            roa_interp = "Efficient asset utilization." if roa >= Decimal("5") else "Moderate asset returns." if roa >= Decimal("0") else "Negative return on assets."
        else:
            roa = Decimal("0")
            roa_interp = "No assets recorded."
        ratios.append(RatioResult(name="Return on Assets (%)", value=str(roa), benchmark="> 5%", interpretation=roa_interp, category="profitability"))

        if total_equity > 0:
            roe = _round(net_income / total_equity * 100)
            roe_interp = "Strong return for shareholders." if roe >= Decimal("15") else "Moderate shareholder returns." if roe >= Decimal("0") else "Negative shareholder return."
        else:
            roe = Decimal("0")
            roe_interp = "No equity recorded."
        ratios.append(RatioResult(name="Return on Equity (%)", value=str(roe), benchmark="> 15%", interpretation=roe_interp, category="profitability"))

    # --- Leverage Ratios ---
    if "leverage" in requested:
        if total_equity > 0:
            de = _round(total_liabilities / total_equity)
            de_interp = "Low leverage - conservative capital structure." if de <= Decimal("1") else "Moderate leverage." if de <= Decimal("2") else "High leverage - increased financial risk."
        else:
            de = Decimal("0")
            de_interp = "No equity (negative or zero) - unable to compute."
        ratios.append(RatioResult(name="Debt-to-Equity", value=str(de), benchmark="< 1.0", interpretation=de_interp, category="leverage"))

        if total_assets > 0:
            dr = _round(total_liabilities / total_assets)
            dr_interp = "Low debt proportion." if dr <= Decimal("0.5") else "Moderate debt level." if dr <= Decimal("0.7") else "High debt level."
        else:
            dr = Decimal("0")
            dr_interp = "No assets recorded."
        ratios.append(RatioResult(name="Debt Ratio", value=str(dr), benchmark="< 0.5", interpretation=dr_interp, category="leverage"))

    # --- Efficiency Ratios ---
    if "efficiency" in requested:
        if total_assets > 0:
            at = _round(total_revenue / total_assets)
            at_interp = "Efficient asset usage generating revenue." if at >= Decimal("1") else "Assets may be underutilized."
        else:
            at = Decimal("0")
            at_interp = "No assets recorded."
        ratios.append(RatioResult(name="Asset Turnover", value=str(at), benchmark="> 1.0", interpretation=at_interp, category="efficiency"))

        if total_revenue > 0:
            er = _round(total_expenses / total_revenue * 100)
            er_interp = "Good cost control." if er <= Decimal("80") else "Costs are high relative to revenue." if er <= Decimal("95") else "Expenses nearly match or exceed revenue."
        else:
            er = Decimal("0")
            er_interp = "No revenue recorded."
        ratios.append(RatioResult(name="Expense Ratio (%)", value=str(er), benchmark="< 80%", interpretation=er_interp, category="efficiency"))

    count = len(ratios)
    summary = f"Computed {count} financial ratios across {len(requested)} categories for fiscal year {inp.fiscal_year}."

    return CalculateFinancialRatiosOutput(
        fiscal_year=inp.fiscal_year,
        ratios=ratios,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Tool 3: Assess Financial Health
# ---------------------------------------------------------------------------

def assess_financial_health(inp: AssessFinancialHealthInput, db: Session) -> AssessFinancialHealthOutput:
    """Score financial health (0-100) based on weighted ratio analysis."""
    if inp.period:
        from_date = date(inp.fiscal_year, inp.period, 1)
        if inp.period == 12:
            to_date = date(inp.fiscal_year, 12, 31)
        else:
            to_date = date(inp.fiscal_year, inp.period + 1, 1) - __import__("datetime").timedelta(days=1)
    else:
        from_date = date(inp.fiscal_year, 1, 1)
        to_date = date(inp.fiscal_year, 12, 31)

    # Compute core figures
    total_assets = _sum_by_prefix(db, "1", from_date, to_date)
    total_liabilities = _sum_by_prefix(db, "2", from_date, to_date)
    total_equity = _sum_by_prefix(db, "3", from_date, to_date)
    total_revenue = _sum_credit_by_prefix(db, "4", from_date, to_date)
    total_expenses = (_sum_by_prefix(db, "5", from_date, to_date) +
                       _sum_by_prefix(db, "6", from_date, to_date) +
                       _sum_by_prefix(db, "8", from_date, to_date))
    total_cogs = _sum_by_prefix(db, "5", from_date, to_date)
    net_income = total_revenue - total_expenses

    if total_revenue == 0 and total_assets == 0:
        return AssessFinancialHealthOutput(
            health_assessment="insufficient_data",
            score=0,
            key_metrics=[],
            strengths=["Insufficient financial data to assess."],
            weaknesses=[],
            recommendations=["Record financial transactions to enable health assessment."],
            summary="No financial data found for the specified period.",
        )

    metrics: list[MetricRating] = []
    strengths: list[str] = []
    weaknesses: list[str] = []
    recommendations: list[str] = []

    # 1. Profitability (30% weight)
    profit_score = 0
    if total_revenue > 0:
        npm = float(net_income / total_revenue * 100)
        if npm >= 10:
            profit_score = 30
            strengths.append(f"Strong net profit margin of {npm:.1f}%")
        elif npm >= 5:
            profit_score = 20
            strengths.append(f"Moderate net profit margin of {npm:.1f}%")
        elif npm >= 0:
            profit_score = 10
            weaknesses.append(f"Thin net profit margin of {npm:.1f}% - monitor costs")
        else:
            profit_score = 0
            weaknesses.append(f"Negative net profit margin of {npm:.1f}% - operating at a loss")
            recommendations.append("Review cost structure and pricing strategy to return to profitability")
        metrics.append(MetricRating(name="Net Profit Margin", value=f"{npm:.1f}%", rating="strong" if npm >= 10 else "moderate" if npm >= 5 else "weak" if npm >= 0 else "critical"))
    else:
        metrics.append(MetricRating(name="Net Profit Margin", value="N/A", rating="insufficient_data"))

    # 2. Liquidity (25% weight)
    liq_score = 0
    if total_liabilities > 0:
        cr = float(total_assets / total_liabilities)
        if cr >= 1.5:
            liq_score = 25
            strengths.append(f"Healthy current ratio of {cr:.1f}")
        elif cr >= 1.0:
            liq_score = 15
            weaknesses.append(f"Adequate current ratio of {cr:.1f} - could be stronger")
        else:
            liq_score = 5
            weaknesses.append(f"Weak current ratio of {cr:.1f} - potential liquidity concerns")
            recommendations.append("Improve working capital by reducing short-term liabilities or increasing current assets")
        metrics.append(MetricRating(name="Current Ratio", value=f"{cr:.1f}", rating="strong" if cr >= 1.5 else "moderate" if cr >= 1.0 else "weak"))
    else:
        liq_score = 25
        metrics.append(MetricRating(name="Current Ratio", value="N/A", rating="strong"))

    # 3. Leverage (20% weight)
    lev_score = 0
    if total_equity > 0:
        de = float(total_liabilities / total_equity)
        if de <= 1.0:
            lev_score = 20
            strengths.append(f"Low debt-to-equity of {de:.1f} - conservative financing")
        elif de <= 2.0:
            lev_score = 10
            weaknesses.append(f"Moderate debt-to-equity of {de:.1f}")
        else:
            lev_score = 0
            weaknesses.append(f"High debt-to-equity of {de:.1f} - elevated financial risk")
            recommendations.append("Develop a debt reduction plan to lower leverage")
        metrics.append(MetricRating(name="Debt-to-Equity", value=f"{de:.1f}", rating="strong" if de <= 1.0 else "moderate" if de <= 2.0 else "weak"))
    else:
        lev_score = 10
        metrics.append(MetricRating(name="Debt-to-Equity", value="N/A", rating="moderate"))

    # 4. Efficiency (15% weight)
    eff_score = 0
    if total_revenue > 0:
        er = float(total_expenses / total_revenue * 100)
        if er <= 80:
            eff_score = 15
            strengths.append(f"Strong expense control at {er:.1f}% expense ratio")
        elif er <= 90:
            eff_score = 10
            weaknesses.append(f"Expense ratio of {er:.1f}% - room for improvement")
        else:
            eff_score = 5
            weaknesses.append(f"High expense ratio of {er:.1f}% - costs need attention")
            recommendations.append("Implement cost control measures to reduce expense ratio")
        metrics.append(MetricRating(name="Expense Ratio", value=f"{er:.1f}%", rating="strong" if er <= 80 else "moderate" if er <= 90 else "weak"))
    else:
        metrics.append(MetricRating(name="Expense Ratio", value="N/A", rating="insufficient_data"))

    # 5. Budget variance (10% weight)
    bud_score = 0
    budgets = db.query(Budget).filter(Budget.fiscal_year == inp.fiscal_year).all()
    if budgets:
        total_budget = sum(b.budget_amount for b in budgets)
        if total_budget > 0:
            variance = float(abs(total_expenses - total_budget) / total_budget * 100)
            if variance <= 5:
                bud_score = 10
                strengths.append(f"Spending within 5% of budget - good adherence")
            elif variance <= 10:
                bud_score = 5
                weaknesses.append(f"Spending deviates {variance:.1f}% from budget")
            else:
                bud_score = 0
                weaknesses.append(f"Significant budget variance of {variance:.1f}%")
                recommendations.append("Review budget assumptions and investigate major variances")
    else:
        bud_score = 5  # Neutral if no budget

    total_score = profit_score + liq_score + lev_score + eff_score + bud_score

    if total_score >= 70:
        assessment = "strong"
    elif total_score >= 50:
        assessment = "moderate"
    elif total_score >= 30:
        assessment = "weak"
    else:
        assessment = "critical"

    # Generate summary
    summary = (
        f"Financial health assessment: {assessment.upper()} (Score: {total_score}/100). "
        f"{len(strengths)} strength(s), {len(weaknesses)} weakness(es), {len(recommendations)} recommendation(s)."
    )

    return AssessFinancialHealthOutput(
        health_assessment=assessment,
        score=total_score,
        key_metrics=metrics,
        strengths=strengths,
        weaknesses=weaknesses,
        recommendations=recommendations,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Tool 4: Generate Cost Cutting Recommendations
# ---------------------------------------------------------------------------

def generate_cost_cutting_recommendations(inp: GenerateCostCuttingInput, db: Session) -> GenerateCostCuttingOutput:
    """Identify top expense categories and suggest cost-cutting opportunities."""
    if inp.period:
        from_date = date(inp.fiscal_year, inp.period, 1)
        if inp.period == 12:
            to_date = date(inp.fiscal_year, 12, 31)
        else:
            to_date = date(inp.fiscal_year, inp.period + 1, 1) - __import__("datetime").timedelta(days=1)
    else:
        from_date = date(inp.fiscal_year, 1, 1)
        to_date = date(inp.fiscal_year, 12, 31)

    prefixes = inp.target_account_prefixes or ["5", "6", "8"]
    entries = _aggregate_expenses(db, from_date, to_date, prefixes)

    if not entries:
        return GenerateCostCuttingOutput(
            total_expenses=Decimal("0"),
            top_expense_categories=[],
            recommendations=[],
            estimated_total_savings=Decimal("0"),
            summary="No expense data found for the specified period.",
        )

    total_expenses = sum(max(e.debit_amount, e.credit_amount) for e in entries)

    # Categorize by account prefix
    cat_map: dict[str, Decimal] = {}
    for e in entries:
        amt = max(e.debit_amount, e.credit_amount)
        prefix = _get_prefix(e.debit_account)
        cat_map[prefix] = cat_map.get(prefix, Decimal("0")) + amt

    # Determine which categories are "essential" vs "discretionary"
    essential_prefixes = {"5": "Cost of Goods Sold"}  # COGS directly tied to revenue
    discretionary_categories = {
        "6": ("Operating Expenses", 0.15),   # 15% savings potential
        "8": ("Other Expenses", 0.20),        # 20% savings potential
    }
    # Additional essential costs
    essential_labels = {
        "5": "Cost of Goods Sold",
    }

    recommendations: list[Recommendation] = []
    top_categories: list[CategorySpend] = []

    for prefix, amount in sorted(cat_map.items(), key=lambda x: -x[1]):
        pct = _round(amount / total_expenses * 100) if total_expenses > 0 else Decimal("0")
        cat_name = _prefix_label(prefix)
        top_categories.append(CategorySpend(name=cat_name, amount=_round(amount), percentage=pct, count=0))

        if prefix in essential_prefixes:
            continue  # No cutting recommendation for essential costs

        if prefix in discretionary_categories:
            label, savings_rate = discretionary_categories[prefix]
            potential = _round(amount * Decimal(str(savings_rate)))
            if inp.min_savings_threshold and potential < inp.min_savings_threshold:
                continue

            suggestions = {
                "6": "Review operational expenses - negotiate vendor contracts, reduce discretionary spending on supplies and travel.",
                "8": "Audit other expenses for one-off or non-recurring items that can be eliminated or reduced.",
            }
            priority = "high" if pct > 20 else "medium" if pct > 10 else "low"
            suggestions_text = suggestions.get(prefix, "Review expenses in this category for reduction opportunities.")

            recommendations.append(Recommendation(
                area=label,
                current_spend=_round(amount),
                potential_savings=potential,
                suggestion=suggestions_text,
                priority=priority,
            ))

    recommendations.sort(key=lambda r: -r.potential_savings)

    total_savings = sum(r.potential_savings for r in recommendations)

    if not recommendations:
        summary = f"Total expenses: {_round(Decimal(str(total_expenses)))}. No cost-cutting opportunities identified - expenses are primarily essential (COGS)."
    else:
        summary = f"Identified {len(recommendations)} cost-cutting opportunities with estimated total savings of {_round(total_savings)} out of {_round(Decimal(str(total_expenses)))} total expenses."

    return GenerateCostCuttingOutput(
        total_expenses=_round(Decimal(str(total_expenses))),
        top_expense_categories=sorted(top_categories, key=lambda x: -x.amount),
        recommendations=recommendations,
        estimated_total_savings=_round(total_savings),
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Tool 5: Generate Custom Report
# ---------------------------------------------------------------------------

def generate_custom_report(inp: GenerateCustomReportInput, db: Session) -> GenerateCustomReportOutput:
    """Generate a structured financial report based on type and sections."""
    report_id = f"RPT-{uuid.uuid4().hex[:8].upper()}"

    if inp.period_from and inp.period_to and inp.period_from > inp.period_to:
        raise ValueError("period_from must be <= period_to")

    period_from = inp.period_from or 1
    period_to = inp.period_to or 12

    from_date = date(inp.fiscal_year, period_from, 1)
    if period_to == 12:
        to_date = date(inp.fiscal_year, 12, 31)
    else:
        to_date = date(inp.fiscal_year, period_to + 1, 1) - __import__("datetime").timedelta(days=1)

    include = set(inp.include_sections) if inp.include_sections else {"revenue", "expenses", "ratios", "budget_variance", "trends"}

    sections: list[ReportSection] = []

    total_revenue = _sum_credit_by_prefix(db, "4", from_date, to_date)
    total_expenses = (_sum_by_prefix(db, "5", from_date, to_date) +
                       _sum_by_prefix(db, "6", from_date, to_date) +
                       _sum_by_prefix(db, "8", from_date, to_date))
    net = total_revenue - total_expenses
    total_assets = _sum_by_prefix(db, "1", from_date, to_date)
    total_liabilities = _sum_by_prefix(db, "2", from_date, to_date)
    total_equity = _sum_by_prefix(db, "3", from_date, to_date)

    if inp.report_type == "summary":
        sections.append(ReportSection(
            title="Financial Summary",
            content=f"Revenue: {total_revenue}, Expenses: {total_expenses}, Net Income: {net}",
            data={"revenue": str(total_revenue), "expenses": str(total_expenses), "net_income": str(net)},
        ))
        if "ratios" in include:
            cr = str(_round(total_assets / total_liabilities)) if total_liabilities > 0 else "N/A"
            npm = str(_round(net / total_revenue * 100)) if total_revenue > 0 else "N/A"
            de = str(_round(total_liabilities / total_equity)) if total_equity > 0 else "N/A"
            sections.append(ReportSection(
                title="Key Ratios",
                content=f"Current Ratio: {cr}, Net Profit Margin: {npm}%, Debt-to-Equity: {de}",
                data={"current_ratio": cr, "net_profit_margin": npm, "debt_to_equity": de},
            ))

    elif inp.report_type == "detailed":
        rev_detail = _round(total_revenue)
        exp_detail = _round(total_expenses)
        sections.append(ReportSection(
            title="Revenue Breakdown",
            content=f"Total Revenue (prefix 4): {rev_detail}",
            data={"total_revenue": str(rev_detail)},
        ))
        sections.append(ReportSection(
            title="Expense Breakdown",
            content=f"Total Expenses (prefixes 5/6/8): {exp_detail}",
            data={"total_expenses": str(exp_detail)},
        ))
        sections.append(ReportSection(
            title="Net Result",
            content=f"Net Income: {_round(net)}",
            data={"net_income": str(_round(net))},
        ))

    elif inp.report_type == "comparative":
        if inp.period_from and inp.period_to:
            comp_from = date(inp.fiscal_year, inp.period_from, 1)
            if inp.period_from == 12:
                comp_to_first = date(inp.fiscal_year, 12, 31)
            else:
                comp_to_first = date(inp.fiscal_year, inp.period_from + 1, 1) - __import__("datetime").timedelta(days=1)
            rev_a = _sum_credit_by_prefix(db, "4", comp_from, comp_to_first)
            exp_a = (_sum_by_prefix(db, "5", comp_from, comp_to_first) +
                      _sum_by_prefix(db, "6", comp_from, comp_to_first) +
                      _sum_by_prefix(db, "8", comp_from, comp_to_first))
            rev_b = total_revenue
            exp_b = total_expenses

            rev_change = _round((rev_b - rev_a) / rev_a * 100) if rev_a > 0 else Decimal("0")
            exp_change = _round((exp_b - exp_a) / exp_a * 100) if exp_a > 0 else Decimal("0")

            sections.append(ReportSection(
                title=f"Comparative: Period {inp.period_from} vs Period {inp.period_to}",
                content=f"Revenue: {rev_a} -> {rev_b} ({rev_change}% change). Expenses: {exp_a} -> {exp_b} ({exp_change}% change).",
                data={
                    "revenue_a": str(rev_a), "revenue_b": str(rev_b), "revenue_change_pct": str(rev_change),
                    "expenses_a": str(exp_a), "expenses_b": str(exp_b), "expenses_change_pct": str(exp_change),
                },
            ))

    elif inp.report_type == "trend":
        months_data = []
        for m in range(period_from, period_to + 1):
            mf = date(inp.fiscal_year, m, 1)
            mt = date(inp.fiscal_year, m + 1, 1) - __import__("datetime").timedelta(days=1) if m < 12 else date(inp.fiscal_year, 12, 31)
            m_rev = _sum_credit_by_prefix(db, "4", mf, mt)
            m_exp = (_sum_by_prefix(db, "5", mf, mt) +
                      _sum_by_prefix(db, "6", mf, mt) +
                      _sum_by_prefix(db, "8", mf, mt))
            months_data.append({"month": f"{inp.fiscal_year}-{m:02d}", "revenue": str(m_rev), "expenses": str(m_exp)})

        sections.append(ReportSection(
            title="Monthly Trend Analysis",
            content=f"Revenue trend across {len(months_data)} months.",
            data={"months": months_data},
        ))

    # Budget variance section
    if "budget_variance" in include:
        budgets = db.query(Budget).filter(Budget.fiscal_year == inp.fiscal_year).all()
        if budgets:
            total_budget = _round(sum(b.budget_amount for b in budgets))
            variance = _round(total_expenses - total_budget)
            var_pct = _round(variance / total_budget * 100) if total_budget > 0 else Decimal("0")
            sections.append(ReportSection(
                title="Budget Variance",
                content=f"Budget: {total_budget}, Actual: {_round(total_expenses)}, Variance: {variance} ({var_pct}%)",
                data={"budget": str(total_budget), "actual": str(_round(total_expenses)), "variance": str(variance), "variance_pct": str(var_pct)},
            ))

    summary_text = f"Report '{inp.report_title}' ({inp.report_type}) generated with {len(sections)} section(s) for FY {inp.fiscal_year}."

    return GenerateCustomReportOutput(
        report_id=report_id,
        report_title=inp.report_title,
        report_type=inp.report_type,
        generated_at=date.today(),
        sections=sections,
        summary=summary_text,
        needs_approval=True,
    )
