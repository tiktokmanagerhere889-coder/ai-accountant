"""Tests for ledger tools 4-6: AP subledger, AR subledger, payroll ledger.

Uses PostgreSQL via test_helpers.TEST_DATABASE_URL.
Each test class creates a fresh schema (drop_all + create_all) and seeds
its own data in setup_method, ensuring full isolation.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, JournalEntry, PayrollEntry
from tools.ledger_tools import get_ap_subledger, get_ar_subledger, get_payroll_ledger
from tools.schemas import (
    GetAPSubledgerInput,
    GetARSubledgerInput,
    GetPayrollLedgerInput,
)
from tests.test_helpers import TEST_DATABASE_URL


class TestGetAPSubledger:
    """Tests for get_ap_subledger -- queries journal_entries with debit_account starting with '2000'."""

    def setup_method(self):
        engine = create_engine(TEST_DATABASE_URL, echo=False)
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine)
        self.session = SessionLocal()
        self._seed_data()

    def teardown_method(self):
        self.session.close()

    def _seed_data(self):
        entries = [
            JournalEntry(
                entry_id="AP-001", description="Vendor A invoice 1",
                posted_date=date(2026, 6, 15), reference="VENDOR-A",
                debit_account="2000-01", debit_amount=Decimal("5000.00"),
                credit_account="5000-01", credit_amount=Decimal("5000.00"),
                status="posted",
            ),
            JournalEntry(
                entry_id="AP-002", description="Vendor A invoice 2",
                posted_date=date(2026, 6, 20), reference="VENDOR-A",
                debit_account="2000-01", debit_amount=Decimal("3000.00"),
                credit_account="5000-02", credit_amount=Decimal("3000.00"),
                status="posted",
            ),
            JournalEntry(
                entry_id="AP-003", description="Vendor B invoice",
                posted_date=date(2026, 6, 25), reference="VENDOR-B",
                debit_account="2000-02", debit_amount=Decimal("7000.00"),
                credit_account="5000-03", credit_amount=Decimal("7000.00"),
                status="posted",
            ),
            # Non-AP entry to verify filtering (debit_account does not start with "2000")
            JournalEntry(
                entry_id="AP-004", description="Cash deposit",
                posted_date=date(2026, 6, 10), reference="CASH-001",
                debit_account="1000-01", debit_amount=Decimal("2000.00"),
                credit_account="4000-01", credit_amount=Decimal("2000.00"),
                status="posted",
            ),
        ]
        for e in entries:
            self.session.add(e)
        self.session.commit()

    def test_ap_with_entries(self):
        """Returns grouped AP entries with correct totals."""
        inp = GetAPSubledgerInput(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
        )
        result = get_ap_subledger(self.session, inp)
        assert len(result.entries) == 2
        vendor_names = {e.vendor_name for e in result.entries}
        assert vendor_names == {"VENDOR-A", "VENDOR-B"}
        assert result.total_outstanding == Decimal("15000.00")
        assert result.total_paid == Decimal("0.00")

    def test_ap_empty(self):
        """Returns empty entries and zero total when no entries match."""
        inp = GetAPSubledgerInput(
            from_date=date(2025, 1, 1),
            to_date=date(2025, 1, 31),
        )
        result = get_ap_subledger(self.session, inp)
        assert len(result.entries) == 0
        assert result.total_outstanding == Decimal("0.00")

    def test_ap_vendor_filter(self):
        """Filters by vendor_contact_id, returning only that vendor's entries."""
        inp = GetAPSubledgerInput(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
            vendor_contact_id="VENDOR-A",
        )
        result = get_ap_subledger(self.session, inp)
        assert len(result.entries) == 1
        assert result.entries[0].vendor_name == "VENDOR-A"
        assert result.entries[0].invoice_amount == Decimal("8000.00")
        assert result.total_outstanding == Decimal("8000.00")


