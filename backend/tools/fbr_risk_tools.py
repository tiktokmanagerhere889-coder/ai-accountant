"""FBR audit-risk scoring tool - self-contained.

Scores a Pakistani business's risk of being selected for FBR audit, computed
from the client's own ledger using HISTORICALLY DISCLOSED FBR risk parameters.
Read-only (no DB writes), deterministic, and honest about what it can and
cannot verify.

HISTORICAL SCOPE
- Income tax: FBR Board-in-Council 14-02-2013 TY2011 parameter set (reproduced
  in Member (Audit) orders dated 18-01-2024).
- Sales tax: FBR Audit Policies 2016-2018.
- Exclusion: Finance Act 2025 / ITO 2001 s.214C immunity for persons selected
  for audit in any of the preceding three tax years.

SCORING RUBRIC
Start at 0. +25 per parameter with triggered=True and confidence in
("computed_from_ledger", "manual_input"), capped at 100. Parameters with
triggered=None (not_verifiable, or a required manual input was not supplied)
never add to the score - the score always comes from the evaluable subset.
Band mapping:
  score == 0             -> "low"
  triggered_count >= 3   -> "critical"
  triggered_count >= 1   -> "high"  (courts have held even a single risk
                          parameter qualifies a case as high risk - Ittefaq
                          Rice Mills [2013 PTD 1274])
  else                   -> "medium"  (defensive fallback: score > 0 with no
                          clearly-triggered parameter; unreachable under the
                          current +25-per-trigger rule)
If prior_3yr_audit_status == "audited", Finance Act 2025 immunity overrides
everything: risk_score = 0 and risk_band = "low" (the parameter table is still
computed for information and the exclusion is reported).

HONESTY LIMITS
Current (post-2016) income-tax selection parameters are kept confidential by
law (ITO 2001 s.214C(1A)) and FBR publishes no CRM/ML selection weights, so
this tool does NOT reproduce FBR's current selection model. See DISCLAIMER.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from db.models import JournalEntry, TaxFiling, Contact
from tools.account_utils import revenue_filter_clause, expense_filter_clause


def _round(value: Decimal, places: int = 2) -> Decimal:
    return value.quantize(Decimal("0." + "0" * places), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Pydantic models (defined here; tools/schemas.py is NOT touched)
# ---------------------------------------------------------------------------

class FbrRiskParameter(BaseModel):
    code: str
    name: str
    tax_type: str                       # "income_tax" | "sales_tax"
    source: str
    source_url: Optional[str] = None
    threshold: str
    actual_value: Optional[str] = None
    confidence: str                     # "computed_from_ledger" | "manual_input" | "not_verifiable"
    triggered: Optional[bool] = None    # None when not verifiable / data insufficient - never guessed
    note: Optional[str] = None


class FbrFlaggedItem(BaseModel):
    param_code: str
    description: str
    amount: Optional[Decimal] = None
    tax_year: Optional[int] = None
    ledger_entry_ids: list[str] = Field(default_factory=list)


class AssessFbrAuditRiskInput(BaseModel):
    fiscal_year: int
    business_type: str = "non_corporate"          # "corporate" | "non_corporate"
    is_manufacturer: bool = False
    prior_3yr_audit_status: str = "unknown"       # "audited" | "not_audited" | "unknown"
    months_non_filing: Optional[int] = None
    customs_import_value: Optional[Decimal] = None
    exempt_income: Optional[Decimal] = None
    refund_claim: Optional[Decimal] = None


class AssessFbrAuditRiskOutput(BaseModel):
    fiscal_year: int
    business_type: str
    risk_score: Decimal
    risk_band: str                                # "low" | "medium" | "high" | "critical"
    triggered_count: int
    exclusions_applied: list[str] = Field(default_factory=list)
    parameters: list[FbrRiskParameter] = Field(default_factory=list)
    flagged_items: list[FbrFlaggedItem] = Field(default_factory=list)
    disclaimer: str
    summary: str


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_IT_SOURCE = "FBR Board-in-Council 2013 (TY2011 set)"
_IT_URL = "http://www.fbr.gov.pk/pr/fbrs-board-in-council-meets/789/2013"
_ST_SOURCE = "FBR Audit Policy 2017"
_ST_URL = "https://download1.fbr.gov.pk/Docs/2018410114156425AuditPolicy2017.pdf"
_IMMUNITY_URL = "https://download1.fbr.gov.pk/Docs/2025841183918948CircularNo01of2025-26IncomeTax.pdf"

_DISCLAIMER = (
    "This is a risk heuristic based on HISTORICALLY DISCLOSED FBR audit parameters "
    "(Income Tax TY2011 set; Sales Tax Audit Policies 2016-2018). Current (post-2016) "
    "income-tax selection parameters are kept confidential by law (ITO 2001 s.214C(1A)), "
    "and FBR publishes no CRM/ML weights, so this tool does NOT reproduce FBR's current "
    "selection model and is not a guarantee of (or protection from) audit selection. "
    "Verify with a qualified accountant."
)


# ---------------------------------------------------------------------------
# Ledger helpers (read-only SELECTs)
# ---------------------------------------------------------------------------

def _posted_rows(db: Session, fiscal_year: int):
    """All posted journal entries for a fiscal year (via posted_date year)."""
    return db.query(JournalEntry).filter(
        JournalEntry.status == "posted",
        func.extract("year", JournalEntry.posted_date) == fiscal_year,
    ).all()


def _revenue_for_year(db: Session, fiscal_year: int) -> tuple[Decimal, list[str]]:
    """Posted revenue credits for a year (chart-resolved, codebase-standard).

    Uses the same revenue_filter_clause as tools/tax_tools.py: exact chart
    account match by account_type='revenue', else numeric-prefix fallback from
    chart codes, else name fallback on 'revenue'/'income'. Documented
    caveat inherited from that clause: a credit to an account whose name
    contains 'income' (e.g. a tax-payable accrual) is treated as revenue.
    """
    rows = db.query(JournalEntry).filter(
        JournalEntry.status == "posted",
        func.extract("year", JournalEntry.posted_date) == fiscal_year,
        revenue_filter_clause(JournalEntry.credit_account, db),
    ).all()
    total = Decimal("0")
    for r in rows:
        total += Decimal(str(r.credit_amount or "0"))
    return _round(total, 2), [r.entry_id for r in rows]


def _expenses_for_year(db: Session, fiscal_year: int) -> tuple[Decimal, list[str]]:
    """Posted expense debits for a year (chart-resolved, codebase-standard)."""
    rows = db.query(JournalEntry).filter(
        JournalEntry.status == "posted",
        func.extract("year", JournalEntry.posted_date) == fiscal_year,
        expense_filter_clause(JournalEntry.debit_account, db),
    ).all()
    total = Decimal("0")
    for r in rows:
        total += Decimal(str(r.debit_amount or "0"))
    return _round(total, 2), [r.entry_id for r in rows]


def _is_cogs_account(account_name: str) -> bool:
    """True for a purchases/COGS account: 5/6/8 numeric prefix or a
    cost-of-sale / purchase / cogs name (spec definition, documented)."""
    a = (account_name or "").lower()
    return (
        a.split("-")[0].strip()[:1] in ("5", "6", "8")
        or "cost of sale" in a or "cost of goods" in a
        or "purchase" in a or "cogs" in a
    )


def _cogs_for_year(db: Session, fiscal_year: int) -> tuple[Decimal, list[str]]:
    """COGS/purchases: posted debits to purchases/COGS accounts (see spec)."""
    total = Decimal("0")
    ids: list[str] = []
    for r in _posted_rows(db, fiscal_year):
        if _is_cogs_account(r.debit_account or ""):
            total += Decimal(str(r.debit_amount or "0"))
            ids.append(r.entry_id)
    return _round(total, 2), ids


def _finance_cost_for_year(db: Session, fiscal_year: int) -> tuple[Decimal, list[str]]:
    """Financial cost: expense accounts whose name contains finance/interest/
    bank charge/markup."""
    total = Decimal("0")
    ids: list[str] = []
    for r in _posted_rows(db, fiscal_year):
        acct = (r.debit_account or "").lower()
        if any(k in acct for k in ("finance", "interest", "bank charge", "markup")):
            total += Decimal(str(r.debit_amount or "0"))
            ids.append(r.entry_id)
    return _round(total, 2), ids


def _is_revenue_account(account_name: str) -> bool:
    """Name/prefix revenue check used for exempt-income classification."""
    a = (account_name or "").lower()
    return a.split("-")[0].strip().startswith("4") or "revenue" in a or "income" in a


def _exempt_revenue_for_year(db: Session, fiscal_year: int) -> tuple[Decimal, list[str]]:
    """Proxy for exempt income: revenue credits to accounts whose name contains
    'exempt'/'export'/'dividend'. Documented as a heuristic - the ledger has no
    reliable exempt-income tag, so this may understate true exempt income."""
    total = Decimal("0")
    ids: list[str] = []
    for r in _posted_rows(db, fiscal_year):
        acct = (r.credit_account or "").lower()
        if _is_revenue_account(r.credit_account) and any(
            k in acct for k in ("exempt", "export", "dividend")
        ):
            total += Decimal(str(r.credit_amount or "0"))
            ids.append(r.entry_id)
    return _round(total, 2), ids


def _income_filing_for(db: Session, fiscal_year: int) -> Optional[TaxFiling]:
    return db.query(TaxFiling).filter(
        TaxFiling.filing_type == "income",
        TaxFiling.fiscal_year == fiscal_year,
    ).first()


def _income_profit_by_year(db: Session) -> dict[int, Decimal]:
    """fiscal_year -> net profit (total_revenue - total_expenses) from income filings."""
    by_year: dict[int, Decimal] = {}
    for r in db.query(TaxFiling).filter(TaxFiling.filing_type == "income").all():
        rev = Decimal(str(r.total_revenue or "0"))
        exp = Decimal(str(r.total_expenses or "0"))
        by_year[r.fiscal_year] = _round(rev - exp, 2)
    return by_year


def _tax_paid_for(db: Session, fiscal_year: int) -> Optional[Decimal]:
    """Tax-paid indicator from the income filing: tax_liability when > 0,
    else net_payable when > 0, else 0. None when no filing exists."""
    f = _income_filing_for(db, fiscal_year)
    if f is None:
        return None
    liab = Decimal(str(f.tax_liability or "0"))
    if liab > 0:
        return liab
    np_ = Decimal(str(f.net_payable or "0"))
    return np_ if np_ > 0 else Decimal("0")


def _sales_filing_periods(db: Session, fiscal_year: int) -> set[int]:
    """Distinct monthly sales-filing periods recorded for a fiscal year."""
    rows = db.query(TaxFiling).filter(
        TaxFiling.filing_type == "sales",
        TaxFiling.fiscal_year == fiscal_year,
    ).all()
    return {r.period for r in rows if r.period is not None}


def _sales_tax_ledger_by_year(db: Session) -> tuple[dict[int, Decimal], dict[int, Decimal]]:
    """fiscal_year -> (input_tax, output_tax) from sales-tax ledger accounts.

    Input tax = posted debits to accounts containing 'input tax'; output tax =
    posted credits to accounts containing 'output tax'."""
    in_by_year: dict[int, Decimal] = {}
    out_by_year: dict[int, Decimal] = {}
    for r in db.query(JournalEntry).filter(JournalEntry.status == "posted").all():
        dr = (r.debit_account or "").lower()
        if "input tax" in dr:
            y = r.posted_date.year
            in_by_year[y] = in_by_year.get(y, Decimal("0")) + Decimal(str(r.debit_amount or "0"))
        cr = (r.credit_account or "").lower()
        if "output tax" in cr:
            y = r.posted_date.year
            out_by_year[y] = out_by_year.get(y, Decimal("0")) + Decimal(str(r.credit_amount or "0"))
    return in_by_year, out_by_year


def _carry_forward_input_tax_by_year(db: Session) -> dict[int, Decimal]:
    """fiscal_year -> sum of debits to carry-forward input-tax accounts."""
    by_year: dict[int, Decimal] = {}
    for r in db.query(JournalEntry).filter(JournalEntry.status == "posted").all():
        acct = (r.debit_account or "").lower()
        if "input tax" in acct and ("carry" in acct or "forward" in acct):
            y = r.posted_date.year
            by_year[y] = by_year.get(y, Decimal("0")) + Decimal(str(r.debit_amount or "0"))
    return by_year


def _decline_pct(current: Decimal, prior: Decimal) -> Optional[Decimal]:
    """YoY decline as a positive percentage when current < prior. None when
    prior is missing or zero (percentage not meaningful)."""
    if prior is None or prior <= 0:
        return None
    return (prior - current) / prior * 100


def _fmt_change(current: Decimal, prior: Decimal) -> str:
    """Signed percent-change string, e.g. '-50%' or '+11.1%'."""
    if prior is None or prior <= 0:
        return "N/A"
    pct = (current - prior) / prior * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{_round(pct, 1)}%"


def _risk_band(score: Decimal, triggered_count: int) -> str:
    """Map score + triggered count to a band (see module docstring rubric)."""
    if score == 0:
        return "low"
    if triggered_count >= 3:
        return "critical"
    if triggered_count >= 1:
        return "high"
    return "medium"


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

def assess_fbr_audit_risk(inp: AssessFbrAuditRiskInput, db: Session) -> AssessFbrAuditRiskOutput:
    """Score FBR audit-selection risk from the client's own ledger (read-only)."""
    fy = inp.fiscal_year
    corporate = inp.business_type == "corporate"
    immune = inp.prior_3yr_audit_status == "audited"

    revenue_cur, revenue_ids = _revenue_for_year(db, fy)
    revenue_prev, revenue_prev_ids = _revenue_for_year(db, fy - 1)
    expenses_cur, _ = _expenses_for_year(db, fy)
    expenses_prev, _ = _expenses_for_year(db, fy - 1)
    cogs_cur, cogs_ids = _cogs_for_year(db, fy)
    finance_cur, finance_ids = _finance_cost_for_year(db, fy)
    exempt_cur, exempt_ids = _exempt_revenue_for_year(db, fy)
    exempt_prev, _ = _exempt_revenue_for_year(db, fy - 1)

    income_profits = _income_profit_by_year(db)
    input_tax_by_year, output_tax_by_year = _sales_tax_ledger_by_year(db)
    carry_by_year = _carry_forward_input_tax_by_year(db)
    contacts_exist = db.query(Contact).count() > 0

    parameters: list[FbrRiskParameter] = []
    flagged: list[FbrFlaggedItem] = []

    def add_param(code, name, tax_type, source, source_url, threshold, confidence,
                  triggered, actual_value=None, note=None) -> FbrRiskParameter:
        p = FbrRiskParameter(
            code=code, name=name, tax_type=tax_type, source=source,
            source_url=source_url, threshold=threshold, actual_value=actual_value,
            confidence=confidence, triggered=triggered, note=note,
        )
        parameters.append(p)
        return p

    def flag(param_code, description, amount=None, tax_year=None, ledger_entry_ids=None):
        flagged.append(FbrFlaggedItem(
            param_code=param_code, description=description, amount=amount,
            tax_year=tax_year, ledger_entry_ids=ledger_entry_ids or [],
        ))

    # ------------------------------------------------------------------
    # Income tax - corporate / non-corporate (TY2011 set)
    # ------------------------------------------------------------------
    # IT-01 sales/imports mismatch > 5% (manual customs value required)
    if inp.customs_import_value is None:
        add_param("IT-01", "Sales/imports mismatch", "income_tax", _IT_SOURCE, _IT_URL,
                  "imports > 5% above declared sales", "manual_input", None,
                  actual_value="N/A",
                  note="customs_import_value not provided; import/sales mismatch cannot be assessed.")
    else:
        customs = inp.customs_import_value
        if revenue_cur > 0:
            mismatch = (customs - revenue_cur) / revenue_cur * 100
            trig = mismatch > 5
            add_param("IT-01", "Sales/imports mismatch", "income_tax", _IT_SOURCE, _IT_URL,
                      "imports > 5% above declared sales", "manual_input", trig,
                      actual_value=f"imports {_round(mismatch, 1)}% vs declared sales",
                      note=f"customs_import_value {customs} vs declared revenue {revenue_cur}; only the imports-above-sales direction is flagged.")
            if trig:
                flag("IT-01", f"Imports exceed declared sales by {_round(mismatch, 1)}%.",
                     amount=_round(customs - revenue_cur, 2), tax_year=fy,
                     ledger_entry_ids=revenue_ids)
        else:
            add_param("IT-01", "Sales/imports mismatch", "income_tax", _IT_SOURCE, _IT_URL,
                      "imports > 5% above declared sales", "manual_input", None,
                      actual_value="N/A",
                      note="No declared revenue in ledger to compare imports against.")

    # IT-02 sales decline > 10% YoY
    decl = _decline_pct(revenue_cur, revenue_prev)
    if decl is None:
        add_param("IT-02", "Sales decline YoY", "income_tax", _IT_SOURCE, _IT_URL,
                  "sales decline > 10% YoY", "computed_from_ledger", None,
                  actual_value="N/A",
                  note="Prior-year revenue missing or zero; sales decline cannot be assessed.")
    else:
        trig = decl > 10
        add_param("IT-02", "Sales decline YoY", "income_tax", _IT_SOURCE, _IT_URL,
                  "sales decline > 10% YoY", "computed_from_ledger", trig,
                  actual_value=_fmt_change(revenue_cur, revenue_prev))
        if trig:
            flag("IT-02", f"Revenue declined {_round(decl, 1)}% year-on-year.",
                 amount=_round(revenue_prev - revenue_cur, 2), tax_year=fy,
                 ledger_entry_ids=revenue_ids + revenue_prev_ids)

    # IT-03 refund claim > Rs.10M corporate / > Rs.5M non-corporate
    refund_threshold = Decimal("10000000") if corporate else Decimal("5000000")
    threshold_str = "refund claim > Rs 10M (corporate)" if corporate else "refund claim > Rs 5M (non-corporate)"
    if inp.refund_claim is not None:
        refund = inp.refund_claim
        refund_confidence = "manual_input"
        refund_note = f"refund_claim override supplied: {refund}."
    else:
        f = _income_filing_for(db, fy)
        if f is not None and Decimal(str(f.net_payable or "0")) < 0:
            refund = abs(Decimal(str(f.net_payable)))
            refund_confidence = "computed_from_ledger"
            refund_note = f"Derived from income TaxFiling {f.filing_id} negative net_payable."
        else:
            refund = Decimal("0")
            refund_confidence = "computed_from_ledger"
            refund_note = "No refund claim on record (no negative net_payable income filing, no override)."
    trig = refund > refund_threshold
    add_param("IT-03", "Large refund claim", "income_tax", _IT_SOURCE, _IT_URL,
              threshold_str, refund_confidence, trig,
              actual_value=f"Rs {_round(refund, 2)}", note=refund_note)
    if trig:
        flag("IT-03", f"Refund claim Rs {_round(refund, 2)} exceeds threshold Rs {refund_threshold}.",
             amount=refund, tax_year=fy)

    # IT-04 net profit decline > 5% over last 3 years (income filings)
    if all(y in income_profits for y in (fy, fy - 1, fy - 2)):
        base = income_profits[fy - 2]
        cur = income_profits[fy]
        if base > 0:
            decline = (base - cur) / base * 100
            trig = decline > 5
            add_param("IT-04", "Net profit decline over 3 years", "income_tax", _IT_SOURCE, _IT_URL,
                      "net profit decline > 5% over last 3 years", "computed_from_ledger", trig,
                      actual_value=f"FY{fy - 2}: {base} -> FY{fy}: {cur}",
                      note=f"Net profit (revenue - expenses) from income filings; {_round(decline, 1)}% decline over the window.")
            if trig:
                flag("IT-04", f"Net profit declined {_round(decline, 1)}% over the last 3 years.",
                     amount=_round(base - cur, 2), tax_year=fy)
        else:
            add_param("IT-04", "Net profit decline over 3 years", "income_tax", _IT_SOURCE, _IT_URL,
                      "net profit decline > 5% over last 3 years", "computed_from_ledger", None,
                      actual_value=f"FY{fy - 2}: {base} -> FY{fy}: {cur}",
                      note="Base-year net profit is zero or negative; percentage decline is not meaningful.")
    else:
        add_param("IT-04", "Net profit decline over 3 years", "income_tax", _IT_SOURCE, _IT_URL,
                  "net profit decline > 5% over last 3 years", "not_verifiable", None,
                  actual_value="N/A",
                  note="Fewer than 3 years of income TaxFiling data; net-profit trend cannot be assessed.")

    # IT-05 exempt income > Rs.5M corporate / > Rs.2M non-corporate
    exempt_threshold = Decimal("5000000") if corporate else Decimal("2000000")
    if inp.exempt_income is not None:
        exempt = inp.exempt_income
        exempt_confidence = "manual_input"
        exempt_note = "exempt_income override supplied."
    else:
        exempt = exempt_cur
        exempt_confidence = "computed_from_ledger"
        exempt_note = "Proxied from ledger revenue accounts containing 'exempt'/'export'/'dividend'; may understate true exempt income."
    trig = exempt > exempt_threshold
    add_param("IT-05", "High exempt income", "income_tax", _IT_SOURCE, _IT_URL,
              "exempt income > Rs 5M (corporate) / > Rs 2M (non-corporate)", exempt_confidence, trig,
              actual_value=f"Rs {_round(exempt, 2)}", note=exempt_note)
    if trig:
        flag("IT-05", f"Exempt income Rs {_round(exempt, 2)} exceeds threshold Rs {exempt_threshold}.",
             amount=exempt, tax_year=fy, ledger_entry_ids=exempt_ids)

    # IT-06 financial cost > 5% of turnover
    if revenue_cur > 0:
        ratio = finance_cur / revenue_cur * 100
        trig = ratio > 5
        add_param("IT-06", "High financial cost", "income_tax", _IT_SOURCE, _IT_URL,
                  "financial cost > 5% of turnover", "computed_from_ledger", trig,
                  actual_value=f"{_round(ratio, 1)}% of turnover",
                  note="Finance/interest/bank-charge/markup expense accounts.")
        if trig:
            flag("IT-06", f"Financial cost {_round(ratio, 1)}% of turnover exceeds 5%.",
                 amount=finance_cur, tax_year=fy, ledger_entry_ids=finance_ids)
    else:
        add_param("IT-06", "High financial cost", "income_tax", _IT_SOURCE, _IT_URL,
                  "financial cost > 5% of turnover", "computed_from_ledger", None,
                  actual_value="N/A",
                  note="No revenue in ledger; financial-cost ratio cannot be assessed.")

    # IT-07 turnover increase not reflected in income (5% margin)
    net_cur = revenue_cur - expenses_cur
    net_prev = revenue_prev - expenses_prev
    rev_growth = revenue_cur - revenue_prev
    net_growth = net_cur - net_prev
    if revenue_prev > 0 and rev_growth > 0:
        trig = net_growth < rev_growth * Decimal("0.05")
        add_param("IT-07", "Turnover increase not reflected in income", "income_tax", _IT_SOURCE, _IT_URL,
                  "turnover increase not reflected in income (5% margin)", "computed_from_ledger", trig,
                  actual_value=f"revenue {_fmt_change(revenue_cur, revenue_prev)}, net income {_fmt_change(net_cur, net_prev)}",
                  note="Flagged when net-income growth is below 5% of the turnover increase.")
        if trig:
            flag("IT-07", "Turnover increased but income did not follow (5% margin).",
                 tax_year=fy, ledger_entry_ids=revenue_ids + revenue_prev_ids)
    elif revenue_prev <= 0:
        add_param("IT-07", "Turnover increase not reflected in income", "income_tax", _IT_SOURCE, _IT_URL,
                  "turnover increase not reflected in income (5% margin)", "computed_from_ledger", None,
                  actual_value="N/A",
                  note="No prior-year revenue; income-reflection cannot be assessed.")
    else:
        add_param("IT-07", "Turnover increase not reflected in income", "income_tax", _IT_SOURCE, _IT_URL,
                  "turnover increase not reflected in income (5% margin)", "computed_from_ledger", False,
                  actual_value=f"revenue {_fmt_change(revenue_cur, revenue_prev)}, net income {_fmt_change(net_cur, net_prev)}",
                  note="Revenue did not increase; parameter not applicable.")

    # IT-08 COGS > 80% of sales (non-corporate spec; hotels/restaurants > 70%)
    if revenue_cur > 0:
        ratio = cogs_cur / revenue_cur * 100
        trig = ratio > 80
        add_param("IT-08", "High COGS ratio", "income_tax", _IT_SOURCE, _IT_URL,
                  "COGS > 80% of sales", "computed_from_ledger", trig,
                  actual_value=f"{_round(ratio, 1)}%",
                  note="Spec defines 80% for non-corporate (70% for hotels/restaurants); no industry input exists, so 80% is used for all.")
        if trig:
            excess = _round(cogs_cur - revenue_cur * Decimal("0.80"), 2)
            flag("IT-08", f"COGS Rs {_round(cogs_cur, 2)} ({_round(ratio, 1)}% of sales) exceeds "
                          f"the 80% threshold (Rs {_round(revenue_cur * Decimal('0.80'), 2)}); "
                          f"excess above threshold Rs {excess}.",
                 amount=excess, tax_year=fy,
                 ledger_entry_ids=cogs_ids)
    else:
        add_param("IT-08", "High COGS ratio", "income_tax", _IT_SOURCE, _IT_URL,
                  "COGS > 80% of sales", "computed_from_ledger", None,
                  actual_value="N/A",
                  note="No revenue in ledger; COGS ratio cannot be assessed.")

    # IT-09 continuous loss for last 3 years (income filings)
    if all(y in income_profits for y in (fy, fy - 1, fy - 2)):
        losses = all(income_profits[y] < 0 for y in (fy, fy - 1, fy - 2))
        add_param("IT-09", "Continuous losses", "income_tax", _IT_SOURCE, _IT_URL,
                  "continuous loss for last 3 years", "computed_from_ledger", losses,
                  actual_value=", ".join(f"FY{y}: {income_profits[y]}" for y in (fy - 2, fy - 1, fy)),
                  note="Net profit per year from income filings.")
        if losses:
            flag("IT-09", "Net loss in each of the last 3 fiscal years.", tax_year=fy)
    else:
        add_param("IT-09", "Continuous losses", "income_tax", _IT_SOURCE, _IT_URL,
                  "continuous loss for last 3 years", "not_verifiable", None,
                  actual_value="N/A",
                  note="Fewer than 3 years of income TaxFiling data.")

    # IT-10 net tax paid decline > 10% YoY (income filings)
    tax_cur = _tax_paid_for(db, fy)
    tax_prev = _tax_paid_for(db, fy - 1)
    if tax_cur is None or tax_prev is None:
        add_param("IT-10", "Net tax paid decline YoY", "income_tax", _IT_SOURCE, _IT_URL,
                  "net tax paid decline > 10% YoY", "not_verifiable", None,
                  actual_value="N/A",
                  note="Income TaxFiling data for two consecutive years required.")
    elif tax_prev > 0:
        decline = (tax_prev - tax_cur) / tax_prev * 100
        trig = decline > 10
        add_param("IT-10", "Net tax paid decline YoY", "income_tax", _IT_SOURCE, _IT_URL,
                  "net tax paid decline > 10% YoY", "computed_from_ledger", trig,
                  actual_value=f"FY{fy - 1}: {tax_prev} -> FY{fy}: {tax_cur}",
                  note="Tax-paid indicator from income filing tax_liability (fallback net_payable).")
        if trig:
            flag("IT-10", f"Net tax paid declined {_round(decline, 1)}% year-on-year.",
                 amount=_round(tax_prev - tax_cur, 2), tax_year=fy)
    else:
        add_param("IT-10", "Net tax paid decline YoY", "income_tax", _IT_SOURCE, _IT_URL,
                  "net tax paid decline > 10% YoY", "computed_from_ledger", None,
                  actual_value=f"FY{fy - 1}: {tax_prev} -> FY{fy}: {tax_cur}",
                  note="Prior-year tax paid is zero; percentage decline is not meaningful.")

    # ------------------------------------------------------------------
    # Sales tax - Audit Policy 2016/2017/2018
    # ------------------------------------------------------------------
    # ST-01 value of supplies decline > 10% YoY
    decl = _decline_pct(revenue_cur, revenue_prev)
    if decl is None:
        add_param("ST-01", "Supplies decline YoY", "sales_tax", _ST_SOURCE, _ST_URL,
                  "value of supplies decline > 10% YoY", "computed_from_ledger", None,
                  actual_value="N/A",
                  note="Prior-year supplies/revenue missing or zero.")
    else:
        trig = decl > 10
        add_param("ST-01", "Supplies decline YoY", "sales_tax", _ST_SOURCE, _ST_URL,
                  "value of supplies decline > 10% YoY", "computed_from_ledger", trig,
                  actual_value=_fmt_change(revenue_cur, revenue_prev),
                  note="Uses declared revenue as a proxy for value of supplies.")
        if trig:
            flag("ST-01", f"Value of supplies declined {_round(decl, 1)}% year-on-year.",
                 amount=_round(revenue_prev - revenue_cur, 2), tax_year=fy,
                 ledger_entry_ids=revenue_ids + revenue_prev_ids)

    # ST-02 output/input tax ratio declining over 3 years
    if all(y in input_tax_by_year and y in output_tax_by_year for y in (fy, fy - 1, fy - 2)) and all(
        input_tax_by_year[y] > 0 for y in (fy, fy - 1, fy - 2)
    ):
        r_base = output_tax_by_year[fy - 2] / input_tax_by_year[fy - 2]
        r_cur = output_tax_by_year[fy] / input_tax_by_year[fy]
        trig = r_cur < r_base * Decimal("0.95")
        add_param("ST-02", "Declining output/input tax ratio", "sales_tax", _ST_SOURCE, _ST_URL,
                  "output/input tax ratio declining over 3 years", "computed_from_ledger", trig,
                  actual_value=f"{_round(r_base, 2)} (FY{fy - 2}) -> {_round(r_cur, 2)} (FY{fy})",
                  note="Output tax credits vs input tax debits in sales-tax ledger accounts.")
        if trig:
            flag("ST-02", "Output/input tax ratio declined over the last 3 years.", tax_year=fy)
    else:
        add_param("ST-02", "Declining output/input tax ratio", "sales_tax", _ST_SOURCE, _ST_URL,
                  "output/input tax ratio declining over 3 years", "not_verifiable", None,
                  actual_value="N/A",
                  note="Fewer than 3 years of output/input sales-tax account data.")

    # ST-03 taxable/total supplies ratio decline >= 10% YoY
    if exempt_cur == 0 and exempt_prev == 0:
        add_param("ST-03", "Declining taxable/total supplies ratio", "sales_tax", _ST_SOURCE, _ST_URL,
                  "taxable/total supplies ratio decline >= 10% YoY", "not_verifiable", None,
                  actual_value="N/A",
                  note="No exempt-classified revenue in ledger; taxable vs total supplies not distinguishable.")
    elif revenue_cur > 0 and revenue_prev > 0:
        ratio_cur = (revenue_cur - exempt_cur) / revenue_cur
        ratio_prev = (revenue_prev - exempt_prev) / revenue_prev
        if ratio_prev > 0:
            decline = (ratio_prev - ratio_cur) / ratio_prev * 100
            trig = decline >= 10
            add_param("ST-03", "Declining taxable/total supplies ratio", "sales_tax", _ST_SOURCE, _ST_URL,
                      "taxable/total supplies ratio decline >= 10% YoY", "computed_from_ledger", trig,
                      actual_value=f"{_round(ratio_prev, 3)} (FY{fy - 1}) -> {_round(ratio_cur, 3)} (FY{fy})")
            if trig:
                flag("ST-03", f"Taxable/total supplies ratio declined {_round(decline, 1)}% YoY.",
                     tax_year=fy, ledger_entry_ids=revenue_ids + revenue_prev_ids)
        else:
            add_param("ST-03", "Declining taxable/total supplies ratio", "sales_tax", _ST_SOURCE, _ST_URL,
                      "taxable/total supplies ratio decline >= 10% YoY", "computed_from_ledger", None,
                      actual_value="N/A",
                      note="Prior-year taxable/total ratio is zero; percentage decline not meaningful.")
    else:
        add_param("ST-03", "Declining taxable/total supplies ratio", "sales_tax", _ST_SOURCE, _ST_URL,
                  "taxable/total supplies ratio decline >= 10% YoY", "computed_from_ledger", None,
                  actual_value="N/A",
                  note="Missing revenue for a year; ratio cannot be assessed.")

    # ST-04 value addition < 10% (manufacturers only - skipped otherwise)
    if inp.is_manufacturer:
        if revenue_cur > 0:
            value_added = (revenue_cur - cogs_cur) / revenue_cur * 100
            trig = value_added < 10
            add_param("ST-04", "Low value addition", "sales_tax", _ST_SOURCE, _ST_URL,
                      "value addition < 10% (manufacturers)", "computed_from_ledger", trig,
                      actual_value=f"{_round(value_added, 1)}%",
                      note="Value addition = (sales - purchases) / sales.")
            if trig:
                flag("ST-04", f"Value addition {_round(value_added, 1)}% is below 10%.",
                     amount=_round(revenue_cur * Decimal("0.10") - cogs_cur, 2), tax_year=fy,
                     ledger_entry_ids=cogs_ids)
        else:
            add_param("ST-04", "Low value addition", "sales_tax", _ST_SOURCE, _ST_URL,
                      "value addition < 10% (manufacturers)", "computed_from_ledger", None,
                      actual_value="N/A", note="No revenue in ledger.")

    # ST-05 > 30% (corporate) / > 40% (non-corporate) purchases from unregistered persons
    if not contacts_exist:
        add_param("ST-05", "Purchases from unregistered persons", "sales_tax", _ST_SOURCE, _ST_URL,
                  "> 30% (corporate) / > 40% (non-corporate) purchases from unregistered persons",
                  "not_verifiable", None, actual_value="N/A",
                  note="No Contact data; supplier registration status cannot be assessed.")
    else:
        unreg = Decimal("0")
        total = Decimal("0")
        unreg_ids: list[str] = []
        for r in _posted_rows(db, fy):
            if _is_cogs_account(r.debit_account or ""):
                amount = Decimal(str(r.debit_amount or "0"))
                total += amount
                contact = None
                if r.contact_id:
                    contact = db.query(Contact).filter(Contact.contact_id == r.contact_id).first()
                if contact is None or not contact.tax_id:
                    unreg += amount
                    unreg_ids.append(r.entry_id)
        threshold = Decimal("30") if corporate else Decimal("40")
        if total > 0:
            pct = unreg / total * 100
            trig = pct > threshold
            add_param("ST-05", "Purchases from unregistered persons", "sales_tax", _ST_SOURCE, _ST_URL,
                      f"> {int(threshold)}% purchases from unregistered persons", "computed_from_ledger", trig,
                      actual_value=f"{_round(pct, 1)}% of purchase value from unregistered suppliers",
                      note="Assumption: a supplier is registered only when a Contact record has a tax_id; a missing contact or missing tax_id counts as unregistered.")
            if trig:
                flag("ST-05", f"{_round(pct, 1)}% of purchases from suppliers without an NTN.",
                     amount=_round(unreg, 2), tax_year=fy, ledger_entry_ids=unreg_ids)
        else:
            add_param("ST-05", "Purchases from unregistered persons", "sales_tax", _ST_SOURCE, _ST_URL,
                      "> 30% (corporate) / > 40% (non-corporate) purchases from unregistered persons",
                      "computed_from_ledger", False,
                      actual_value="0% (no purchases in ledger)")

    # ST-06 carry-forward input tax increasing while sales decrease >= 10%
    if not carry_by_year:
        add_param("ST-06", "Rising input tax carry-forward with falling sales", "sales_tax", _ST_SOURCE, _ST_URL,
                  "carry-forward input tax increasing while sales decrease >= 10%", "not_verifiable", None,
                  actual_value="N/A",
                  note="No carry-forward input-tax accounts in ledger.")
    else:
        cur = carry_by_year.get(fy)
        prev = carry_by_year.get(fy - 1)
        decl = _decline_pct(revenue_cur, revenue_prev)
        if cur is None or prev is None or decl is None:
            add_param("ST-06", "Rising input tax carry-forward with falling sales", "sales_tax", _ST_SOURCE, _ST_URL,
                      "carry-forward input tax increasing while sales decrease >= 10%", "computed_from_ledger", None,
                      actual_value="N/A",
                      note="Need 2 years of carry-forward input-tax data and prior-year sales.")
        else:
            trig = decl >= 10 and cur > prev
            add_param("ST-06", "Rising input tax carry-forward with falling sales", "sales_tax", _ST_SOURCE, _ST_URL,
                      "carry-forward input tax increasing while sales decrease >= 10%", "computed_from_ledger", trig,
                      actual_value=f"carry-forward input tax {_round(prev, 2)} -> {_round(cur, 2)}; sales {_fmt_change(revenue_cur, revenue_prev)}")
            if trig:
                flag("ST-06", "Carry-forward input tax rose while sales declined.", tax_year=fy)

    # ST-07 non-filing > 6 months
    if inp.months_non_filing is not None:
        months = inp.months_non_filing
        conf = "manual_input"
        note = f"months_non_filing override supplied: {months}."
        trig = months > 6
        add_param("ST-07", "Non-filing", "sales_tax", _ST_SOURCE, _ST_URL,
                  "non-filing > 6 months", conf, trig,
                  actual_value=f"{months} months non-filing", note=note)
        if trig:
            flag("ST-07", f"No filing recorded for {months} months.", tax_year=fy)
    else:
        # The tax_filings table only records filings PREPARED inside this app.
        # A business may have filed on the FBR portal directly, so the absence
        # of in-app sales-filing periods (or a partial set) is NOT evidence of
        # actual non-filing. Only a manual months_non_filing input from the
        # owner/CA is reliable, so without it this parameter is not_verifiable
        # rather than triggered from an incomplete record.
        periods = _sales_filing_periods(db, fy)
        if periods:
            period_note = f"{len(periods)} in-app sales filing period(s) recorded for FY {fy}; "
        else:
            period_note = ""
        add_param("ST-07", "Non-filing", "sales_tax", _ST_SOURCE, _ST_URL,
                  "non-filing > 6 months", "not_verifiable", None,
                  actual_value="N/A",
                  note=(period_note +
                        "the app only tracks filings prepared here, not FBR portal submissions; "
                        "non-filing cannot be confirmed without a manual months_non_filing value."))

    # ------------------------------------------------------------------
    # Scoring (see module docstring rubric)
    # ------------------------------------------------------------------
    triggered_count = sum(1 for p in parameters if p.triggered is True)

    if immune:
        risk_score = Decimal("0")
        risk_band = "low"
        exclusions = ["prior_3yr_audited: immune from selection under Finance Act 2025 (ITO s.214C)"]
        summary = (
            f"Audited in one of the preceding three tax years: immune from audit selection "
            f"under Finance Act 2025 (ITO 2001 s.214C; FBR Circular No. 01 of 2025-26, "
            f"{_IMMUNITY_URL}). Risk band is low (score 0). The parameter table below is "
            f"computed for information only."
        )
    else:
        risk_score = _round(min(Decimal("100"), Decimal("25") * triggered_count), 2)
        risk_band = _risk_band(risk_score, triggered_count)
        exclusions = []
        evaluable = sum(1 for p in parameters if p.triggered is not None)
        summary = (
            f"Risk band {risk_band} with score {risk_score}/100. {triggered_count} of "
            f"{evaluable} evaluable HISTORICALLY DISCLOSED FBR risk parameters triggered. "
            f"Current (post-2016) FBR selection parameters are confidential, so this does "
            f"not reproduce FBR's current selection model."
        )
        if triggered_count >= 1:
            for p in parameters:
                if p.triggered is True:
                    p.note = ((p.note + " ") if p.note else "") + (
                        "Even a single risk parameter qualifies a case as high risk - "
                        "Ittefaq Rice Mills [2013 PTD 1274]."
                    )
                    break

    disclaimer = f"This client is assessed as {risk_band} risk. " + _DISCLAIMER

    return AssessFbrAuditRiskOutput(
        fiscal_year=fy,
        business_type=inp.business_type,
        risk_score=risk_score,
        risk_band=risk_band,
        triggered_count=triggered_count,
        exclusions_applied=exclusions,
        parameters=parameters,
        flagged_items=flagged,
        disclaimer=disclaimer,
        summary=summary,
    )
