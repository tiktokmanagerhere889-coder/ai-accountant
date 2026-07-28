"""Integration tests for Ledger & Master Data tools (Agent 2, tools 1-3): create_journal_entry, get_general_ledger, suggest_chart_of_accounts.

Run from backend/:
    python -m tests.test_ledger_tools_123
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, JournalEntry
from tools.schemas import (
    CreateJournalEntryInput,
    GetGeneralLedgerInput,
    SuggestChartOfAccountsInput,
)
from tools.ledger_tools import (
    create_journal_entry,
    get_general_ledger,
    suggest_chart_of_accounts,
)
from tests.test_helpers import TEST_DATABASE_URL


def run_tests():
    """Run all ledger tool tests against a fresh PostgreSQL test database."""
    engine = create_engine(TEST_DATABASE_URL, echo=False)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    s = Session()

    today = date(2026, 7, 29)

    results = []

    print("=" * 70)
    print("LEDGER & MASTER DATA — TOOLS 1-3 INTEGRATION TEST (PostgreSQL)")
    print("=" * 70)

    # ====== Tool 1: create_journal_entry ======

    print("\n--- Tool 1: create_journal_entry ---")

    # Test 1: Basic journal entry creation
    print("\n[1] Create a basic journal entry")
    r1 = create_journal_entry(CreateJournalEntryInput(
        description="Office rent for July",
        posted_date=today,
        debit_account="6000-Office Rent",
        debit_amount=Decimal("50000.00"),
        credit_account="1000-Cash",
        credit_amount=Decimal("50000.00"),
        status="posted",
    ), s)
    assert r1.entry_id.startswith("JE-20260729-"), f"Expected JE-20260729- prefix, got {r1.entry_id}"
    assert r1.debit_amount == Decimal("50000.00")
    assert r1.credit_amount == Decimal("50000.00")
    assert r1.status == "posted"
    assert r1.description == "Office rent for July"
    print(f"  PASS: entry_id={r1.entry_id}, Dr {r1.debit_account} {r1.debit_amount}, Cr {r1.credit_account} {r1.credit_amount}")
    results.append(("create_journal_entry: basic", True))

    # Test 2: Second entry auto-increments sequence
    print("\n[2] Create another entry on same day (sequence increment)")
    r2 = create_journal_entry(CreateJournalEntryInput(
        description="Client payment received",
        posted_date=today,
        debit_account="1000-Cash",
        debit_amount=Decimal("150000.00"),
        credit_account="4000-Revenue",
        credit_amount=Decimal("150000.00"),
    ), s)
    assert r2.entry_id != r1.entry_id, "Entry IDs must be unique"
    assert r2.entry_id == "JE-20260729-002", f"Expected JE-20260729-002, got {r2.entry_id}"
    print(f"  PASS: entry_id={r2.entry_id}")
    results.append(("create_journal_entry: sequence increment", True))

    # Test 3: Different date generates different date prefix
    print("\n[3] Create entry with different date")
    yesterday = today - timedelta(days=1)
    r3 = create_journal_entry(CreateJournalEntryInput(
        description="Previous day transaction",
        posted_date=yesterday,
        debit_account="6000-Office Rent",
        debit_amount=Decimal("10000.00"),
        credit_account="1000-Cash",
        credit_amount=Decimal("10000.00"),
    ), s)
    expected_prefix = yesterday.strftime("JE-%Y%m%d-")
    assert r3.entry_id.startswith(expected_prefix), f"Expected {expected_prefix} prefix, got {r3.entry_id}"
    assert r3.entry_id.endswith("-001"), f"Expected sequence 001, got {r3.entry_id}"
    print(f"  PASS: entry_id={r3.entry_id}")
    results.append(("create_journal_entry: different date", True))

    # Test 4: Debits != credits raises ValueError
    print("\n[4] Reject entry with debits != credits")
    try:
        create_journal_entry(CreateJournalEntryInput(
            description="Unbalanced entry",
            posted_date=today,
            debit_account="6000-Office Rent",
            debit_amount=Decimal("50000.00"),
            credit_account="1000-Cash",
            credit_amount=Decimal("40000.00"),
        ), s)
        print("  FAIL: Expected ValueError")
        results.append(("create_journal_entry: unbalanced", False))
    except ValueError as e:
        assert "Debits" in str(e) and "credits" in str(e)
        print(f"  PASS: {e}")
        results.append(("create_journal_entry: unbalanced", True))

    # Test 5: Draft status accepted
    print("\n[5] Create entry with draft status")
    r5 = create_journal_entry(CreateJournalEntryInput(
        description="Draft entry for review",
        posted_date=today,
        debit_account="6000-Salaries",
        debit_amount=Decimal("100000.00"),
        credit_account="2000-Accrued Salaries",
        credit_amount=Decimal("100000.00"),
        status="draft",
    ), s)
    assert r5.status == "draft"
    print(f"  PASS: status=draft, entry_id={r5.entry_id}")
    results.append(("create_journal_entry: draft status", True))

    # ====== Tool 2: get_general_ledger ======

    print("\n--- Tool 2: get_general_ledger ---")

    # Test 6: Basic general ledger query
    print("\n[6] Get general ledger for date range")
    r6 = get_general_ledger(GetGeneralLedgerInput(
        from_date=yesterday,
        to_date=today,
    ), s)
    assert len(r6.accounts) >= 1, "Expected at least one account"
    total_debits = sum(a.total_debits for a in r6.accounts)
    total_credits = sum(a.total_credits for a in r6.accounts)
    assert total_debits == total_credits, f"GL must balance: {total_debits} != {total_credits}"
    print(f"  PASS: {len(r6.accounts)} accounts, total_debits={total_debits}, total_credits={total_credits}")
    results.append(("get_general_ledger: basic", True))

    # Test 7: account_code_prefix filter
    print("\n[7] Filter by account_code_prefix '6000'")
    r7 = get_general_ledger(GetGeneralLedgerInput(
        from_date=yesterday,
        to_date=today,
        account_code_prefix="6000",
    ), s)
    assert len(r7.accounts) >= 1, "Expected at least '6000' prefixed accounts"
    for a in r7.accounts:
        assert a.account_code.startswith("6000"), f"Account {a.account_code} does not start with '6000'"
    print(f"  PASS: {len(r7.accounts)} accounts with 6000 prefix")
    results.append(("get_general_ledger: prefix filter", True))

    # Test 8: from_date > to_date raises ValueError
    print("\n[8] Reject from_date > to_date")
    try:
        get_general_ledger(GetGeneralLedgerInput(
            from_date=today + timedelta(days=10),
            to_date=today,
        ), s)
        print("  FAIL: Expected ValueError")
        results.append(("get_general_ledger: invalid date range", False))
    except ValueError as e:
        assert "from_date" in str(e) and "to_date" in str(e)
        print(f"  PASS: {e}")
        results.append(("get_general_ledger: invalid date range", True))

    # Test 9: No entries in range returns empty list
    print("\n[9] Query with no matching entries")
    future_start = date(2099, 1, 1)
    future_end = date(2099, 12, 31)
    r9 = get_general_ledger(GetGeneralLedgerInput(
        from_date=future_start,
        to_date=future_end,
    ), s)
    assert r9.accounts == [], f"Expected empty list, got {len(r9.accounts)} accounts"
    assert r9.total_debits == Decimal("0.00")
    assert r9.total_credits == Decimal("0.00")
    print("  PASS: empty list returned")
    results.append(("get_general_ledger: no entries", True))

    # Test 10: Prefix filter with no matches returns empty list
    print("\n[10] Prefix filter with no matches")
    r10 = get_general_ledger(GetGeneralLedgerInput(
        from_date=yesterday,
        to_date=today,
        account_code_prefix="9999",
    ), s)
    assert r10.accounts == [], f"Expected empty list, got {len(r10.accounts)} accounts"
    print("  PASS: empty list for unmatched prefix")
    results.append(("get_general_ledger: prefix no matches", True))

    # ====== Tool 3: suggest_chart_of_accounts ======

    print("\n--- Tool 3: suggest_chart_of_accounts ---")

    # Test 11: Retail chart
    print("\n[11] Retail chart of accounts")
    r11 = suggest_chart_of_accounts(SuggestChartOfAccountsInput(business_type="retail"))
    assert r11.business_type == "retail"
    assert r11.total_count == len(r11.accounts)
    assert r11.total_count >= 10
    assert r11.needs_approval is True
    # Check a few expected accounts
    codes = {a.account_code for a in r11.accounts}
    assert "1000" in codes
    assert "4000" in codes
    assert "5000" in codes
    print(f"  PASS: {r11.total_count} accounts, needs_approval={r11.needs_approval}")
    results.append(("suggest_chart: retail", True))

    # Test 12: Freelance chart
    print("\n[12] Freelance chart of accounts")
    r12 = suggest_chart_of_accounts(SuggestChartOfAccountsInput(business_type="freelance"))
    assert r12.business_type == "freelance"
    assert r12.total_count >= 5
    codes = {a.account_code for a in r12.accounts}
    assert "4000" in codes  # Service Revenue
    print(f"  PASS: {r12.total_count} accounts")
    results.append(("suggest_chart: freelance", True))

    # Test 13: Manufacturing chart
    print("\n[13] Manufacturing chart of accounts")
    r13 = suggest_chart_of_accounts(SuggestChartOfAccountsInput(business_type="manufacturing"))
    assert r13.business_type == "manufacturing"
    assert r13.total_count >= 15
    codes = {a.account_code for a in r13.accounts}
    assert "1500" in codes  # PP&E
    assert "5000" in codes  # Raw Materials
    print(f"  PASS: {r13.total_count} accounts")
    results.append(("suggest_chart: manufacturing", True))

    # Test 14: Tech startup chart
    print("\n[14] Tech startup chart of accounts")
    r14 = suggest_chart_of_accounts(SuggestChartOfAccountsInput(business_type="tech_startup"))
    assert r14.business_type == "tech_startup"
    codes = {a.account_code for a in r14.accounts}
    assert "6100" in codes  # Cloud Infrastructure
    print(f"  PASS: {r14.total_count} accounts with Cloud Infrastructure")
    results.append(("suggest_chart: tech_startup", True))

    # Test 15: Restaurant chart
    print("\n[15] Restaurant chart of accounts")
    r15 = suggest_chart_of_accounts(SuggestChartOfAccountsInput(business_type="restaurant"))
    assert r15.business_type == "restaurant"
    codes = {a.account_code for a in r15.accounts}
    assert "1200" in codes  # Food & Beverage Inventory
    assert "5000" in codes  # Cost of Food Sold
    print(f"  PASS: {r15.total_count} accounts")
    results.append(("suggest_chart: restaurant", True))

    # Test 16: Non-profit chart
    print("\n[16] Non-profit chart of accounts")
    r16 = suggest_chart_of_accounts(SuggestChartOfAccountsInput(business_type="non_profit"))
    assert r16.business_type == "non_profit"
    codes = {a.account_code for a in r16.accounts}
    assert "4000" in codes  # Donations
    assert "3000" in codes  # Net Assets
    print(f"  PASS: {r16.total_count} accounts")
    results.append(("suggest_chart: non_profit", True))

    # Test 17: Real estate chart
    print("\n[17] Real estate chart of accounts")
    r17 = suggest_chart_of_accounts(SuggestChartOfAccountsInput(business_type="real_estate"))
    assert r17.business_type == "real_estate"
    codes = {a.account_code for a in r17.accounts}
    assert "1100" in codes  # Rental Properties
    print(f"  PASS: {r17.total_count} accounts")
    results.append(("suggest_chart: real_estate", True))

    # Test 18: Service-based chart
    print("\n[18] Service-based chart of accounts")
    r18 = suggest_chart_of_accounts(SuggestChartOfAccountsInput(business_type="service_based"))
    assert r18.business_type == "service_based"
    codes = {a.account_code for a in r18.accounts}
    assert "4000" in codes  # Service Revenue
    print(f"  PASS: {r18.total_count} accounts")
    results.append(("suggest_chart: service_based", True))

    # Test 19: Business type alias (freelancer -> freelance)
    print("\n[19] Alias resolution: 'freelancer' -> 'freelance'")
    r19 = suggest_chart_of_accounts(SuggestChartOfAccountsInput(business_type="freelancer"))
    assert r19.business_type == "freelance"
    print(f"  PASS: resolved to '{r19.business_type}'")
    results.append(("suggest_chart: alias resolution", True))

    # Test 20: Unknown business type raises ValueError
    print("\n[20] Unknown business type raises ValueError")
    try:
        suggest_chart_of_accounts(SuggestChartOfAccountsInput(business_type="quantum_computing"))
        print("  FAIL: Expected ValueError")
        results.append(("suggest_chart: unknown type", False))
    except ValueError as e:
        assert "quantum_computing" in str(e)
        print(f"  PASS: {e}")
        results.append(("suggest_chart: unknown type", True))

    # Test 21: All suggested accounts have required fields
    print("\n[21] All accounts have non-empty account_code, account_name, account_type")
    for biz_type in ["retail", "freelance", "manufacturing", "tech_startup", "restaurant", "non_profit", "real_estate", "service_based"]:
        r = suggest_chart_of_accounts(SuggestChartOfAccountsInput(business_type=biz_type))
        for acct in r.accounts:
            assert acct.account_code, f"Empty code in {biz_type}"
            assert acct.account_name, f"Empty name in {biz_type} for {acct.account_code}"
            assert acct.account_type, f"Empty type in {biz_type} for {acct.account_code}"
    print("  PASS: all accounts valid across all business types")
    results.append(("suggest_chart: field validation", True))

    # ====== Cleanup ======
    s.close()

    # ====== Summary ======
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print("\n" + "=" * 70)
    for scenario, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}: {scenario}")
    print(f"\nLedger Tools 1-3 Test: {passed}/{total} passed")
    print("=" * 70)
    return passed == total


if __name__ == "__main__":
    sys.exit(0 if run_tests() else 1)
