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

from intent_router import _extract_amount

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
        # Needs debit/credit accounts + amount. The router passes only description.
        desc = params.get("description", "")
        amount = _extract_amount(desc)
        if not amount:
            return (
                "To post a journal entry I need: the amount, the debit account, "
                "and the credit account. What are they? (e.g. 50000 debit Office Rent, "
                "credit Cash)"
            )
        return (
            f"Almost there — which accounts should I debit and credit for {amount}? "
            "(e.g. debit Office Rent, credit Cash)"
        )
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
    if tool_name in ("manage_contact", "manage_petty_cash"):
        params["description"] = answer.strip()
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
        # Router provides description/posted_date; a real amount is required.
        return bool(_extract_amount(params.get("description", "")))
    return True
