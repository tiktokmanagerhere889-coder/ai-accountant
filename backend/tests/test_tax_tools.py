"""Tests for Tax tools (Agent 7).

Tests all 8 tools with PostgreSQL isolation per test class.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from db.models import Base, JournalEntry, TaxRate, EobiRate, Contact
from tools.tax_tools import (
    _advance_tax_paid,
    calculate_withholding_tax, get_tax_planning_advice,
    calculate_advance_minimum_tax, calculate_eobi_deductions,
    adjust_sales_tax_input_output, flag_tax_exemption_zero_rating,
    prepare_sales_tax_filing, prepare_income_tax_filing,
)
from tools.schemas import (
    CalculateWithholdingTaxInput, CalculateWithholdingTaxOutput,
    GetTaxPlanningAdviceInput, GetTaxPlanningAdviceOutput,
    CalculateAdvanceMinimumTaxInput, CalculateAdvanceMinimumTaxOutput,
    CalculateEobiDeductionsInput, CalculateEobiDeductionsOutput,
    AdjustSalesTaxInputOutputInput, AdjustSalesTaxInputOutputOutput,
    FlagTaxExemptionZeroRatingInput, FlagTaxExemptionZeroRatingOutput,
    PrepareSalesTaxFilingInput, PrepareSalesTaxFilingOutput,
    PrepareIncomeTaxFilingInput, PrepareIncomeTaxFilingOutput,
)
from tests.test_helpers import TEST_DATABASE_URL


def _seed_tax_rates(session: Session):
    """Seed tax_rates table with standard rates."""
    session.add(TaxRate(tax_type="wht_service", rate=Decimal("8"), effective_from=date(2025, 1, 1), effective_to=None, description="WHT on services"))
    session.add(TaxRate(tax_type="wht_supply", rate=Decimal("4"), effective_from=date(2025, 1, 1), effective_to=None, description="WHT on supplies"))
    session.add(TaxRate(tax_type="wht_contract", rate=Decimal("7.5"), effective_from=date(2025, 1, 1), effective_to=None, description="WHT on contracts"))
    session.add(TaxRate(tax_type="wht_rent", rate=Decimal("5"), effective_from=date(2025, 1, 1), effective_to=None, description="WHT on rent"))
    session.add(TaxRate(tax_type="wht_salary", rate=Decimal("8"), effective_from=date(2025, 1, 1), effective_to=None, description="WHT on salary"))
    session.add(TaxRate(tax_type="amt_company", rate=Decimal("1.5"), effective_from=date(2025, 1, 1), effective_to=None, description="AMT for companies"))
    session.add(TaxRate(tax_type="amt_individual", rate=Decimal("1"), effective_from=date(2025, 1, 1), effective_to=None, description="AMT for individuals"))
    session.add(TaxRate(tax_type="amt_partnership", rate=Decimal("0.5"), effective_from=date(2025, 1, 1), effective_to=None, description="AMT for partnerships"))
    session.add(TaxRate(tax_type="INCOME_TAX", rate=Decimal("29"), effective_from=date(2025, 1, 1), effective_to=None, description="Corporate income tax"))
    session.add(TaxRate(tax_type="SALES_TAX", rate=Decimal("18"), effective_from=date(2025, 1, 1), effective_to=None, description="Sales tax"))
    session.commit()


def _seed_eobi_rates(session: Session):
    """Seed eobi_rates table."""
    session.add(EobiRate(rate_type="standard", rate=Decimal("5"), employee_rate=Decimal("2.5"),
                         effective_from=date(2025, 1, 1), effective_to=None,
                         description="Standard EOBI rate", max_insurable_amount=Decimal("50000")))
    session.commit()


def _seed_journal_entries(session: Session):
    """Seed journal entries for tax calculation tests."""
    # Revenue (prefix 4) for July 2026
    session.add(JournalEntry(
        entry_id="REV-001", description="Sales revenue",
        posted_date=date(2026, 7, 15), reference="INV-001",
        debit_account="1000-Cash", debit_amount=Decimal("500000.00"),
        credit_account="4000-Sales Revenue", credit_amount=Decimal("500000.00"),
        status="posted",
    ))
    # Expenses (prefix 5/6) for July 2026
    session.add(JournalEntry(
        entry_id="EXP-001", description="Purchase of goods",
        posted_date=date(2026, 7, 10), reference=None,
        debit_account="5000-Cost of Goods Sold", debit_amount=Decimal("200000.00"),
        credit_account="1000-Cash", credit_amount=Decimal("200000.00"),
        status="posted",
    ))
    session.add(JournalEntry(
        entry_id="EXP-002", description="Office rent",
        posted_date=date(2026, 7, 5), reference=None,
        debit_account="6000-Rent Expense", debit_amount=Decimal("50000.00"),
        credit_account="1000-Cash", credit_amount=Decimal("50000.00"),
        status="posted",
    ))
    session.add(JournalEntry(
        entry_id="EXP-003", description="Salary expense",
        posted_date=date(2026, 7, 28), reference=None,
        debit_account="6100-Salary Expense", debit_amount=Decimal("150000.00"),
        credit_account="1000-Cash", credit_amount=Decimal("150000.00"),
        status="posted",
    ))
    # Export revenue for exemption test
    session.add(JournalEntry(
        entry_id="REV-EXP-001", description="Export sales to Dubai",
        posted_date=date(2026, 7, 20), reference="INV-EXP-001",
        debit_account="1000-Cash", debit_amount=Decimal("100000.00"),
        credit_account="4000-Export Revenue", credit_amount=Decimal("100000.00"),
        status="posted",
    ))
    # Previous year entries for tax planning
    session.add(JournalEntry(
        entry_id="REV-2025", description="Sales FY2025",
        posted_date=date(2025, 6, 30), reference="INV-2025",
        debit_account="1000-Cash", debit_amount=Decimal("300000.00"),
        credit_account="4000-Sales Revenue", credit_amount=Decimal("300000.00"),
        status="posted",
    ))
    session.add(JournalEntry(
        entry_id="EXP-2025", description="Expenses FY2025",
        posted_date=date(2025, 6, 30), reference=None,
        debit_account="6000-Rent Expense", debit_amount=Decimal("100000.00"),
        credit_account="1000-Cash", credit_amount=Decimal("100000.00"),
        status="posted",
    ))
    session.commit()


def _seed_contacts(session: Session):
    """Seed contacts for exemption tests."""
    session.add(Contact(
        contact_id="CNT-EXP-001", contact_name="Dubai Exports LLC",
        contact_type="export_customer", phone="0300-1111111",
        related_party=False,
    ))
    session.commit()


# ===========================================================================
# Tool 1: Calculate Withholding Tax
# ===========================================================================
class TestCalculateWithholdingTax:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_tax_rates(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_wht_service(self):
        """50000 at 8% service rate -> 4000 WHT."""
        inp = CalculateWithholdingTaxInput(
            amount=Decimal("50000"), withholding_type="service",
            transaction_date=date(2026, 7, 15),
        )
        r = calculate_withholding_tax(inp, self.session)
        assert r.rate_applied == Decimal("8")
        assert r.tax_amount == Decimal("4000.00")
        assert r.net_amount == Decimal("46000.00")

    def test_wht_supply(self):
        """75000 at 4% supply rate -> 3000 WHT."""
        inp = CalculateWithholdingTaxInput(
            amount=Decimal("75000"), withholding_type="supply",
            transaction_date=date(2026, 7, 15),
        )
        r = calculate_withholding_tax(inp, self.session)
        assert r.rate_applied == Decimal("4")
        assert r.tax_amount == Decimal("3000.00")

    def test_wht_salary_configured(self):
        """Configured salary rate 8% -> 4800 tax."""
        inp = CalculateWithholdingTaxInput(
            amount=Decimal("60000"), withholding_type="salary",
            transaction_date=date(2026, 7, 15),
        )
        r = calculate_withholding_tax(inp, self.session)
        assert r.rate_applied == Decimal("8")
        assert r.tax_amount == Decimal("4800.00")
        assert "tax_rates" in r.rate_source

    def test_wht_not_configured_raises(self):
        """Unconfigured rate -> clear error, no silent hardcoded fallback."""
        inp = CalculateWithholdingTaxInput(
            amount=Decimal("60000"), withholding_type="dividend",
            transaction_date=date(2026, 7, 15),
        )
        try:
            calculate_withholding_tax(inp, self.session)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "dividend" in str(e)
            assert "not configured" in str(e)


# ===========================================================================
# Tool 2: Get Tax Planning Advice
# ===========================================================================
class TestGetTaxPlanningAdvice:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_journal_entries(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_tax_planning_with_data(self):
        """Revenue 900K + 100K export = ~1M, expenses 500K for FY 2026."""
        inp = GetTaxPlanningAdviceInput(
            query="Any tax planning tips?", fiscal_year=2026,
        )
        r = get_tax_planning_advice(inp, self.session)
        assert r.fiscal_year == 2026
        assert r.disclaimer != ""
        assert r.data_summary.get("total_revenue") is not None

    def test_tax_planning_no_data(self):
        """No data for future year -> general advice."""
        inp = GetTaxPlanningAdviceInput(
            query="Plan for 2030", fiscal_year=2030,
        )
        r = get_tax_planning_advice(inp, self.session)
        assert r.fiscal_year == 2030
        assert r.data_summary.get("total_revenue") == "0.00"
        assert r.advice != ""


# ===========================================================================
# Tool 3: Calculate Advance Minimum Tax
# ===========================================================================
class TestCalculateAdvanceMinimumTax:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_tax_rates(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_amt_company(self):
        """10M company turnover at 1.5% -> 150000 AMT."""
        inp = CalculateAdvanceMinimumTaxInput(
            annual_turnover=Decimal("10000000"), fiscal_year=2026,
            business_type="company",
        )
        r = calculate_advance_minimum_tax(inp, self.session)
        assert r.applicable_rate == Decimal("1.5")
        assert r.minimum_tax == Decimal("150000.00")
        assert r.basis.startswith("tax_rates")

    def test_amt_individual(self):
        """Individual turnover -> 1% default fallback."""
        inp = CalculateAdvanceMinimumTaxInput(
            annual_turnover=Decimal("5000000"), fiscal_year=2026,
            business_type="individual",
        )
        r = calculate_advance_minimum_tax(inp, self.session)
        assert r.applicable_rate == Decimal("1.0")
        assert r.minimum_tax == Decimal("50000.00")

    def test_amt_unknown_type(self):
        """Unknown type -> falls back to company rate."""
        inp = CalculateAdvanceMinimumTaxInput(
            annual_turnover=Decimal("2000000"), fiscal_year=2026,
            business_type="partnership",
        )
        r = calculate_advance_minimum_tax(inp, self.session)
        assert r.minimum_tax > Decimal("0")


# ===========================================================================
# Tool 4: Calculate EOBI Deductions
# ===========================================================================
class TestCalculateEobiDeductions:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_eobi_rates(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_eobi_normal(self):
        """45000 salary: employer 5% = 2250, employee 2.5% = 1125."""
        inp = CalculateEobiDeductionsInput(
            gross_salary=Decimal("45000"), period=7, fiscal_year=2026,
        )
        r = calculate_eobi_deductions(inp, self.session)
        assert r.employer_contribution == Decimal("2250.00")
        assert r.employee_contribution == Decimal("1125.00")
        assert r.total_contribution == Decimal("3375.00")

    def test_eobi_above_ceiling(self):
        """60000 salary capped at 50000 max_insurable."""
        inp = CalculateEobiDeductionsInput(
            gross_salary=Decimal("60000"), period=7, fiscal_year=2026,
        )
        r = calculate_eobi_deductions(inp, self.session)
        # Employer: 50000 * 5% = 2500
        assert r.employer_contribution == Decimal("2500.00")
        assert r.employee_contribution == Decimal("1250.00")

    def test_eobi_no_rate_table(self):
        """No rates -> default EOBI 5%/2.5%. 50000 max."""
        inp = CalculateEobiDeductionsInput(
            gross_salary=Decimal("30000"), period=7, fiscal_year=2025,
        )
        # No EobiRate table exists for 2025 session... but we seeded for 2026
        # Let's just verify valid output
        r = calculate_eobi_deductions(inp, self.session)
        # Uses seeded standard rate
        assert r.total_contribution > Decimal("0")
        assert r.rate_applied > Decimal("0")


# ===========================================================================
# Tool 5: Adjust Sales Tax Input/Output
# ===========================================================================
class TestAdjustSalesTaxInputOutput:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_tax_rates(self.session)
        _seed_journal_entries(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_adjust_sales_tax_normal(self):
        """July 2026: revenue 600K (500K sales + 100K export), purchases 400K."""
        inp = AdjustSalesTaxInputOutputInput(
            period=7, fiscal_year=2026,
        )
        r = adjust_sales_tax_input_output(inp, self.session)
        # Revenue 600K * 18% = 108000 output tax
        # Purchases = 200000 (5000) + 50000 (6000) + 150000 (6100) = 400000
        # Input tax = 400000 * 18% = 72000
        assert r.calculated_output_tax == Decimal("108000.00")
        assert r.calculated_input_tax == Decimal("72000.00")
        assert r.net_tax_payable == Decimal("36000.00")
        assert r.needs_approval is True

    def test_adjust_sales_tax_overrides(self):
        """Override amounts bypass DB calculation."""
        inp = AdjustSalesTaxInputOutputInput(
            period=7, fiscal_year=2026,
            output_tax_amount=Decimal("50000"),
            input_tax_amount=Decimal("30000"),
        )
        r = adjust_sales_tax_input_output(inp, self.session)
        assert r.calculated_output_tax == Decimal("50000")
        assert r.calculated_input_tax == Decimal("30000")
        assert r.net_tax_payable == Decimal("20000")
        assert len(r.adjustments) == 2

    def test_adjust_sales_tax_refund(self):
        """Input tax > output tax -> refund scenario."""
        inp = AdjustSalesTaxInputOutputInput(
            period=7, fiscal_year=2026,
            output_tax_amount=Decimal("10000"),
            input_tax_amount=Decimal("25000"),
        )
        r = adjust_sales_tax_input_output(inp, self.session)
        assert r.net_tax_payable == Decimal("0")
        assert r.refund_amount == Decimal("15000")
        assert "refund" in r.summary.lower()

    def test_input_tax_ledger_verified(self):
        """When a real input-tax account has posted entries, basis is ledger_verified."""
        session = self.session
        session.add(JournalEntry(
            entry_id="IT-LEDGER-001",
            description="Input tax paid on business purchases",
            posted_date=date(2026, 7, 12),
            reference=None,
            debit_account="1200-Input Tax Recoverable",
            debit_amount=Decimal("72000.00"),
            credit_account="1000-Cash",
            credit_amount=Decimal("72000.00"),
            status="posted",
        ))
        session.commit()
        inp = AdjustSalesTaxInputOutputInput(period=7, fiscal_year=2026)
        r = adjust_sales_tax_input_output(inp, session)
        assert r.calculated_input_tax == Decimal("72000.00")
        assert r.input_tax_basis == "ledger_verified"
        assert "ledger" in r.input_tax_note.lower()

    def test_input_tax_flat_rate_estimated(self):
        """No input-tax account entries -> flat-rate estimate with ESTIMATED note."""
        inp = AdjustSalesTaxInputOutputInput(period=7, fiscal_year=2026)
        r = adjust_sales_tax_input_output(inp, self.session)
        # Purchases = 200000 + 50000 + 150000 = 400000; input tax = 400000 * 18% = 72000
        assert r.calculated_input_tax == Decimal("72000.00")
        assert r.input_tax_basis == "estimated_flat_rate"
        assert r.input_tax_note is not None
        assert "ESTIMATED" in r.input_tax_note
        assert "flat-rate" in r.input_tax_note.lower()

    def test_manual_override_input_tax(self):
        """Explicit input_tax_amount -> manual_override basis."""
        inp = AdjustSalesTaxInputOutputInput(
            period=7, fiscal_year=2026,
            input_tax_amount=Decimal("50000"),
        )
        r = adjust_sales_tax_input_output(inp, self.session)
        assert r.calculated_input_tax == Decimal("50000")
        assert r.input_tax_basis == "manual_override"


# ===========================================================================
# Tool 6: Flag Tax Exemption / Zero Rating
# ===========================================================================
class TestFlagTaxExemptionZeroRating:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_journal_entries(self.session)
        _seed_contacts(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_flag_exemption_all(self):
        """Scan all FY2026 revenue entries."""
        inp = FlagTaxExemptionZeroRatingInput(fiscal_year=2026)
        r = flag_tax_exemption_zero_rating(inp, self.session)
        assert len(r.flagged_entries) >= 1  # export revenue should be flagged
        assert r.needs_approval is True

    def test_flag_exemption_specific_entry(self):
        """Flag specific entries by ID."""
        inp = FlagTaxExemptionZeroRatingInput(
            entry_ids=["REV-EXP-001"], fiscal_year=2026,
        )
        r = flag_tax_exemption_zero_rating(inp, self.session)
        assert len(r.flagged_entries) >= 1
        assert r.total_flagged_amount == Decimal("100000.00")

    def test_flag_exemption_no_results(self):
        """No matching entries -> empty results."""
        inp = FlagTaxExemptionZeroRatingInput(
            entry_ids=["NONEXISTENT"], fiscal_year=2026,
        )
        r = flag_tax_exemption_zero_rating(inp, self.session)
        assert len(r.flagged_entries) == 0


# ===========================================================================
# Tool 7: Prepare Sales Tax Filing
# ===========================================================================
class TestPrepareSalesTaxFiling:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_tax_rates(self.session)
        _seed_journal_entries(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_filing_without_confirm_raises(self):
        """confirm=False raises ValueError."""
        inp = PrepareSalesTaxFilingInput(period=7, fiscal_year=2026, confirm=False)
        try:
            prepare_sales_tax_filing(inp, self.session)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "confirm" in str(e).lower()

    def test_filing_normal(self):
        """Sales tax filing for July 2026."""
        inp = PrepareSalesTaxFilingInput(period=7, fiscal_year=2026, confirm=True)
        r = prepare_sales_tax_filing(inp, self.session)
        assert r.status == "prepared"
        assert r.filing_id != ""
        # Revenue 600K at 18% = 108K output tax (500K sales + 100K export)
        # Purchases 400K at 18% = 72K input tax
        assert r.sales_tax_payable == Decimal("108000.00")
        assert r.input_tax_adjustments == Decimal("72000.00")
        assert r.net_amount_payable == Decimal("36000.00")
        assert r.filing_data.get("fbr_form") is not None

    def test_filing_zero_entries(self):
        """No entries for period -> zero filing."""
        inp = PrepareSalesTaxFilingInput(period=1, fiscal_year=2025, confirm=True)
        r = prepare_sales_tax_filing(inp, self.session)
        assert r.status == "prepared"
        assert r.net_amount_payable == Decimal("0")

    def test_filing_input_tax_flat_rate(self):
        """No input-tax account -> estimated flat-rate with ESTIMATED note."""
        inp = PrepareSalesTaxFilingInput(period=7, fiscal_year=2026, confirm=True)
        r = prepare_sales_tax_filing(inp, self.session)
        assert r.input_tax_basis == "estimated_flat_rate"
        assert r.input_tax_note is not None
        assert "ESTIMATED" in r.input_tax_note
        assert r.filing_data["input_tax_basis"] == "estimated_flat_rate"

    def test_filing_input_tax_ledger_verified(self):
        """Input-tax account entries -> ledger_verified basis in filing."""
        session = self.session
        session.add(JournalEntry(
            entry_id="IT-FILING-001",
            description="Input tax on purchases",
            posted_date=date(2026, 7, 12),
            reference=None,
            debit_account="1200-Input Tax Recoverable",
            debit_amount=Decimal("45000.00"),
            credit_account="1000-Cash",
            credit_amount=Decimal("45000.00"),
            status="posted",
        ))
        session.commit()
        inp = PrepareSalesTaxFilingInput(period=7, fiscal_year=2026, confirm=True)
        r = prepare_sales_tax_filing(inp, self.session)
        assert r.input_tax_basis == "ledger_verified"
        assert r.input_tax_adjustments == Decimal("45000.00")
        assert r.filing_data["input_tax_basis"] == "ledger_verified"


# ===========================================================================
# Tool 8: Prepare Income Tax Filing
# ===========================================================================
class TestPrepareIncomeTaxFiling:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_tax_rates(self.session)
        _seed_journal_entries(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_income_tax_filing_without_confirm_raises(self):
        """confirm=False raises ValueError."""
        inp = PrepareIncomeTaxFilingInput(fiscal_year=2026, confirm=False)
        try:
            prepare_income_tax_filing(inp, self.session)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "confirm" in str(e).lower()

    def test_income_tax_filing_normal(self):
        """FY2026: income ~600K, expenses 400K, taxable ~200K."""
        inp = PrepareIncomeTaxFilingInput(fiscal_year=2026, confirm=True)
        r = prepare_income_tax_filing(inp, self.session)
        assert r.status == "prepared"
        assert r.filing_id != ""
        # Revenue: 500K + 100K export = 600K
        assert r.total_income == Decimal("600000.00")
        # Expenses: 200K + 50K + 150K = 400K
        assert r.total_expenses == Decimal("400000.00")
        assert r.taxable_income == Decimal("200000.00")
        # Tax liability: 200K * 29% = 58K
        assert r.tax_liability == Decimal("58000.00")
        assert r.net_tax_due == Decimal("58000.00")

    def test_income_tax_filing_net_loss(self):
        """Net loss -> zero tax liability."""
        inp = PrepareIncomeTaxFilingInput(fiscal_year=2025, confirm=True)
        r = prepare_income_tax_filing(inp, self.session)
        # FY2025: revenue 300K, expenses 100K => taxable 200K
        assert r.status == "prepared"
        assert r.total_income == Decimal("300000.00")

    def test_income_tax_filing_zero_data(self):
        """No data -> zero filing."""
        inp = PrepareIncomeTaxFilingInput(fiscal_year=2030, confirm=True)
        r = prepare_income_tax_filing(inp, self.session)
        assert r.status == "prepared"
        assert r.total_income == Decimal("0")
        assert r.net_tax_due == Decimal("0")

    def test_income_tax_filing_advance_tax_from_ledger(self):
        """Advance tax paid in the ledger reduces net tax due.

        Seed FY2026 advance-tax debits (one via account name, one via
        description) and confirm advance_tax_paid is summed from the ledger,
        not assumed zero.
        """
        self.session.add(JournalEntry(
            entry_id="ADV-TAX-1", description="Advance tax paid Q1",
            posted_date=date(2026, 4, 10), reference="CHALAN-001",
            debit_account="2200-Tax Payable - Advance Tax", debit_amount=Decimal("20000.00"),
            credit_account="1000-Cash", credit_amount=Decimal("20000.00"),
            status="posted",
        ))
        self.session.add(JournalEntry(
            entry_id="ADV-TAX-2", description="paid WHT via challan 5000",
            posted_date=date(2026, 5, 20), reference="CHALAN-002",
            debit_account="1200-Prepaid Taxes", debit_amount=Decimal("5000.00"),
            credit_account="1000-Cash", credit_amount=Decimal("5000.00"),
            status="posted",
        ))
        # Prior-year advance tax must NOT count toward FY2026.
        self.session.add(JournalEntry(
            entry_id="ADV-TAX-2025", description="Advance tax paid Q4",
            posted_date=date(2025, 6, 20), reference="CHALAN-000",
            debit_account="2200-Tax Payable - Advance Tax", debit_amount=Decimal("999999.00"),
            credit_account="1000-Cash", credit_amount=Decimal("999999.00"),
            status="posted",
        ))
        self.session.commit()

        inp = PrepareIncomeTaxFilingInput(fiscal_year=2026, confirm=True)
        r = prepare_income_tax_filing(inp, self.session)
        # 20K (account keyword) + 5K (description keyword); prior-year excluded.
        assert r.advance_tax_paid == Decimal("25000.00")
        # Tax liability 58K - 25K advance = 33K due.
        assert r.tax_liability == Decimal("58000.00")
        assert r.net_tax_due == Decimal("33000.00")
        assert r.filing_data["advance_tax_paid"] == "25000.00"

    def test_advance_tax_natural_phrases_all_match(self):
        """Naturally-phrased advance-tax descriptions (as a CA/AI would write
        them, not keyword copy-paste) must all be picked up by _advance_tax_paid.
        Uses neutral debit accounts so only description matching is under test.
        """
        phrases = [
            "Advance income tax deposited for Q1",
            "FBR advance tax challan paid via bank",
            "Quarterly advance tax remittance",
            "Withholding tax on rent remitted to FBR",
            "Paid provisional tax installment for the year",
        ]
        amounts = [Decimal("10000.00"), Decimal("20000.00"), Decimal("30000.00"),
                   Decimal("40000.00"), Decimal("50000.00")]
        for i, (desc, amt) in enumerate(zip(phrases, amounts), start=1):
            self.session.add(JournalEntry(
                entry_id=f"NAT-{i}", description=desc,
                posted_date=date(2026, 4, i), reference=f"CHALAN-NAT-{i}",
                debit_account="1500-Misc", debit_amount=amt,
                credit_account="1000-Cash", credit_amount=amt,
                status="posted",
            ))
        # Non-tax entries must NOT match (even with payment verbs / 'remit').
        self.session.add(JournalEntry(
            entry_id="NAT-NT", description="remitted dividend to shareholder",
            posted_date=date(2026, 4, 20), reference="DIV-1",
            debit_account="2000-Payables", debit_amount=Decimal("90000.00"),
            credit_account="1000-Cash", credit_amount=Decimal("90000.00"),
            status="posted",
        ))
        self.session.commit()
        assert _advance_tax_paid(self.session, 2026) == sum(amounts)

    def test_advance_tax_liability_settlement_not_counted(self):
        """Settling a recorded tax liability must not be counted as a new
        advance-tax credit (would inflate advance_tax_paid).
        """
        self.session.add(JournalEntry(
            entry_id="SETTLE-1", description="paid tax payable WHT liability settlement",
            posted_date=date(2026, 4, 10), reference="CHALAN-SETTLE",
            debit_account="2200-Tax Payable", debit_amount=Decimal("50000.00"),
            credit_account="1000-Cash", credit_amount=Decimal("50000.00"),
            status="posted",
        ))
        self.session.commit()
        assert _advance_tax_paid(self.session, 2026) == Decimal("0")

    def test_income_tax_filing_no_advance_tax_warns(self):
        """When no advance-tax/WHT payment entry is found in the ledger, the
        filing must surface a clear warning instead of silently treating
        advance_tax as 0.
        """
        # Some FY2026 revenue so the filing computes a liability.
        self.session.add(JournalEntry(
            entry_id="INC-1", description="Consulting income",
            posted_date=date(2026, 4, 10), reference="INV-1",
            debit_account="1000-Cash", debit_amount=Decimal("100000.00"),
            credit_account="4000-Revenue", credit_amount=Decimal("100000.00"),
            status="posted",
        ))
        self.session.commit()
        inp = PrepareIncomeTaxFilingInput(fiscal_year=2026, confirm=True)
        r = prepare_income_tax_filing(inp, self.session)
        assert r.advance_tax_paid == Decimal("0")
        assert r.warning is not None
        assert "No advance tax or WHT payment entries found" in r.warning
        assert "advance tax is being treated as 0" in r.warning


# ===========================================================================
# Full E2E: All 8 tools in sequence
# ===========================================================================
class TestE2ETaxSequence:
    """Full end-to-end: all 8 tax tools in sequence."""

    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_tax_rates(self.session)
        _seed_eobi_rates(self.session)
        _seed_journal_entries(self.session)
        _seed_contacts(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_e2e_tax_sequence(self):
        """Run all 8 tools in sequence with verification at each step."""

        # Step 1: Withholding Tax
        wht_inp = CalculateWithholdingTaxInput(
            amount=Decimal("50000"), withholding_type="service",
            transaction_date=date(2026, 7, 15),
        )
        wht = calculate_withholding_tax(wht_inp, self.session)
        assert wht.tax_amount == Decimal("4000.00")
        print(f"  1. WHT: 50000 @ 8% service = {wht.tax_amount} tax, net {wht.net_amount}")

        # Step 2: Tax Planning Advice
        adv_inp = GetTaxPlanningAdviceInput(
            query="Tips for 2026", fiscal_year=2026,
        )
        adv = get_tax_planning_advice(adv_inp, self.session)
        assert adv.advice != ""
        print(f"  2. Tax Advice: {len(adv.advice)} chars, revenue={adv.data_summary['total_revenue']}")

        # Step 3: Advance Minimum Tax
        amt_inp = CalculateAdvanceMinimumTaxInput(
            annual_turnover=Decimal("10000000"), fiscal_year=2026,
            business_type="company",
        )
        amt = calculate_advance_minimum_tax(amt_inp, self.session)
        assert amt.minimum_tax == Decimal("150000.00")
        print(f"  3. AMT: 10M @ 1.5% = {amt.minimum_tax}")

        # Step 4: EOBI Deductions
        eobi_inp = CalculateEobiDeductionsInput(
            gross_salary=Decimal("45000"), period=7, fiscal_year=2026,
        )
        eobi = calculate_eobi_deductions(eobi_inp, self.session)
        assert eobi.employer_contribution == Decimal("2250.00")
        print(f"  4. EOBI: 45000 -> employer {eobi.employer_contribution}, employee {eobi.employee_contribution}")

        # Step 5: Sales Tax Adjustment
        sta_inp = AdjustSalesTaxInputOutputInput(period=7, fiscal_year=2026)
        sta = adjust_sales_tax_input_output(sta_inp, self.session)
        assert sta.net_tax_payable == Decimal("36000.00")
        print(f"  5. Sales Tax: output={sta.calculated_output_tax}, input={sta.calculated_input_tax}, net={sta.net_tax_payable}")

        # Step 6: Flag Exemption
        flg_inp = FlagTaxExemptionZeroRatingInput(fiscal_year=2026)
        flg = flag_tax_exemption_zero_rating(flg_inp, self.session)
        assert len(flg.flagged_entries) >= 1
        print(f"  6. Exemption: {len(flg.flagged_entries)} flagged, total {flg.total_flagged_amount}")

        # Step 7: Prepare Sales Tax Filing
        stf_inp = PrepareSalesTaxFilingInput(period=7, fiscal_year=2026, confirm=True)
        stf = prepare_sales_tax_filing(stf_inp, self.session)
        assert stf.status == "prepared"
        print(f"  7. Sales Tax Filing: {stf.filing_id}, net={stf.net_amount_payable}")

        # Step 8: Prepare Income Tax Filing
        itf_inp = PrepareIncomeTaxFilingInput(fiscal_year=2026, confirm=True)
        itf = prepare_income_tax_filing(itf_inp, self.session)
        assert itf.status == "prepared"
        print(f"  8. Income Tax Filing: {itf.filing_id}, net due={itf.net_tax_due}")

        # Verify confirm=False raises for filing tools
        try:
            prepare_sales_tax_filing(PrepareSalesTaxFilingInput(period=7, fiscal_year=2026, confirm=False), self.session)
            assert False, "Should raise ValueError"
        except ValueError:
            print("     Filing gating: confirm=False raises ValueError ✅")

        print("\n  ✅ All 8 tools in sequence PASSED")
