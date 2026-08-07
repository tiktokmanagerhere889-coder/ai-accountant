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
    return {"fiscal_year": _extract_year(text) or date.today().year, "period": _extract_period(text)}


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
    """Date-range params. Prefers explicit dates in the message.

    If the message names only a bare year (e.g. "for 2026"), the range is that
    whole calendar year - otherwise it falls back to the current month, which
    keeps "this month" prompts correct.
    """
    from_d, to_d = _extract_date_pair(text)
    if from_d is None:
        yr = _extract_year(text)
        if yr:
            from_d = date(yr, 1, 1)
            to_d = date(yr, 12, 31)
    today = date.today()
    first_of_month = today.replace(day=1)
    return {
        "from_date": from_d if from_d else first_of_month,
        "to_date": to_d if to_d else today,
    }


def _params_spending(text: str) -> dict:
    """Date-range params for spending analysis. Handles quarters like
    'Q2 2026' -> Apr 1 - Jun 30; otherwise delegates to _params_dates."""
    m = re.search(r"\bQ([1-4])\b[,\s]*(20\d{2})", text, re.I)
    if m:
        q, yr = int(m.group(1)), int(m.group(2))
        start_month = {1: 1, 2: 4, 3: 7, 4: 10}[q]
        end_month = {1: 3, 2: 6, 3: 9, 4: 12}[q]
        from_d = date(yr, start_month, 1)
        to_d = date(yr, end_month, 30)  # 31st month end handled below
        if end_month in (3, 12):
            to_d = date(yr, end_month, 31)
        return {"from_date": from_d, "to_date": to_d}
    return _params_dates(text)


_REPORT_TYPE_KEYWORDS = {
    "summary": "summary", "detailed": "detailed", "comparative": "comparative", "trend": "trend",
}


