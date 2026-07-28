"""Tests for reconciliation tools 1-2: run_bank_reconciliation, post_accrual_entry.

Uses PostgreSQL via test_helpers.TEST_DATABASE_URL.
Each test class creates a fresh schema (drop_all + create_all) and seeds
its own data in setup_method, ensuring full isolation.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from db.models import Base, BankTransaction, JournalEntry
from tools.reconciliation_tools import run_bank_reconciliation, post_accrual_entry
from tools.schemas import (
    PostAccrualEntryInput,
    RunBankReconciliationInput,
)
from tests.test_helpers import TEST_DATABASE_URL


# Shared test constants
BANK_ACCOUNT_ID = "BA-001"
STATEMENT_DATE = date(2026, 7, 31)


# =============================================================================
# Tool 1: run_bank_reconciliation
# =============================================================================


class TestRunBankReconciliation:
    """Tests for run_bank_reconciliation -- matching bank txns to journal entries."""

    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    # ------------------------------------------------------------------
    # Test 1: Empty bank statement period
    # ------------------------------------------------------------------

    def test_empty_bank_statement_period(self):
        """No bank transactions for the period -> empty matches, zero totals."""
        inp = RunBankReconciliationInput(
            bank_account_id=BANK_ACCOUNT_ID,
            statement_date=STATEMENT_DATE,
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31),
        )
        result = run_bank_reconciliation(inp, self.session)
        assert result.matches == []
        assert result.unmatched_bank == []
        assert result.total_matched == 0
        assert result.total_unmatched == 0
        assert result.total_amount_matched == Decimal("0")
        assert result.total_amount_unmatched == Decimal("0")
        assert result.status == "completed"
        assert result.run_id.startswith("REC-")

    # ------------------------------------------------------------------
    # Test 2: No matching journal entries -> all bank items unmatched
    # ------------------------------------------------------------------

    def test_no_matching_journal_entries(self):
        """Bank txns exist but no JEs with matching amounts -> all unmatched."""
        self.session.add_all([
            BankTransaction(
                transaction_id="BT-001", date=date(2026, 6, 15),
                description="Vendor payment", amount=Decimal("5000.00"),
                type="credit", status="cleared", reference="INV-100",
                balance_after=Decimal("10000.00"), account_id=BANK_ACCOUNT_ID,
            ),
            BankTransaction(
                transaction_id="BT-002", date=date(2026, 6, 20),
                description="Customer deposit", amount=Decimal("3000.00"),
                type="debit", status="cleared", reference="DEP-200",
                balance_after=Decimal("13000.00"), account_id=BANK_ACCOUNT_ID,
            ),
        ])
        self.session.commit()

        # Create a JE with a different amount so no match occurs
        self.session.add(
            JournalEntry(
                entry_id="JE-XXX", description="Some entry",
                posted_date=date(2026, 6, 15),
                debit_account="6100-Salary", debit_amount=Decimal("9999.00"),
                credit_account="2000-Accrued Liabilities",
                credit_amount=Decimal("9999.00"), status="posted",
            )
        )
        self.session.commit()

        inp = RunBankReconciliationInput(
            bank_account_id=BANK_ACCOUNT_ID,
            statement_date=STATEMENT_DATE,
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
        )
        result = run_bank_reconciliation(inp, self.session)
        assert result.total_matched == 0
        assert result.total_unmatched == 2
        assert len(result.unmatched_bank) == 2
        for u in result.unmatched_bank:
            assert u.reason == "no_journal_match"
        assert result.total_amount_unmatched == Decimal("8000.00")

    # ------------------------------------------------------------------
    # Test 3: Multiple possible matches -> top 3 returned
    # ------------------------------------------------------------------

    def test_multiple_possible_matches(self):
        """Bank txn with multiple candidate JEs -> top 3 by confidence."""
        self.session.add(
            BankTransaction(
                transaction_id="BT-MULTI", date=date(2026, 6, 15),
                description="Payment", amount=Decimal("1000.00"),
                type="credit", status="cleared", reference="INV-001",
                balance_after=Decimal("5000.00"), account_id=BANK_ACCOUNT_ID,
            )
        )
        self.session.commit()

        # JE1: exact match (reference in description, same date) -> 95%
        self.session.add(
            JournalEntry(
                entry_id="JE-100", description="Payment for INV-001",
                posted_date=date(2026, 6, 15),
                debit_account="2000-Accounts Payable",
                debit_amount=Decimal("1000.00"),
                credit_account="1000-Cash",
                credit_amount=Decimal("1000.00"), status="posted",
            )
        )
        # JE2: amount match + date within 3 days -> 70%
        self.session.add(
            JournalEntry(
                entry_id="JE-200", description="Another entry",
                posted_date=date(2026, 6, 17),
                debit_account="6100-Salary",
                debit_amount=Decimal("1000.00"),
                credit_account="2000-Accrued Liabilities",
                credit_amount=Decimal("1000.00"), status="posted",
            )
        )
        # JE3: amount match only -> 50%
        self.session.add(
            JournalEntry(
                entry_id="JE-300", description="Old entry",
                posted_date=date(2026, 5, 1),
                debit_account="6200-Utilities",
                debit_amount=Decimal("1000.00"),
                credit_account="2000-Accrued Liabilities",
                credit_amount=Decimal("1000.00"), status="posted",
            )
        )
        self.session.commit()

        inp = RunBankReconciliationInput(
            bank_account_id=BANK_ACCOUNT_ID,
            statement_date=STATEMENT_DATE,
            from_date=date(2026, 5, 1),
            to_date=date(2026, 6, 30),
        )
        result = run_bank_reconciliation(inp, self.session)

        # One bank txn matched, top 3 candidates returned
        assert result.total_matched == 1
        assert len(result.matches) == 3

        # Sorted by confidence descending
        assert result.matches[0].confidence == 95
        assert result.matches[0].journal_entry_id == "JE-100"
        assert result.matches[0].match_type == "exact"

        assert result.matches[1].confidence == 70
        assert result.matches[1].journal_entry_id == "JE-200"
        assert result.matches[1].match_type == "amount_date"

        assert result.matches[2].confidence == 50
        assert result.matches[2].journal_entry_id == "JE-300"
        assert result.matches[2].match_type == "amount_only"

        assert result.total_unmatched == 0

    # ------------------------------------------------------------------
    # Test 4: Amount match with date gap > 3 days -> 50 % confidence
    # ------------------------------------------------------------------

    def test_amount_match_date_gap(self):
        """Amount matches but dates > 3 days apart -> 50 % confidence amount_only."""
        self.session.add(
            BankTransaction(
                transaction_id="BT-DATEGAP", date=date(2026, 1, 1),
                description="Old payment", amount=Decimal("2000.00"),
                type="credit", status="cleared", reference="INV-001",
                balance_after=Decimal("5000.00"), account_id=BANK_ACCOUNT_ID,
            )
        )
        self.session.commit()

        self.session.add(
            JournalEntry(
                entry_id="JE-DATEGAP", description="Some expense",
                posted_date=date(2026, 1, 10),
                debit_account="6100-Salary",
                debit_amount=Decimal("2000.00"),
                credit_account="2000-Accrued Liabilities",
                credit_amount=Decimal("2000.00"), status="posted",
            )
        )
        self.session.commit()

        inp = RunBankReconciliationInput(
            bank_account_id=BANK_ACCOUNT_ID,
            statement_date=STATEMENT_DATE,
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31),
        )
        result = run_bank_reconciliation(inp, self.session)
        assert result.total_matched == 1
        assert len(result.matches) == 1
        assert result.matches[0].confidence == 50
        assert result.matches[0].match_type == "amount_only"

    # ------------------------------------------------------------------
    # Test 5: Amount differs by < 1 % -> partial_match flag
    # ------------------------------------------------------------------

    def test_partial_match_flag(self):
        """Amount differs by < 1 % -> partial_match=True."""
        self.session.add(
            BankTransaction(
                transaction_id="BT-PARTIAL", date=date(2026, 6, 15),
                description="Payment", amount=Decimal("1000.00"),
                type="credit", status="cleared",
                balance_after=Decimal("5000.00"), account_id=BANK_ACCOUNT_ID,
            )
        )
        self.session.commit()

        # JE amount is 1005 (0.5 % diff from 1000) -> partial match
        self.session.add(
            JournalEntry(
                entry_id="JE-PARTIAL", description="Close entry",
                posted_date=date(2026, 6, 15),
                debit_account="6100-Salary",
                debit_amount=Decimal("1005.00"),
                credit_account="2000-Accrued Liabilities",
                credit_amount=Decimal("1005.00"), status="posted",
            )
        )
        self.session.commit()

        inp = RunBankReconciliationInput(
            bank_account_id=BANK_ACCOUNT_ID,
            statement_date=STATEMENT_DATE,
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
        )
        result = run_bank_reconciliation(inp, self.session)
        assert result.total_matched == 1
        assert len(result.matches) == 1
        assert result.matches[0].partial_match is True
        # 1000 vs 1005 with dates same day -> partial + date diff <=3 -> 40 %
        assert result.matches[0].confidence == 40

    # ------------------------------------------------------------------
    # Test 6: Existing reconciliation for same period -> return existing
    # ------------------------------------------------------------------

    def test_existing_reconciliation_for_period(self):
        """Same period + account already reconciled -> return existing run with note."""
        # First, create a bank txn and do an initial reconciliation
        self.session.add(
            BankTransaction(
                transaction_id="BT-EXIST", date=date(2026, 6, 15),
                description="Payment", amount=Decimal("500.00"),
                type="credit", status="cleared",
                balance_after=Decimal("5000.00"), account_id=BANK_ACCOUNT_ID,
            )
        )
        self.session.commit()

        self.session.add(
            JournalEntry(
                entry_id="JE-EXIST", description="Entry",
                posted_date=date(2026, 6, 15),
                debit_account="6100-Salary",
                debit_amount=Decimal("500.00"),
                credit_account="2000-Accrued Liabilities",
                credit_amount=Decimal("500.00"), status="posted",
            )
        )
        self.session.commit()

        inp = RunBankReconciliationInput(
            bank_account_id=BANK_ACCOUNT_ID,
            statement_date=STATEMENT_DATE,
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
        )

        # First call creates the run
        result1 = run_bank_reconciliation(inp, self.session)
        assert result1.status == "completed"
        assert result1.existing_run_note is None

        # Second call returns existing
        result2 = run_bank_reconciliation(inp, self.session)
        assert result2.existing_run_note is not None
        assert "already exists" in result2.existing_run_note
        assert result2.run_id == result1.run_id
        assert result2.total_matched == 1

    # ------------------------------------------------------------------
    # Test 7: Normal exact match -> 95 % confidence
    # ------------------------------------------------------------------

    def test_normal_exact_match(self):
        """Bank reference in JE description + amount match -> 95 %."""
        self.session.add(
            BankTransaction(
                transaction_id="BT-EXACT", date=date(2026, 6, 15),
                description="Payment for INV-999", amount=Decimal("2500.00"),
                type="credit", status="cleared", reference="INV-999",
                balance_after=Decimal("5000.00"), account_id=BANK_ACCOUNT_ID,
            )
        )
        self.session.commit()

        self.session.add(
            JournalEntry(
                entry_id="JE-EXACT", description="Payment for INV-999 done",
                posted_date=date(2026, 6, 15),
                debit_account="2000-Accounts Payable",
                debit_amount=Decimal("2500.00"),
                credit_account="1000-Cash",
                credit_amount=Decimal("2500.00"), status="posted",
            )
        )
        self.session.commit()

        inp = RunBankReconciliationInput(
            bank_account_id=BANK_ACCOUNT_ID,
            statement_date=STATEMENT_DATE,
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
        )
        result = run_bank_reconciliation(inp, self.session)
        assert result.total_matched == 1
        assert len(result.matches) == 1
        assert result.matches[0].confidence == 95
        assert result.matches[0].match_type == "exact"
        assert result.matches[0].partial_match is False
        assert result.matches[0].bank_txn_id == "BT-EXACT"
        assert result.matches[0].journal_entry_id == "JE-EXACT"
        assert result.matches[0].bank_amount == Decimal("2500.00")
        assert result.matches[0].journal_amount == Decimal("2500.00")


# =============================================================================
# Tool 2: post_accrual_entry
# =============================================================================


class TestPostAccrualEntry:
    """Tests for post_accrual_entry -- preparing accrual journal entries."""

    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    # ------------------------------------------------------------------
    # Test 8: Normal accrual -> correct accounts, pending_approval
    # ------------------------------------------------------------------

    def test_normal_accrual(self):
        """Normal salary accrual -> correct debit/credit accounts and pending_approval."""
        inp = PostAccrualEntryInput(
            accrual_type="salary",
            amount=Decimal("50000.00"),
            description="Salary accrual for July",
            period_date=date(2026, 7, 31),
        )
        result = post_accrual_entry(inp, self.session)
        assert result.accrual_type == "salary"
        assert result.debit_account == "6100-Salary"
        assert result.credit_account == "2000-Accrued Liabilities"
        assert result.debit_amount == Decimal("50000.00")
        assert result.credit_amount == Decimal("50000.00")
        assert result.needs_approval is True
        assert result.status == "pending_approval"
        assert result.entry_id is None
        assert result.warnings == []
        assert result.accrual_id.startswith("ACC-")

    # ------------------------------------------------------------------
    # Test 9: Duplicate for same period + type -> warning
    # ------------------------------------------------------------------

    def test_duplicate_same_period_type(self):
        """Same period + accrual type already posted -> duplicate warning."""
        self.session.add(
            JournalEntry(
                entry_id="JE-DUP-PERIOD", description="Salary accrual June",
                posted_date=date(2026, 7, 15),
                debit_account="6100-Salary",
                debit_amount=Decimal("50000.00"),
                credit_account="2000-Accrued Liabilities",
                credit_amount=Decimal("50000.00"), status="posted",
            )
        )
        self.session.commit()

        inp = PostAccrualEntryInput(
            accrual_type="salary",
            amount=Decimal("50000.00"),
            description="Salary accrual July",
            period_date=date(2026, 7, 31),
        )
        result = post_accrual_entry(inp, self.session)
        assert len(result.warnings) >= 1
        assert any("Duplicate accrual" in w for w in result.warnings)

    # ------------------------------------------------------------------
    # Test 10: Back-dated (> 30 days) -> warning
    # ------------------------------------------------------------------

    def test_back_dated_entry(self):
        """Period_date > 30 days in past -> back-dated warning."""
        inp = PostAccrualEntryInput(
            accrual_type="rent",
            amount=Decimal("10000.00"),
            description="Rent accrual for January",
            period_date=date(2025, 1, 1),
        )
        result = post_accrual_entry(inp, self.session)
        assert len(result.warnings) >= 1
        assert any("Back-dated" in w for w in result.warnings)

    # ------------------------------------------------------------------
    # Test 11: Partial period proration -> correct calculation
    # ------------------------------------------------------------------

    def test_partial_period_proration(self):
        """Partial period proration -> amount * days / 30."""
        inp = PostAccrualEntryInput(
            accrual_type="utilities",
            amount=Decimal("30000.00"),
            description="Partial month utilities",
            period_date=date(2026, 7, 31),
            partial_period_days=15,
        )
        result = post_accrual_entry(inp, self.session)
        assert result.prorated_amount == Decimal("15000.00")
        assert result.debit_amount == Decimal("15000.00")
        assert result.credit_amount == Decimal("15000.00")
        assert result.partial_period_days == 15
        assert result.needs_approval is True
        assert result.status == "pending_approval"

    # ------------------------------------------------------------------
    # Test 12: Unusual account pairing -> warning
    # ------------------------------------------------------------------

    def test_unusual_account_pairing_warning(self):
        """Salary credited to revenue account -> unusual pairing warning."""
        inp = PostAccrualEntryInput(
            accrual_type="salary",
            amount=Decimal("50000.00"),
            description="Salary accrual with unusual account",
            period_date=date(2026, 7, 31),
            credit_account="4000-Revenue",
        )
        result = post_accrual_entry(inp, self.session)
        assert len(result.warnings) >= 1
        assert any("Unusual" in w and "revenue" in w for w in result.warnings)
        # Override should be reflected
        assert result.credit_account == "4000-Revenue"

    # ------------------------------------------------------------------
    # Test 13: Duplicate within 24 hours -> warning
    # ------------------------------------------------------------------

    def test_duplicate_within_24h(self):
        """Similar entry posted within last 24h -> duplicate warning."""
        self.session.add(
            JournalEntry(
                entry_id="JE-RECENT", description="Recent salary entry",
                posted_date=date.today(),
                debit_account="6100-Salary",
                debit_amount=Decimal("50000.00"),
                credit_account="2000-Accrued Liabilities",
                credit_amount=Decimal("50000.00"), status="posted",
            )
        )
        self.session.commit()

        inp = PostAccrualEntryInput(
            accrual_type="salary",
            amount=Decimal("60000.00"),
            description="Another salary entry",
            period_date=date(2026, 7, 31),
        )
        result = post_accrual_entry(inp, self.session)
        assert len(result.warnings) >= 1
        assert any("24h" in w for w in result.warnings)
