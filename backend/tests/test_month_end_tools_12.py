"""Tests for month-end tools 1-2: review_unpaid_bills, calculate_prepaid_adjustment."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from db.models import Base, JournalEntry, Contact, PrepaidExpense
from tools.month_end_tools import review_unpaid_bills, calculate_prepaid_adjustment
from tools.schemas import ReviewUnpaidBillsInput, CalculatePrepaidAdjustmentInput
from tests.test_helpers import TEST_DATABASE_URL

AS_OF = date(2026, 7, 29)


class TestReviewUnpaidBills:
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

    def test_no_unpaid_bills(self):
        """No AP entries -> empty list, zero totals."""
        inp = ReviewUnpaidBillsInput(as_of_date=AS_OF)
        result = review_unpaid_bills(inp, self.session)
        assert result.items == []
        assert result.total_unpaid == Decimal("0")
        assert result.total_overdue == Decimal("0")

    def test_with_unpaid_bills(self):
        """AP entries present -> correctly listed."""
        self.session.add(Contact(contact_id="CNT-V001", contact_name="Abdullah Store", contact_type="vendor"))
        self.session.add(JournalEntry(entry_id="JE-AP-001", description="Bill 1",
            posted_date=date(2026, 6, 15), reference="CNT-V001",
            debit_account="2000-Accounts Payable", debit_amount=Decimal("25000.00"),
            credit_account="6100-Expense", credit_amount=Decimal("25000.00"), status="posted"))
        self.session.add(JournalEntry(entry_id="JE-AP-002", description="Bill 2",
            posted_date=date(2026, 7, 1), reference="CNT-V001",
            debit_account="2000-Accounts Payable", debit_amount=Decimal("15000.00"),
            credit_account="6100-Expense", credit_amount=Decimal("15000.00"), status="posted"))
        self.session.commit()

        inp = ReviewUnpaidBillsInput(as_of_date=AS_OF)
        result = review_unpaid_bills(inp, self.session)
        assert len(result.items) == 2
        assert result.total_unpaid == Decimal("40000.00")
        assert result.items[0].vendor_name == "Abdullah Store"
        assert result.items[0].days_overdue == 44

    def test_all_bills_paid(self):
        """Entries with zero outstanding -> listed as paid."""
        self.session.add(JournalEntry(entry_id="JE-AP-PAID", description="Paid bill",
            posted_date=date(2026, 7, 1), reference=None,
            debit_account="2000-Accounts Payable", debit_amount=Decimal("1000.00"),
            credit_account="1000-Cash", credit_amount=Decimal("1000.00"), status="posted"))
        self.session.commit()
        inp = ReviewUnpaidBillsInput(as_of_date=AS_OF)
        result = review_unpaid_bills(inp, self.session)
        assert len(result.items) == 1

    def test_overdue_90_days_flagged(self):
        """Entry >90 days overdue -> days_overdue > 90."""
        self.session.add(JournalEntry(entry_id="JE-OLD", description="Old bill",
            posted_date=date(2025, 1, 1), reference=None,
            debit_account="2000-Accounts Payable", debit_amount=Decimal("5000.00"),
            credit_account="6100-Expense", credit_amount=Decimal("5000.00"), status="posted"))
        self.session.commit()
        inp = ReviewUnpaidBillsInput(as_of_date=AS_OF)
        result = review_unpaid_bills(inp, self.session)
        assert len(result.items) == 1
        assert result.items[0].days_overdue >= 574


class TestCalculatePrepaidAdjustment:
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

    def test_no_prepaids(self):
        """No active prepaids -> empty list."""
        inp = CalculatePrepaidAdjustmentInput(as_of_date=AS_OF)
        result = calculate_prepaid_adjustment(inp, self.session)
        assert result.items == []
        assert result.total_adjustment == Decimal("0")

    def test_active_prepaid_calculated(self):
        """Active prepaid -> correct monthly adjustment."""
        self.session.add(PrepaidExpense(prepaid_id="PRE-001", description="Insurance",
            total_amount=Decimal("120000.00"), start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31), monthly_amount=Decimal("10000.00"),
            remaining_balance=Decimal("60000.00"), status="active"))
        self.session.commit()
        inp = CalculatePrepaidAdjustmentInput(as_of_date=AS_OF)
        result = calculate_prepaid_adjustment(inp, self.session)
        assert len(result.items) == 1
        assert result.items[0].monthly_amount == Decimal("10000.00")
        assert result.items[0].suggested_adjustment == Decimal("10000.00")

    def test_fully_amortized_prepaid(self):
        """Prepaid with zero remaining balance -> adjustment = 0."""
        self.session.add(PrepaidExpense(prepaid_id="PRE-FULL", description="Done",
            total_amount=Decimal("5000.00"), start_date=date(2025, 1, 1),
            end_date=date(2025, 6, 30), monthly_amount=Decimal("833.33"),
            remaining_balance=Decimal("0"), status="active"))
        self.session.commit()
        inp = CalculatePrepaidAdjustmentInput(as_of_date=AS_OF)
        result = calculate_prepaid_adjustment(inp, self.session)
        # remaining=0 -> suggested_adjustment = min(833.33, 0) = 0
        assert result.items[0].suggested_adjustment == Decimal("0")

    def test_prepaid_filter_by_id(self):
        """Filtering by specific prepaid_id returns only that one."""
        self.session.add(PrepaidExpense(prepaid_id="PRE-A", description="A",
            total_amount=Decimal("6000.00"), start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31), monthly_amount=Decimal("500.00"),
            remaining_balance=Decimal("3000.00"), status="active"))
        self.session.add(PrepaidExpense(prepaid_id="PRE-B", description="B",
            total_amount=Decimal("12000.00"), start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31), monthly_amount=Decimal("1000.00"),
            remaining_balance=Decimal("6000.00"), status="active"))
        self.session.commit()
        inp = CalculatePrepaidAdjustmentInput(as_of_date=AS_OF, prepaid_id="PRE-A")
        result = calculate_prepaid_adjustment(inp, self.session)
        assert len(result.items) == 1
        assert result.items[0].prepaid_id == "PRE-A"

    def test_negative_balance_handled(self):
        """Prepaid with negative balance -> adjustment clamped."""
        self.session.add(PrepaidExpense(prepaid_id="PRE-NEG", description="Neg",
            total_amount=Decimal("1000.00"), start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31), monthly_amount=Decimal("100.00"),
            remaining_balance=Decimal("-500.00"), status="active"))
        self.session.commit()
        inp = CalculatePrepaidAdjustmentInput(as_of_date=AS_OF)
        result = calculate_prepaid_adjustment(inp, self.session)
        assert result.items[0].suggested_adjustment == Decimal("0")
