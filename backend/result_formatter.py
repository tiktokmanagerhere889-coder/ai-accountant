"""Deterministic result formatter — converts tool result dicts to plain English.

No LLM dependency. The LLM (best-effort) may polish the text further, but this
formatter guarantees a readable answer for every tool result even when Groq is
rate-limited or down.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any


def _money(v: Any) -> str:
    """Format a number as money with PKR prefix."""
    try:
        n = Decimal(str(v))
        return f"PKR {n:,.2f}"
    except Exception:
        return str(v)


def _num(v: Any) -> str:
    try:
        n = Decimal(str(v))
        return f"{n:,}"
    except Exception:
        return str(v)


def format_tool_result(tool_name: str, result: dict) -> str:
    """Return a plain-English summary of a tool result dict."""
    if not result or not isinstance(result, dict):
        return "Completed successfully."

    # Generic common fields
    formatter = _FORMATTERS.get(tool_name)
    if formatter:
        try:
            return formatter(result)
        except Exception:
            pass

    return _generic(result)


def has_dedicated_formatter(tool_name: str) -> bool:
    """True if this tool has a dedicated plain-English formatter.

    When True, the deterministic text is already readable and the LLM polish
    step must NOT override it (Groq has hallucinated numbers over correct data).
    Only tools WITHOUT a dedicated formatter fall back to LLM polish.
    """
    return tool_name in _FORMATTERS


def _generic(result: dict) -> str:
    """Fallback: pick the most meaningful field, else pretty JSON."""
    # Common summary fields
    if "summary" in result and result["summary"]:
        return str(result["summary"])
    if "message" in result and result["message"]:
        return str(result["message"])
    if "total_amount" in result and "vendor_name" in result:
        return f"Extraction: vendor {result['vendor_name']}, total {_money(result['total_amount'])}, confidence {result.get('confidence')}"
    # Try to find a 'count' or 'total' field
    for key in ["total_anomalies", "accounts_carried_forward", "total_unpaid", "total_overdue"]:
        if key in result:
            return f"{key.replace('_', ' ').title()}: {_num(result[key])}"
    # Fallback: compact JSON
    import json
    return json.dumps(result, indent=2, default=str)[:2000]


# --- Per-tool formatters ---

def _fmt_cash(result: dict) -> str:
    return f"Net cash position: {_money(result.get('closing_balance'))} as of {result.get('as_of_date')}."


def _fmt_trial_balance(result: dict) -> str:
    bal = "balanced" if result.get("in_balance") else "NOT balanced"
    diff = result.get("difference", 0)
    extra = "" if result.get("in_balance") else f" Difference: {_money(diff)}."
    return f"Trial balance as of {result.get('as_of_date')}: {result.get('total_debits', 0)} total debits, {result.get('total_credits', 0)} total credits. Status: {bal}.{extra}"


def _fmt_pnl(result: dict) -> str:
    net = result.get("net_income", 0)
    return f"P&L from {result.get('from_date')} to {result.get('to_date')}: Revenue {_money(result.get('total_revenue'))}, Expenses {_money(result.get('total_expenses'))}, Net Income {_money(net)}."


def _fmt_balance_sheet(result: dict) -> str:
    status = "balanced" if result.get("balanced") else "NOT balanced"
    return f"Balance sheet as of {result.get('as_of_date')}: Assets {_money(result.get('total_assets'))}, Liabilities {_money(result.get('total_liabilities'))}, Equity {_money(result.get('total_equity'))}. {status}."


def _fmt_cash_flow(result: dict) -> str:
    return f"Cash flow statement from {result.get('from_date')} to {result.get('to_date')}: {_money(result.get('net_cash_flow', 0))} net cash flow."


def _fmt_aging(result: dict) -> str:
    # GetAPAgingReportOutput uses grand_total; GetARAgingReportOutput uses
    # total_outstanding. Read whichever the tool returned.
    total = result.get("total_outstanding")
    if total is None:
        total = result.get("grand_total", 0)
    return f"Aging report as of {result.get('as_of_date')}: total outstanding {_money(total)}."


def _fmt_unpaid_bills(result: dict) -> str:
    """Plain-English unpaid-bills summary: per-bill lines + totals."""
    items = result.get("items") or []
    fd = result.get("as_of_date") or "today"
    if not items:
        return f"No unpaid bills as of {fd}."
    lines = []
    for b in items[:15]:
        vendor = b.get("vendor_name") or b.get("reference") or "Unknown"
        due = b.get("due_date", "")
        overdue = b.get("days_overdue")
        od = f", {overdue} days overdue" if overdue else ""
        lines.append(f"  - {vendor}: {_money(b.get('outstanding_balance', b.get('invoice_amount', 0)))} (due {due}{od})")
    more = f"\n  ... and {len(items) - 15} more" if len(items) > 15 else ""
    over = result.get("total_overdue")
    over_s = f", {_money(over)} overdue" if over else ""
    return f"Unpaid bills as of {fd}: {_money(result.get('total_unpaid', 0))}{over_s}.\n" + "\n".join(lines) + more


def _fmt_prepaid(result: dict) -> str:
    """Plain-English prepaid-adjustment summary: per-item + total."""
    items = result.get("items") or []
    fd = result.get("as_of_date") or "today"
    if not items:
        return f"No active prepaid expenses as of {fd}."
    lines = []
    for p in items[:15]:
        lines.append(
            f"  - {p.get('prepaid_id')} {p.get('description')}: {_money(p.get('monthly_amount', 0))}/mo, "
            f"{p.get('months_elapsed', 0)} months elapsed, {_money(p.get('amount_amortized', 0))} amortized, "
            f"{_money(p.get('remaining_balance', 0))} remaining"
        )
    return (
        f"Prepaid adjustment as of {fd}: total {_money(result.get('total_adjustment', 0))}.\n"
        + "\n".join(lines)
    )


def _fmt_depreciation(result: dict) -> str:
    """Plain-English depreciation summary: per-asset + total."""
    items = result.get("items") or []
    period = result.get("period_date") or "the period"
    method = result.get("method") or "straight_line"
    if not items:
        return f"No depreciation for {period}."
    lines = []
    for d in items[:15]:
        lines.append(
            f"  - {d.get('asset_name')} ({d.get('asset_id')}): {_money(d.get('monthly_depreciation', 0))}, "
            f"accumulated {_money(d.get('accumulated_depreciation', 0))}, "
            f"book value {_money(d.get('book_value', 0))}"
        )
    return (
        f"Depreciation for {period} ({method}): total {_money(result.get('total_depreciation', 0))}.\n"
        + "\n".join(lines)
    )


def _fmt_amortization(result: dict) -> str:
    """Plain-English amortization summary: per-asset + total."""
    items = result.get("items") or []
    period = result.get("period_date") or "the period"
    if not items:
        return f"No amortization for {period}."
    lines = []
    for d in items[:15]:
        lines.append(
            f"  - {d.get('asset_name')} ({d.get('asset_id')}): {_money(d.get('monthly_amortization', 0))}, "
            f"accumulated {_money(d.get('accumulated_amortization', 0))}, "
            f"book value {_money(d.get('book_value', 0))}"
        )
    return (
        f"Amortization for {period}: total {_money(result.get('total_amortization', 0))}.\n"
        + "\n".join(lines)
    )


def _fmt_payroll_recon(result: dict) -> str:
    """Plain-English payroll reconciliation summary."""
    total = _money(result.get('total_salary', 0))
    ded = _money(result.get('total_deductions', 0))
    net = _money(result.get('total_net_pay', 0))
    disc = result.get('discrepancies', 0)
    disc_s = "No discrepancies." if not disc else f"{disc} discrepancy(ies) found."
    return (
        f"Payroll reconciliation ({result.get('period_from')} to {result.get('period_to')}): "
        f"salary {total}, deductions {ded}, net pay {net}. {disc_s}"
    )


def _fmt_budget_variance(result: dict) -> str:
    """Plain-English budget-variance summary: per-account + flagged."""
    items = result.get("items") or []
    if not items:
        return f"Budget variance for FY {result.get('fiscal_year')} P{result.get('period')}: no budget rows."
    lines = []
    for v in items[:15]:
        flag = " [FLAGGED]" if v.get("flagged") else ""
        lines.append(
            f"  - {v.get('account_code')}: budget {_money(v.get('budget_amount', 0))}, "
            f"actual {_money(v.get('actual_amount', 0))}, variance {_money(v.get('variance', 0))} "
            f"({v.get('variance_pct', 0)}%){flag}"
        )
    return (
        f"Budget variance FY {result.get('fiscal_year')} period {result.get('period')}: "
        f"{result.get('flagged_count', 0)} flagged of {len(items)}.\n"
        + "\n".join(lines)
    )


def _fmt_general_ledger(result: dict) -> str:
    """Plain-English general ledger summary with per-account rows.

    The result is a period + list of account rows (code/name/type, opening,
    debits, credits, net movement, closing). Show each account on its own line
    with the closing balance, then the period totals.
    """
    accounts = result.get("accounts") or []
    fd = result.get("period_from") or result.get("from_date") or "start"
    td = result.get("period_to") or result.get("to_date") or "end"
    if not accounts:
        return f"General ledger ({fd} to {td}): no account activity found."
    lines = []
    for a in accounts[:15]:
        name = a.get("account_name") or a.get("account_code") or "?"
        code = a.get("account_code")
        label = f"{code} {name}".strip()
        lines.append(
            f"  - {label}: opening {_money(a.get('opening_balance', 0))}, "
            f"dr {_money(a.get('total_debits', 0))}, cr {_money(a.get('total_credits', 0))}, "
            f"closing {_money(a.get('closing_balance', a.get('net_movement', 0)))}"
        )
    more = f"\n  ... and {len(accounts) - 15} more accounts" if len(accounts) > 15 else ""
    total_dr = result.get("total_debits")
    total_cr = result.get("total_credits")
    totals = ""
    if total_dr is not None or total_cr is not None:
        totals = f"\nTotals: {_money(total_dr)} debits, {_money(total_cr)} credits."
    return f"General ledger ({fd} to {td}), {len(accounts)} account(s):\n" + "\n".join(lines) + more + totals


def _fmt_anomaly(result: dict) -> str:
    n = result.get("total_anomalies", 0)
    status = result.get("status", "clean")
    if n == 0:
        return f"Anomaly scan complete: {status}. No anomalies found."
    lines = []
    for a in result.get("anomalies", [])[:5]:
        lines.append(f"  - {a.get('anomaly_type')}: {a.get('description')} ({_money(a.get('amount'))}) - {a.get('reasoning')}")
    more = f"\n  ... and {n-5} more" if n > 5 else ""
    return f"Anomaly scan: {n} anomaly(ies) found.\n" + "\n".join(lines) + more


def _fmt_withholding(result: dict) -> str:
    return f"Withholding tax ({result.get('withholding_type')}): gross {_money(result.get('gross_amount'))}, rate {result.get('rate_applied')}%, tax {_money(result.get('tax_amount'))}, net {_money(result.get('net_amount'))}."


def _fmt_eobi(result: dict) -> str:
    return f"EOBI: gross salary {_money(result.get('gross_salary'))}, employee {_money(result.get('employee_contribution'))}, employer {_money(result.get('employer_contribution'))}, total {_money(result.get('total_contribution'))}."


def _fmt_retained(result: dict) -> str:
    return f"Retained earnings FY {result.get('fiscal_year')}: beginning {_money(result.get('beginning_retained_earnings'))}, net income {_money(result.get('net_income'))}, ending {_money(result.get('ending_retained_earnings'))}."


def _fmt_currency(result: dict) -> str:
    return f"{_money(result.get('original_amount'))} {result.get('from_currency')} = {_money(result.get('converted_amount'))} {result.get('to_currency')} at rate {result.get('conversion_rate')}."


def _fmt_breakeven(result: dict) -> str:
    return f"Break-even: {_num(result.get('breakeven_units'))} units, {_money(result.get('breakeven_revenue'))} revenue. Contribution margin/unit {_money(result.get('contribution_margin_per_unit'))}."


def _fmt_health(result: dict) -> str:
    score = result.get("score")
    return f"Financial health score: {score}/100." if score is not None else "Financial health assessment complete."


def _fmt_ratios(result: dict) -> str:
    ratios = result.get("ratios") or result.get("financial_ratios") or []
    if isinstance(ratios, list):
        parts = [
            f"{r.get('name', '?')}: {r.get('value', '?')} ({r.get('interpretation', '')})"
            for r in ratios[:8]
        ]
        return f"Financial ratios for FY {result.get('fiscal_year')}:\n" + "\n".join(f"  - {p}" for p in parts)
    if isinstance(ratios, dict):
        parts = [f"{k}: {v}" for k, v in list(ratios.items())[:6]]
        return "Financial ratios:\n" + "\n".join(f"  - {p}" for p in parts)
    return f"Financial ratios for FY {result.get('fiscal_year')}."


def _fmt_spending(result: dict) -> str:
    cats = result.get("categories") or result.get("items") or []
    fd = result.get("from_date") or result.get("period_from") or "start"
    td = result.get("to_date") or result.get("period_to") or "end"
    if isinstance(cats, list) and cats:
        parts = [f"{c.get('account_name', c.get('category', '?'))}: {_money(c.get('total', c.get('amount', 0)))}" for c in cats[:8]]
        total = result.get("total_spent", result.get("total", 0))
        return f"Spending analysis ({fd} to {td}):\n" + "\n".join(f"  - {p}" for p in parts) + f"\nTotal: {_money(total)}"
    total = result.get("total_spent", result.get("total", 0))
    if total:
        return f"Spending analysis ({fd} to {td}): Total {_money(total)}."
    return f"No spending data found for the period ({fd} to {td})."


def _fmt_custom_report(result: dict) -> str:
    return f"Report '{result.get('report_title')}' generated ({result.get('report_type')}): {result.get('summary', '')}"


def _fmt_loan(result: dict) -> str:
    return f"Loan schedule: {result.get('loan_name')} principal {_money(result.get('principal_amount'))}, rate {result.get('interest_rate')}%, term {result.get('term_months')} months."


def _fmt_forecast(result: dict) -> str:
    proj = result.get("projections") or []
    net = result.get("net_monthly_average", result.get("closing_balance"))
    parts = [
        f"  {p.get('date')}: inflow {_money(p.get('projected_inflow'))}, outflow {_money(p.get('projected_outflow'))}, net {_money(p.get('projected_net', 0))}"
        for p in proj[:5]
    ]
    head = f"Cash flow forecast ({result.get('forecast_days')} days):\n" + "\n".join(parts)
    if net:
        head += f"\nNet monthly average: {_money(net)}"
    return head


def _fmt_filing(result: dict) -> str:
    filing_id = result.get("filing_id") or result.get("report_id")
    id_s = f"\nFiling ID: {filing_id}" if filing_id else ""
    return f"{result.get('message') or result.get('summary') or 'Filing prepared.'}{id_s}"


def _fmt_amt(result: dict) -> str:
    """Plain-English advance minimum tax summary."""
    rate = result.get("applicable_rate")
    rate_s = f"{rate}%" if rate is not None else "the configured rate"
    return (
        f"Advance minimum tax on {_money(result.get('annual_turnover'))} turnover "
        f"for FY {result.get('fiscal_year')}: {rate_s}, minimum tax {_money(result.get('minimum_tax'))}. "
        f"(rate basis: {result.get('basis')})"
    )


def _fmt_sales_tax_adjust(result: dict) -> str:
    """Plain-English sales-tax input/output adjustment summary."""
    refund = result.get("refund_amount")
    refund_s = f", refund {_money(refund)}" if refund else ""
    return (
        f"Sales tax adjustment for period {result.get('period')} / FY {result.get('fiscal_year')}: "
        f"output tax {_money(result.get('calculated_output_tax'))}, "
        f"input tax {_money(result.get('calculated_input_tax'))}, "
        f"net payable {_money(result.get('net_tax_payable'))}{refund_s}."
    )


def _fmt_flag_exemption(result: dict) -> str:
    """Plain-English tax-exemption/zero-rating flag summary."""
    items = result.get("flagged_entries") or []
    if not items:
        return result.get("recommendation") or "No entries flagged for tax exemption or zero-rating."
    lines = []
    for f in items[:15]:
        lines.append(
            f"  - {f.get('entry_id')} {f.get('description')}: {_money(f.get('amount'))} "
            f"[{f.get('exemption_type')}, {f.get('confidence')} confidence]"
        )
    more = f"\n  ... and {len(items) - 15} more" if len(items) > 15 else ""
    return (
        f"Tax exemption/zero-rating flags: {_money(result.get('total_flagged_amount'))} across "
        f"{len(items)} entries.\n" + "\n".join(lines) + more
    )


def _fmt_generic_report(result: dict) -> str:
    return f"Report generated: {result.get('report_title')} - {result.get('summary', '')}"


_FORMATTERS = {
    "check_cash_position": _fmt_cash,
    "generate_trial_balance": _fmt_trial_balance,
    "generate_profit_loss": _fmt_pnl,
    "generate_balance_sheet": _fmt_balance_sheet,
    "generate_cash_flow_statement": _fmt_cash_flow,
    "get_ar_aging_report": _fmt_aging,
    "get_ap_aging_report": _fmt_aging,
    "get_general_ledger": _fmt_general_ledger,
    "review_unpaid_bills": _fmt_unpaid_bills,
    "calculate_prepaid_adjustment": _fmt_prepaid,
    "calculate_depreciation": _fmt_depreciation,
    "calculate_amortization": _fmt_amortization,
    "reconcile_payroll": _fmt_payroll_recon,
    "analyze_budget_variance": _fmt_budget_variance,
    "detect_anomaly_transactions": _fmt_anomaly,
    "calculate_withholding_tax": _fmt_withholding,
    "calculate_advance_minimum_tax": _fmt_amt,
    "adjust_sales_tax_input_output": _fmt_sales_tax_adjust,
    "flag_tax_exemption_zero_rating": _fmt_flag_exemption,
    "calculate_eobi_deductions": _fmt_eobi,
    "transfer_retained_earnings": _fmt_retained,
    "convert_foreign_currency": _fmt_currency,
    "calculate_breakeven": _fmt_breakeven,
    "assess_financial_health": _fmt_health,
    "calculate_financial_ratios": _fmt_ratios,
    "analyze_spending_patterns": _fmt_spending,
    "generate_custom_report": _fmt_custom_report,
    "forecast_cash_flow": _fmt_forecast,
    "get_loan_debt_schedule": _fmt_loan,
    "prepare_income_tax_filing": _fmt_filing,
    "prepare_sales_tax_filing": _fmt_filing,
    "draft_notes_to_financials": _fmt_generic_report,
    "prepare_budget_forecast": _fmt_generic_report,
    "get_tax_planning_advice": lambda r: r.get("advice") or "Tax planning advice generated.",
}
