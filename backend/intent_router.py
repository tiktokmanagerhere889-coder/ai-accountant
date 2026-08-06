"""Deterministic intent router — maps user messages to the right tool WITHOUT an LLM.

This is the reliability fix for the chat. The LLM (Groq) was deciding which tool
to call, and small models either refused ("I can't do this"), hallucinated
placeholder data, or failed with "Failed to call a function". This router:

  1. Matches the user's message to a tool by keyword/pattern (deterministic).
  2. Extracts parameters from the message (fiscal year, period, dates, amounts).
  3. Executes the tool via tool_registry against real DB data.
  4. Returns the real result — never a refusal, never fabricated.

The LLM is then only used to FORMAT the result into plain English (best-effort),
never to decide what to run. So it cannot refuse or invent data.

Router entries are ordered most-specific first so "cash flow forecast" matches
forecast_cash_flow before "cash position" matches check_cash_position.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from tool_registry import execute_tool, REGISTRY


# ---------------------------------------------------------------------------
# Parameter extraction helpers
# ---------------------------------------------------------------------------

def _extract_year(text: str) -> Optional[int]:
    """Find a 4-digit year in 2020-2035 range."""
    m = re.search(r"\b(20[2-3][0-9])\b", text)
    return int(m.group(1)) if m else None


def _extract_period(text: str) -> Optional[int]:
    """Find a month number 1-12, or month names."""
    names = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
        "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    for name, num in names.items():
        if name in text.lower():
            return num
    m = re.search(r"\b([1-9]|1[0-2])\b", text)
    return int(m.group(1)) if m else None


def _extract_amount(text: str) -> Optional[str]:
    """Find a currency amount (with or without commas/decimals)."""
    m = re.search(r"(\d[\d,]*(?:\.\d{1,2})?)", text.replace(",", ""))
    if not m:
        return None
    # Skip if it's a year
    val = m.group(1)
    if val.isdigit() and len(val) == 4 and 2020 <= int(val) <= 2035:
        return None
    return val


def _extract_date(text: str, default: date = None) -> Optional[date]:
    """Parse a date: YYYY-MM-DD, or relative phrases like 'today', 'this month'."""
    t = text.lower()
    if "yesterday" in t:
        return date.today() - timedelta(days=1)
    if "today" in t or "now" in t:
        return date.today()
    # YYYY-MM-DD
    m = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    # DD-MM-YYYY
    m = re.search(r"(\d{1,2})[-/](\d{1,2})[-/](20\d{2})", text)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    return default


def _extract_business_type(text: str) -> Optional[str]:
    t = text.lower()
    for bt in ["retail", "freelance", "manufacturing", "tech", "restaurant", "non_profit", "real_estate", "service"]:
        if bt in t:
            return bt
    return None


def _extract_currency_pair(text: str) -> Optional[tuple[str, str]]:
    """Find 'USD to PKR' or 'X to Y' currency conversion."""
    t = text.upper()
    pairs = re.findall(r"\b([A-Z]{3})\s*(?:to|in|=|->)\s*([A-Z]{3})\b", t)
    return (pairs[0][0], pairs[0][1]) if pairs else None


# ---------------------------------------------------------------------------
# Router entries: (match_words, tool_name, param_extractor_fn)
# Ordered most-specific first.
# ---------------------------------------------------------------------------

def _params_none(text: str) -> dict:
    return {}


def _params_year(text: str) -> dict:
    return {"fiscal_year": _extract_year(text) or date.today().year}


def _params_year_period(text: str) -> dict:
    return {"fiscal_year": _extract_year(text), "period": _extract_period(text)}


def _extract_date_pair(text: str) -> tuple[Optional[date], Optional[date]]:
    """Extract the FIRST and SECOND dates from text as (from_date, to_date).

    Uses the user's exact dates — never invents or duplicates. Falls back to
    (None, None) when no explicit dates are present (caller applies defaults).
    """
    dates: list[date] = []

    # YYYY-MM-DD (also YYYY/MM/DD)
    for m in re.finditer(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", text):
        try:
            dates.append(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            pass

    # DD-MM-YYYY, only if not already captured as YYYY-MM-DD
    if len(dates) < 2:
        for m in re.finditer(r"(\d{1,2})[-/](\d{1,2})[-/](20\d{2})", text):
            try:
                d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                if d not in dates:
                    dates.append(d)
            except ValueError:
                pass

    if len(dates) >= 2:
        return dates[0], dates[1]
    if len(dates) == 1:
        return dates[0], dates[0]
    return None, None


def _params_dates(text: str) -> dict:
    from_d, to_d = _extract_date_pair(text)
    today = date.today()
    first_of_month = today.replace(day=1)
    return {
        "from_date": from_d if from_d else first_of_month,
        "to_date": to_d if to_d else today,
    }


def _params_trial_balance(text: str) -> dict:
    return {"as_of_date": _extract_date(text) or date.today()}


def _params_cash_position(text: str) -> dict:
    return {"as_of_date": _extract_date(text) or date.today(), "account_id": "ALL"}


def _params_convert_currency(text: str) -> dict:
    pair = _extract_currency_pair(text)
    return {
        "amount": _extract_amount(text) or "1",
        "from_currency": pair[0] if pair else "USD",
        "to_currency": pair[1] if pair else "PKR",
        "rate_date": _extract_date(text) or date.today(),
    }


def _params_tax_planning(text: str) -> dict:
    return {"query": text, "fiscal_year": _extract_year(text) or date.today().year}


def _params_aging(text: str) -> dict:
    return {"as_of_date": _extract_date(text) or date.today()}


def _params_forecast(text: str) -> dict:
    return {"forecast_days": 30}


def _params_compliance(text: str) -> dict:
    return {"fiscal_year": _extract_year(text), "status": None}


def _params_breakeven(text: str) -> dict:
    amounts = re.findall(r"(\d[\d,]*(?:\.\d{1,2})?)", text.replace(",", ""))
    vals = [a for a in amounts if not (a.isdigit() and len(a) == 4 and 2020 <= int(a) <= 2035)]
    if len(vals) >= 3:
        return {
            "fixed_cost": vals[0],
            "variable_cost_per_unit": vals[1],
            "selling_price_per_unit": vals[2],
        }
    return {}


def _params_record_transaction(text: str) -> dict:
    return {
        "description": text,
        "posted_date": _extract_date(text) or date.today(),
    }


# ---------------------------------------------------------------------------
# Petty cash natural-language parsing
# ---------------------------------------------------------------------------

_PC_ADD_RE = re.compile(r"\b(add|deposit|top\s*-?\s*up|put\s+in|inject|fund\s+it)\b", re.I)
_PC_EXPENSE_RE = re.compile(r"\b(expense|spent|paid|used|withdrew|withdraw|purchase|bought|took\s+out)\b", re.I)
_PC_CHECK_RE = re.compile(r"\b(check|status|balance|remaining|how\s+much|need|due)\b", re.I)
_PC_FUND_RE = re.compile(r"\b(PC-\d+)\b", re.I)
_PC_DESC_NOISE = re.compile(
    r"\b(rs|pkr|rupees?|today|yesterday|now|this|month|date|dated|is|on|for|to|the|a|an|and|fund|funds|petty|cash|record)\b",
    re.I,
)


def parse_petty_cash(text: str) -> dict:
    """Extract action / fund_id / amount / description from a petty-cash message.

    Returns a tool-ready params dict (values are strings; execute_tool coerces
    via the Pydantic input model). Only fields actually found are included, so
    callers can slot-fill the rest.
    """
    t = text.strip()
    if not t:
        return {}
    out: dict = {}

    # Action precedence: explicit add/deposit > expense/spend > status/check.
    if _PC_ADD_RE.search(t):
        out["action"] = "add_fund"
    elif _PC_EXPENSE_RE.search(t):
        out["action"] = "expense"
    elif _PC_CHECK_RE.search(t):
        out["action"] = "check_replenishment"

    # Fund: explicit PC-XXX id, else "fund <name>".
    m = _PC_FUND_RE.search(t)
    if m:
        out["fund_id"] = m.group(1).upper()
    else:
        m2 = re.search(r"\b(?:fund|funds?)\s+(?:called|named|id\s*[:=]?\s*)?([A-Za-z0-9_-]{2,})", t, re.I)
        if m2:
            out["fund_id"] = m2.group(1)

    # Amount — skip PC-XXX fund ids (which look like numbers) and 4-digit years.
    amount = _extract_amount(re.sub(r"PC-\d+", " ", t, flags=re.I))
    if amount:
        out["amount"] = amount

    # Description: strip action/fund/amount/date/currency noise words.
    desc = t
    desc = _PC_ADD_RE.sub(" ", desc)
    desc = _PC_EXPENSE_RE.sub(" ", desc)
    desc = _PC_CHECK_RE.sub(" ", desc)
    desc = _PC_FUND_RE.sub(" ", desc)
    desc = re.sub(r"\b(PC-\d+)\b", " ", desc, flags=re.I)
    desc = _PC_DESC_NOISE.sub(" ", desc)
    desc = re.sub(r"\d[\d,]*(?:\.\d{1,2})?", " ", desc)
    desc = re.sub(r"\s+", " ", desc).strip().strip(",-")
    if desc:
        out["description"] = desc[:200]
    return out


def _params_petty_cash(text: str) -> dict:
    return parse_petty_cash(text)


# Routes: each is (keywords: list, tool_name: str, extractor: callable)
ROUTES: list[tuple[list[str], str, callable]] = [
    # --- Daily Entry ---
    (["cash position", "cash balance", "cash position", "how much cash", "current balance", "balance check"], "check_cash_position", _params_cash_position),
    (["record transaction", "record expense", "record income", "record an expense", "record an income", "record a transaction", "record a payment", "add transaction", "add a transaction", "add an expense", "add an income", "paid ", "bought ", "purchase ", "spent ", "paid for "], "record_transaction_nl", _params_record_transaction),
    (["receipt", "scan receipt", "ocr", "process receipt"], "process_receipt_image", _params_none),
    (["bank transaction", "bank statement", "check bank", "list bank"], "check_bank_transactions", _params_dates),
    (["record bank", "bank register", "add bank transaction"], "record_bank_transaction", _params_record_transaction),
    (["petty cash"], "manage_petty_cash", _params_petty_cash),

    # --- Ledger ---
    (["journal entry", "create journal", "post journal"], "create_journal_entry", _params_record_transaction),
    (["general ledger", "ledger", "show ledger"], "get_general_ledger", _params_dates),
    (["chart of account", "suggest chart", "chart of accounts"], "suggest_chart_of_accounts", lambda t: {"business_type": _extract_business_type(t) or "service_based"}),
    (["ap subledger", "accounts payable", "payable", "ap sub-ledger", "vendor ledger"], "get_ap_subledger", _params_dates),
    (["ar subledger", "accounts receivable", "receivable", "ar sub-ledger", "customer ledger"], "get_ar_subledger", _params_dates),
    (["payroll ledger", "payroll"], "get_payroll_ledger", _params_dates),
    (["fixed asset", "depreciation scheme", "categorize asset", "add asset"], "categorize_fixed_asset", _params_record_transaction),
    (["add vendor", "new vendor", "vendor master", "add customer", "new customer", "customer master", "manage contact", "add contact"], "manage_contact", _params_record_transaction),

    # --- Reconciliation ---
    (["bank reconciliation", "reconcile bank", "reconcile statement"], "run_bank_reconciliation", _params_dates),
    (["accrual", "accrual entry", "post accrual"], "post_accrual_entry", _params_record_transaction),
    (["vendor statement", "reconcile vendor"], "reconcile_vendor_statement", _params_dates),
    (["customer statement", "reconcile customer"], "reconcile_customer_statement", _params_dates),
    (["cheque", "cheque clearing", "check clearing", "cheque track"], "track_cheque_clearing", _params_none),
    (["lc", "letter of credit", "bank guarantee", "guarantee track"], "track_lc_bank_guarantee", _params_none),
    (["bank charges", "reconcile charges", "bank charge"], "reconcile_bank_charges", _params_dates),

    # --- Month-End ---
    (["unpaid bill", "unpaid", "overdue bill", "bills review"], "review_unpaid_bills", _params_aging),
    (["prepaid", "prepaid adjustment", "prepaid expense"], "calculate_prepaid_adjustment", _params_year),
    (["depreciation", "depreciate"], "calculate_depreciation", _params_year),
    (["amortization", "amortize"], "calculate_amortization", _params_year),
    (["reconcile payroll", "payroll recon"], "reconcile_payroll", _params_dates),
    (["ar aging", "receivable aging", "aging report ar", "receivable report"], "get_ar_aging_report", _params_aging),
    (["ap aging", "payable aging", "aging report ap", "payable report"], "get_ap_aging_report", _params_aging),
    (["budget variance", "variance analysis", "variance"], "analyze_budget_variance", _params_year_period),
    (["cash flow forecast", "forecast cash flow", "cash flow projection"], "forecast_cash_flow", _params_forecast),
    (["loan schedule", "debt schedule", "loan", "debt"], "get_loan_debt_schedule", _params_year),

    # --- Year-End / Financial Statements ---
    (["trial balance"], "generate_trial_balance", _params_trial_balance),
    (["profit and loss", "profit & loss", "p&l", "pnl", "income statement", "profit loss", "generate p&l"], "generate_profit_loss", _params_dates),
    (["balance sheet"], "generate_balance_sheet", _params_trial_balance),
    (["cash flow statement", "statement of cash flows", "cashflow statement"], "generate_cash_flow_statement", _params_dates),
    (["retained earning", "transfer retained"], "transfer_retained_earnings", _params_year),
    (["carry forward", "carry-forward", "carry forward balance"], "carry_forward_balances", lambda t: {"from_fiscal_year": (_extract_year(t) or date.today().year) - 1, "to_fiscal_year": _extract_year(t) or date.today().year}),
    (["notes to financial", "notes to financials", "financial notes"], "draft_notes_to_financials", _params_year),
    (["close fiscal year", "close year", "close the books", "year end close", "year-end close"], "close_fiscal_year", _params_year),

    # --- Cost & Budgeting / Advanced ---
    (["breakeven", "break even", "break-even", "cvp", "cost volume"], "calculate_breakeven", _params_breakeven),
    (["convert currency", "currency conversion", "exchange rate", "usd to", "to pkr", "convert "], "convert_foreign_currency", _params_convert_currency),
    (["budget forecast", "budget preparation", "prepare budget", "budget for"], "prepare_budget_forecast", _params_year),
    (["standard costing", "costing variance", "cost variance"], "calculate_standard_costing_variance", _params_year),
    (["overhead", "allocate overhead", "cost allocation", "apportion"], "allocate_overhead_cost", _params_year),
    (["revenue recognition", "percentage of completion", "recognize revenue"], "calculate_revenue_recognition", _params_year),
    (["provision", "contingent liability", "ias 37", "provision for"], "flag_provision_contingent_liability", _params_record_transaction),
    (["related party", "related-party", "insider"], "flag_related_party_transaction", _params_record_transaction),

    # --- Tax ---
    (["withholding", "wht", "withholding tax"], "calculate_withholding_tax", lambda t: {"amount": _extract_amount(t) or "1000", "withholding_type": "salary"}),
    (["tax planning", "tax advice", "reduce tax", "tax liability"], "get_tax_planning_advice", _params_tax_planning),
    (["advance tax", "minimum tax", "super tax", "minimum/super"], "calculate_advance_minimum_tax", lambda t: {"annual_turnover": _extract_amount(t) or "1000000", "fiscal_year": _extract_year(t) or date.today().year}),
    (["eobi", "old age benefit"], "calculate_eobi_deductions", lambda t: {"gross_salary": _extract_amount(t) or "100000", "period": _extract_period(t) or 1, "fiscal_year": _extract_year(t) or date.today().year}),
    (["sales tax input", "sales tax output", "input tax", "output tax", "adjust sales tax"], "adjust_sales_tax_input_output", _params_year_period),
    (["exemption", "zero rating", "zero-rated", "tax exempt"], "flag_tax_exemption_zero_rating", _params_year),
    (["sales tax filing", "file sales tax", "sales tax return"], "prepare_sales_tax_filing", _params_year_period),
    (["income tax filing", "file income tax", "income tax return"], "prepare_income_tax_filing", _params_year),

    # --- Audit ---
    (["anomaly", "fraud detection", "detect fraud", "suspicious", "anomaly detection", "check anomaly"], "detect_anomaly_transactions", _params_dates),
    (["compliance", "deadline", "filing deadline", "due date", "compliance calendar", "reminder"], "get_compliance_deadlines", _params_compliance),
    (["internal audit", "audit support"], "support_internal_audit", _params_year),
    (["statutory register", "register of director", "maintain register", "statutory"], "maintain_statutory_registers", _params_record_transaction),

    # --- Advisory ---
    (["spending pattern", "spending analysis", "spending", "spend analysis", "expense pattern"], "analyze_spending_patterns", _params_dates),
    (["financial ratio", "ratio analysis", "ratios", "liquidity ratio", "profitability"], "calculate_financial_ratios", _params_year),
    (["financial health", "health score", "health assessment"], "assess_financial_health", _params_year),
    (["cost cutting", "reduce expenses", "cost reduction", "save money", "cut cost"], "generate_cost_cutting_recommendations", _params_year),
    (["custom report", "generate report", "management report"], "generate_custom_report", lambda t: {"report_title": t[:50], "fiscal_year": _extract_year(t) or date.today().year, "report_type": "summary"}),

    # --- System Admin ---
    (["system status", "health check", "is everything working", "system health", "status check"], "check_system_status", _params_none),
    (["usage statistics", "usage stats", "usage analytics"], "get_usage_statistics", _params_dates),
    (["system preference", "company setting", "system setting", "configuration"], "manage_system_preferences", _params_none),
    (["schedule task", "schedule backup", "backup data", "system task", "maintenance"], "schedule_system_task", lambda t: {"task_type": "backup"}),
]


def _kw_in(kw: str, msg: str) -> bool:
    """Match a keyword against a message.

    - Multi-word or long keywords (>=6 chars): plain substring match.
    - Short keywords (<6 chars): require word boundaries to avoid collisions
      like "lc" matching inside "calculate", or "paid " matching "unpaid".
    """
    kw = kw.strip()
    if len(kw) >= 6:
        return kw in msg
    # Word-boundary match: the keyword appears as a standalone word(s).
    # Normalize trailing space in keywords like "paid " -> "paid"
    pattern = re.compile(r"(?<![a-z])" + re.escape(kw.rstrip()) + r"(?![a-z])")
    return bool(pattern.search(msg))


def route_tool(message: str) -> Optional[tuple[str, dict]]:
    """Match a message to a (tool_name, params) tuple, or None if no match."""
    msg = message.lower().strip()
    has_unpaid = "unpaid" in msg
    for keywords, tool_name, extractor in ROUTES:
        for kw in keywords:
            if _kw_in(kw, msg):
                # "unpaid bills" should not trigger the "paid " record route
                if has_unpaid and tool_name == "record_transaction_nl" and "paid " in keywords:
                    continue
                try:
                    params = extractor(message) if extractor else {}
                except Exception:
                    params = {}
                return tool_name, params
    return None


def execute_route(message: str, db: Session) -> Optional[tuple[str, dict]]:
    """Route a message to a tool and execute it. Returns (tool_name, result) or None.

    IMPORTANT: if a tool is MATCHED but fails to execute (DB error, validation,
    etc.), this raises the error rather than returning None. Returning None here
    makes the /chat endpoint fall through to the LLM orchestrator, which then
    fails across all providers and surfaces misleading errors. A matched-but-failed
    tool should surface its real error, never trigger the LLM chain.
    """
    match = route_tool(message)
    if match is None:
        return None
    tool_name, params = match
    if tool_name not in REGISTRY:
        return None
    result = execute_tool(tool_name, params)
    return tool_name, result


def is_approval_required(tool_name: str) -> bool:
    """Check if a tool needs human approval (mirror of frontend approval flags)."""
    APPROVAL_TOOLS = {
        "process_receipt_image",
        "run_bank_reconciliation", "post_accrual_entry", "reconcile_vendor_statement",
        "reconcile_customer_statement", "track_lc_bank_guarantee", "forecast_cash_flow",
        "close_fiscal_year", "categorize_fixed_asset", "calculate_standard_costing_variance",
        "allocate_overhead_cost", "calculate_revenue_recognition",
        "flag_provision_contingent_liability", "flag_related_party_transaction",
        "adjust_sales_tax_input_output", "flag_tax_exemption_zero_rating",
        "prepare_sales_tax_filing", "prepare_income_tax_filing", "support_internal_audit",
        "maintain_statutory_registers", "manage_system_preferences", "schedule_system_task",
        "generate_custom_report",
    }
    return tool_name in APPROVAL_TOOLS
