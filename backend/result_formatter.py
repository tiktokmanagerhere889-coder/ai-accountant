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
    return f"Aging report as of {result.get('as_of_date')}: total outstanding {_money(result.get('total_outstanding'))}."


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
    return f"{result.get('message') or result.get('summary') or 'Filing prepared.'} (filing ID {result.get('filing_id') or result.get('report_id')})"


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
    "detect_anomaly_transactions": _fmt_anomaly,
    "calculate_withholding_tax": _fmt_withholding,
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
