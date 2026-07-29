"""Tests for month-end tool 10: forecast_cash_flow."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from db.models import Base, JournalEntry
from tools.month_end_tools import forecast_cash_flow
from tools.schemas import ForecastCashFlowInput
from tests.test_helpers import TEST_DATABASE_URL

TODAY = date.today()


class TestForecastCashFlow:
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

    def test_no_history_low_confidence(self):
        """No journal entries -> zero averages, low confidence."""
        inp = ForecastCashFlowInput(forecast_days=30, starting_balance=Decimal("0"))
        result = forecast_cash_flow(inp, self.session)
        assert len(result.projections) == 30
        assert result.confidence == "low"
        assert result.net_monthly_average == Decimal("0")

    def test_with_history_high_confidence(self):
        """3+ months of history with activity -> high confidence."""
        for i in range(90):
            d = TODAY - timedelta(days=90 - i)
            self.session.add(JournalEntry(
                entry_id=f"JE-CF-{i:03d}", description=f"Entry {i}",
                posted_date=d, reference=None,
                debit_account="1000-Cash", debit_amount=Decimal("1000.00"),
                credit_account="4000-Revenue", credit_amount=Decimal("1000.00"),
                status="posted"))
        self.session.commit()
        inp = ForecastCashFlowInput(forecast_days=30, starting_balance=Decimal("50000.00"))
        result = forecast_cash_flow(inp, self.session)
        assert result.confidence == "high"
        assert len(result.projections) == 30

    def test_forecast_days_60(self):
        """60-day forecast returns 60 projections."""
        inp = ForecastCashFlowInput(forecast_days=60, starting_balance=Decimal("0"))
        result = forecast_cash_flow(inp, self.session)
        assert len(result.projections) == 60

    def test_forecast_days_90(self):
        """90-day forecast returns 90 projections."""
        inp = ForecastCashFlowInput(forecast_days=90, starting_balance=Decimal("100000.00"))
        result = forecast_cash_flow(inp, self.session)
        assert len(result.projections) == 90

    def test_needs_approval(self):
        """Output has needs_approval=True."""
        inp = ForecastCashFlowInput(forecast_days=30, starting_balance=Decimal("0"))
        result = forecast_cash_flow(inp, self.session)
        assert result.needs_approval is True
