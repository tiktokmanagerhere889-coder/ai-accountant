"""Tests for Year-End Close & Financial Statements tools (Agent 5).

Tests all 8 tools: trial balance, P&L, balance sheet, cash flow statement,
retained earnings, carry-forward, notes to financials, close fiscal year.

Uses PostgreSQL via TEST_DATABASE_URL. Each test class creates fresh schema.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from db.models import Base, JournalEntry, ChartOfAccount, FixedAsset, Loan, RetainedEarnings, FiscalYearClose
from tools.year_end_tools import (
    generate_trial_balance, generate_profit_loss, generate_balance_sheet,
    generate_cash_flow_statement, transfer_retained_earnings,
    carry_forward_balances, draft_notes_to_financials, close_fiscal_year,
)
from tools.schemas import (
    GenerateTrialBalanceInput, GenerateProfitLossInput, GenerateBalanceSheetInput,
    GenerateCashFlowInput, TransferRetainedEarningsInput,
    CarryForwardBalancesInput, DraftNotesToFinancialsInput, CloseFiscalYearInput,
)
from tests.test_helpers import TEST_DATABASE_URL


def _seed_full_chart(session: Session):
    """Seed comprehensive journal entries covering all prefix categories."""
    # Cash opening (1000)
    session.add(JournalEntry(
        entry_id="OPEN-001", description="Opening balance",
        posted_date=date(2026, 1, 1), reference=None,
        debit_account="1000-Cash", debit_amount=Decimal("500000.00"),
        credit_account="3000-Opening Equity", credit_amount=Decimal("500000.00"),
        status="posted",
    ))
    # Revenue (4xxx)
    session.add(JournalEntry(
        entry_id="REV-001", description="Sales revenue",
        posted_date=date(2026, 7, 15), reference="INV-001",
        debit_account="1000-Cash", debit_amount=Decimal("200000.00"),
        credit_account="4000-Sales Revenue", credit_amount=Decimal("200000.00"),
        status="posted",
    ))
    session.add(JournalEntry(
        entry_id="REV-002", description="Service income",
        posted_date=date(2026, 8, 15), reference="INV-002",
        debit_account="1000-Cash", debit_amount=Decimal("100000.00"),
        credit_account="4100-Service Revenue", credit_amount=Decimal("100000.00"),
        status="posted",
    ))
    # Expenses (6xxx)
    session.add(JournalEntry(
        entry_id="EXP-001", description="Rent expense July",
        posted_date=date(2026, 7, 31), reference=None,
        debit_account="6000-Rent Expense", debit_amount=Decimal("50000.00"),
        credit_account="1000-Cash", credit_amount=Decimal("50000.00"),
        status="posted",
    ))
    session.add(JournalEntry(
        entry_id="EXP-002", description="Salary expense",
        posted_date=date(2026, 7, 31), reference=None,
        debit_account="6100-Salary Expense", debit_amount=Decimal("120000.00"),
        credit_account="1000-Cash", credit_amount=Decimal("120000.00"),
        status="posted",
    ))
    session.add(JournalEntry(
        entry_id="EXP-003", description="Utilities expense",
        posted_date=date(2026, 8, 31), reference=None,
        debit_account="6200-Utilities Expense", debit_amount=Decimal("15000.00"),
        credit_account="1000-Cash", credit_amount=Decimal("15000.00"),
        status="posted",
    ))
    # AP / Liability (2xxx)
    session.add(JournalEntry(
        entry_id="LIAB-001", description="Vendor bill payable",
        posted_date=date(2026, 7, 20), reference="VENDOR-001",
        debit_account="6300-Office Supplies", debit_amount=Decimal("30000.00"),
        credit_account="2000-Accounts Payable", credit_amount=Decimal("30000.00"),
        status="posted",
    ))
    # Loan (2xxx for long-term)
    session.add(JournalEntry(
        entry_id="LOAN-001", description="Loan disbursement",
        posted_date=date(2026, 3, 1), reference="LN-001",
        debit_account="1000-Cash", debit_amount=Decimal("1000000.00"),
        credit_account="2100-Long Term Loan", credit_amount=Decimal("1000000.00"),
        status="posted",
    ))
    # Fixed asset (1xxx)
    session.add(JournalEntry(
        entry_id="ASSET-001", description="Purchase delivery truck",
        posted_date=date(2026, 6, 1), reference="FA-001",
        debit_account="1500-Delivery Truck", debit_amount=Decimal("2400000.00"),
        credit_account="1000-Cash", credit_amount=Decimal("2400000.00"),
        status="posted",
    ))
    session.commit()


class TestGenerateTrialBalance:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_full_chart(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_trial_balance_in_balance(self):
        """Trial balance should have debits = credits."""
        inp = GenerateTrialBalanceInput(as_of_date=date(2026, 12, 31))
        result = generate_trial_balance(inp, self.session)
        assert result.in_balance is True, f"Not in balance! Difference: {result.difference}"
        assert result.total_debits == result.total_credits
        assert result.total_debits > Decimal("0")

    def test_trial_balance_empty(self):
        """No entries -> empty accounts, in_balance true."""
        inp = GenerateTrialBalanceInput(as_of_date=date(2025, 1, 1))
        result = generate_trial_balance(inp, self.session)
        assert result.in_balance is True
        assert result.accounts == []
        assert result.total_debits == Decimal("0")


class TestGenerateProfitLoss:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_full_chart(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_pl_net_profit(self):
        """Q3 (Jul-Sep) revenue minus expenses = correct net."""
        inp = GenerateProfitLossInput(from_date=date(2026, 7, 1), to_date=date(2026, 9, 30))
        result = generate_profit_loss(inp, self.session)
        # Revenue: 200000 (sales) + 100000 (service) = 300000
        assert result.total_revenue == Decimal("300000.00")
        # Expenses: 50000 (rent) + 120000 (salary) + 15000 (utilities) + 30000 (supplies) = 215000
        assert result.total_expenses == Decimal("215000.00")
        assert result.net_income == Decimal("85000.00")
        assert "profit" in result.summary.lower()

    def test_pl_empty(self):
        """No entries for date range -> zero totals."""
        inp = GenerateProfitLossInput(from_date=date(2025, 1, 1), to_date=date(2025, 1, 31))
        result = generate_profit_loss(inp, self.session)
        assert result.total_revenue == Decimal("0")
        assert result.total_expenses == Decimal("0")
        assert result.net_income == Decimal("0")


class TestGenerateBalanceSheet:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_full_chart(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_balance_sheet_balanced(self):
        """Assets = Liabilities + Equity."""
        inp = GenerateBalanceSheetInput(as_of_date=date(2026, 12, 31))
        result = generate_balance_sheet(inp, self.session)
        assert result.balanced is True, f"Not balanced! Difference: {result.difference}"
        assert result.total_assets > Decimal("0")
        assert result.total_liabilities > Decimal("0") or result.total_equity > Decimal("0")

    def test_balance_sheet_empty(self):
        """No entries -> zero totals, balanced."""
        inp = GenerateBalanceSheetInput(as_of_date=date(2025, 1, 1))
        result = generate_balance_sheet(inp, self.session)
        assert result.balanced is True
        assert result.total_assets == Decimal("0")


class TestGenerateCashFlowStatement:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_full_chart(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_cash_flow_reconciliation(self):
        """Closing = Opening + Net Change."""
        inp = GenerateCashFlowInput(from_date=date(2026, 7, 1), to_date=date(2026, 9, 30))
        result = generate_cash_flow_statement(inp, self.session)
        # Opening cash = 500000 (opening) + 1000000 (loan) - 2400000 (truck) + ... before July
        # Actually let's just verify the basic math
        assert result.closing_cash == result.opening_cash + result.net_change_in_cash
        assert result.net_change_in_cash == result.net_operating + result.net_investing + result.net_financing

    def test_cash_flow_empty(self):
        """No entries -> zero everything."""
        inp = GenerateCashFlowInput(from_date=date(2025, 1, 1), to_date=date(2025, 1, 31))
        result = generate_cash_flow_statement(inp, self.session)
        assert result.opening_cash == Decimal("0")
        assert result.closing_cash == Decimal("0")
        assert result.net_change_in_cash == Decimal("0")


class TestTransferRetainedEarnings:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_full_chart(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_retained_earnings(self):
        """Net income transferred correctly."""
        inp = TransferRetainedEarningsInput(fiscal_year=2026)
        result = transfer_retained_earnings(inp, self.session)
        assert result.fiscal_year == 2026
        # Revenue: 200000 + 100000 = 300000
        # Expenses: 50000+120000+15000+30000 = 215000
        # Net: 85000
        assert result.net_income == Decimal("85000.00")
        assert result.ending_retained_earnings == result.beginning_retained_earnings + result.net_income
        # Verify stored in DB
        re_record = self.session.query(RetainedEarnings).filter_by(fiscal_year=2026).first()
        assert re_record is not None
        assert re_record.ending_balance == Decimal("85000.00")


class TestCarryForwardBalances:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_full_chart(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_carry_forward(self):
        """Permanent accounts carried forward."""
        inp = CarryForwardBalancesInput(
            from_fiscal_year=2026, to_fiscal_year=2027,
            closing_date=date(2026, 12, 31),
        )
        result = carry_forward_balances(inp, self.session)
        assert result.accounts_carried_forward > 0
        assert result.status == "completed"


class TestDraftNotesToFinancials:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        # Seed a fixed asset for depreciation note
        self.session.add(FixedAsset(
            asset_id="FA-TEST", asset_name="Test Machine",
            asset_category="machinery", purchase_cost=Decimal("100000.00"),
            purchase_date=date(2026, 1, 1), useful_life_years=5,
            depreciation_method="straight_line", residual_value=Decimal("10000.00"),
            current_book_value=Decimal("100000.00"), status="approved",
        ))
        self.session.commit()

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_draft_notes(self):
        """All requested note types generated."""
        inp = DraftNotesToFinancialsInput(
            fiscal_year=2026,
            note_types=["accounting_policies", "depreciation_method", "commitments", "contingencies"],
        )
        result = draft_notes_to_financials(inp, self.session)
        assert len(result.notes) >= 3
        assert result.disclaimer != ""


class TestCloseFiscalYear:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_full_chart(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_close_without_confirm_raises(self):
        """confirm=False raises ValueError."""
        inp = CloseFiscalYearInput(fiscal_year=2026, closing_date=date(2026, 12, 31), confirm=False)
        try:
            close_fiscal_year(inp, self.session)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "confirm" in str(e).lower()

    def test_close_fiscal_year(self):
        """Successfully close fiscal year."""
        inp = CloseFiscalYearInput(fiscal_year=2026, closing_date=date(2026, 12, 31), confirm=True)
        result = close_fiscal_year(inp, self.session)
        assert result.status == "closed"
        assert result.closing_entries_created > 0
        assert result.net_income_transferred == Decimal("85000.00")

    def test_double_close_raises(self):
        """Closing already-closed year raises ValueError."""
        inp = CloseFiscalYearInput(fiscal_year=2026, closing_date=date(2026, 12, 31), confirm=True)
        close_fiscal_year(inp, self.session)

        # Try again
        inp2 = CloseFiscalYearInput(fiscal_year=2026, closing_date=date(2026, 12, 31), confirm=True)
        try:
            close_fiscal_year(inp2, self.session)
            assert False, "Should have raised ValueError for double close"
        except ValueError as e:
            assert "already closed" in str(e).lower()

    def test_close_no_entries_handles_gracefully(self):
        """Empty year -> still creates FiscalYearClose record."""
        # Clean session with no data
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        clean_session = Session(bind=self.engine)

        inp = CloseFiscalYearInput(fiscal_year=2025, closing_date=date(2025, 12, 31), confirm=True)
        result = close_fiscal_year(inp, clean_session)
        assert result.status == "closed"
        clean_session.close()


# ---------------------------------------------------------------------------
# Full E2E: All 8 tools in sequence
# ---------------------------------------------------------------------------

class TestE2EYearEndSequence:
    """Full end-to-end: trial balance -> P&L -> balance sheet -> cash flow ->
    retained earnings -> carry forward -> notes -> close fiscal year."""

    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_full_chart(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_e2e_year_end_sequence(self):
        """Run full year-end close sequence with verification at each step."""
        AS_OF = date(2026, 12, 31)
        JUL_SEP = (date(2026, 7, 1), date(2026, 9, 30))

        # Step 1: Trial Balance
        tb_inp = GenerateTrialBalanceInput(as_of_date=AS_OF)
        tb = generate_trial_balance(tb_inp, self.session)
        assert tb.in_balance is True, f"TB not balanced: diff={tb.difference}"
        assert tb.total_debits > Decimal("0")
        print(f"  TB: {len(tb.accounts)} accounts, debits={tb.total_debits}, credits={tb.total_credits}")

        # Step 2: P&L
        pl_inp = GenerateProfitLossInput(from_date=JUL_SEP[0], to_date=JUL_SEP[1])
        pl = generate_profit_loss(pl_inp, self.session)
        assert pl.net_income == Decimal("85000.00")
        assert len(pl.revenue_items) >= 1
        assert len(pl.expense_items) >= 1
        print(f"  P&L: revenue={pl.total_revenue}, expenses={pl.total_expenses}, net={pl.net_income}")

        # Step 3: Balance Sheet
        bs_inp = GenerateBalanceSheetInput(as_of_date=AS_OF)
        bs = generate_balance_sheet(bs_inp, self.session)
        assert bs.balanced is True, f"BS not balanced: diff={bs.difference}"
        # Verify accounting equation
        assert bs.total_assets == bs.total_liabilities + bs.total_equity, \
            f"Assets ({bs.total_assets}) != Liabilities ({bs.total_liabilities}) + Equity ({bs.total_equity})"
        print(f"  BS: assets={bs.total_assets}, liabilities={bs.total_liabilities}, equity={bs.total_equity}")

        # Step 4: Cash Flow Statement
        cf_inp = GenerateCashFlowInput(from_date=JUL_SEP[0], to_date=JUL_SEP[1])
        cf = generate_cash_flow_statement(cf_inp, self.session)
        assert cf.closing_cash == cf.opening_cash + cf.net_change_in_cash
        assert cf.net_change_in_cash == cf.net_operating + cf.net_investing + cf.net_financing
        print(f"  CF: opening={cf.opening_cash}, operating={cf.net_operating}, closing={cf.closing_cash}")

        # Step 5: Transfer Retained Earnings
        re_inp = TransferRetainedEarningsInput(fiscal_year=2026)
        re = transfer_retained_earnings(re_inp, self.session)
        assert re.net_income == Decimal("85000.00")
        assert re.ending_retained_earnings == re.beginning_retained_earnings + re.net_income
        print(f"  RE: beginning={re.beginning_retained_earnings}, net={re.net_income}, ending={re.ending_retained_earnings}")

        # Step 6: Carry Forward Balances
        cf_inp2 = CarryForwardBalancesInput(
            from_fiscal_year=2026, to_fiscal_year=2027,
            closing_date=AS_OF,
        )
        cf2 = carry_forward_balances(cf_inp2, self.session)
        assert cf2.accounts_carried_forward > 0
        print(f"  CFwd: {cf2.accounts_carried_forward} accounts")

        # Step 7: Draft Notes to Financials
        notes_inp = DraftNotesToFinancialsInput(
            fiscal_year=2026,
            note_types=["accounting_policies", "depreciation_method", "commitments"],
        )
        notes = draft_notes_to_financials(notes_inp, self.session)
        assert len(notes.notes) >= 2
        print(f"  Notes: {len(notes.notes)} notes drafted")

        # Step 8: Close Fiscal Year (approval-gated)
        close_inp = CloseFiscalYearInput(fiscal_year=2026, closing_date=AS_OF, confirm=True)
        close_result = close_fiscal_year(close_inp, self.session)
        assert close_result.status == "closed"
        assert close_result.closing_entries_created > 0
        print(f"  Close: {close_result.closing_entries_created} entries, transferred {close_result.net_income_transferred}")

        # Verify double-close prevention
        try:
            close_fiscal_year(CloseFiscalYearInput(fiscal_year=2026, closing_date=AS_OF, confirm=True), self.session)
            assert False, "Double close should raise"
        except ValueError:
            print("  Double-close prevention: OK")

        print("\n  ✅ All 8 tools in sequence PASSED")
