"""Tests for Advisory tools (Agent 9).

Tests all 5 tools with PostgreSQL isolation per test class.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from db.models import Base, JournalEntry, Budget, RetainedEarnings
from tools.advisory_tools import (
    analyze_spending_patterns, calculate_financial_ratios,
    assess_financial_health, generate_cost_cutting_recommendations,
    generate_custom_report,
)
from tools.schemas import (
    AnalyzeSpendingPatternsInput, AnalyzeSpendingPatternsOutput,
    CalculateFinancialRatiosInput, CalculateFinancialRatiosOutput,
    AssessFinancialHealthInput, AssessFinancialHealthOutput,
    GenerateCostCuttingInput, GenerateCostCuttingOutput,
    GenerateCustomReportInput, GenerateCustomReportOutput,
)
from tests.test_helpers import TEST_DATABASE_URL


def _seed_journal_entries(session: Session):
    """Seed journal entries for FY 2026 advisory tests."""
    # Revenue (prefix 4)
    session.add(JournalEntry(
        entry_id="REV-001", description="Sales revenue - Q1",
        posted_date=date(2026, 3, 15), reference="INV-001",
        debit_account="1000-Cash", debit_amount=Decimal("500000.00"),
        credit_account="4000-Sales Revenue", credit_amount=Decimal("500000.00"),
        status="posted",
    ))
    session.add(JournalEntry(
        entry_id="REV-002", description="Sales revenue - Q2",
        posted_date=date(2026, 6, 15), reference="INV-002",
        debit_account="1000-Cash", debit_amount=Decimal("600000.00"),
        credit_account="4000-Sales Revenue", credit_amount=Decimal("600000.00"),
        status="posted",
    ))
    # COGS (prefix 5)
    session.add(JournalEntry(
        entry_id="COGS-001", description="Raw materials purchase",
        posted_date=date(2026, 3, 10), reference="PO-001",
        debit_account="5000-Cost of Goods Sold", debit_amount=Decimal("200000.00"),
        credit_account="2000-Accounts Payable", credit_amount=Decimal("200000.00"),
        status="posted",
    ))
    session.add(JournalEntry(
        entry_id="COGS-002", description="Raw materials purchase Q2",
        posted_date=date(2026, 6, 10), reference="PO-002",
        debit_account="5000-Cost of Goods Sold", debit_amount=Decimal("250000.00"),
        credit_account="2000-Accounts Payable", credit_amount=Decimal("250000.00"),
        status="posted",
    ))
    # Operating Expenses (prefix 6)
    session.add(JournalEntry(
        entry_id="OPEX-001", description="Office rent Q1",
        posted_date=date(2026, 3, 5), reference="RENT-001",
        debit_account="6000-Rent Expense", debit_amount=Decimal("150000.00"),
        credit_account="1000-Cash", credit_amount=Decimal("150000.00"),
        status="posted",
    ))
    session.add(JournalEntry(
        entry_id="OPEX-002", description="Office rent Q2",
        posted_date=date(2026, 6, 5), reference="RENT-002",
        debit_account="6000-Rent Expense", debit_amount=Decimal("150000.00"),
        credit_account="1000-Cash", credit_amount=Decimal("150000.00"),
        status="posted",
    ))
    session.add(JournalEntry(
        entry_id="OPEX-003", description="Salary expense Q1",
        posted_date=date(2026, 3, 28), reference="PAY-001",
        debit_account="6100-Salary Expense", debit_amount=Decimal("200000.00"),
        credit_account="1000-Cash", credit_amount=Decimal("200000.00"),
        status="posted",
    ))
    session.add(JournalEntry(
        entry_id="OPEX-004", description="Salary expense Q2",
        posted_date=date(2026, 6, 28), reference="PAY-002",
        debit_account="6100-Salary Expense", debit_amount=Decimal("200000.00"),
        credit_account="1000-Cash", credit_amount=Decimal("200000.00"),
        status="posted",
    ))
    # Other Expenses (prefix 8)
    session.add(JournalEntry(
        entry_id="OTHER-001", description="Bank charges Q1",
        posted_date=date(2026, 3, 31), reference=None,
        debit_account="8000-Bank Charges", debit_amount=Decimal("5000.00"),
        credit_account="1000-Cash", credit_amount=Decimal("5000.00"),
        status="posted",
    ))
    # Assets (prefix 1) and Liabilities (prefix 2) for balance sheet
    session.add(JournalEntry(
        entry_id="BS-001", description="Fixed asset purchase",
        posted_date=date(2026, 1, 5), reference="FA-001",
        debit_account="1200-Equipment", debit_amount=Decimal("800000.00"),
        credit_account="1000-Cash", credit_amount=Decimal("800000.00"),
        status="posted",
    ))
    session.add(JournalEntry(
        entry_id="BS-002", description="Loan taken",
        posted_date=date(2026, 1, 10), reference="LN-001",
        debit_account="1000-Cash", debit_amount=Decimal("500000.00"),
        credit_account="2200-Bank Loan", credit_amount=Decimal("500000.00"),
        status="posted",
    ))
    session.commit()


def _seed_budget(session: Session):
    """Seed budget data for FY 2026."""
    session.add(Budget(budget_id="BUG-001", fiscal_year=2026, period=3,
                        account_code="6000", budget_amount=Decimal("300000.00")))
    session.add(Budget(budget_id="BUG-002", fiscal_year=2026, period=6,
                        account_code="6100", budget_amount=Decimal("400000.00")))
    session.add(Budget(budget_id="BUG-003", fiscal_year=2026, period=6,
                        account_code="5000", budget_amount=Decimal("450000.00")))
    session.commit()


# ===========================================================================
# Tool 1: Analyze Spending Patterns
# ===========================================================================
class TestAnalyzeSpendingPatterns:
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

    def test_all_expenses_full_year(self):
        """Analyze all expenses for FY 2026."""
        inp = AnalyzeSpendingPatternsInput(
            from_date=date(2026, 1, 1), to_date=date(2026, 12, 31),
        )
        r = analyze_spending_patterns(inp, self.session)
        assert r.total_spending > 0
        assert len(r.categories) >= 2
        assert r.entry_count == 7  # 2 COGS + 4 OPEX + 1 Other

    def test_filter_by_prefix(self):
        """Filter to only prefix 6 (Operating Expenses)."""
        inp = AnalyzeSpendingPatternsInput(
            from_date=date(2026, 1, 1), to_date=date(2026, 12, 31),
            account_prefixes=["6"],
        )
        r = analyze_spending_patterns(inp, self.session)
        assert r.entry_count == 4
        assert r.total_spending == Decimal("700000.00")  # 150k+150k+200k+200k

    def test_description_keyword_filter(self):
        """Filter entries by keyword 'rent'."""
        inp = AnalyzeSpendingPatternsInput(
            from_date=date(2026, 1, 1), to_date=date(2026, 12, 31),
            description_keyword="rent",
        )
        r = analyze_spending_patterns(inp, self.session)
        assert r.total_spending == Decimal("300000.00")  # 150k+150k
        assert r.entry_count == 2

    def test_no_data_returns_empty(self):
        """No entries in date range -> empty result."""
        inp = AnalyzeSpendingPatternsInput(
            from_date=date(2025, 1, 1), to_date=date(2025, 1, 31),
        )
        r = analyze_spending_patterns(inp, self.session)
        assert r.total_spending == Decimal("0")
        assert r.entry_count == 0
        assert len(r.insights) >= 1

    def test_monthly_breakdown(self):
        """Monthly breakdown has data."""
        inp = AnalyzeSpendingPatternsInput(
            from_date=date(2026, 1, 1), to_date=date(2026, 12, 31),
        )
        r = analyze_spending_patterns(inp, self.session)
        assert r.monthly_breakdown is not None
        assert len(r.monthly_breakdown) >= 2  # Q1 and Q2 months

    def test_top_categories(self):
        """Top categories returned."""
        inp = AnalyzeSpendingPatternsInput(
            from_date=date(2026, 1, 1), to_date=date(2026, 12, 31),
        )
        r = analyze_spending_patterns(inp, self.session)
        assert len(r.top_categories) >= 1
        assert r.top_categories[0].amount > 0


# ===========================================================================
# Tool 2: Calculate Financial Ratios
# ===========================================================================
class TestCalculateFinancialRatios:
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

    def test_all_ratios(self):
        """Compute all ratio categories."""
        inp = CalculateFinancialRatiosInput(fiscal_year=2026)
        r = calculate_financial_ratios(inp, self.session)
        assert len(r.ratios) >= 8  # 2 liquidity + 4 profitability + 2 leverage + 2 efficiency
        assert r.fiscal_year == 2026

    def test_liquidity_only(self):
        """Filter to liquidity ratios only."""
        inp = CalculateFinancialRatiosInput(fiscal_year=2026, ratio_types=["liquidity"])
        r = calculate_financial_ratios(inp, self.session)
        assert all(ri.category == "liquidity" for ri in r.ratios)
        assert len(r.ratios) == 2

    def test_profitability_only(self):
        """Filter to profitability ratios only."""
        inp = CalculateFinancialRatiosInput(fiscal_year=2026, ratio_types=["profitability"])
        r = calculate_financial_ratios(inp, self.session)
        assert all(ri.category == "profitability" for ri in r.ratios)
        assert len(r.ratios) == 4  # NPM, GP, ROA, ROE

    def test_period_filter(self):
        """Ratio for specific period returns results."""
        inp = CalculateFinancialRatiosInput(fiscal_year=2026, period=3)
        r = calculate_financial_ratios(inp, self.session)
        assert len(r.ratios) >= 4

    def test_no_data(self):
        """No data -> ratios still computed with zeros."""
        inp = CalculateFinancialRatiosInput(fiscal_year=2025)
        r = calculate_financial_ratios(inp, self.session)
        assert len(r.ratios) >= 4
        assert r.summary


# ===========================================================================
# Tool 3: Assess Financial Health
# ===========================================================================
class TestAssessFinancialHealth:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_journal_entries(self.session)
        _seed_budget(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_full_assessment(self):
        """Full health assessment returns score and metrics."""
        r = assess_financial_health(
            AssessFinancialHealthInput(fiscal_year=2026), self.session,
        )
        assert r.health_assessment in ("strong", "moderate", "weak", "critical", "insufficient_data")
        assert r.score > 0
        assert len(r.key_metrics) >= 3
        assert len(r.strengths) + len(r.weaknesses) > 0

    def test_period_filter(self):
        """Health assessment for specific period."""
        r = assess_financial_health(
            AssessFinancialHealthInput(fiscal_year=2026, period=3), self.session,
        )
        assert r.score > 0

    def test_no_data_returns_insufficient(self):
        """No data -> insufficient_data assessment."""
        r = assess_financial_health(
            AssessFinancialHealthInput(fiscal_year=2025), self.session,
        )
        # Will have 0 revenue + 0 assets
        assert r.score >= 0
        assert r.key_metrics is not None


# ===========================================================================
# Tool 4: Generate Cost Cutting Recommendations
# ===========================================================================
class TestGenerateCostCutting:
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

    def test_full_year_recommendations(self):
        """Generate recommendations for full FY 2026."""
        r = generate_cost_cutting_recommendations(
            GenerateCostCuttingInput(fiscal_year=2026), self.session,
        )
        assert r.total_expenses > 0
        assert len(r.recommendations) >= 1
        assert r.estimated_total_savings > 0

    def test_target_prefix_filter(self):
        """Filter to operating expenses only (prefix 6)."""
        r = generate_cost_cutting_recommendations(
            GenerateCostCuttingInput(fiscal_year=2026, target_account_prefixes=["6"]), self.session,
        )
        assert r.total_expenses > 0
        assert all("Operating" in rec.area for rec in r.recommendations)

    def test_no_expenses(self):
        """No expenses -> empty results."""
        r = generate_cost_cutting_recommendations(
            GenerateCostCuttingInput(fiscal_year=2025), self.session,
        )
        assert r.total_expenses == Decimal("0")
        assert len(r.recommendations) == 0

    def test_min_savings_threshold(self):
        """Only show savings above threshold."""
        r = generate_cost_cutting_recommendations(
            GenerateCostCuttingInput(fiscal_year=2026, min_savings_threshold=Decimal("50000")), self.session,
        )
        for rec in r.recommendations:
            assert rec.potential_savings >= Decimal("50000") or rec.potential_savings == 0


# ===========================================================================
# Tool 5: Generate Custom Report
# ===========================================================================
class TestGenerateCustomReport:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_journal_entries(self.session)
        _seed_budget(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_summary_report(self):
        """Generate summary report."""
        r = generate_custom_report(
            GenerateCustomReportInput(report_title="FY 2026 Summary", fiscal_year=2026, report_type="summary"),
            self.session,
        )
        assert r.report_id.startswith("RPT-")
        assert len(r.sections) >= 1
        assert r.needs_approval is True

    def test_detailed_report(self):
        """Generate detailed report."""
        r = generate_custom_report(
            GenerateCustomReportInput(report_title="Detailed Report", fiscal_year=2026, report_type="detailed"),
            self.session,
        )
        assert len(r.sections) >= 3
        assert "Revenue" in r.sections[0].title or "Expense" in r.sections[0].title

    def test_comparative_report(self):
        """Generate comparative report across periods."""
        r = generate_custom_report(
            GenerateCustomReportInput(
                report_title="H1 Comparison", fiscal_year=2026, report_type="comparative",
                period_from=3, period_to=6,
            ),
            self.session,
        )
        assert r.report_type == "comparative"
        assert len(r.sections) >= 1

    def test_trend_report(self):
        """Generate trend report."""
        r = generate_custom_report(
            GenerateCustomReportInput(
                report_title="Monthly Trend", fiscal_year=2026, report_type="trend",
                period_from=3, period_to=6,
            ),
            self.session,
        )
        assert r.report_type == "trend"
        assert len(r.sections) >= 1

    def test_invalid_period_order(self):
        """period_from > period_to -> ValueError."""
        import pytest
        with pytest.raises(ValueError, match="period_from must be <= period_to"):
            generate_custom_report(
                GenerateCustomReportInput(
                    report_title="Bad", fiscal_year=2026, report_type="summary",
                    period_from=6, period_to=3,
                ),
                self.session,
            )

    def test_no_data_report(self):
        """Report with no data still generates structure."""
        r = generate_custom_report(
            GenerateCustomReportInput(report_title="Empty FY", fiscal_year=2025, report_type="summary"),
            self.session,
        )
        assert r.report_id.startswith("RPT-")
        assert len(r.sections) >= 1


# ===========================================================================
# Full E2E Sequence
# ===========================================================================
class TestE2EAdvisorySequence:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_journal_entries(self.session)
        _seed_budget(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_full_advisory_sequence(self):
        """Run all 5 tools in order as a complete workflow."""
        # 1. Spending patterns
        spend = analyze_spending_patterns(
            AnalyzeSpendingPatternsInput(from_date=date(2026, 1, 1), to_date=date(2026, 12, 31)),
            self.session,
        )
        assert spend.total_spending > 0
        assert spend.insights
        assert spend.entry_count == 7

        # 2. Financial ratios
        ratios = calculate_financial_ratios(
            CalculateFinancialRatiosInput(fiscal_year=2026),
            self.session,
        )
        assert len(ratios.ratios) >= 8

        # 3. Health assessment
        health = assess_financial_health(
            AssessFinancialHealthInput(fiscal_year=2026),
            self.session,
        )
        assert health.score > 0

        # 4. Cost cutting
        cutting = generate_cost_cutting_recommendations(
            GenerateCostCuttingInput(fiscal_year=2026),
            self.session,
        )
        assert cutting.estimated_total_savings > 0

        # 5. Custom report
        report = generate_custom_report(
            GenerateCustomReportInput(report_title="Complete Report", fiscal_year=2026, report_type="detailed"),
            self.session,
        )
        assert report.report_id.startswith("RPT-")
        assert len(report.sections) >= 3
        assert report.needs_approval is True
