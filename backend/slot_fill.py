"""Multi-turn slot-filling for write tools.

When a write tool (record_transaction_nl, create_journal_entry, ...) is matched
but required fields are missing (e.g. "record an expense" has no amount), we do
NOT execute the tool. Instead we:

  1. Try to derive the missing field from the message itself.
  2. Otherwise register a pending intent keyed by conversation_id and return a
     clarifying question.
  3. On the next turn the user's answer is merged into the pending params; when
     all required fields are present the tool executes.

Pending intents are held in memory keyed by conversation_id (partial tool-args
stay with the session until complete). This resets on restart, which is fine for
a live chat session.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from intent_router import (
    _extract_amount,
    parse_petty_cash,
    _params_journal_entry,
    _params_manage_contact,
    _params_bank_reconciliation,
    _params_accrual,
    _params_vendor_statement,
    _params_customer_statement,
    _params_cheque,
    _params_lcbg,
    _params_bank_charges,
    _params_record_bank_transaction,
    _params_withholding,
    _params_amt,
    _params_eobi,
    _params_year_period,
    _params_filing_sales,
    _params_standard_costing,
    _params_overhead,
    _params_revenue_recognition,
    _params_provision,
    _params_related_party,
    _params_statutory_registers,
)

# Tools that write to the DB and benefit from slot-filling when fields are missing.
WRITE_TOOLS = {
    "record_transaction_nl",
    "create_journal_entry",
    "record_bank_transaction",
    "manage_contact",
    "manage_petty_cash",
    # Agent 3 (Reconciliation & Banking) — approval-required tools queue for
    # human approval; slot-fill ensures they never queue with garbage params.
    "run_bank_reconciliation",
    "post_accrual_entry",
    "reconcile_vendor_statement",
    "reconcile_customer_statement",
    "track_cheque_clearing",
    "track_lc_bank_guarantee",
    "reconcile_bank_charges",
    # Agent 5 (Tax): compute tools need amount/turnover/salary; approval tools
    # need period/year. Never queue or execute with invented defaults.
    "calculate_withholding_tax",
    "calculate_advance_minimum_tax",
    "calculate_eobi_deductions",
    "adjust_sales_tax_input_output",
    "prepare_sales_tax_filing",
    # Agent 7 (Cost & Budgeting): structured-field tools. Missing fields must
    # be asked for, never executed/queued with a bare {"fiscal_year": ...}.
    "calculate_standard_costing_variance",
    "allocate_overhead_cost",
    "calculate_revenue_recognition",
    "flag_provision_contingent_liability",
    "flag_related_party_transaction",
    # Agent 8 (Audit & Registers): statutory-register writes need action +
    # register_type + date + description; never queue with only a description.
    "maintain_statutory_registers",
}

# In-memory pending intents: conversation_id -> PendingIntent dict
PENDING_INTENTS: dict[str, dict] = {}

# Map each Agent 3 tool to its natural-language parser so merge_answer can
# re-derive fields when the user answers a slot-fill question.
_AGENT3_PARSE_TOOLS = {
    "run_bank_reconciliation": _params_bank_reconciliation,
    "post_accrual_entry": _params_accrual,
    "reconcile_vendor_statement": _params_vendor_statement,
    "reconcile_customer_statement": _params_customer_statement,
    "track_cheque_clearing": _params_cheque,
    "track_lc_bank_guarantee": _params_lcbg,
    "reconcile_bank_charges": _params_bank_charges,
}

_TAX_PARSE_TOOLS = {
    "calculate_withholding_tax": _params_withholding,
    "calculate_advance_minimum_tax": _params_amt,
    "calculate_eobi_deductions": _params_eobi,
    "adjust_sales_tax_input_output": _params_year_period,
    "prepare_sales_tax_filing": _params_filing_sales,
}

_COST_PARSE_TOOLS = {
    "calculate_standard_costing_variance": _params_standard_costing,
    "allocate_overhead_cost": _params_overhead,
    "calculate_revenue_recognition": _params_revenue_recognition,
    "flag_provision_contingent_liability": _params_provision,
    "flag_related_party_transaction": _params_related_party,
}

_AUDIT_PARSE_TOOLS = {
    "maintain_statutory_registers": _params_statutory_registers,
}


def is_write_tool(tool_name: str) -> bool:
    return tool_name in WRITE_TOOLS


def _category_keywords() -> list[str]:
    # Mirrors transaction_tools.EXPENSE_ACCOUNTS keys (category words).
    return [
        "rent", "salary", "wage", "utilities", "electric", "gas", "water",
        "office supplies", "stationery", "travel", "transport", "fuel", "petrol",
        "food", "meal", "entertainment", "advertising", "marketing", "insurance",
        "maintenance", "repair", "tax", "professional fee", "consultant",
        "miscellaneous",
    ]


def _has_category(desc: str) -> bool:
    d = desc.lower()
    return any(k in d for k in _category_keywords())


def describe_missing(tool_name: str, params: dict) -> Optional[str]:
    """Return a clarifying question if the tool call lacks required info, else None.

    Deterministic where possible (amount/category for transactions). For other
    write tools we ask generically for the missing action details.
    """
    if tool_name == "record_transaction_nl":
        desc = params.get("description", "")
        amount = _extract_amount(desc)
        if not amount:
            return (
                "Sure, I can record that for you. I need a couple more details:\n"
                "1. What amount? (e.g. 50000)\n"
                "2. What is it for? (e.g. office rent, electricity, salary)"
            )
        if not _has_category(desc):
            return (
                f"For the {amount} amount — what is this expense for? "
                "(e.g. rent, salary, utilities, travel)"
            )
        return None
    if tool_name == "create_journal_entry":
        # Needs debit/credit accounts + amounts. The router parses them when
        # present ("debiting 6000-Office Rent 50000 and crediting 1000-Cash 50000"),
        # otherwise ask for what's missing.
        missing: list[str] = []
        if not params.get("debit_account"):
            missing.append("the debit account (e.g. Office Rent)")
        if not params.get("debit_amount"):
            missing.append("the debit amount")
        if not params.get("credit_account"):
            missing.append("the credit account (e.g. Cash)")
        if not params.get("credit_amount"):
            missing.append("the credit amount")
        if missing:
            return (
                "To post a journal entry I need:\n"
                + "\n".join(f"{i+1}. {m}" for i, m in enumerate(missing))
                + "\n(e.g. debit Office Rent 50000, credit Cash 50000)"
            )
        return None
    if tool_name == "manage_petty_cash":
        parsed = parse_petty_cash(str(params.get("description", "") or ""))
        missing: list[str] = []
        if not params.get("action"):
            missing.append("what you want to do (add funds, record an expense, or check the balance)")
        if not params.get("fund_id"):
            missing.append("which petty cash fund (e.g. PC-001)")
        if not params.get("amount") and parsed.get("action") in ("add_fund", "expense"):
            missing.append("the amount")
        if missing:
            return (
                "I can help with that. I need a few more details:\n"
                + "\n".join(f"{i+1}. {m}" for i, m in enumerate(missing))
            )
        return None
    if tool_name == "manage_contact":
        # Needs action + contact_type + contact_name. Router parses them from
        # natural phrasing ("add vendor AL-MADINA GENERAL STORE"), otherwise
        # ask for what's missing.
        missing: list[str] = []
        if not params.get("action"):
            missing.append("what you want to do (add, update, delete, or search a contact)")
        if not params.get("contact_type"):
            missing.append("whether it's a vendor or a customer")
        if not params.get("contact_name"):
            missing.append("the contact name")
        if missing:
            return (
                "To manage a contact I need:\n"
                + "\n".join(f"{i+1}. {m}" for i, m in enumerate(missing))
                + "\n(e.g. add vendor AL-MADINA GENERAL STORE)"
            )
        return None
    if tool_name == "record_bank_transaction":
        # Needs amount + type + account. Router defaults account to 1100-Bank
        # and type to debit; only amount is truly required. A complete message
        # must return None (NOT the generic question) so it executes.
        if not params.get("amount"):
            return (
                "I can record that bank transaction. I need a couple more details:\n"
                "1. What amount? (e.g. 50000)\n"
                "2. Is it a debit or a credit?\n"
                "3. What bank account? (e.g. 1100-Bank)"
            )
        return None
    if tool_name == "run_bank_reconciliation":
        # Needs bank account + statement date + period. Router defaults bank
        # account to 1100-Bank and period to current month; only statement_date
        # can go missing.
        missing: list[str] = []
        if not params.get("bank_account_id"):
            missing.append("which bank account (e.g. 1100-Bank)")
        if not params.get("statement_date"):
            missing.append("the statement date")
        if not params.get("from_date") or not params.get("to_date"):
            missing.append("the period to reconcile (e.g. July 2026)")
        if missing:
            return (
                "To run a bank reconciliation I need:\n"
                + "\n".join(f"{i+1}. {m}" for i, m in enumerate(missing))
                + "\n(e.g. run bank reconciliation for 1100-Bank for July 2026)"
            )
        return None
    if tool_name == "post_accrual_entry":
        missing: list[str] = []
        if not params.get("accrual_type"):
            missing.append("the accrual type (salary, utilities, rent)")
        if not params.get("amount"):
            missing.append("the amount")
        if not params.get("period_date"):
            missing.append("the period date (e.g. 2026-07-31)")
        if missing:
            return (
                "To post an accrual entry I need:\n"
                + "\n".join(f"{i+1}. {m}" for i, m in enumerate(missing))
                + "\n(e.g. post accrual entry for salaries 150000 for July)"
            )
        return None
    if tool_name in ("reconcile_vendor_statement", "reconcile_customer_statement"):
        kind = "vendor" if tool_name == "reconcile_vendor_statement" else "customer"
        id_field = f"{kind}_contact_id"
        missing: list[str] = []
        if not params.get(id_field):
            missing.append(f"which {kind} contact (e.g. {kind.upper()}-NAME or CNT-001)")
        if not params.get("statement_lines"):
            missing.append("the statement lines (reference + amount, e.g. INV-200 50000)")
        if missing:
            return (
                f"To reconcile a {kind} statement I need:\n"
                + "\n".join(f"{i+1}. {m}" for i, m in enumerate(missing))
                + f"\n(e.g. reconcile {kind} statement from ABC Trading with line INV-200 50000)"
            )
        return None
    if tool_name == "track_cheque_clearing":
        missing: list[str] = []
        if not params.get("action"):
            missing.append("what you want to do (issue, clear, bounce, reconcile, status)")
        if not params.get("cheque_id") and params.get("action") in ("clear", "bounce", "reconcile", "status"):
            missing.append("the cheque number (e.g. CHQ-001234)")
        if params.get("action") == "issue":
            if not params.get("vendor_name"):
                missing.append("who the cheque is for (vendor name)")
            if not params.get("amount"):
                missing.append("the amount")
        if missing:
            return (
                "For cheque tracking I need:\n"
                + "\n".join(f"{i+1}. {m}" for i, m in enumerate(missing))
                + "\n(e.g. issue cheque number 001234 for 50000 to Abdullah General Store)"
            )
        return None
    if tool_name == "track_lc_bank_guarantee":
        missing: list[str] = []
        if not params.get("action"):
            missing.append("what you want to do (issue, amend, expire, close, status)")
        if not params.get("lc_id") and params.get("action") in ("amend", "expire", "close", "status"):
            missing.append("the LC/BG ID (e.g. LC-202607-001)")
        if params.get("action") == "issue":
            if not params.get("type"):
                missing.append("whether it's an LC or a BG")
            if not params.get("beneficiary"):
                missing.append("the beneficiary name")
            if not params.get("amount"):
                missing.append("the amount")
        if missing:
            return (
                "For LC/BG tracking I need:\n"
                + "\n".join(f"{i+1}. {m}" for i, m in enumerate(missing))
                + "\n(e.g. issue LC for 5000000 to ABC Trading, expiring 2026-12-31)"
            )
        return None
    if tool_name == "reconcile_bank_charges":
        missing: list[str] = []
        if not params.get("bank_account_id"):
            missing.append("which bank account (e.g. 1100-Bank)")
        if not params.get("from_date") or not params.get("to_date"):
            missing.append("the period to check (e.g. July 2026)")
        if missing:
            return (
                "To reconcile bank charges I need:\n"
                + "\n".join(f"{i+1}. {m}" for i, m in enumerate(missing))
                + "\n(e.g. reconcile bank charges for 1100-Bank for July)"
            )
        return None

    # --- Agent 5 (Tax) ---
    if tool_name == "calculate_withholding_tax":
        missing: list[str] = []
        if not params.get("amount"):
            missing.append("the payment amount")
        if not params.get("withholding_type"):
            missing.append("the withholding type (salary, contract, supply, service, rent, commission)")
        if missing:
            return (
                "To calculate withholding tax I need:\n"
                + "\n".join(f"{i+1}. {m}" for i, m in enumerate(missing))
                + "\n(e.g. calculate withholding tax on 50000 for services)"
            )
        return None
    if tool_name == "calculate_advance_minimum_tax":
        if not params.get("annual_turnover"):
            return (
                "To calculate advance minimum tax I need the annual turnover. "
                "\n(e.g. calculate minimum tax on 10000000 turnover as a company)"
            )
        return None
    if tool_name == "calculate_eobi_deductions":
        missing: list[str] = []
        if not params.get("gross_salary"):
            missing.append("the gross salary amount")
        if not params.get("period"):
            missing.append("the period (1-12 or month name)")
        if missing:
            return (
                "To calculate EOBI deductions I need:\n"
                + "\n".join(f"{i+1}. {m}" for i, m in enumerate(missing))
                + "\n(e.g. calculate EOBI on gross salary 45000 for period 7)"
            )
        return None
    if tool_name in ("adjust_sales_tax_input_output", "prepare_sales_tax_filing"):
        if not params.get("period"):
            return (
                f"For {tool_name.replace('_', ' ')} I need the period (month number or name). "
                "\n(e.g. adjust sales tax for July 2026)"
            )
        return None

    # --- Agent 7 (Cost & Budgeting) ---
    if tool_name == "calculate_standard_costing_variance":
        missing: list[str] = []
        if not params.get("account_code"):
            missing.append("the expense account code (e.g. 6000)")
        if not params.get("period"):
            missing.append("the period (1-12 or month name)")
        if not params.get("standard_cost"):
            missing.append("the standard/budgeted cost")
        if missing:
            return (
                "To calculate the standard costing variance I need:\n"
                + "\n".join(f"{i+1}. {m}" for i, m in enumerate(missing))
                + "\n(e.g. calculate standard costing variance for account 6000 period 7 fiscal year 2026 with standard cost 50000)"
            )
        return None
    if tool_name == "allocate_overhead_cost":
        missing: list[str] = []
        if not params.get("total_overhead"):
            missing.append("the total overhead cost")
        if not params.get("allocation_basis"):
            missing.append("the allocation basis (sq_ft, headcount, revenue_pct, or custom)")
        if not params.get("allocation_pool"):
            missing.append("the departments to allocate across, each with a value (e.g. sales 2000, hr 1500, production 3000)")
        if not params.get("period"):
            missing.append("the period (1-12 or month name)")
        if missing:
            return (
                "To allocate overhead cost I need:\n"
                + "\n".join(f"{i+1}. {m}" for i, m in enumerate(missing))
                + "\n(e.g. allocate 100000 overhead by revenue to sales 2000, hr 1500, production 3000 for period 7 fiscal year 2026)"
            )
        return None
    if tool_name == "calculate_revenue_recognition":
        missing: list[str] = []
        if not params.get("contract_id"):
            missing.append("the contract ID")
        if not params.get("contract_value"):
            missing.append("the total contract value")
        if not params.get("completion_percentage"):
            missing.append("the percentage of completion (e.g. 60%)")
        if not params.get("period"):
            missing.append("the period (1-12 or month name)")
        if missing:
            return (
                "To calculate revenue recognition I need:\n"
                + "\n".join(f"{i+1}. {m}" for i, m in enumerate(missing))
                + "\n(e.g. recognize revenue for contract CON-001 value 500000 at 60% completion for period 7 fiscal year 2026)"
            )
        return None
    if tool_name == "flag_provision_contingent_liability":
        missing: list[str] = []
        if not params.get("description") or len(params.get("description", "")) < 5:
            missing.append("a description of the contingent event")
        if not params.get("estimated_amount"):
            missing.append("the estimated financial impact")
        if not params.get("probability"):
            missing.append("the probability (probable, possible, or remote)")
        if missing:
            return (
                "To flag a provision/contingent liability I need:\n"
                + "\n".join(f"{i+1}. {m}" for i, m in enumerate(missing))
                + "\n(e.g. flag a probable provision of 200000 for an ongoing lawsuit in fiscal year 2026)"
            )
        return None
    if tool_name == "flag_related_party_transaction":
        missing: list[str] = []
        if not params.get("entry_id"):
            missing.append("the journal entry ID (e.g. JE-20260715-001)")
        if not params.get("amount"):
            missing.append("the transaction amount")
        if not params.get("counterparty_name"):
            missing.append("the counterparty name")
        if missing:
            return (
                "To flag a related-party transaction I need:\n"
                + "\n".join(f"{i+1}. {m}" for i, m in enumerate(missing))
                + "\n(e.g. flag JE-20260715-001 of 500000 paid to ABC Trading as a related party transaction in fiscal year 2026)"
            )
        return None
    if tool_name == "maintain_statutory_registers":
        # A bare "register of directors" is a view (safe read); only write
        # actions (add/update/delete) need the extra fields asked for.
        action = params.get("action")
        if action in ("update", "delete") and not params.get("register_id"):
            return (
                f"To {action} a statutory register entry I need the register ID. "
                "\n(e.g. update register entry REG-202607-001 ...)"
            )
        missing: list[str] = []
        if not params.get("register_type"):
            missing.append("the register type (directors, members, charges, contracts, beneficial owners)")
        if not params.get("description") or len(params.get("description", "")) < 5:
            missing.append("a description of the entry")
        if missing:
            return (
                "To maintain a statutory register I need:\n"
                + "\n".join(f"{i+1}. {m}" for i, m in enumerate(missing))
                + "\n(e.g. add director register entry: Ali Khan appointed 2026-07-01, reference DIR-001)"
            )
        return None

    # Other write tools: generic clarifying question.
    return (
        "I need a bit more detail to complete that. Can you give me the amount, "
        "date, and what it's for?"
    )


def merge_answer(pending: dict, answer: str) -> dict:
    """Merge a user's answer into a pending intent's params, deriving fields.

    The description is extended with the answer so record_transaction_nl can
    parse the amount and category from it (first number + keyword match).
    """
    params = dict(pending.get("params", {}))
    tool_name = pending.get("tool_name", "")
    description = params.get("description", "")
    merged = description

    if answer and answer.strip():
        merged = f"{description} {answer}".strip()
    params["description"] = merged

    # For non-transaction tools, keep the answer as the description field too.
    if tool_name == "manage_petty_cash":
        # Merge the answer into the description, then re-parse the whole message
        # so action/fund_id/amount are derived from everything the user said.
        merged = f"{description} {answer.strip()}".strip() if answer else description
        parsed = parse_petty_cash(merged)
        params = {**params, **parsed}
        params["description"] = merged
        return params
    if tool_name == "create_journal_entry":
        # Re-parse the full merged message so "debit Office Rent 50000, credit
        # Cash 50000" fills the account/amount fields, not just the description.
        merged = f"{description} {answer.strip()}".strip() if answer else description
        parsed = _params_journal_entry(merged)
        params = {**params, **parsed}
        params["description"] = merged
        return params
    if tool_name == "manage_contact":
        # Re-parse the full merged message so "vendor AL-MADINA GENERAL STORE"
        # fills contact_type/contact_name (plus phone/email/tax_id if given).
        merged = f"{description} {answer.strip()}".strip() if answer else description
        parsed = _params_manage_contact(merged)
        params = {**params, **parsed}
        params["description"] = merged
        return params
    if tool_name in _AGENT3_PARSE_TOOLS:
        # Re-parse the merged message through the tool's own parser so the
        # answer fills the missing fields.
        merged = f"{description} {answer.strip()}".strip() if answer else description
        parser = _AGENT3_PARSE_TOOLS[tool_name]
        parsed = parser(merged)
        params = {**params, **parsed}
        params["description"] = merged
        return params
    if tool_name == "record_bank_transaction":
        merged = f"{description} {answer.strip()}".strip() if answer else description
        parsed = _params_record_bank_transaction(merged)
        params = {**params, **parsed}
        params["description"] = merged
        return params
    if tool_name in _TAX_PARSE_TOOLS:
        # Re-parse the merged message through the tax tool's own parser so the
        # answer fills the missing fields (e.g. '50000 for services' fills both
        # amount and withholding_type).
        merged = f"{description} {answer.strip()}".strip() if answer else description
        parser = _TAX_PARSE_TOOLS[tool_name]
        parsed = parser(merged)
        params = {**params, **parsed}
        params["description"] = merged
        return params
    if tool_name in _COST_PARSE_TOOLS:
        # Re-parse the merged message through the Cost & Budgeting tool's own
        # parser so the answer fills the structured fields (account code,
        # overhead amount + pool, contract id + %, description, etc.).
        merged = f"{description} {answer.strip()}".strip() if answer else description
        parser = _COST_PARSE_TOOLS[tool_name]
        parsed = parser(merged)
        params = {**params, **parsed}
        params["description"] = merged
        return params
    if tool_name in _AUDIT_PARSE_TOOLS:
        # Same for statutory-register actions: re-parse the merged message so
        # "add director register entry ..." fills action/register_type/date.
        merged = f"{description} {answer.strip()}".strip() if answer else description
        parser = _AUDIT_PARSE_TOOLS[tool_name]
        parsed = parser(merged)
        params = {**params, **parsed}
        params["description"] = merged
        return params
    return params


def is_complete(tool_name: str, params: dict) -> bool:
    """True if a write tool now has the required fields to execute."""
    if tool_name == "record_transaction_nl":
        desc = params.get("description", "")
        if not _extract_amount(desc):
            return False
        if not _has_category(desc):
            return False
        return True
    if tool_name == "create_journal_entry":
        # Need the debit + credit accounts AND amounts, not just any number in
        # the message (an account code like "6000-" was being read as the amount).
        return bool(
            params.get("debit_account")
            and params.get("debit_amount")
            and params.get("credit_account")
            and params.get("credit_amount")
        )
    if tool_name == "manage_petty_cash":
        # Require the pieces the implementation needs: an action + a fund.
        if not params.get("action"):
            return False
        if not params.get("fund_id"):
            return False
        # add_fund/expense also need an amount.
        if params.get("action") in ("add_fund", "expense") and not params.get("amount"):
            return False
        return True
    if tool_name == "manage_contact":
        # Require action + contact_type + contact_name (all three are required
        # by ManageContactInput). Without them the tool raises validation errors.
        return bool(
            params.get("action")
            and params.get("contact_type")
            and params.get("contact_name")
        )
    if tool_name == "record_bank_transaction":
        # Amount is the only truly required field (type/account have defaults).
        return bool(params.get("amount"))
    if tool_name == "run_bank_reconciliation":
        return bool(
            params.get("bank_account_id")
            and params.get("statement_date")
            and params.get("from_date")
            and params.get("to_date")
        )
    if tool_name == "post_accrual_entry":
        return bool(
            params.get("accrual_type")
            and params.get("amount")
            and params.get("period_date")
        )
    if tool_name == "reconcile_vendor_statement":
        return bool(
            params.get("vendor_contact_id")
            and params.get("statement_lines")
        )
    if tool_name == "reconcile_customer_statement":
        return bool(
            params.get("customer_contact_id")
            and params.get("statement_lines")
        )
    if tool_name == "track_cheque_clearing":
        if not params.get("action"):
            return False
        if params.get("action") in ("clear", "bounce", "reconcile", "status"):
            return bool(params.get("cheque_id"))
        if params.get("action") == "issue":
            # vendor_name/amount optional in schema; action alone is enough.
            return True
        return True
    if tool_name == "track_lc_bank_guarantee":
        if not params.get("action"):
            return False
        if params.get("action") in ("amend", "expire", "close", "status"):
            return bool(params.get("lc_id"))
        return True
    if tool_name == "reconcile_bank_charges":
        return bool(
            params.get("bank_account_id")
            and params.get("from_date")
            and params.get("to_date")
        )
    if tool_name == "calculate_withholding_tax":
        return bool(params.get("amount") and params.get("withholding_type"))
    if tool_name == "calculate_advance_minimum_tax":
        return bool(params.get("annual_turnover"))
    if tool_name == "calculate_eobi_deductions":
        return bool(params.get("gross_salary") and params.get("period"))
    if tool_name in ("adjust_sales_tax_input_output", "prepare_sales_tax_filing"):
        return bool(params.get("period") and params.get("fiscal_year"))
    if tool_name == "calculate_standard_costing_variance":
        return bool(
            params.get("account_code")
            and params.get("period")
            and params.get("fiscal_year")
            and params.get("standard_cost")
        )
    if tool_name == "allocate_overhead_cost":
        return bool(
            params.get("total_overhead")
            and params.get("allocation_basis")
            and params.get("allocation_pool")
            and params.get("period")
            and params.get("fiscal_year")
        )
    if tool_name == "calculate_revenue_recognition":
        return bool(
            params.get("contract_id")
            and params.get("contract_value")
            and params.get("completion_percentage")
            and params.get("period")
            and params.get("fiscal_year")
        )
    if tool_name == "flag_provision_contingent_liability":
        return bool(
            params.get("description")
            and params.get("estimated_amount")
            and params.get("probability")
            and params.get("fiscal_year")
        )
    if tool_name == "flag_related_party_transaction":
        return bool(
            params.get("entry_id")
            and params.get("transaction_description")
            and params.get("amount")
            and params.get("counterparty_name")
            and params.get("fiscal_year")
        )
    if tool_name == "maintain_statutory_registers":
        action = params.get("action")
        if action in ("update", "delete"):
            # update/delete need the register_id; the other fields come from
            # the stored row.
            return bool(params.get("register_id"))
        # add/view need action + register_type + date + description (all four
        # are schema-required; add also wants a description).
        return bool(
            action
            and params.get("register_type")
            and params.get("entry_date")
            and (action == "view" or params.get("description"))
        )
    return True
