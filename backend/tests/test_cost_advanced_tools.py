"""Tests for Cost, Advanced Accounting & Budgeting tools (Agent 6).

Tests all 8 tools with PostgreSQL isolation per test class.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, timedelta, datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from db.models import Base, JournalEntry, Contact, ExchangeRate, Budget
from tools.cost_advanced_tools import (
    calculate_breakeven, convert_foreign_currency, prepare_budget_forecast,
    calculate_standard_costing_variance, allocate_overhead_cost,
    calculate_revenue_recognition, flag_provision_contingent_liability,
    flag_related_party_transaction,
)
from unittest.mock import patch
from tools.schemas import (
    CalculateBreakevenInput, CalculateBreakevenOutput,
    ConvertForeignCurrencyInput, ConvertForeignCurrencyOutput,
    PrepareBudgetForecastInput, PrepareBudgetForecastOutput,
    CalculateStandardCostingVarianceInput, CalculateStandardCostingVarianceOutput,
    AllocateOverheadCostInput, AllocateOverheadCostOutput, AllocationPoolItem,
    CalculateRevenueRecognitionInput, CalculateRevenueRecognitionOutput,
    FlagProvisionContingentLiabilityInput, FlagProvisionContingentLiabilityOutput,
    FlagRelatedPartyTransactionInput, FlagRelatedPartyTransactionOutput,
)
from tests.test_helpers import TEST_DATABASE_URL


def _seed_rate_data(session: Session):
    """Seed exchange rate records with stale fetched_at (10 days ago)."""
    stale = datetime.utcnow() - timedelta(days=10)
    session.add(ExchangeRate(from_currency="USD", to_currency="PKR", rate=Decimal("278.50"), rate_date=date(2026, 7, 1), source="SBP", fetched_at=stale))
    session.add(ExchangeRate(from_currency="USD", to_currency="PKR", rate=Decimal("279.00"), rate_date=date(2026, 7, 15), source="SBP", fetched_at=stale))
    session.add(ExchangeRate(from_currency="USD", to_currency="PKR", rate=Decimal("280.00"), rate_date=date(2026, 7, 25), source="SBP", fetched_at=stale))
    session.add(ExchangeRate(from_currency="EUR", to_currency="PKR", rate=Decimal("300.00"), rate_date=date(2026, 7, 1), source="SBP", fetched_at=stale))
    session.commit()


def _seed_historical_data(session: Session):
    """Seed journal entries with 12+ months of history for budget forecast."""
    for m in range(1, 13):
        session.add(JournalEntry(
            entry_id=f"HIST-{m:04d}", description=f"Rent month {m}",
            posted_date=date(2026, m, 1), reference=None,
            debit_account="6000-Rent Expense", debit_amount=Decimal("50000.00"),
            credit_account="1000-Cash", credit_amount=Decimal("50000.00"),
            status="posted",
        ))
        session.add(JournalEntry(
            entry_id=f"HIST-SAL-{m:04d}", description=f"Salary month {m}",
            posted_date=date(2026, m, 15), reference=None,
            debit_account="6100-Salary Expense", debit_amount=Decimal("120000.00"),
            credit_account="1000-Cash", credit_amount=Decimal("120000.00"),
            status="posted",
        ))
    # Revenue entries
    session.add(JournalEntry(
        entry_id="HIST-REV-001", description="Sales Jan",
        posted_date=date(2026, 1, 31), reference="INV-001",
        debit_account="1000-Cash", debit_amount=Decimal("200000.00"),
        credit_account="4000-Sales Revenue", credit_amount=Decimal("200000.00"),
        status="posted",
    ))
    session.add(JournalEntry(
        entry_id="HIST-REV-002", description="Sales Feb",
        posted_date=date(2026, 2, 28), reference="INV-002",
        debit_account="1000-Cash", debit_amount=Decimal("180000.00"),
        credit_account="4000-Sales Revenue", credit_amount=Decimal("180000.00"),
        status="posted",
    ))
    session.commit()


def _seed_contact_data(session: Session):
    """Seed contacts for related-party testing."""
    session.add(Contact(
        contact_id="CNT-RP-001", contact_name="Abdullah Traders",
        contact_type="vendor", phone="0300-1111111",
        related_party=True,
    ))
    session.add(Contact(
        contact_id="CNT-NRP-002", contact_name="General Suppliers",
        contact_type="vendor", phone="0300-2222222",
        related_party=False,
    ))
    session.add(Contact(
        contact_id="CNT-CUST-001", contact_name="Premium Client",
        contact_type="customer", phone="0300-3333333",
        related_party=False,
    ))
    session.commit()


def _seed_rp_journal_entries(session: Session):
    """Seed journal entries with contact_id and reference for related-party testing."""
    # Entry with contact_id (reliable match)
    session.add(JournalEntry(
        entry_id="JE-RP-001", description="Payment to Abdullah Traders",
        posted_date=date(2026, 7, 1), reference="INV-100",
        contact_id="CNT-RP-001",
        debit_account="6300-Office Supplies", debit_amount=Decimal("50000.00"),
        credit_account="1000-Cash", credit_amount=Decimal("50000.00"),
        status="posted",
    ))
    # Entry with reference fallback (contact_id match)
    session.add(JournalEntry(
        entry_id="JE-RP-002", description="Payment to General Suppliers",
        posted_date=date(2026, 7, 15), reference="CNT-NRP-002",
        debit_account="6100-Salary Expense", debit_amount=Decimal("30000.00"),
        credit_account="1000-Cash", credit_amount=Decimal("30000.00"),
        status="posted",
    ))
    # Entry with no contact match at all
    session.add(JournalEntry(
        entry_id="JE-RP-003", description="Payment to Unknown Vendor",
        posted_date=date(2026, 7, 20), reference="INV-999",
        debit_account="6300-Office Supplies", debit_amount=Decimal("10000.00"),
        credit_account="1000-Cash", credit_amount=Decimal("10000.00"),
        status="posted",
    ))
    session.commit()


# ===========================================================================
# Tool 1: Calculate Breakeven
# ===========================================================================
class TestCalculateBreakeven:
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

    def test_breakeven_normal(self):
        """Fixed cost 500000, VC 300, price 500 -> 2500 units."""
        inp = CalculateBreakevenInput(
            fixed_cost=Decimal("500000"),
            variable_cost_per_unit=Decimal("300"),
            selling_price_per_unit=Decimal("500"),
        )
        r = calculate_breakeven(inp, self.session)
        assert r.breakeven_units == Decimal("2500")
        assert r.breakeven_revenue == Decimal("1250000")
        assert r.contribution_margin_per_unit == Decimal("200")
        assert r.formula_used != ""

    def test_breakeven_zero_fixed_cost(self):
        """Zero fixed cost -> breakeven is 0."""
        inp = CalculateBreakevenInput(
            fixed_cost=Decimal("0"),
            variable_cost_per_unit=Decimal("100"),
            selling_price_per_unit=Decimal("200"),
        )
        r = calculate_breakeven(inp, self.session)
        assert r.breakeven_units == Decimal("0")
        assert r.breakeven_revenue == Decimal("0")

    def test_breakeven_price_equals_variable_cost_raises(self):
        """selling_price <= variable_cost raises ValueError."""
        inp = CalculateBreakevenInput(
            fixed_cost=Decimal("50000"),
            variable_cost_per_unit=Decimal("100"),
            selling_price_per_unit=Decimal("100"),
        )
        try:
            calculate_breakeven(inp, self.session)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "exceed" in str(e).lower()


# ===========================================================================
# Tool 2: Convert Foreign Currency
# ===========================================================================
class TestConvertForeignCurrency:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_rate_data(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_convert_normal(self):
        """1000 USD to PKR with latest cached rate (280.00)."""
        inp = ConvertForeignCurrencyInput(
            amount=Decimal("1000"),
            from_currency="USD",
            to_currency="PKR",
        )
        with patch("tools.cost_advanced_tools._fetch_live_rate", return_value=None):
            r = convert_foreign_currency(inp, self.session)
        # Stale cached rate (10 days old) used with warning
        assert r.conversion_rate == Decimal("280.00")
        assert r.converted_amount == Decimal("280000.00")
        assert r.rate_date == date(2026, 7, 25)

    def test_convert_same_currency(self):
        """USD to USD -> rate=1, no change."""
        inp = ConvertForeignCurrencyInput(
            amount=Decimal("1000"),
            from_currency="USD",
            to_currency="USD",
        )
        r = convert_foreign_currency(inp, self.session)
        assert r.conversion_rate == Decimal("1.0")
        assert r.converted_amount == Decimal("1000")
        assert r.rate_source == "same_currency"

    def test_convert_no_rate_found(self):
        """Unknown pair, no live rate -> 1:1 fallback with warning."""
        inp = ConvertForeignCurrencyInput(
            amount=Decimal("1000"),
            from_currency="GBP",
            to_currency="PKR",
        )
        with patch("tools.cost_advanced_tools._fetch_live_rate", return_value=None):
            r = convert_foreign_currency(inp, self.session)
        assert r.conversion_rate == Decimal("1.0")
        assert r.converted_amount == Decimal("1000")
        assert r.warning is not None

    def test_convert_specific_date(self):
        """Use rate on or before the specific date (nearest backward)."""
        inp = ConvertForeignCurrencyInput(
            amount=Decimal("100"),
            from_currency="USD",
            to_currency="PKR",
            rate_date=date(2026, 7, 10),
        )
        with patch("tools.cost_advanced_tools._fetch_live_rate", return_value=None):
            r = convert_foreign_currency(inp, self.session)
        assert r.conversion_rate == Decimal("278.50")
        assert r.converted_amount == Decimal("27850.00")

    def test_convert_stale_rate_warning(self):
        """Stale cached rate with requested future date -> stale warning."""
        inp = ConvertForeignCurrencyInput(
            amount=Decimal("100"),
            from_currency="USD",
            to_currency="PKR",
            rate_date=date(2026, 8, 28),
        )
        with patch("tools.cost_advanced_tools._fetch_live_rate", return_value=None):
            r = convert_foreign_currency(inp, self.session)
        assert r.warning is not None
        assert "stale" in r.warning.lower()

    def test_convert_live_rate_primary_success(self):
        """Live API (primary) returns a rate -> used and saved to cache."""
        inp = ConvertForeignCurrencyInput(
            amount=Decimal("1000"),
            from_currency="GBP",
            to_currency="PKR",
        )
        live_rate = (Decimal("200.00"), date(2026, 8, 8))
        with patch("tools.cost_advanced_tools._fetch_live_rate", return_value=live_rate):
            r = convert_foreign_currency(inp, self.session)
        assert r.conversion_rate == Decimal("200.00")
        assert r.converted_amount == Decimal("200000.00")
        assert r.rate_source == "open.er-api.com / exchangerate-api.com"
        assert r.warning is None


# ===========================================================================
# Tool 3: Prepare Budget Forecast
# ===========================================================================
class TestPrepareBudgetForecast:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_historical_data(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_forecast_normal(self):
        """12 months of data -> high confidence forecast."""
        inp = PrepareBudgetForecastInput(fiscal_year=2027, periods=12)
        r = prepare_budget_forecast(inp, self.session)
        assert len(r.forecast_items) > 0
        assert r.confidence == "high"
        assert r.data_months >= 12
        assert r.total_forecast > Decimal("0")

    def test_forecast_empty(self):
        """No matching data -> empty items, low confidence."""
        inp = PrepareBudgetForecastInput(
            fiscal_year=2027, periods=12,
            account_code_prefix="9999",  # non-matching prefix
        )
        r = prepare_budget_forecast(inp, self.session)
        assert r.confidence == "low"
        assert r.total_forecast == Decimal("0")
        assert len(r.forecast_items) == 0

    def test_forecast_with_prefix(self):
        """Prefix filter narrows results."""
        inp = PrepareBudgetForecastInput(
            fiscal_year=2027, periods=6,
            account_code_prefix="6000",
        )
        r = prepare_budget_forecast(inp, self.session)
        for item in r.forecast_items:
            assert "6000" in item.account_code


# ===========================================================================
# Tool 4: Calculate Standard Costing Variance
# ===========================================================================
class TestCalculateStandardCostingVariance:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        # Seed actual expense data for period 7, FY 2026
        self.session.add(JournalEntry(
            entry_id="VAR-001", description="Rent July",
            posted_date=date(2026, 7, 1), reference=None,
            debit_account="6000-Rent Expense", debit_amount=Decimal("55000.00"),
            credit_account="1000-Cash", credit_amount=Decimal("55000.00"),
            status="posted",
        ))
        self.session.commit()

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_variance_unfavorable(self):
        """Actual 55000 vs standard 50000 -> unfavorable 5000."""
        inp = CalculateStandardCostingVarianceInput(
            account_code="6000", period=7, fiscal_year=2026,
            standard_cost=Decimal("50000"),
        )
        r = calculate_standard_costing_variance(inp, self.session)
        assert r.actual_cost == Decimal("55000.00")
        assert r.cost_variance == Decimal("5000.00")
        assert r.variance_pct == Decimal("10.00")
        assert "unfavorable" in r.explanation.lower()
        assert r.needs_approval is True

    def test_variance_favorable(self):
        """Actual 45000 vs standard 50000 -> favorable -5000."""
        inp = CalculateStandardCostingVarianceInput(
            account_code="6000", period=7, fiscal_year=2026,
            standard_cost=Decimal("60000"),
        )
        r = calculate_standard_costing_variance(inp, self.session)
        assert r.cost_variance == Decimal("-5000.00")
        assert r.variance_pct == Decimal("-8.33")
        assert "favorable" in r.explanation.lower()

    def test_variance_no_actuals(self):
        """No actuals -> actual=0, full standard as variance."""
        inp = CalculateStandardCostingVarianceInput(
            account_code="9999", period=7, fiscal_year=2026,
            standard_cost=Decimal("10000"),
        )
        r = calculate_standard_costing_variance(inp, self.session)
        assert r.actual_cost == Decimal("0")
        assert r.cost_variance == Decimal("-10000.00")

    def test_variance_with_quantity(self):
        """Quantity variance included when standard_quantity provided."""
        inp = CalculateStandardCostingVarianceInput(
            account_code="6000", period=7, fiscal_year=2026,
            standard_cost=Decimal("50000"),
            standard_quantity=Decimal("2"),
        )
        r = calculate_standard_costing_variance(inp, self.session)
        assert r.quantity_variance is not None
        assert r.actual_quantity is not None


# ===========================================================================
# Tool 5: Allocate Overhead Cost
# ===========================================================================
class TestAllocateOverheadCost:
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

    def test_overhead_split_normal(self):
        """3 departments by headcount: 10+25+15=50 total."""
        inp = AllocateOverheadCostInput(
            total_overhead=Decimal("100000"),
            allocation_basis="headcount",
            allocation_pool=[
                AllocationPoolItem(name="Sales", value=Decimal("10")),
                AllocationPoolItem(name="Engineering", value=Decimal("25")),
                AllocationPoolItem(name="Support", value=Decimal("15")),
            ],
            period=7, fiscal_year=2026,
        )
        r = allocate_overhead_cost(inp, self.session)
        assert len(r.allocations) == 3
        assert r.total_allocated == Decimal("100000")
        # Sales: 10/50 = 20% -> 20000
        assert r.allocations[0].percentage == 20.0
        assert r.allocations[0].allocated_amount == Decimal("20000.00")
        # Engineering: 25/50 = 50% -> 50000
        assert r.allocations[1].percentage == 50.0
        assert r.allocations[1].allocated_amount == Decimal("50000.00")

    def test_overhead_single_department(self):
        """Single department -> 100% allocation."""
        inp = AllocateOverheadCostInput(
            total_overhead=Decimal("50000"),
            allocation_basis="sq_ft",
            allocation_pool=[
                AllocationPoolItem(name="Factory", value=Decimal("10000")),
            ],
            period=7, fiscal_year=2026,
        )
        r = allocate_overhead_cost(inp, self.session)
        assert len(r.allocations) == 1
        assert r.allocations[0].percentage == 100.0
        assert r.allocations[0].allocated_amount == Decimal("50000.00")

    def test_overhead_zero_basis_raises(self):
        """Allocation values sum to zero -> raises ValueError."""
        inp = AllocateOverheadCostInput(
            total_overhead=Decimal("100000"),
            allocation_basis="headcount",
            allocation_pool=[
                AllocationPoolItem(name="Dept A", value=Decimal("0")),
                AllocationPoolItem(name="Dept B", value=Decimal("0")),
            ],
            period=7, fiscal_year=2026,
        )
        try:
            allocate_overhead_cost(inp, self.session)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "sum to zero" in str(e).lower()


# ===========================================================================
# Tool 6: Calculate Revenue Recognition
# ===========================================================================
class TestCalculateRevenueRecognition:
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

    def test_revenue_recognition_normal(self):
        """500K contract, 60% complete, 200K recognized -> 100K current period."""
        inp = CalculateRevenueRecognitionInput(
            contract_id="C-001",
            contract_value=Decimal("500000"),
            completion_percentage=Decimal("60"),
            previous_recognized=Decimal("200000"),
            period=7, fiscal_year=2026,
        )
        r = calculate_revenue_recognition(inp, self.session)
        assert r.total_recognizable == Decimal("300000.00")
        assert r.current_period_revenue == Decimal("100000.00")
        assert r.remaining_revenue == Decimal("200000.00")
        assert r.needs_approval is True

    def test_revenue_recognition_complete(self):
        """100% complete -> all remaining recognized."""
        inp = CalculateRevenueRecognitionInput(
            contract_id="C-002",
            contract_value=Decimal("100000"),
            completion_percentage=Decimal("100"),
            previous_recognized=Decimal("50000"),
            period=7, fiscal_year=2026,
        )
        r = calculate_revenue_recognition(inp, self.session)
        assert r.completion_percentage == Decimal("100")
        assert r.current_period_revenue == Decimal("50000.00")
        assert r.remaining_revenue == Decimal("0")

    def test_revenue_recognition_full_at_100(self):
        """100% complete -> all remaining recognized."""
        inp = CalculateRevenueRecognitionInput(
            contract_id="C-003",
            contract_value=Decimal("50000"),
            completion_percentage=Decimal("100"),
            previous_recognized=Decimal("0"),
            period=7, fiscal_year=2026,
        )
        r = calculate_revenue_recognition(inp, self.session)
        assert r.completion_percentage == Decimal("100")
        assert r.current_period_revenue == Decimal("50000.00")

    def test_revenue_recognition_zero_completion_raises(self):
        """completion <= 0 -> raises ValueError."""
        inp = CalculateRevenueRecognitionInput(
            contract_id="C-004",
            contract_value=Decimal("50000"),
            completion_percentage=Decimal("0"),
            period=7, fiscal_year=2026,
        )
        try:
            calculate_revenue_recognition(inp, self.session)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "must be > 0" in str(e).lower()

    def test_revenue_recognition_over_recognized_raises(self):
        """previous_recognized > total_recognizable -> raises ValueError."""
        inp = CalculateRevenueRecognitionInput(
            contract_id="C-005",
            contract_value=Decimal("100000"),
            completion_percentage=Decimal("30"),
            previous_recognized=Decimal("50000"),
            period=7, fiscal_year=2026,
        )
        try:
            calculate_revenue_recognition(inp, self.session)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "over-recognized" in str(e).lower()


# ===========================================================================
# Tool 7: Flag Provision / Contingent Liability
# ===========================================================================
class TestFlagProvisionContingentLiability:
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

    def test_provision_probable(self):
        """Probable -> recognize."""
        inp = FlagProvisionContingentLiabilityInput(
            description="Lawsuit settlement",
            estimated_amount=Decimal("200000"),
            probability="probable",
            fiscal_year=2026,
        )
        r = flag_provision_contingent_liability(inp, self.session)
        assert r.accounting_treatment == "recognize"
        assert r.status == "pending_approval"
        assert r.needs_approval is True

    def test_provision_possible(self):
        """Possible -> disclose."""
        inp = FlagProvisionContingentLiabilityInput(
            description="Tax dispute",
            estimated_amount=Decimal("50000"),
            probability="possible",
            fiscal_year=2026,
        )
        r = flag_provision_contingent_liability(inp, self.session)
        assert r.accounting_treatment == "disclose"
        assert r.status == "draft"

    def test_provision_remote(self):
        """Remote -> ignore."""
        inp = FlagProvisionContingentLiabilityInput(
            description="Minor claim",
            estimated_amount=Decimal("10000"),
            probability="remote",
            fiscal_year=2026,
        )
        r = flag_provision_contingent_liability(inp, self.session)
        assert r.accounting_treatment == "ignore"
        assert r.status == "draft"

    def test_provision_invalid_probability_raises(self):
        """Invalid probability -> raises ValueError."""
        inp = FlagProvisionContingentLiabilityInput(
            description="Test",
            estimated_amount=Decimal("10000"),
            probability="unlikely",
            fiscal_year=2026,
        )
        try:
            flag_provision_contingent_liability(inp, self.session)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "invalid" in str(e).lower()


# ===========================================================================
# Tool 8: Flag Related Party Transaction (hybrid matching)
# ===========================================================================
class TestFlagRelatedPartyTransaction:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_contact_data(self.session)
        _seed_rp_journal_entries(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_rp_contact_id_match_confirmed(self):
        """contact_id matches confirmed related party."""
        inp = FlagRelatedPartyTransactionInput(
            entry_id="JE-RP-001",
            transaction_description="Payment to Abdullah Traders",
            amount=Decimal("50000"),
            counterparty_name="Abdullah Traders",
            fiscal_year=2026,
        )
        r = flag_related_party_transaction(inp, self.session)
        assert r.related_party_status == "confirmed_related"
        assert r.confidence == "high"
        assert r.matched_via == "contact_id"
        assert r.disclosure_required is True

    def test_rp_reference_fallback_not_related(self):
        """Reference matches contact that is NOT related_party."""
        inp = FlagRelatedPartyTransactionInput(
            entry_id="JE-RP-002",
            transaction_description="Payment to General Suppliers",
            amount=Decimal("30000"),
            counterparty_name="General Suppliers",
            fiscal_year=2026,
        )
        r = flag_related_party_transaction(inp, self.session)
        assert r.related_party_status == "potential_related"
        assert r.confidence == "medium"
        assert r.matched_via == "reference_fallback"
        assert r.disclosure_required is False

    def test_rp_no_match(self):
        """No contact found -> not_related, low confidence."""
        inp = FlagRelatedPartyTransactionInput(
            entry_id="JE-RP-003",
            transaction_description="Payment to Unknown Vendor",
            amount=Decimal("10000"),
            counterparty_name="Unknown Vendor",
            fiscal_year=2026,
        )
        r = flag_related_party_transaction(inp, self.session)
        assert r.related_party_status == "not_related"
        assert r.confidence == "low"
        assert r.matched_via == "no_match"

    def test_rp_entry_not_found(self):
        """Entry ID doesn't exist -> not_related."""
        inp = FlagRelatedPartyTransactionInput(
            entry_id="NONEXISTENT",
            transaction_description="Ghost transaction",
            amount=Decimal("1000"),
            counterparty_name="Ghost Co",
            fiscal_year=2026,
        )
        r = flag_related_party_transaction(inp, self.session)
        assert r.related_party_status == "not_related"
        assert r.matched_via == "no_match"


