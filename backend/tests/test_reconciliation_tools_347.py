"""Integration tests for Reconciliation tools (Agent 3, tools 3, 4, 7):
reconcile_vendor_statement, reconcile_customer_statement, reconcile_bank_charges.

Run from backend/:
    python -m pytest tests/test_reconciliation_tools_347.py -v
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, Contact, JournalEntry, BankTransaction
from tools.schemas import (
    ReconcileVendorStatementInput,
    ReconcileCustomerStatementInput,
    ReconcileBankChargesInput,
    VendorStatementLine,
)
from tools.reconciliation_tools import (
    reconcile_vendor_statement,
    reconcile_customer_statement,
    reconcile_bank_charges,
)
from tests.test_helpers import TEST_DATABASE_URL


class TestReconciliationTools347:
    """Tests for reconciliation tools 3, 4, and 7."""

    @classmethod
    def setup_class(cls):
        """Create engine once per class."""
        cls.engine = create_engine(TEST_DATABASE_URL, echo=False)

    def setup_method(self):
        """Create fresh tables and seed data before each test."""
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self._seed_data()

    def teardown_method(self):
        """Close session after each test."""
        self.session.close()

    def _seed_data(self):
        """Create baseline test data shared across many tests."""
        # Contacts
        self.vendor = Contact(
            contact_id="CNT-V001",
            contact_name="Test Vendor",
            contact_type="vendor",
        )
        self.customer = Contact(
            contact_id="CNT-C001",
            contact_name="Test Customer",
            contact_type="customer",
        )
        self.session.add_all([self.vendor, self.customer])

        # AP journal entries (debit_account starts with "2000")
        self.ap_entry_1 = JournalEntry(
            entry_id="JE-20260705-001",
            description="Invoice 001 from vendor",
            posted_date=date(2026, 7, 5),
            reference="INV-001",
            debit_account="2000-Accounts Payable",
            debit_amount=Decimal("50000.00"),
            credit_account="1000-Cash",
            credit_amount=Decimal("50000.00"),
            status="posted",
        )
        self.ap_entry_2 = JournalEntry(
            entry_id="JE-20260715-001",
            description="Invoice 002 from vendor",
            posted_date=date(2026, 7, 15),
            reference="INV-002",
            debit_account="2000-Accounts Payable",
            debit_amount=Decimal("75000.00"),
            credit_account="1000-Cash",
            credit_amount=Decimal("75000.00"),
            status="posted",
        )

        # AR journal entries (debit_account starts with "1200")
        self.ar_entry_1 = JournalEntry(
            entry_id="JE-20260703-001",
            description="Invoice to customer",
            posted_date=date(2026, 7, 3),
            reference="CINV-001",
            debit_account="1200-Accounts Receivable",
            debit_amount=Decimal("100000.00"),
            credit_account="4000-Revenue",
            credit_amount=Decimal("100000.00"),
            status="posted",
        )
        self.ar_entry_2 = JournalEntry(
            entry_id="JE-20260720-001",
            description="Invoice to customer 2",
            posted_date=date(2026, 7, 20),
            reference="CINV-002",
            debit_account="1200-Accounts Receivable",
            debit_amount=Decimal("200000.00"),
            credit_account="4000-Revenue",
            credit_amount=Decimal("200000.00"),
            status="posted",
        )

        # Bank charges (type="debit", negative amounts)
        self.bank_charge_1 = BankTransaction(
            transaction_id="BT-C-001",
            date=date(2026, 7, 10),
            description="Bank service fee July",
            amount=Decimal("-1500.00"),
            type="debit",
            status="cleared",
            balance_after=Decimal("500000.00"),
            account_id="BA-001",
        )
        self.bank_charge_2 = BankTransaction(
            transaction_id="BT-C-002",
            date=date(2026, 7, 25),
            description="Account maintenance fee",
            amount=Decimal("-500.00"),
            type="debit",
            status="cleared",
            balance_after=Decimal("498500.00"),
            account_id="BA-001",
        )

        # Journal entries matching bank charges
        self.je_charge_1 = JournalEntry(
            entry_id="JE-20260710-001",
            description="Bank service charge",
            posted_date=date(2026, 7, 10),
            reference="BANK-SVC-001",
            debit_account="6000-Bank Charges",
            debit_amount=Decimal("1500.00"),
            credit_account="1000-Cash",
            credit_amount=Decimal("1500.00"),
            status="posted",
        )
        self.je_charge_2 = JournalEntry(
            entry_id="JE-20260725-001",
            description="Bank maintenance fee",
            posted_date=date(2026, 7, 25),
            reference="BANK-MNT-001",
            debit_account="6000-Bank Charges",
            debit_amount=Decimal("500.00"),
            credit_account="1000-Cash",
            credit_amount=Decimal("500.00"),
            status="posted",
        )

        self.session.add_all([
            self.ap_entry_1, self.ap_entry_2,
            self.ar_entry_1, self.ar_entry_2,
            self.bank_charge_1, self.bank_charge_2,
            self.je_charge_1, self.je_charge_2,
        ])
        self.session.commit()

    # ================================================================
    # Tool 3: reconcile_vendor_statement
    # ================================================================

    def test_vendor_normal_match(self):
        """Both statement lines match journal entries perfectly."""
        result = reconcile_vendor_statement(self.session, ReconcileVendorStatementInput(
            vendor_contact_id="CNT-V001",
            statement_date=date(2026, 7, 31),
            from_date=date(2026, 7, 1),
            to_date=date(2026, 7, 31),
            statement_lines=[
                VendorStatementLine(reference="INV-001", date=date(2026, 7, 5), amount=Decimal("50000.00")),
                VendorStatementLine(reference="INV-002", date=date(2026, 7, 15), amount=Decimal("75000.00")),
            ],
        ))

        assert result.reconciliation_id == "VSR-20260731-001"
        assert result.vendor_contact_id == "CNT-V001"
        assert len(result.matches) == 2
        assert all(m.status == "matched" for m in result.matches)
        assert all(m.amount_match for m in result.matches)
        assert all(m.date_match for m in result.matches)
        assert len(result.differences) == 0
        assert result.total_difference == Decimal("0.00")
        assert result.status == "pending_approval"

    def test_vendor_no_match(self):
        """Statement line has no corresponding journal entry."""
        result = reconcile_vendor_statement(self.session, ReconcileVendorStatementInput(
            vendor_contact_id="CNT-V001",
            statement_date=date(2026, 7, 31),
            from_date=date(2026, 7, 1),
            to_date=date(2026, 7, 31),
            statement_lines=[
                VendorStatementLine(reference="INV-999", date=date(2026, 7, 20), amount=Decimal("99999.00")),
            ],
        ))

        assert len(result.matches) == 1
        assert result.matches[0].status == "unmatched"
        assert result.matches[0].statement_ref == "INV-999"
        assert not result.matches[0].amount_match
        assert not result.matches[0].date_match
        # Both internal entries are unmatched by the statement
        assert len(result.differences) == 2

    def test_vendor_contact_not_found(self):
        """Non-existent contact_id raises ValueError."""
        with pytest.raises(ValueError) as ctx:
            reconcile_vendor_statement(self.session, ReconcileVendorStatementInput(
                vendor_contact_id="CNT-INVALID",
                statement_date=date(2026, 7, 31),
                from_date=date(2026, 7, 1),
                to_date=date(2026, 7, 31),
                statement_lines=[],
            ))
        assert "not found in contacts" in str(ctx.value)

    def test_vendor_amount_disagreement(self):
        """Same reference but different amount yields partial match."""
        result = reconcile_vendor_statement(self.session, ReconcileVendorStatementInput(
            vendor_contact_id="CNT-V001",
            statement_date=date(2026, 7, 31),
            from_date=date(2026, 7, 1),
            to_date=date(2026, 7, 31),
            statement_lines=[
                VendorStatementLine(reference="INV-001", date=date(2026, 7, 5), amount=Decimal("48000.00")),
            ],
        ))

        assert len(result.matches) == 1
        assert result.matches[0].status == "partial"
        assert not result.matches[0].amount_match  # amounts differ
        assert result.matches[0].date_match        # dates match
        assert result.total_difference == Decimal("48000.00") - Decimal("125000.00")

    def test_vendor_partial_payment(self):
        """One line matches, one is unmatched, one journal entry is a difference."""
        result = reconcile_vendor_statement(self.session, ReconcileVendorStatementInput(
            vendor_contact_id="CNT-V001",
            statement_date=date(2026, 7, 31),
            from_date=date(2026, 7, 1),
            to_date=date(2026, 7, 31),
            statement_lines=[
                VendorStatementLine(reference="INV-001", date=date(2026, 7, 5), amount=Decimal("50000.00")),
                VendorStatementLine(reference="INV-999", date=date(2026, 7, 20), amount=Decimal("30000.00")),
            ],
        ))

        assert len(result.matches) == 2
        # First line matched
        assert result.matches[0].status == "matched"
        assert result.matches[0].statement_ref == "INV-001"
        # Second line unmatched
        assert result.matches[1].status == "unmatched"
        assert result.matches[1].statement_ref == "INV-999"
        # INV-002 is unmatched internally
        assert len(result.differences) == 1
        assert result.differences[0].reference == "INV-002"
        assert result.differences[0].internal_amount == Decimal("75000.00")

    def test_vendor_date_mismatch(self):
        """Statement date range with no journal entries."""
        result = reconcile_vendor_statement(self.session, ReconcileVendorStatementInput(
            vendor_contact_id="CNT-V001",
            statement_date=date(2026, 6, 30),
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
            statement_lines=[
                VendorStatementLine(reference="INV-001", date=date(2026, 6, 5), amount=Decimal("50000.00")),
            ],
        ))

        assert len(result.matches) == 1
        assert result.matches[0].status == "unmatched"
        assert len(result.differences) == 0  # no journal entries in June

    # ================================================================
    # Tool 4: reconcile_customer_statement
    # ================================================================

    def test_customer_normal_match(self):
        """Both customer statement lines match journal entries perfectly."""
        result = reconcile_customer_statement(self.session, ReconcileCustomerStatementInput(
            customer_contact_id="CNT-C001",
            statement_date=date(2026, 7, 31),
            from_date=date(2026, 7, 1),
            to_date=date(2026, 7, 31),
            statement_lines=[
                VendorStatementLine(reference="CINV-001", date=date(2026, 7, 3), amount=Decimal("100000.00")),
                VendorStatementLine(reference="CINV-002", date=date(2026, 7, 20), amount=Decimal("200000.00")),
            ],
        ))

        assert result.reconciliation_id == "CSR-20260731-001"
        assert result.customer_contact_id == "CNT-C001"
        assert len(result.matches) == 2
        assert all(m.status == "matched" for m in result.matches)
        assert len(result.differences) == 0
        assert result.total_difference == Decimal("0.00")
        assert result.status == "pending_approval"

    def test_customer_no_match(self):
        """Customer statement line has no matching journal entry."""
        result = reconcile_customer_statement(self.session, ReconcileCustomerStatementInput(
            customer_contact_id="CNT-C001",
            statement_date=date(2026, 7, 31),
            from_date=date(2026, 7, 1),
            to_date=date(2026, 7, 31),
            statement_lines=[
                VendorStatementLine(reference="CINV-999", date=date(2026, 7, 10), amount=Decimal("99999.00")),
            ],
        ))

        assert len(result.matches) == 1
        assert result.matches[0].status == "unmatched"
        assert len(result.differences) == 2  # both AR entries unmatched

    def test_customer_contact_not_found(self):
        """Non-existent customer contact_id raises ValueError."""
        with pytest.raises(ValueError) as ctx:
            reconcile_customer_statement(self.session, ReconcileCustomerStatementInput(
                customer_contact_id="CNT-INVALID",
                statement_date=date(2026, 7, 31),
                from_date=date(2026, 7, 1),
                to_date=date(2026, 7, 31),
                statement_lines=[],
            ))
        assert "not found in contacts" in str(ctx.value)

    def test_customer_amount_disagreement(self):
        """Same customer reference but amount differs."""
        result = reconcile_customer_statement(self.session, ReconcileCustomerStatementInput(
            customer_contact_id="CNT-C001",
            statement_date=date(2026, 7, 31),
            from_date=date(2026, 7, 1),
            to_date=date(2026, 7, 31),
            statement_lines=[
                VendorStatementLine(reference="CINV-001", date=date(2026, 7, 3), amount=Decimal("95000.00")),
            ],
        ))

        assert len(result.matches) == 1
        assert result.matches[0].status == "partial"
        assert not result.matches[0].amount_match
        assert result.matches[0].date_match

    def test_customer_partial_payment(self):
        """One customer line matches, one does not."""
        result = reconcile_customer_statement(self.session, ReconcileCustomerStatementInput(
            customer_contact_id="CNT-C001",
            statement_date=date(2026, 7, 31),
            from_date=date(2026, 7, 1),
            to_date=date(2026, 7, 31),
            statement_lines=[
                VendorStatementLine(reference="CINV-001", date=date(2026, 7, 3), amount=Decimal("100000.00")),
                VendorStatementLine(reference="CINV-999", date=date(2026, 7, 25), amount=Decimal("50000.00")),
            ],
        ))

        assert len(result.matches) == 2
        assert result.matches[0].status == "matched"
        assert result.matches[1].status == "unmatched"
        assert len(result.differences) == 1  # CINV-002 unmatched internally

    def test_customer_date_mismatch(self):
        """Customer statement range with no AR entries."""
        result = reconcile_customer_statement(self.session, ReconcileCustomerStatementInput(
            customer_contact_id="CNT-C001",
            statement_date=date(2026, 8, 31),
            from_date=date(2026, 8, 1),
            to_date=date(2026, 8, 31),
            statement_lines=[
                VendorStatementLine(reference="CINV-001", date=date(2026, 8, 5), amount=Decimal("100000.00")),
            ],
        ))

        assert len(result.matches) == 1
        assert result.matches[0].status == "unmatched"
        assert len(result.differences) == 0

    # ================================================================
    # Tool 7: reconcile_bank_charges
    # ================================================================

    def test_bank_charges_normal_match(self):
        """Bank charges match journal entries."""
        result = reconcile_bank_charges(self.session, ReconcileBankChargesInput(
            bank_account_id="BA-001",
            from_date=date(2026, 7, 1),
            to_date=date(2026, 7, 31),
        ))

        assert result.total_charges_found == 2
        assert result.total_matched == 2
        assert result.total_unmatched == 0
        assert all(c.match_status == "matched" for c in result.charges)
        assert result.period_from == date(2026, 7, 1)
        assert result.period_to == date(2026, 7, 31)
        assert result.warning is None

    def test_bank_charges_no_charges(self):
        """No bank charges in the specified period."""
        result = reconcile_bank_charges(self.session, ReconcileBankChargesInput(
            bank_account_id="BA-001",
            from_date=date(2025, 1, 1),
            to_date=date(2025, 1, 31),
        ))

        assert result.total_charges_found == 0
        assert result.total_matched == 0
        assert result.total_unmatched == 0
        assert result.charges == []
        assert result.warning == "No bank charges found in the specified period"

    def test_bank_charges_type_filter(self):
        """Filter by charge_type matches only matching descriptions."""
        result = reconcile_bank_charges(self.session, ReconcileBankChargesInput(
            bank_account_id="BA-001",
            from_date=date(2026, 7, 1),
            to_date=date(2026, 7, 31),
            charge_type="service",
        ))

        # Only bank_charge_1 has "service" in description
        assert result.total_charges_found == 1
        assert result.total_charges_found == 1
        # Matching charge should be the service fee
        assert result.charges[0].description == "Bank service fee July"
        assert result.charges[0].match_status == "matched"

    def test_bank_charges_type_filter_no_match(self):
        """charge_type filter yields no results."""
        result = reconcile_bank_charges(self.session, ReconcileBankChargesInput(
            bank_account_id="BA-001",
            from_date=date(2026, 7, 1),
            to_date=date(2026, 7, 31),
            charge_type="transfer",
        ))

        assert result.total_charges_found == 0
        assert result.warning is not None
        assert "transfer" in result.warning

    def test_bank_charges_unmatched(self):
        """Bank charge with no matching journal entry."""
        # Add an extra bank charge with no corresponding journal entry
        orphan_charge = BankTransaction(
            transaction_id="BT-C-003",
            date=date(2026, 7, 20),
            description="ATM withdrawal fee",
            amount=Decimal("-350.00"),
            type="debit",
            status="cleared",
            balance_after=Decimal("498150.00"),
            account_id="BA-001",
        )
        self.session.add(orphan_charge)
        self.session.commit()

        result = reconcile_bank_charges(self.session, ReconcileBankChargesInput(
            bank_account_id="BA-001",
            from_date=date(2026, 7, 1),
            to_date=date(2026, 7, 31),
        ))

        assert result.total_charges_found == 3
        assert result.total_matched == 2  # original two matched
        assert result.total_unmatched == 1  # orphan unmatched

        unmatched = [c for c in result.charges if c.match_status == "unmatched"]
        assert len(unmatched) == 1
        assert unmatched[0].bank_txn_id == "BT-C-003"
        assert unmatched[0].journal_match_id is None

    def test_bank_charges_duplicate(self):
        """Two bank charges matching the same journal entry are flagged."""
        # Add a second charge with same amount as bank_charge_1 within 3 days
        dup_charge = BankTransaction(
            transaction_id="BT-C-004",
            date=date(2026, 7, 12),  # within 3 days of je_charge_1 (July 10)
            description="Duplicate service fee",
            amount=Decimal("-1500.00"),
            type="debit",
            status="cleared",
            balance_after=Decimal("498500.00"),
            account_id="BA-001",
        )
        self.session.add(dup_charge)
        self.session.commit()

        result = reconcile_bank_charges(self.session, ReconcileBankChargesInput(
            bank_account_id="BA-001",
            from_date=date(2026, 7, 1),
            to_date=date(2026, 7, 31),
        ))

        assert result.total_charges_found == 3
        assert result.total_matched == 3
        assert result.total_unmatched == 0
        # Both -1500 charges match je_charge_1
        assert result.warning is not None
        assert "Duplicate" in result.warning
