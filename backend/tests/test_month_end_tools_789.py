"""Tests for month-end tools 7-8-9: get_ap_aging_report, analyze_budget_variance, get_loan_debt_schedule."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from db.models import Base, JournalEntry, Contact, Budget, Loan, LoanPaymentSchedule
from tools.month_end_tools import get_ap_aging_report, analyze_budget_variance, get_loan_debt_schedule
from tools.schemas import GetAPAgingReportInput, AnalyzeBudgetVarianceInput, GetLoanDebtScheduleInput
from tests.test_helpers import TEST_DATABASE_URL

AS_OF = date(2026, 7, 29)


class TestGetAPAgingReport:
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

    def test_no_ap_entries(self):
        inp = GetAPAgingReportInput(as_of_date=AS_OF)
        result = get_ap_aging_report(inp, self.session)
        assert result.buckets == []
        assert result.grand_total == Decimal("0")

    def test_with_ap_entries(self):
        self.session.add(Contact(contact_id="CNT-V001", contact_name="Abdullah Store", contact_type="vendor"))
        self.session.add(JournalEntry(entry_id="JE-AP-AGING-1", description="Bill",
            posted_date=date(2026, 7, 1), reference="CNT-V001",
            debit_account="2000-Accounts Payable", debit_amount=Decimal("30000.00"),
            credit_account="6100-Expense", credit_amount=Decimal("30000.00"), status="posted"))
        self.session.commit()
        inp = GetAPAgingReportInput(as_of_date=AS_OF)
        result = get_ap_aging_report(inp, self.session)
        assert len(result.buckets) == 1
        assert result.buckets[0].vendor_name == "Abdullah Store"
        assert result.grand_total == Decimal("30000.00")

    def test_vendor_filter(self):
        self.session.add(Contact(contact_id="CNT-VA", contact_name="Vendor A", contact_type="vendor"))
        self.session.add(JournalEntry(entry_id="JE-AP-V1", description="V1",
            posted_date=date(2026, 7, 1), reference="CNT-VA",
            debit_account="2000-Accounts Payable", debit_amount=Decimal("10000.00"),
            credit_account="6100-Expense", credit_amount=Decimal("10000.00"), status="posted"))
        self.session.commit()
        inp = GetAPAgingReportInput(as_of_date=AS_OF, vendor_contact_id="CNT-VA")
        result = get_ap_aging_report(inp, self.session)
        assert len(result.buckets) == 1


class TestAnalyzeBudgetVariance:
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

    def test_no_budget_raises(self):
        inp = AnalyzeBudgetVarianceInput(fiscal_year=2026, period=7)
        try:
            analyze_budget_variance(inp, self.session)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "No budgets found" in str(e)

    def test_on_budget(self):
        self.session.add(Budget(budget_id="BDG-001", fiscal_year=2026, period=7,
            account_code="6000", budget_amount=Decimal("50000.00")))
        self.session.commit()
        inp = AnalyzeBudgetVarianceInput(fiscal_year=2026, period=7)
        result = analyze_budget_variance(inp, self.session)
        assert len(result.items) == 1
        assert result.items[0].variance == Decimal("-50000.00")  # actual 0 - budget 50000
        assert result.items[0].flagged is True

    def test_budget_with_actuals(self):
        self.session.add(Budget(budget_id="BDG-002", fiscal_year=2026, period=7,
            account_code="6000", budget_amount=Decimal("100000.00")))
        self.session.add(JournalEntry(entry_id="JE-BV-1", description="Expense",
            posted_date=date(2026, 7, 15), reference=None,
            debit_account="6000-Office Rent", debit_amount=Decimal("80000.00"),
            credit_account="1000-Cash", credit_amount=Decimal("80000.00"), status="posted"))
        self.session.commit()
        inp = AnalyzeBudgetVarianceInput(fiscal_year=2026, period=7)
        result = analyze_budget_variance(inp, self.session)
        assert result.total_actual == Decimal("80000.00")
        assert result.total_budget == Decimal("100000.00")
        assert result.total_variance == Decimal("-20000.00")

    def test_zero_budget_no_division_by_zero(self):
        self.session.add(Budget(budget_id="BDG-ZERO", fiscal_year=2026, period=7,
            account_code="6000", budget_amount=Decimal("0")))
        self.session.commit()
        inp = AnalyzeBudgetVarianceInput(fiscal_year=2026, period=7)
        result = analyze_budget_variance(inp, self.session)
        assert result.items[0].variance_pct == Decimal("0")

    def test_prefix_filter(self):
        self.session.add(Budget(budget_id="BDG-P1", fiscal_year=2026, period=7,
            account_code="6000", budget_amount=Decimal("10000.00")))
        self.session.add(Budget(budget_id="BDG-P2", fiscal_year=2026, period=7,
            account_code="7000", budget_amount=Decimal("20000.00")))
        self.session.commit()
        inp = AnalyzeBudgetVarianceInput(fiscal_year=2026, period=7, account_code_prefix="6000")
        result = analyze_budget_variance(inp, self.session)
        assert len(result.items) == 1
        assert result.items[0].account_code == "6000"


class TestGetLoanDebtSchedule:
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

    def test_loan_not_found(self):
        inp = GetLoanDebtScheduleInput(loan_id="LN-NONEXIST")
        try:
            get_loan_debt_schedule(inp, self.session)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "not found" in str(e)

    def test_loan_with_interest(self):
        self.session.add(Loan(loan_id="LN-001", loan_name="Business Loan",
            principal_amount=Decimal("1000000.00"), interest_rate=Decimal("12"),
            term_months=12, start_date=date(2026, 1, 1), status="active"))
        self.session.commit()
        inp = GetLoanDebtScheduleInput(loan_id="LN-001")
        result = get_loan_debt_schedule(inp, self.session)
        assert result.loan_id == "LN-001"
        assert len(result.schedule) == 12
        assert result.source == "computed"
        assert result.total_interest > Decimal("0")

    def test_zero_interest_loan(self):
        self.session.add(Loan(loan_id="LN-ZERO", loan_name="Zero Interest Loan",
            principal_amount=Decimal("120000.00"), interest_rate=Decimal("0"),
            term_months=12, start_date=date(2026, 1, 1), status="active"))
        self.session.commit()
        inp = GetLoanDebtScheduleInput(loan_id="LN-ZERO")
        result = get_loan_debt_schedule(inp, self.session)
        assert len(result.schedule) == 12
        assert result.total_interest == Decimal("0")

    def test_single_period_loan(self):
        self.session.add(Loan(loan_id="LN-1M", loan_name="Single Month",
            principal_amount=Decimal("50000.00"), interest_rate=Decimal("10"),
            term_months=1, start_date=date(2026, 7, 1), status="active"))
        self.session.commit()
        inp = GetLoanDebtScheduleInput(loan_id="LN-1M")
        result = get_loan_debt_schedule(inp, self.session)
        assert len(result.schedule) == 1