# ===========================================================================
# Full E2E: All 8 tools in sequence
# ===========================================================================
class TestE2ECostAdvancedSequence:
    """Full end-to-end: calculate_breakeven -> convert_foreign_currency ->
    prepare_budget_forecast -> calculate_standard_costing_variance ->
    allocate_overhead_cost -> calculate_revenue_recognition ->
    flag_provision_contingent_liability -> flag_related_party_transaction."""

    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_rate_data(self.session)
        _seed_historical_data(self.session)
        _seed_contact_data(self.session)
        _seed_rp_journal_entries(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_e2e_cost_advanced_sequence(self):
        """Run all 8 tools in sequence with verification at each step."""

        # Step 1: Calculate Breakeven
        be_inp = CalculateBreakevenInput(
            fixed_cost=Decimal("500000"),
            variable_cost_per_unit=Decimal("300"),
            selling_price_per_unit=Decimal("500"),
        )
        be = calculate_breakeven(be_inp, self.session)
        assert be.breakeven_units == Decimal("2500")
        print(f"  1. Breakeven: {be.breakeven_units} units, revenue={be.breakeven_revenue}")

        # Step 2: Convert Foreign Currency
        fx_inp = ConvertForeignCurrencyInput(
            amount=Decimal("1000"),
            from_currency="USD",
            to_currency="PKR",
        )
        with patch("tools.cost_advanced_tools._fetch_live_rate", return_value=None):
            fx = convert_foreign_currency(fx_inp, self.session)
        assert fx.converted_amount == Decimal("280000.00")
        print(f"  2. Forex: 1000 USD -> {fx.converted_amount} PKR @ rate {fx.conversion_rate}")

        # Step 3: Prepare Budget Forecast
        bf_inp = PrepareBudgetForecastInput(fiscal_year=2027, periods=12)
        bf = prepare_budget_forecast(bf_inp, self.session)
        assert len(bf.forecast_items) > 0
        assert bf.confidence == "high"
        print(f"  3. Budget: {len(bf.forecast_items)} accounts, {bf.data_months} months data, confidence={bf.confidence}")

        # Step 4: Calculate Standard Costing Variance
        var_inp = CalculateStandardCostingVarianceInput(
            account_code="6000", period=1, fiscal_year=2026,
            standard_cost=Decimal("52000"),
        )
        var = calculate_standard_costing_variance(var_inp, self.session)
        assert var.cost_variance == Decimal("-2000.00")  # actual 50000 - standard 52000
        print(f"  4. Variance: standard={var.standard_cost}, actual={var.actual_cost}, variance={var.cost_variance}")

        # Step 5: Allocate Overhead Cost
        oh_inp = AllocateOverheadCostInput(
            total_overhead=Decimal("100000"),
            allocation_basis="headcount",
            allocation_pool=[
                AllocationPoolItem(name="Sales", value=Decimal("10")),
                AllocationPoolItem(name="Engineering", value=Decimal("25")),
                AllocationPoolItem(name="Support", value=Decimal("15")),
            ],
            period=7, fiscal_year=2026,
        )
        oh = allocate_overhead_cost(oh_inp, self.session)
        assert len(oh.allocations) == 3
        assert oh.total_allocated == Decimal("100000")
        print(f"  5. Overhead: {len(oh.allocations)} depts, total={oh.total_allocated}")

        # Step 6: Calculate Revenue Recognition
        rr_inp = CalculateRevenueRecognitionInput(
            contract_id="C-001",
            contract_value=Decimal("500000"),
            completion_percentage=Decimal("60"),
            previous_recognized=Decimal("200000"),
            period=7, fiscal_year=2026,
        )
        rr = calculate_revenue_recognition(rr_inp, self.session)
        assert rr.current_period_revenue == Decimal("100000.00")
        print(f"  6. Revenue: total_rec={rr.total_recognizable}, current={rr.current_period_revenue}")

        # Step 7: Flag Provision
        prov_inp = FlagProvisionContingentLiabilityInput(
            description="Lawsuit",
            estimated_amount=Decimal("200000"),
            probability="probable",
            fiscal_year=2026,
        )
        prov = flag_provision_contingent_liability(prov_inp, self.session)
        assert prov.accounting_treatment == "recognize"
        print(f"  7. Provision: treatment={prov.accounting_treatment}, status={prov.status}")

        # Step 8: Flag Related Party Transaction
        rp_inp = FlagRelatedPartyTransactionInput(
            entry_id="JE-RP-001",
            transaction_description="Payment to Abdullah Traders",
            amount=Decimal("50000"),
            counterparty_name="Abdullah Traders",
            fiscal_year=2026,
        )
        rp = flag_related_party_transaction(rp_inp, self.session)
        assert rp.related_party_status == "confirmed_related"
        assert rp.matched_via == "contact_id"
        print(f"  8. Related Party: status={rp.related_party_status}, via={rp.matched_via}")

        print("\n  ✅ All 8 tools in sequence PASSED")