class TestGetARSubledger:
    """Tests for get_ar_subledger -- queries journal_entries with debit_account starting with '1200'."""

    def setup_method(self):
        engine = create_engine(TEST_DATABASE_URL, echo=False)
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine)
        self.session = SessionLocal()
        self._seed_data()

    def teardown_method(self):
        self.session.close()

    def _seed_data(self):
        entries = [
            JournalEntry(
                entry_id="AR-001", description="Customer X invoice",
                posted_date=date(2026, 6, 10), reference="CUST-X",
                debit_account="1200-01", debit_amount=Decimal("4000.00"),
                credit_account="4000-01", credit_amount=Decimal("4000.00"),
                status="posted",
            ),
            JournalEntry(
                entry_id="AR-002", description="Customer Y invoice",
                posted_date=date(2026, 6, 15), reference="CUST-Y",
                debit_account="1200-02", debit_amount=Decimal("6000.00"),
                credit_account="4000-02", credit_amount=Decimal("6000.00"),
                status="posted",
            ),
            # Non-AR entry to verify filtering
            JournalEntry(
                entry_id="AR-003", description="Office expense",
                posted_date=date(2026, 6, 5), reference="EXP-001",
                debit_account="5000-01", debit_amount=Decimal("1000.00"),
                credit_account="1000-01", credit_amount=Decimal("1000.00"),
                status="posted",
            ),
        ]
        for e in entries:
            self.session.add(e)
        self.session.commit()

    def test_ar_with_entries(self):
        """Returns grouped AR entries with correct totals."""
        inp = GetARSubledgerInput(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
        )
        result = get_ar_subledger(self.session, inp)
        assert len(result.entries) == 2
        assert result.total_outstanding == Decimal("10000.00")
        customer_names = {e.customer_name for e in result.entries}
        assert customer_names == {"CUST-X", "CUST-Y"}

    def test_ar_empty(self):
        """Returns empty entries and zero total when no entries match."""
        inp = GetARSubledgerInput(
            from_date=date(2025, 1, 1),
            to_date=date(2025, 1, 31),
        )
        result = get_ar_subledger(self.session, inp)
        assert len(result.entries) == 0
        assert result.total_outstanding == Decimal("0.00")


class TestGetPayrollLedger:
    """Tests for get_payroll_ledger -- queries payroll_entries table."""

    def setup_method(self):
        engine = create_engine(TEST_DATABASE_URL, echo=False)
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine)
        self.session = SessionLocal()
        self._seed_data()

    def teardown_method(self):
        self.session.close()

    def _seed_data(self):
        entries = [
            PayrollEntry(
                entry_id="PR-001", employee_name="John Doe",
                salary_amount=Decimal("50000.00"), deductions=Decimal("5000.00"),
                net_pay=Decimal("45000.00"),
                period_start=date(2026, 6, 1), period_end=date(2026, 6, 30),
                posted_date=date(2026, 6, 30),
            ),
            PayrollEntry(
                entry_id="PR-002", employee_name="Jane Smith",
                salary_amount=Decimal("60000.00"), deductions=Decimal("8000.00"),
                net_pay=Decimal("52000.00"),
                period_start=date(2026, 6, 1), period_end=date(2026, 6, 30),
                posted_date=date(2026, 6, 30),
            ),
            PayrollEntry(
                entry_id="PR-003", employee_name="Bob Wilson",
                salary_amount=Decimal("30000.00"), deductions=Decimal("35000.00"),
                net_pay=Decimal("-5000.00"),
                period_start=date(2026, 6, 1), period_end=date(2026, 6, 30),
                posted_date=date(2026, 6, 30),
            ),
        ]
        for e in entries:
            self.session.add(e)
        self.session.commit()

    def test_payroll_with_entries(self):
        """Returns all payroll entries with correct aggregate totals."""
        inp = GetPayrollLedgerInput(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
        )
        result = get_payroll_ledger(self.session, inp)
        assert len(result.entries) == 3
        assert result.total_salary == Decimal("140000.00")
        assert result.total_deductions == Decimal("48000.00")
        assert result.total_net_pay == Decimal("92000.00")

    def test_payroll_empty(self):
        """Returns empty entries and zero totals when no entries match."""
        inp = GetPayrollLedgerInput(
            from_date=date(2025, 1, 1),
            to_date=date(2025, 1, 31),
        )
        result = get_payroll_ledger(self.session, inp)
        assert len(result.entries) == 0
        assert result.total_salary == Decimal("0.00")
        assert result.total_deductions == Decimal("0.00")
        assert result.total_net_pay == Decimal("0.00")

    def test_payroll_employee_filter(self):
        """Filters by employee_name, returning only that employee's entries."""
        inp = GetPayrollLedgerInput(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
            employee_name="John Doe",
        )
        result = get_payroll_ledger(self.session, inp)
        assert len(result.entries) == 1
        assert result.entries[0].employee_name == "John Doe"
        assert result.entries[0].salary_amount == Decimal("50000.00")
        assert result.entries[0].deductions == Decimal("5000.00")

    def test_payroll_deduction_warning(self):
        """Flags entries where deductions exceed salary with warning=True."""
        inp = GetPayrollLedgerInput(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
        )
        result = get_payroll_ledger(self.session, inp)
        # Bob Wilson has deductions > salary -> warning should be True
        bob = [e for e in result.entries if e.employee_name == "Bob Wilson"][0]
        assert bob.warning is True
        assert bob.deductions > bob.salary_amount
        # John Doe has normal deductions -> warning should be False
        john = [e for e in result.entries if e.employee_name == "John Doe"][0]
        assert john.warning is False
