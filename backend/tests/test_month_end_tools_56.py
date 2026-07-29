"""Tests for month-end tools 5-6: reconcile_payroll, get_ar_aging_report."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from db.models import Base, PayrollEntry, JournalEntry, Contact
from tools.month_end_tools import reconcile_payroll, get_ar_aging_report
from tools.schemas import ReconcilePayrollInput, GetARAgingReportInput
from tests.test_helpers import TEST_DATABASE_URL

AS_OF = date(2026, 7, 29)


class TestReconcilePayroll:
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

    def test_no_payroll_entries(self):
        """No payroll for period -> empty list."""
        inp = ReconcilePayrollInput(from_date=date(2026, 1, 1), to_date=date(2026, 1, 31))
        result = reconcile_payroll(inp, self.session)
        assert result.items == []
        assert result.total_salary == Decimal("0")

    def test_payroll_with_discrepancy(self):
        """Payroll entry where salary - deductions != net -> flagged."""
        self.session.add(PayrollEntry(entry_id="PR-001", employee_name="Ali",
            salary_amount=Decimal("100000.00"), deductions=Decimal("15000.00"),
            net_pay=Decimal("80000.00"),
            period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
            posted_date=date(2026, 7, 28)))
        self.session.commit()
        inp = ReconcilePayrollInput(from_date=date(2026, 7, 1), to_date=date(2026, 7, 31))
        result = reconcile_payroll(inp, self.session)
        assert len(result.items) == 1
        assert result.discrepancies >= 1
        assert result.items[0].discrepancy is not None

    def test_payroll_perfect_match(self):
        """Payroll where salary - deductions == net -> no discrepancy."""
        self.session.add(PayrollEntry(entry_id="PR-002", employee_name="Sara",
            salary_amount=Decimal("100000.00"), deductions=Decimal("15000.00"),
            net_pay=Decimal("85000.00"),
            period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
            posted_date=date(2026, 7, 28)))
        self.session.commit()
        inp = ReconcilePayrollInput(from_date=date(2026, 7, 1), to_date=date(2026, 7, 31))
        result = reconcile_payroll(inp, self.session)
        assert len(result.items) == 1
        assert result.items[0].discrepancy is None

    def test_employee_filter(self):
        """Filtering by employee returns only matching entries."""
        self.session.add(PayrollEntry(entry_id="PR-A", employee_name="Ali Khan",
            salary_amount=Decimal("100000.00"), deductions=Decimal("15000.00"),
            net_pay=Decimal("85000.00"),
            period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
            posted_date=date(2026, 7, 28)))
        self.session.add(PayrollEntry(entry_id="PR-B", employee_name="Sara Ali",
            salary_amount=Decimal("50000.00"), deductions=Decimal("5000.00"),
            net_pay=Decimal("45000.00"),
            period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
            posted_date=date(2026, 7, 28)))
        self.session.commit()
        inp = ReconcilePayrollInput(from_date=date(2026, 7, 1), to_date=date(2026, 7, 31), employee_name="Ali")
        result = reconcile_payroll(inp, self.session)
        assert len(result.items) == 2  # Both have "Ali" in name

    def test_no_gl_entries(self):
        """No GL salary entries -> still returns payroll data."""
        self.session.add(PayrollEntry(entry_id="PR-NOGL", employee_name="Test",
            salary_amount=Decimal("50000.00"), deductions=Decimal("0"),
            net_pay=Decimal("50000.00"),
            period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
            posted_date=date(2026, 7, 28)))
        self.session.commit()
        inp = ReconcilePayrollInput(from_date=date(2026, 7, 1), to_date=date(2026, 7, 31))
        result = reconcile_payroll(inp, self.session)
        assert len(result.items) == 1


class TestGetARAgingReport:
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

    def test_no_ar_entries(self):
        """No AR entries -> empty buckets, zero total."""
        inp = GetARAgingReportInput(as_of_date=AS_OF)
        result = get_ar_aging_report(inp, self.session)
        assert result.buckets == []
        assert result.customer_details == []
        assert result.total_outstanding == Decimal("0")

    def test_with_ar_entries(self):
        """AR entries present -> correct aging buckets."""
        self.session.add(Contact(contact_id="CNT-C001", contact_name="ABC Trading", contact_type="customer"))
        self.session.add(JournalEntry(entry_id="JE-AR-001", description="Invoice 1",
            posted_date=date(2026, 7, 1), reference="CNT-C001",
            debit_account="1200-Accounts Receivable", debit_amount=Decimal("100000.00"),
            credit_account="4000-Revenue", credit_amount=Decimal("100000.00"), status="posted"))
        self.session.add(JournalEntry(entry_id="JE-AR-002", description="Invoice 2",
            posted_date=date(2026, 5, 1), reference="CNT-C001",
            debit_account="1200-Accounts Receivable", debit_amount=Decimal("50000.00"),
            credit_account="4000-Revenue", credit_amount=Decimal("50000.00"), status="posted"))
        self.session.commit()
        inp = GetARAgingReportInput(as_of_date=AS_OF)
        result = get_ar_aging_report(inp, self.session)
        assert len(result.customer_details) == 1
        assert result.total_outstanding == Decimal("150000.00")
        # 28 days old -> current (0-30)
        # 89 days old -> past_60 (61-90)
        assert result.customer_details[0].current == Decimal("100000.00")
        assert result.customer_details[0].past_60 == Decimal("50000.00")

    def test_multiple_customers(self):
        """Multiple customers -> separate details."""
        self.session.add(JournalEntry(entry_id="JE-AR-M1", description="Inv A",
            posted_date=date(2026, 7, 1), reference="CUST-A",
            debit_account="1200-Accounts Receivable", debit_amount=Decimal("50000.00"),
            credit_account="4000-Revenue", credit_amount=Decimal("50000.00"), status="posted"))
        self.session.add(JournalEntry(entry_id="JE-AR-M2", description="Inv B",
            posted_date=date(2026, 7, 1), reference="CUST-B",
            debit_account="1200-Accounts Receivable", debit_amount=Decimal("75000.00"),
            credit_account="4000-Revenue", credit_amount=Decimal("75000.00"), status="posted"))
        self.session.commit()
        inp = GetARAgingReportInput(as_of_date=AS_OF)
        result = get_ar_aging_report(inp, self.session)
        assert len(result.customer_details) == 2

    def test_no_reference_unknown_customer(self):
        """Entry with no reference -> handled gracefully."""
        self.session.add(JournalEntry(entry_id="JE-AR-NOREF", description="No ref",
            posted_date=date(2026, 6, 1), reference=None,
            debit_account="1200-Accounts Receivable", debit_amount=Decimal("10000.00"),
            credit_account="4000-Revenue", credit_amount=Decimal("10000.00"), status="posted"))
        self.session.commit()
        inp = GetARAgingReportInput(as_of_date=AS_OF)
        result = get_ar_aging_report(inp, self.session)
        assert len(result.customer_details) == 1