def _params_custom_report(text: str) -> dict:
    """Params for generate_custom_report. report_title = the message with
    trigger words/verbs stripped (was raw message, e.g. 'generate a custom
    management report for 2026'). report_type inferred from keywords, default
    summary."""
    rtype = next(
        (k for k in _REPORT_TYPE_KEYWORDS if re.search(rf"\b{k}\b", text.lower())),
        "summary",
    )
    title = re.sub(r"\b(generate|create|make|give|for|a|an|the|my)\b", "", text, flags=re.I)
    title = re.sub(r"\bQ[1-4]\b", "", title, flags=re.I)
    title = re.sub(r"20\d{2}", "", title)
    title = re.sub(r"\s+", " ", title).strip(" -:.,")
    title = title[:50] or "Management Report"
    return {
        "report_title": title,
        "fiscal_year": _extract_year(text) or date.today().year,
        "report_type": rtype,
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


_WHT_TYPES = {
    "salary": "salary", "contract": "contract", "supply": "supply",
    "service": "service", "services": "service", "rent": "rent",
    "commission": "commission",
}


def _extract_withholding_type(text: str) -> str:
    """Map a phrase in the message to a valid withholding_type.

    Defaults to 'salary' only when a type is actually named in the message
    (e.g. 'salary', 'rent', 'services'). The route requires the type to be
    present; otherwise it routes to slot-fill so the missing field is asked
    for instead of silently computing WHT on a guessed type.
    """
    t = text.lower()
    for word, kind in _WHT_TYPES.items():
        if word in t:
            return kind
    return ""


def _params_withholding(text: str) -> dict:
    return {
        "amount": _extract_amount(text),
        "withholding_type": _extract_withholding_type(text),
        "transaction_date": _extract_date(text) or date.today(),
    }


def _params_amt(text: str) -> dict:
    bt = "individual" if "individual" in text.lower() else (
        "aop" if "aop" in text.lower() else "company"
    )
    return {
        "annual_turnover": _extract_amount(text),
        "fiscal_year": _extract_year(text) or date.today().year,
        "business_type": bt,
    }


def _params_eobi(text: str) -> dict:
    cat = None
    t = text.lower()
    for word in ("worker", "staff", "executive"):
        if word in t:
            cat = word
            break
    return {
        "gross_salary": _extract_amount(text),
        "period": _extract_period(text),
        "fiscal_year": _extract_year(text) or date.today().year,
        "employee_category": cat,
    }


def _params_filing_sales(text: str) -> dict:
    """Sales-tax filing route: period+year from the message, always confirm=True.

    The filing tool refuses to run without confirm=True, so the router injects
    it - the approval gate is the human consent, not a hidden flag.
    """
    p = _params_year_period(text)
    p["confirm"] = True
    return p


def _params_filing_income(text: str) -> dict:
    p = _params_year(text)
    p["confirm"] = True
    return p


def _params_fiscal_close(text: str) -> dict:
    """Close-fiscal-year route: year from the message, always confirm=True.

    close_fiscal_year refuses to run without confirm=True (it is irreversible).
    The router injects it the same way the filing parsers do - the human
    approval is the consent, and the tool must never run without it.
    """
    p = _params_year(text)
    p["confirm"] = True
    return p


def _params_filings(text: str) -> dict:
    """List-tax-filings route: optional type + fiscal year filters from the message."""
    p = {}
    t = text.lower()
    if "income" in t or "itr" in t or "incometax" in t:
        p["filing_type"] = "income"
    elif "sales" in t or "st-" in t:
        p["filing_type"] = "sales"
    year = _extract_year(text)
    if year:
        p["fiscal_year"] = year
    return p


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


def _params_standard_costing(text: str) -> dict:
    """Calculate-standard-costing route: account code, period, year, standard cost."""
    p = _params_year_period(text)
    p["description"] = text  # base for slot-fill re-merge (like record_transaction_nl)
    # Standard cost named explicitly ("standard cost 50000" / "standard 50000")
    # else first amount.
    sc = re.search(
        r"standard\s*(?:cost|budget)?\s*[:=]?\s*(\d[\d,]*(?:\.\d{1,2})?)", text, re.I
    )
    if sc:
        p["standard_cost"] = sc.group(1)
    else:
        p["standard_cost"] = _extract_amount(text)
    # Account code: "account 6000" / "account code 6000" / a bare 4-digit.
    ac = re.search(r"account(?:\s*code)?\s*[:=]?\s*(\d{3,5})", text, re.I)
    if ac:
        p["account_code"] = ac.group(1)
    else:
        m = re.search(r"\b(\d{4})\b", text)
        if m and not (2020 <= int(m.group(1)) <= 2035):
            p["account_code"] = m.group(1)
    return p


_ALLOCATION_BASIS = {
    "sq_ft": ("sq ft", "square foot", "square feet"),
    "headcount": ("headcount", "employees", "employee count", "staff count"),
    "revenue_pct": ("revenue", "sales"),
    "custom": ("custom",),
}

# Words that must never become a department name (period/year/filler), so
# "for period 7" or "fiscal year 2026" are not read as pool entries.
_ALLOCATION_BANNED = {
    "period", "fiscal", "year", "month", "quarter", "standard", "overhead",
    "cost", "the", "to", "for", "by", "of", "at", "on", "in", "and", "across",
}


def _extract_allocation_pool(text: str, total_overhead: Optional[str] = None) -> Optional[list[dict]]:
    """Parse '<name> <value>, <name> <value>' pairs into allocation pool items.

    Names are 1-2 letter words (digits excluded) so the overhead total, the
    year, and filler like "for period 7" can never become a department. The
    match starting at a filler preposition is blocked, and any number equal to
    the overhead total (or a 4-digit year) is dropped.
    """
    pool = []
    total = total_overhead.replace(",", "") if total_overhead else None
    for m in re.finditer(
        r"(?<![\w-])(?!(?:the|to|for|by|of|at|on|in|and|across|into|with|from)\s+[A-Za-z])"
        r"((?:[A-Za-z][A-Za-z'-]*)(?:\s+[A-Za-z][A-Za-z'-]*)?)"
        r"\s+(\d[\d,]*(?:\.\d{1,2})?)(?![\w-])",
        text,
    ):
        name, num = m.group(1).strip(), m.group(2)
        n2 = num.replace(",", "")
        if not n2.replace(".", "", 1).isdigit():
            continue  # not a real number (e.g. trailing garbage)
        if n2.isdigit() and len(n2) == 4 and 2020 <= int(n2) <= 2035:
            continue  # year, not a pool value
        if total and n2 == total:
            continue  # the overhead total, not a department
        toks = {t.lower() for t in name.split()}
        if toks & _ALLOCATION_BANNED:
            continue
        if len(name) >= 2 and not any(p["name"] == name for p in pool):
            pool.append({"name": name, "value": n2})
    return pool or None


def _params_overhead(text: str) -> dict:
    """Allocate-overhead route: amount, basis, department pool, period, year."""
    p = _params_year_period(text)
    p["description"] = text  # base for slot-fill re-merge
    total = _extract_amount(text)
    p["total_overhead"] = total
    t = text.lower()
    for basis, words in _ALLOCATION_BASIS.items():
        if any(w in t for w in words):
            p["allocation_basis"] = basis
            break
    pool = _extract_allocation_pool(text, total_overhead=total)
    if pool:
        p["allocation_pool"] = pool
    return p


def _params_revenue_recognition(text: str) -> dict:
    """Revenue-recognition route: contract id, value, completion %, period, year."""
    p = _params_year_period(text)
    p["description"] = text  # base for slot-fill re-merge
    cid = re.search(
        r"(?:contract|project)\s*[:=#]?\s*([A-Za-z0-9][A-Za-z0-9_-]*)", text, re.I
    )
    if cid:
        p["contract_id"] = cid.group(1)
    # Value: prefer a number near 'value'/'worth'; else first amount, ignoring
    # the contract id (so "CON-001" is not read as the contract value).
    stripped = text
    if cid:
        stripped = re.sub(re.escape(cid.group(0)), " ", text)
    val = re.search(
        r"(?:contract\s*value|value|worth)\s*[:=]?\s*(\d[\d,]*(?:\.\d{1,2})?)",
        stripped,
        re.I,
    )
    p["contract_value"] = val.group(1) if val else _extract_amount(stripped)
    pct = re.search(r"(\d{1,3})\s*%", text) or re.search(
        r"(?:completion|complete|progress)\s*(?:of|at|:)?\s*(\d{1,3})(?:\s*%|\s*percent|\s*pct)?",
        text,
        re.I,
    )
    if pct:
        p["completion_percentage"] = min(int(pct.group(1)), 100)
    prev = re.search(
        r"(?:already|previously)\s*(?:recognized|recognised)\s*(?:revenue)?\s*(?:of)?\s*(\d[\d,]*(?:\.\d{1,2})?)",
        text,
        re.I,
    )
    if prev:
        p["previous_recognized"] = prev.group(1)
    return p


_PROBABILITIES = (
    ("probable", ("probable", "likely", "high probability")),
    ("possible", ("possible", "maybe", "uncertain")),
    ("remote", ("remote", "unlikely", "very low")),
)


def _params_provision(text: str) -> dict:
    """Provision/contingent-liability route: description, amount, probability, year."""
    p = _params_year(text)
    p["description"] = text  # description field is required by the tool schema
    p["estimated_amount"] = _extract_amount(text)
    t = text.lower()
    for prob, words in _PROBABILITIES:
        if any(w in t for w in words):
            p["probability"] = prob
            break
    rp = re.search(
        r"(?:related party|party)\s*[:=]?\s*([A-Za-z][A-Za-z0-9 .&-]{1,40})",
        text,
        re.I,
    )
    if rp:
        p["related_party"] = rp.group(1).strip()
    return p


_REGISTER_TYPES = {
    "director": "directors",
    "directors": "directors",
    "member": "members",
    "members": "members",
    "charge": "charges",
    "charges": "charges",
    "contract": "contracts",
    "contracts": "contracts",
    "beneficial owner": "beneficial_owners",
    "beneficial owners": "beneficial_owners",
    "beneficial_owner": "beneficial_owners",
    "beneficial": "beneficial_owners",
}


def _params_statutory_registers(text: str) -> dict:
    """Maintain-statutory-registers route: action, register type, date, description.

    Derives the four schema-required fields (action/register_type/entry_date/
    description) from natural phrasing. When the action is missing (a bare
    "register of directors" ask), defaults to view; write actions ("add/update/
    delete") stay explicit so slot-fill can ask for what's missing.
    """
    t = text.lower()
    # Action: explicit verb wins; "view/show/list/check" -> view; a bare
    # register-type mention (no verb) -> view.
    if re.search(r"\b(add|create|new|record|enter)\b", t):
        action = "add"
    elif re.search(r"\b(update|edit|modify|amend)\b", t):
        action = "update"
    elif re.search(r"\b(delete|remove)\b", t):
        action = "delete"
    else:
        action = "view"
    reg = None
    for word, kind in _REGISTER_TYPES.items():
        if word in t:
            reg = kind
            break
    p = {
        "action": action,
        "register_type": reg,
        "description": text,
        "entry_date": _extract_date(text) or date.today(),
    }
    ref = re.search(r"\b([A-Z]{2,4}-[A-Za-z0-9-]+)\b", text) or re.search(r"\b([A-Z]{2,4}-?\d+)\b", text)
    if ref:
        p["reference_number"] = ref.group(1)
    amt = _extract_amount(text)
    if amt:
        p["amount"] = amt
    # update/delete act on an existing register_id (REG-<TYPE>-<HEX>); capture
    # a REG- token so the tool runs without a slot-fill round-trip.
    if action in ("update", "delete"):
        rid = re.search(r"\b(REG-[A-Za-z0-9-]+)\b", text, re.I)
        if rid:
            p["register_id"] = rid.group(1).upper()
    return p


def _params_related_party(text: str) -> dict:
    """Flag-related-party route: entry id, description, amount, counterparty, year."""
    p = _params_year(text)
    p["transaction_description"] = text  # description field is required by the tool schema
    p["description"] = text  # base for slot-fill re-merge
    eid = re.search(r"\b(JE-[\w-]+)\b", text, re.I) or re.search(
        r"(?:entry|journal)\s*[:=]?\s*([A-Za-z][A-Za-z0-9_-]*)", text, re.I
    )
    if eid:
        p["entry_id"] = eid.group(1)
    # Amount: prefer an explicit 'amount N' / 'worth N'; else the first amount
    # after any entry-id tokens are stripped (so JE-20260715-001's digits don't
    # become the amount).
    amt = re.search(r"(?:amount|worth|for)\s*[:=]?\s*(\d[\d,]*(?:\.\d{1,2})?)", text, re.I)
    if amt:
        p["amount"] = amt.group(1)
    else:
        stripped = re.sub(r"\bJE-[\w-]+\b", " ", text, flags=re.I)
        p["amount"] = _extract_amount(stripped)
    cp = re.search(r"(?:from|to|paid to|received from)\s+([A-Z][A-Za-z0-9 .&-]{2,40})", text)
    if cp:
        # Truncate at stop words so "paid to ABC Trading as a related party"
        # yields just "ABC Trading".
        name = cp.group(1).strip()
        for stop in (" as ", " in ", " during ", " for ", " of "):
            idx = name.lower().find(stop)
            if idx != -1:
                name = name[:idx]
                break
        p["counterparty_name"] = name.strip()
    return p


def _params_record_transaction(text: str) -> dict:
    return {
        "description": text,
        "posted_date": _extract_date(text) or date.today(),
    }


# ---------------------------------------------------------------------------
# Journal entry (Agent 2) natural-language parsing
# ---------------------------------------------------------------------------

_ACCOUNT_ALIASES = {
    "cash": "1000-Cash",
    "bank": "1100-Bank",
    "rent": "6000-Office Rent",
    "office rent": "6000-Office Rent",
    "salary": "6100-Salary",
    "wage": "6100-Salary",
    "utilities": "6200-Utilities",
    "electric": "6200-Utilities",
    "electricity": "6200-Utilities",
    "office supplies": "6300-Office Supplies",
    "supplies": "6300-Office Supplies",
    "stationery": "6300-Office Supplies",
    "travel": "6400-Travel",
    "transport": "6400-Travel",
    "fuel": "6400-Travel",
    "meals": "6500-Meals",
    "entertainment": "6600-Entertainment",
    "advertising": "6700-Advertising",
    "insurance": "6800-Insurance",
    "maintenance": "6900-Maintenance",
    "repair": "6900-Maintenance",
    "tax": "7000-Tax",
    "professional fees": "7100-Professional Fees",
    "professional fee": "7100-Professional Fees",
    "consultant": "7100-Professional Fees",
    "miscellaneous": "7200-Miscellaneous",
    "accounts receivable": "1200-Accounts Receivable",
    "accounts payable": "2000-Payables",
    "revenue": "4000-Revenue",
    "sales": "4000-Revenue",
    "service income": "4100-Service Income",
}

# A journal entry like: "debiting 6000-Office Rent 50000 and crediting 1000-Cash 50000"
# or "debit Office Rent 50000, credit Cash 50000".
_JOURNAL_DEBIT_RE = re.compile(
    r"(?:debit(?:ing)?|dr)\b[\s:=-]*([0-9A-Za-z&.\- ]+?)\s+(\d[\d,]*(?:\.\d{1,2})?)",
    re.I,
)
_JOURNAL_CREDIT_RE = re.compile(
    r"(?:credit(?:ing)?|cr)\b[\s:=-]*([0-9A-Za-z&.\- ]+?)\s+(\d[\d,]*(?:\.\d{1,2})?)",
    re.I,
)


def _resolve_account_code(name: str) -> Optional[str]:
    """Resolve a possibly name-only account reference to 'code-Name'.

    - Already coded ('6000-Office Rent') -> unchanged.
    - Plain name ('office rent', 'cash') -> alias map, else derive 'code-Name'
      from the category prefix (rent=6..., cash=1...).
    """
    name = (name or "").strip().rstrip("- ").strip()
    if not name:
        return None
    if re.match(r"^\d+-", name):
        return name
    lower = name.lower()
    if lower in _ACCOUNT_ALIASES:
        return _ACCOUNT_ALIASES[lower]
    # Substring alias: "office rent" matches the rent key.
    for key, code in _ACCOUNT_ALIASES.items():
        if key in lower:
            return code
    # Default expense prefix; keep the user's wording as the account name.
    prefix = "6"
    if any(k in lower for k in ("cash", "bank", "receivable")):
        prefix = "1"
    elif any(k in lower for k in ("payable", "loan")):
        prefix = "2"
    elif any(k in lower for k in ("revenue", "income", "sale")):
        prefix = "4"
    return f"{prefix}-{name.title()}"


def _params_journal_entry(text: str) -> dict:
    """Parse debit/credit accounts + amounts from a journal-entry message.

    Handles "debiting X 50000 and crediting Y 50000" and
    "debit X 50000, credit Y 50000". Falls back to _params_record_transaction
    when no structured debit/credit is present (slot-fill asks the user).
    """
    m = _JOURNAL_DEBIT_RE.search(text)
    if not m:
        return _params_record_transaction(text)
    debit_acct = _resolve_account_code(m.group(1))
    debit_amt = m.group(2).replace(",", "")
    credit_acct = None
    credit_amt = None
    c = _JOURNAL_CREDIT_RE.search(text[m.end():])
    if c:
        credit_acct = _resolve_account_code(c.group(1))
        credit_amt = c.group(2).replace(",", "")
    params = {
        "description": text,
        "posted_date": _extract_date(text) or date.today(),
    }
    if debit_acct and debit_amt:
        params["debit_account"] = debit_acct
        params["debit_amount"] = debit_amt
    if credit_acct and credit_amt:
        params["credit_account"] = credit_acct
        params["credit_amount"] = credit_amt
    return params


# ---------------------------------------------------------------------------
# Fixed asset (Agent 2) natural-language parsing
# ---------------------------------------------------------------------------

_FIXED_ASSET_NOUNS = [
    "truck", "vehicle", "van", "car", "machinery", "machine", "equipment",
    "computer", "laptop", "server", "furniture", "building", "land",
    "generator", "furnace", "boiler", "fixture",
]

# "bought a delivery truck for 2M", "purchased new laptop", "add a fixed asset"
_FIXED_ASSET_RE = re.compile(
    r"(?:\b(?:bought|purchased|purchase|acquired|invested\s+in|added|registered|capitalized)\b"
    r"|\bfixed\s+asset\b|\badd\s+asset\b|\bcategorize\s+asset\b)"
    r".{0,50}?"
    r"\b(?:truck|vehicle|van|car|machinery|machine|equipment|computer|laptop|server|furniture|building|land|generator|furnace|boiler|fixture)\b",
    re.I,
)


def _is_fixed_asset_intent(text: str) -> bool:
    t = text.lower()
    if "fixed asset" in t or "add asset" in t or "categorize asset" in t or "depreciation scheme" in t:
        return True
    return bool(_FIXED_ASSET_RE.search(text))


def _params_fixed_asset(text: str) -> dict:
    """Extract asset_name / purchase_cost / purchase_date from chat."""
    cost = _extract_amount(text)
    asset_name = None
    for noun in _FIXED_ASSET_NOUNS:
        m = re.search(r"\b" + re.escape(noun) + r"\b", text, re.I)
        if m:
            prefix = text[: m.start()]
            words = [
                w for w in re.findall(r"[A-Za-z]+", prefix)
                if w.lower() not in ("we", "i", "bought", "purchased", "purchase", "acquired", "a", "an", "the", "our", "my", "for", "of", "new", "us", "capital", "expense")
            ]
            asset_name = " ".join(words[-2:] + [noun]).title()
            break
    if not asset_name:
        asset_name = (text[:40].strip() or "Fixed Asset").title()
    return {
        "asset_name": asset_name,
        "purchase_cost": cost or "1000000",
        "purchase_date": _extract_date(text) or date.today(),
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


def _params_manage_contact(text: str) -> dict:
    """Extract action / contact_type / contact_name / phone / email / tax_id
    from a contact-management message, e.g. "add vendor AL-MADINA, phone 0300-1234567".

    Only fields actually found are included; slot-fill asks for the rest.
    """
    t = text.strip()
    if not t:
        return {}
    tl = t.lower()
    out: dict = {}

    # Action precedence: delete > update > search > add (default).
    if re.search(r"\b(delete|remove|del)\b", tl):
        out["action"] = "delete"
    elif re.search(r"\b(update|change|edit|modify)\b", tl):
        out["action"] = "update"
    elif re.search(r"\b(search|find|lookup|list)\b", tl):
        out["action"] = "search"
    else:
        out["action"] = "add"

    # Contact type.
    if re.search(r"\b(vendor|supplier)\b", tl):
        out["contact_type"] = "vendor"
    elif re.search(r"\b(customer|client|buyer)\b", tl):
        out["contact_type"] = "customer"

    # Contact name: capture the token(s) after vendor/customer/contact, up to
    # a comma, a phone/email marker, or the end of the string.
    m = re.search(
        r"(?:vendor|supplier|customer|client|contact)\s+"
        r"([A-Za-z0-9][A-Za-z0-9 .&'\-]{1,79})",
        t,
        re.IGNORECASE,
    )
    if m:
        out["contact_name"] = m.group(1).strip().rstrip(".,").strip()

    # Optional fields: phone, email, tax id.
    pm = re.search(r"(\+?\d[\d\s\-]{7,}\d)", t)
    if pm:
        out["phone"] = pm.group(1).strip()
    em = re.search(r"([\w.+-]+@[\w.-]+\.[A-Za-z]{2,})", t)
    if em:
        out["email"] = em.group(1)
    tm = re.search(r"\b(?:tax\s*id|ntn)\s*[:#]?\s*([A-Za-z0-9\-]{5,20})", t, re.IGNORECASE)
    if tm:
        out["tax_id"] = tm.group(1)

    return out


# ---------------------------------------------------------------------------
# Reconciliation & Banking (Agent 3) natural-language parsing
# ---------------------------------------------------------------------------

_DEFAULT_BANK_ACCOUNT = "1100-Bank"

_MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _extract_period_dates(text: str) -> Optional[tuple[date, date]]:
    """Parse '<Month> [<YYYY>]' (e.g. "for July" or "for July 2026") into
    (first_day, last_day). A bare month uses the current year."""
    t = text.lower()
    for name, mo in _MONTH_NAMES.items():
        m = re.search(r"\b" + re.escape(name) + r"\s+(\d{4})\b", t)
        if m:
            y = int(m.group(1))
            first = date(y, mo, 1)
            last_day = (date(y + 1, 1, 1) if mo == 12 else date(y, mo + 1, 1)) - timedelta(days=1)
            return first, last_day
    # Bare month name (no year) -> current year.
    for name, mo in _MONTH_NAMES.items():
        if re.search(r"\b" + re.escape(name) + r"\b", t):
            y = date.today().year
            first = date(y, mo, 1)
            last_day = (date(y + 1, 1, 1) if mo == 12 else date(y, mo + 1, 1)) - timedelta(days=1)
            return first, last_day
    return None


def _params_period(text: str) -> dict:
    """from_date/to_date honoring 'for July 2026', explicit dates, else current month."""
    pd = _extract_period_dates(text)
    if pd:
        return {"from_date": pd[0], "to_date": pd[1]}
    from_d, to_d = _extract_date_pair(text)
    today = date.today()
    return {
        "from_date": from_d if from_d else today.replace(day=1),
        "to_date": to_d if to_d else today,
    }


def _params_period_date(text: str) -> dict:
    """Map '<Month> [<YYYY>]' to a single as_of/period date for month-end tools.

    Depreciation/amortization/prepaid run "for July" — the tool takes a single
    period_date/as_of_date, so use the LAST day of the named month (the close
    date). Falls back to today when no month is given.
    """
    pd = _extract_period_dates(text)
    return {"period_date": pd[1] if pd else date.today()}


def _params_prepaid(text: str) -> dict:
    """as_of_date for prepaid adjustment — the named month's last day."""
    pd = _extract_period_dates(text)
    return {"as_of_date": pd[1] if pd else date.today()}


def _params_loan(text: str) -> dict:
    """loan_id + as_of_date for the loan/debt schedule tool."""
    m = re.search(r"\b(?:LN|LOAN)[-\s]?\d+", text, re.I)
    loan_id = m.group(0).upper().replace("LOAN", "LN") if m else None
    return {"loan_id": loan_id, "as_of_date": _extract_date(text)}


def _extract_bank_account(text: str) -> str:
    """Resolve a bank reference to an account_id, defaulting to 1100-Bank.

    Stops the account code at a trailing qualifier ("for", "in", "of", "on",
    a month name, or end of text) so "1100-Bank for July" -> "1100-Bank".
    """
    m = re.search(
        r"(?:BA-\d+|1\d{3}-[A-Za-z ]+?(?=\s+(?:for|in|of|on|dated|month|statement|account)\b|$))",
        text,
        re.I,
    )
    if m:
        return m.group(0).strip().rstrip(" -")
    return _DEFAULT_BANK_ACCOUNT


def _extract_contact_id(text: str) -> Optional[str]:
    m = re.search(r"\b(CNT-\d+)\b", text, re.I)
    return m.group(1).upper() if m else None


def _extract_contact_name(text: str, kind: str) -> Optional[str]:
    """Capture the name after 'from'/'for'/'statement from', e.g. AL-MADINA GENERAL STORE."""
    m = re.search(
        r"(?:statement\s+from|from|for)\s+([A-Za-z][A-Za-z0-9 .&'\-]{2,79}?)"
        r"(?:\s+(?:for|in|statement|from|with|dated|line|using|covering)\b|,|$)",
        text,
        re.I,
    )
    if not m:
        return None
    return m.group(1).strip().rstrip(".,").strip()


def _resolve_contact_id(kind: str, name: str) -> Optional[str]:
    """Resolve a contact name to a contact_id via the DB (best-effort)."""
    try:
        from db.database import get_session
        from db.models import Contact
        db = get_session()
        try:
            row = db.query(Contact).filter(
                Contact.contact_type == kind,
                Contact.contact_name.ilike("%{}%".format(name)),
            ).first()
            return row.contact_id if row else None
        finally:
            db.close()
    except Exception:
        return None


def _parse_statement_lines(text: str, default_date: date) -> list[dict]:
    """Parse 'line INV-200 50000' / 'INV-200 50000 dated 2026-07-15' lines."""
    lines: list[dict] = []
    for m in re.finditer(
        r"\b(INV-\d+|CN-\d+|SI-\d+|PO-\d+|[A-Z]{2,}-\d+)\s+(\d[\d,]*(?:\.\d{1,2})?)",
        text,
        re.I,
    ):
        d = _extract_date(text[m.end():m.end() + 30]) or default_date
        lines.append({
            "reference": m.group(1),
            "date": d,
            "amount": m.group(2).replace(",", ""),
        })
    return lines


def _params_bank_reconciliation(text: str) -> dict:
    base = _params_period(text)
    today = date.today()
    return {
        "bank_account_id": _extract_bank_account(text),
        "statement_date": _extract_date(text) or today,
        "from_date": base["from_date"],
        "to_date": base["to_date"],
    }


def _params_accrual(text: str) -> dict:
    t = text.lower()
    if "salary" in t or "salaries" in t or "wage" in t:
        acc_type = "salary"
    elif "utilit" in t or "electric" in t or "gas" in t or "water" in t:
        acc_type = "utilities"
    elif "rent" in t:
        acc_type = "rent"
    else:
        acc_type = "other"
    pd = _extract_period_dates(text)
    period_date = (pd[1] if pd else _extract_date(text)) or date.today()
    out = {
        "accrual_type": acc_type,
        "description": text[:500],
        "period_date": period_date,
    }
    amt = _extract_amount(text)
    if amt:
        out["amount"] = amt
    pm = re.search(r"partial\s+(\d{1,3})\s+days?", text, re.I)
    if pm:
        out["partial_period_days"] = int(pm.group(1))
    return out


def _params_vendor_statement(text: str) -> dict:
    return _params_statement(text, "vendor")


def _params_customer_statement(text: str) -> dict:
    return _params_statement(text, "customer")


def _params_statement(text: str, kind: str) -> dict:
    base = _params_period(text)
    stmt_date = _extract_date(text) or date.today()
    id_field = "{}_contact_id".format(kind)
    name_field = "{}_name".format(kind)
    out = {
        "statement_date": stmt_date,
        "from_date": base["from_date"],
        "to_date": base["to_date"],
        "statement_lines": _parse_statement_lines(text, stmt_date),
    }
    cid = _extract_contact_id(text)
    if cid:
        out[id_field] = cid
    else:
        name = _extract_contact_name(text, kind)
        if name:
            resolved = _resolve_contact_id(kind, name)
            if resolved:
                out[id_field] = resolved
            else:
                out[name_field] = name
    return out


def _params_cheque(text: str) -> dict:
    t = text.lower()
    if "bounce" in t:
        action = "bounce"
    elif "clear" in t:
        action = "clear"
    elif "reconcil" in t:
        action = "reconcile"
    elif "status" in t or "track" in t or "check" in t:
        action = "status"
    else:
        action = "issue"

    out = {"action": action}
    # Strip any cheque id so its digits don't become the amount.
    amt_text = re.sub(r"\bCHQ-\d+\b", " ", text, flags=re.I)
    m = re.search(r"\b(CHQ-\d+)\b", text, re.I)
    if m:
        out["cheque_id"] = m.group(1).upper()
    else:
        m = re.search(r"cheque\s+(?:number\s+|no\.?\s*)?(\d{4,})", text, re.I)
        if m:
            out["cheque_id"] = "CHQ-" + m.group(1)
            # Drop the cheque-number phrase so its digits don't read as the amount.
            amt_text = text.replace(m.group(0), " ")
    amt = _extract_amount(amt_text)
    if amt:
        out["amount"] = amt
    m = re.search(r"\b(?:to|for)\s+([A-Za-z][A-Za-z0-9 .&'\-]{2,79})", text)
    if m:
        out["vendor_name"] = m.group(1).strip().rstrip(".,")
    d = _extract_date(text)
    if d:
        out["issue_date"] = d
    return out


def _params_lcbg(text: str) -> dict:
    t = text.lower()
    if "amend" in t:
        action = "amend"
    # "expiring" (the expiry date clause on an issue) must NOT become "expire".
    elif re.search(r"\bexpire[sd]?\b", t) or re.search(r"\bexpired\b", t):
        action = "expire"
    elif "close" in t:
        action = "close"
    elif "status" in t or "track" in t or "check" in t:
        action = "status"
    else:
        action = "issue"

    out = {"action": action}
    m = re.search(r"\b(LC-\d+[-\d]*|BG-\d+[-\d]*)\b", text, re.I)
    if m:
        out["lc_id"] = m.group(1).upper()
    if action == "issue":
        if "bank guarantee" in t or "guarantee" in t or re.search(r"\bbg\b", t):
            out["type"] = "BG"
        else:
            out["type"] = "LC"
    amt = _extract_amount(re.sub(r"\b(?:LC|BG)-\d+[-\d]*\b", " ", text, flags=re.I))
    if amt:
        out["amount"] = amt
    m = re.search(r"\bto\s+([A-Za-z][A-Za-z0-9 .&'\-]{2,79})", text)
    if m:
        out["beneficiary"] = m.group(1).strip().rstrip(".,")
    exp_m = re.search(
        r"expir(?:y|ing|es)\s*(?:date\s*[:=]?\s*)?([0-9]{4}[-/][0-9]{1,2}[-/][0-9]{1,2})",
        text, re.I,
    )
    issue_txt = text
    if exp_m:
        out["expiry_date"] = _extract_date(exp_m.group(1))
        issue_txt = text[:exp_m.start()] + text[exp_m.end():]
    d = _extract_date(issue_txt)
    if d:
        out["issue_date"] = d
    return out


def _params_bank_charges(text: str) -> dict:
    base = _params_period(text)
    t = text.lower()
    ctype = None
    for kw in ("service", "maintenance", "transfer", "commission", "fee", "other"):
        if kw in t:
            ctype = kw
            break
    out = {
        "bank_account_id": _extract_bank_account(text),
        "from_date": base["from_date"],
        "to_date": base["to_date"],
    }
    if ctype:
        out["charge_type"] = ctype
    return out


_BANK_DESC_NOISE = re.compile(
    r"\b(record|add|bank|transaction|credit|debit|deposit|withdrawal|withdraw|today|yesterday|on|for|from|to|the|a|an|of|status|cleared|pending|this|and|with)\b",
    re.I,
)


def _clean_desc(text: str) -> str:
    d = _BANK_DESC_NOISE.sub(" ", text)
    d = re.sub(r"\d[\d,]*(?:\.\d{1,2})?", " ", d)
    d = re.sub(r"\s+", " ", d).strip().strip(",-")
    return d[:200]


def _params_record_bank_transaction(text: str) -> dict:
    t = text.lower()
    if "credit" in t or "deposit" in t or "incoming" in t or "received" in t:
        btype = "credit"
    else:
        btype = "debit"
    out = {
        "date": _extract_date(text) or date.today(),
        "description": _clean_desc(text) or text[:200],
        "type": btype,
        "status": "cleared",
        "account_id": _extract_bank_account(text),
    }
    amt = _extract_amount(text)
    if amt:
        # Preserve an explicit negative sign so bank charges (amount < 0)
        # seed correctly for reconcile_bank_charges.
        if re.search(r"-\s*" + re.escape(amt) + r"\b", text):
            amt = "-" + amt
        out["amount"] = amt
    return out


# Routes: each is (keywords: list, tool_name: str, extractor: callable)
ROUTES: list[tuple[list[str], str, callable]] = [
    # --- Daily Entry ---
    (["cash position", "cash balance", "cash position", "how much cash", "current balance", "balance check"], "check_cash_position", _params_cash_position),
    (["record transaction", "record expense", "record income", "record an expense", "record an income", "record a transaction", "record a payment", "add transaction", "add a transaction", "add an expense", "add an income", "paid ", "bought ", "purchase ", "spent ", "paid for "], "record_transaction_nl", _params_record_transaction),
    (["receipt", "scan receipt", "ocr", "process receipt"], "process_receipt_image", _params_none),
    (["record bank", "bank register", "add bank transaction"], "record_bank_transaction", _params_record_bank_transaction),
    (["bank transaction", "bank statement", "check bank", "list bank"], "check_bank_transactions", _params_dates),
    (["petty cash"], "manage_petty_cash", _params_petty_cash),

    # --- Ledger ---
    (["journal entry", "create journal", "post journal", "debit ", "credit ", "journalise", "journalize"], "create_journal_entry", _params_journal_entry),
    (["chart of account", "suggest chart", "chart of accounts"], "suggest_chart_of_accounts", lambda t: {"business_type": _extract_business_type(t) or "service_based"}),
    (["ap subledger", "accounts payable", "payable", "ap sub-ledger", "vendor ledger", "we owe", "owed to", "owe vendor", "owe suppliers"], "get_ap_subledger", _params_dates),
    (["ar subledger", "accounts receivable", "receivable", "ar sub-ledger", "customer ledger", "customers owe", "customer owe", "owed by customers", "owing", "owe us"], "get_ar_subledger", _params_dates),
    # reconcile_payroll must precede get_payroll_ledger (whose "payroll" keyword
    # matches first) so "reconcile payroll" reaches the month-end tool.
    (["reconcile payroll", "payroll recon", "payroll reconciliation"], "reconcile_payroll", _params_period),
    (["payroll ledger", "payroll", "salary ledger", "wage ledger"], "get_payroll_ledger", _params_dates),
    (["general ledger", "ledger", "show ledger"], "get_general_ledger", _params_dates),
    (["fixed asset", "depreciation scheme", "categorize asset", "add asset"], "categorize_fixed_asset", _params_record_transaction),
    (["add vendor", "new vendor", "vendor master", "add customer", "new customer", "customer master", "manage contact", "add contact", "add supplier", "find vendor", "search vendor", "search customer", "update vendor", "update customer", "delete vendor", "delete customer"], "manage_contact", _params_manage_contact),

    # --- Reconciliation ---
    (["cheque", "cheque clearing", "check clearing", "cheque track", "issue cheque", "clear cheque", "bounce cheque"], "track_cheque_clearing", _params_cheque),
    (["lc", "letter of credit", "bank guarantee", "guarantee track", "issue lc", "issue bg"], "track_lc_bank_guarantee", _params_lcbg),
    (["bank charges", "reconcile charges", "bank charge", "bank fees", "service charges", "reconcile service"], "reconcile_bank_charges", _params_bank_charges),
    (["vendor statement", "reconcile vendor", "vendor reconciliation", "reconcile vendor statement"], "reconcile_vendor_statement", _params_vendor_statement),
    (["customer statement", "reconcile customer", "customer reconciliation", "reconcile customer statement"], "reconcile_customer_statement", _params_customer_statement),
    (["accrual", "accrual entry", "post accrual"], "post_accrual_entry", _params_accrual),
    (["bank reconciliation", "reconcile bank", "reconcile statement", "bank statement match"], "run_bank_reconciliation", _params_bank_reconciliation),

    # --- Month-End ---
    (["unpaid bill", "unpaid", "overdue bill", "bills review"], "review_unpaid_bills", _params_aging),
    (["prepaid", "prepaid adjustment", "prepaid expense"], "calculate_prepaid_adjustment", _params_prepaid),
    (["depreciation", "depreciate"], "calculate_depreciation", _params_period_date),
    (["amortization", "amortize"], "calculate_amortization", _params_period_date),
    (["ar aging", "receivable aging", "aging report ar", "receivable report"], "get_ar_aging_report", _params_aging),
    (["ap aging", "payable aging", "aging report ap", "payable report"], "get_ap_aging_report", _params_aging),
    # Costing variance must precede the bare "variance" keyword below so
    # "standard costing variance" reaches calculate_standard_costing_variance.
    (["standard costing variance", "costing variance", "cost variance", "standard cost"], "calculate_standard_costing_variance", _params_standard_costing),
    (["budget variance", "variance analysis", "variance"], "analyze_budget_variance", _params_year_period),
    (["cash flow forecast", "forecast cash flow", "cash flow projection"], "forecast_cash_flow", _params_forecast),
    (["loan schedule", "debt schedule", "loan", "debt"], "get_loan_debt_schedule", _params_loan),

    # --- Year-End / Financial Statements ---
    (["trial balance"], "generate_trial_balance", _params_trial_balance),
    (["profit and loss", "profit & loss", "p&l", "pnl", "income statement", "profit loss", "generate p&l"], "generate_profit_loss", _params_dates),
    (["balance sheet"], "generate_balance_sheet", _params_trial_balance),
    (["cash flow statement", "statement of cash flows", "cashflow statement"], "generate_cash_flow_statement", _params_dates),
    (["retained earning", "transfer retained"], "transfer_retained_earnings", _params_year),
    (["carry forward", "carry-forward", "carry forward balance"], "carry_forward_balances", lambda t: {"from_fiscal_year": (_extract_year(t) or date.today().year) - 1, "to_fiscal_year": _extract_year(t) or date.today().year}),
    (["notes to financial", "notes to financials", "financial notes"], "draft_notes_to_financials", _params_year),
    (["close fiscal year", "close year", "close the books", "year end close", "year-end close"], "close_fiscal_year", _params_fiscal_close),

    # --- Cost & Budgeting / Advanced ---
    (["breakeven", "break even", "break-even", "cvp", "cost volume"], "calculate_breakeven", _params_breakeven),
    (["convert currency", "currency conversion", "exchange rate", "usd to", "to pkr", "convert "], "convert_foreign_currency", _params_convert_currency),
    (["budget forecast", "budget preparation", "prepare budget", "budget for"], "prepare_budget_forecast", _params_year),
    # calculate_standard_costing_variance route lives in the Month-End section
    # (it must precede the bare "variance" keyword); no duplicate route here.
    (["allocate overhead", "overhead allocation", "overhead cost", "overhead ", "cost allocation", "apportion"], "allocate_overhead_cost", _params_overhead),
    (["revenue recognition", "percentage of completion", "recognize revenue", "recognise revenue", "revenue recognized", "revenue recognised"], "calculate_revenue_recognition", _params_revenue_recognition),
    (["contingent liability", "provision", "ias 37", "provision for"], "flag_provision_contingent_liability", _params_provision),
    (["related party", "related-party", "insider", "related party transaction"], "flag_related_party_transaction", _params_related_party),

    # --- Tax ---
    (["withholding", "wht", "withholding tax"], "calculate_withholding_tax", _params_withholding),
    (["tax planning", "tax advice", "reduce tax", "tax liability"], "get_tax_planning_advice", _params_tax_planning),
    (["advance tax", "minimum tax", "super tax", "minimum/super"], "calculate_advance_minimum_tax", _params_amt),
    (["eobi", "old age benefit"], "calculate_eobi_deductions", _params_eobi),
    (["sales tax input", "sales tax output", "input tax", "output tax", "adjust sales tax"], "adjust_sales_tax_input_output", _params_year_period),
    (["exemption", "zero rating", "zero-rated", "tax exempt"], "flag_tax_exemption_zero_rating", _params_year),
    (["show my tax filings", "show tax filings", "tax filings", "my filings", "list filings", "saved filings", "my tax filing"], "list_tax_filings", _params_filings),
    (["sales tax filing", "file sales tax", "sales tax return"], "prepare_sales_tax_filing", _params_filing_sales),
    (["income tax filing", "file income tax", "income tax return"], "prepare_income_tax_filing", _params_filing_income),

    # --- Audit ---
    (["detect anomaly", "detect anomalies", "anomaly", "anomalies", "fraud detection", "detect fraud", "suspicious", "anomaly detection", "check anomaly"], "detect_anomaly_transactions", _params_period),
    (["compliance", "deadline", "filing deadline", "due date", "compliance calendar", "reminder"], "get_compliance_deadlines", _params_compliance),
    (["internal audit", "audit support"], "support_internal_audit", _params_year),
    (["statutory register", "register of director", "register of directors", "register of member", "register of members", "register of charge", "register of charges", "register of contract", "register of contracts", "director register", "member register", "charge register", "contract register", "beneficial owner", "beneficial owner register", "maintain register", "register entry", "register record", "statutory"], "maintain_statutory_registers", _params_statutory_registers),

    # --- Advisory ---
    (["spending pattern", "spending analysis", "spending", "spend analysis", "expense pattern"], "analyze_spending_patterns", _params_spending),
    (["financial ratio", "ratio analysis", "ratios", "liquidity ratio", "profitability"], "calculate_financial_ratios", _params_year),
    (["financial health", "health score", "health assessment"], "assess_financial_health", _params_year),
    (["cost cutting", "reduce expenses", "cost reduction", "save money", "cut cost"], "generate_cost_cutting_recommendations", _params_year),
    (["custom report", "generate report", "management report", "generate a report", "trend report", "comparative report", "detailed report", "summary report"], "generate_custom_report", _params_custom_report),

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
    # Asset purchases ("we bought a delivery truck for 2M") must win over the
    # generic "bought " record_transaction route so they reach the fixed-asset
    # categorizer instead of being treated as an ordinary expense.
    if _is_fixed_asset_intent(msg):
        return "categorize_fixed_asset", _params_fixed_asset(message)
    # "reconcile bank statement" must reach reconciliation, not the Daily Entry
    # check_bank_transactions route (its "bank statement" keyword matches first).
    if "reconcile" in msg and "bank statement" in msg:
        return "run_bank_reconciliation", _params_bank_reconciliation(message)
    # "flag ... as a related party" must reach the related-party tool, not the
    # Daily Entry record_transaction route (its "paid " keyword matches "paid to
    # <name>" in the flag message and swallows the flag).
    if "related party" in msg:
        return "flag_related_party_transaction", _params_related_party(message)
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
