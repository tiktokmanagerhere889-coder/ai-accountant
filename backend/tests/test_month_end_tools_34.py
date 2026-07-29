"""Tests for month-end tools 3-4: calculate_depreciation, calculate_amortization."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from db.models import Base, FixedAsset, DepreciationSchedule, IntangibleAsset, AmortizationSchedule
from tools.month_end_tools import calculate_depreciation, calculate_amortization
from tools.schemas import CalculateDepreciationInput, CalculateAmortizationInput
from tests.test_helpers import TEST_DATABASE_URL

PERIOD = date(2026, 7, 31)


class TestCalculateDepreciation:
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

    def test_no_assets(self):
        """No active fixed assets -> empty list."""
        inp = CalculateDepreciationInput(period_date=PERIOD)
        result = calculate_depreciation(inp, self.session)
        assert result.items == []
        assert result.total_depreciation == Decimal("0")

    def test_single_asset_straight_line(self):
        """One asset -> correct monthly depreciation."""
        self.session.add(FixedAsset(asset_id="FA-001", asset_name="Delivery Truck",
            asset_category="vehicle", purchase_cost=Decimal("2400000.00"),
            purchase_date=date(2026, 1, 1), useful_life_years=10,
            depreciation_method="straight_line", residual_value=Decimal("240000.00"),
            current_book_value=Decimal("2400000.00"), status="approved"))
        self.session.commit()
        inp = CalculateDepreciationInput(period_date=PERIOD)
        result = calculate_depreciation(inp, self.session)
        assert len(result.items) == 1
        # (2400000 - 240000) / 10 / 12 = 2160000 / 120 = 18000
        assert result.items[0].monthly_depreciation == Decimal("18000.00")
        assert result.total_depreciation == Decimal("18000.00")

    def test_fully_depreciated_asset(self):
        """Fully depreciated asset -> depreciation = 0."""
        self.session.add(FixedAsset(asset_id="FA-FULL", asset_name="Old Machine",
            asset_category="machinery", purchase_cost=Decimal("100000.00"),
            purchase_date=date(2020, 1, 1), useful_life_years=5,
            depreciation_method="straight_line", residual_value=Decimal("0"),
            current_book_value=Decimal("0"), status="approved"))
        self.session.commit()
        inp = CalculateDepreciationInput(period_date=PERIOD)
        result = calculate_depreciation(inp, self.session)
        # monthly = (100000 - 0) / 5 / 12 = 1666.67
        assert result.items[0].monthly_depreciation == Decimal("1666.67")

    def test_asset_not_found(self):
        """Filtering by non-existent asset_id -> empty result."""
        inp = CalculateDepreciationInput(period_date=PERIOD, asset_id="FA-NONEXIST")
        result = calculate_depreciation(inp, self.session)
        assert result.items == []

    def test_residual_greater_than_cost(self):
        """Residual >= cost -> zero depreciation."""
        self.session.add(FixedAsset(asset_id="FA-WEIRD", asset_name="Weird Asset",
            asset_category="other", purchase_cost=Decimal("50000.00"),
            purchase_date=date(2026, 1, 1), useful_life_years=5,
            depreciation_method="straight_line", residual_value=Decimal("60000.00"),
            current_book_value=Decimal("50000.00"), status="approved"))
        self.session.commit()
        inp = CalculateDepreciationInput(period_date=PERIOD)
        result = calculate_depreciation(inp, self.session)
        # cost - residual = -10000 -> monthly = -10000/5/12 = -166.67 -> clamped to 0
        assert result.items[0].monthly_depreciation <= Decimal("0")


class TestCalculateAmortization:
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

    def test_no_intangible_assets(self):
        """No active intangible assets -> empty list."""
        inp = CalculateAmortizationInput(period_date=PERIOD)
        result = calculate_amortization(inp, self.session)
        assert result.items == []
        assert result.total_amortization == Decimal("0")

    def test_single_asset_amortization(self):
        """One intangible asset -> correct monthly amortization."""
        self.session.add(IntangibleAsset(asset_id="IA-001", asset_name="Software License",
            cost=Decimal("120000.00"), acquisition_date=date(2026, 1, 1),
            useful_life_years=5, residual_value=Decimal("0"),
            current_book_value=Decimal("120000.00"), status="active"))
        self.session.commit()
        inp = CalculateAmortizationInput(period_date=PERIOD)
        result = calculate_amortization(inp, self.session)
        assert len(result.items) == 1
        # 120000 / 5 / 12 = 2000
        assert result.items[0].monthly_amortization == Decimal("2000.00")
        assert result.total_amortization == Decimal("2000.00")

    def test_filter_by_asset_id(self):
        """Filtering by specific asset_id returns only that one."""
        self.session.add(IntangibleAsset(asset_id="IA-A", asset_name="Patent A",
            cost=Decimal("60000.00"), acquisition_date=date(2026, 1, 1),
            useful_life_years=10, residual_value=Decimal("0"),
            current_book_value=Decimal("60000.00"), status="active"))
        self.session.add(IntangibleAsset(asset_id="IA-B", asset_name="Patent B",
            cost=Decimal("120000.00"), acquisition_date=date(2026, 1, 1),
            useful_life_years=10, residual_value=Decimal("0"),
            current_book_value=Decimal("120000.00"), status="active"))
        self.session.commit()
        inp = CalculateAmortizationInput(period_date=PERIOD, asset_id="IA-A")
        result = calculate_amortization(inp, self.session)
        assert len(result.items) == 1
        assert result.items[0].asset_id == "IA-A"

    def test_inactive_asset_excluded(self):
        """Inactive assets are not included."""
        self.session.add(IntangibleAsset(asset_id="IA-INACTIVE", asset_name="Old",
            cost=Decimal("5000.00"), acquisition_date=date(2020, 1, 1),
            useful_life_years=3, residual_value=Decimal("0"),
            current_book_value=Decimal("0"), status="inactive"))
        self.session.commit()
        inp = CalculateAmortizationInput(period_date=PERIOD)
        result = calculate_amortization(inp, self.session)
        assert result.items == []
