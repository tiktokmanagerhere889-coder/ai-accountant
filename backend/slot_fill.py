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

from intent_router import _extract_amount, parse_petty_cash, _params_journal_entry, _params_manage_contact

# Tools that write to the DB and benefit from slot-filling when fields are missing.
WRITE_TOOLS = {
    "record_transaction_nl",
    "create_journal_entry",
    "record_bank_transaction",
    "manage_contact",
    "manage_petty_cash",
}

# In-memory pending intents: conversation_id -> PendingIntent dict
PENDING_INTENTS: dict[str, dict] = {}


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
    return True
