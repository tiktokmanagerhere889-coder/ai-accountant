"""Tests for assess_fbr_audit_risk (self-contained FBR audit risk tool).

PostgreSQL isolation per test class against TEST_DATABASE_URL. Seeds posted
JournalEntry rows directly with sqlalchemy.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from db.models import Base, JournalEntry, TaxFiling, Contact
from tools.fbr_risk_tools import (
    assess_fbr_audit_risk,
    AssessFbrAuditRiskInput,
)
from tests.test_helpers import TEST_DATABASE_URL


def _add_entry(session, entry_id, posted_date, debit_account, debit_amount,
               credit_account, credit_amount, description="", contact_id=None):
    session.add(JournalEntry(
        entry_id=entry_id,
        description=description or entry_id,
        posted_date=posted_date,
        contact_id=contact_id,
        debit_account=debit_account,
        debit_amount=debit_amount,
        credit_account=credit_account,
        credit_amount=credit_amount,
        status="posted",
    ))


def _seed_normal_ledger(session, fy=2026, prev_fy=2025):
    """Revenue ~1M with ~40% COGS; prior year ~0.9M with ~40% COGS.

    Revenue rises year-on-year, COGS ratio is moderate, no refund, no finance
    cost -> a genuinely low-risk ledger.
    """
    _add_entry(session, f"REV-{fy}", date(fy, 6, 15), "1000-Cash", Decimal("1000000.00"),
               "4000-Sales Revenue", Decimal("1000000.00"), "Sales revenue")
    _add_entry(session, f"COGS-{fy}", date(fy, 6, 10), "5000-Cost of Goods Sold", Decimal("400000.00"),
               "1000-Cash", Decimal("400000.00"), "Purchases")
    _add_entry(session, f"REV-{prev_fy}", date(prev_fy, 6, 15), "1000-Cash", Decimal("900000.00"),
               "4000-Sales Revenue", Decimal("900000.00"), "Sales revenue")
    _add_entry(session, f"COGS-{prev_fy}", date(prev_fy, 6, 10), "5000-Cost of Goods Sold", Decimal("360000.00"),
               "1000-Cash", Decimal("360000.00"), "Purchases")
    session.commit()


def _seed_declining_ledger(session, fy=2026, prev_fy=2025):
    """Current-year revenue well below prior year (50% decline)."""
    _add_entry(session, f"REV-{fy}", date(fy, 6, 15), "1000-Cash", Decimal("500000.00"),
               "4000-Sales Revenue", Decimal("500000.00"), "Sales revenue")
    _add_entry(session, f"COGS-{fy}", date(fy, 6, 10), "5000-Cost of Goods Sold", Decimal("200000.00"),
               "1000-Cash", Decimal("200000.00"), "Purchases")
    _add_entry(session, f"REV-{prev_fy}", date(prev_fy, 6, 15), "1000-Cash", Decimal("1000000.00"),
               "4000-Sales Revenue", Decimal("1000000.00"), "Sales revenue")
    _add_entry(session, f"COGS-{prev_fy}", date(prev_fy, 6, 10), "5000-Cost of Goods Sold", Decimal("400000.00"),
               "1000-Cash", Decimal("400000.00"), "Purchases")
    session.commit()


class TestAssessFbrAuditRisk:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine, checkfirst=False)
        self.session = Session(bind=self.engine)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def _run(self, **kwargs):
        inp = AssessFbrAuditRiskInput(fiscal_year=2026, **kwargs)
        return assess_fbr_audit_risk(inp, self.session)

    def _params(self, result):
        return {p.code: p for p in result.parameters}

    def test_clean_ledger_low_risk(self):
        """Normal revenue, normal COGS, no refund, no finance cost -> low band,
        nothing triggered."""
        _seed_normal_ledger(self.session)
        r = self._run()
        assert r.risk_band == "low"
        assert r.risk_score == Decimal("0")
        assert r.triggered_count == 0
        by_code = self._params(r)
        assert by_code["IT-02"].triggered is False   # revenue rose
        assert by_code["IT-08"].triggered is False   # COGS 40% < 80%
        assert by_code["IT-06"].triggered is False   # no finance cost
        assert by_code["IT-03"].triggered is False   # no refund
        assert "immune" not in r.summary.lower()

    def test_sales_decline_high_risk(self):
        """Revenue far below prior year -> IT-02 (and ST-01) triggered,
        band at least high."""
        _seed_declining_ledger(self.session)
        r = self._run()
        by_code = self._params(r)
        assert by_code["IT-02"].triggered is True
        assert r.risk_band in ("high", "critical")
        assert r.risk_score >= Decimal("25")
        assert r.triggered_count >= 1
        assert any(fi.param_code == "IT-02" for fi in r.flagged_items)

    def test_cogs_ratio_triggered_non_corporate(self):
        """COGS > 80% of revenue -> IT-08 triggered."""
        _add_entry(self.session, "REV-COGS", date(2026, 6, 15), "1000-Cash", Decimal("1000000.00"),
                   "4000-Sales Revenue", Decimal("1000000.00"), "Sales revenue")
        _add_entry(self.session, "COGS-HIGH", date(2026, 6, 10), "5000-Cost of Goods Sold", Decimal("850000.00"),
                   "1000-Cash", Decimal("850000.00"), "Purchases")
        self.session.commit()
        r = self._run()
        by_code = self._params(r)
        assert by_code["IT-08"].triggered is True
        assert r.risk_band in ("high", "critical")

    def test_prior_3yr_audited_immunity(self):
        """prior_3yr_audit_status='audited' -> exclusions non-empty, band low,
        score 0, even though the ledger would otherwise trigger parameters."""
        _seed_declining_ledger(self.session)
        r = self._run(prior_3yr_audit_status="audited")
        assert len(r.exclusions_applied) > 0
        assert "prior_3yr_audited" in r.exclusions_applied[0]
        assert r.risk_band == "low"
        assert r.risk_score == Decimal("0")
        assert "immune" in r.summary.lower()
        # parameter table still computed for information
        by_code = self._params(r)
        assert by_code["IT-02"].triggered is True

    def test_missing_manual_input_does_not_break_score(self):
        """No contacts data + no customs input -> ST-05 not_verifiable and
        IT-01 manual_input (both triggered None), but the score is still
        computed from the other (computed_from_ledger) parameters."""
        _seed_declining_ledger(self.session)
        r = self._run()
        by_code = self._params(r)
        assert by_code["ST-05"].confidence == "not_verifiable"
        assert by_code["ST-05"].triggered is None
        assert by_code["IT-01"].confidence == "manual_input"
        assert by_code["IT-01"].triggered is None
        assert r.risk_score > Decimal("0")
        assert r.triggered_count >= 1

    def test_corporate_refund_trigger(self):
        """Income filing with net_payable strongly negative (< -10M) ->
        IT-03 triggered for a corporate."""
        self.session.add(TaxFiling(
            filing_id="IT-2026", filing_type="income", fiscal_year=2026, period=None,
            total_revenue=Decimal("10000000"), total_expenses=Decimal("8000000"),
            tax_liability=Decimal("500000"), net_payable=Decimal("-20000000"),
            status="prepared",
        ))
        self.session.commit()
        r = self._run(business_type="corporate")
        by_code = self._params(r)
        assert by_code["IT-03"].triggered is True
        assert by_code["IT-03"].confidence == "computed_from_ledger"
        assert any(fi.param_code == "IT-03" for fi in r.flagged_items)
