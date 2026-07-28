"""Tests for reconciliation & banking tools 5-6: track_cheque_clearing, track_lc_bank_guarantee.

Uses PostgreSQL via test_helpers.TEST_DATABASE_URL.
Each test class creates a fresh schema (drop_all + create_all) and seeds
its own data in setup_method, ensuring full isolation.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from db.models import Base, ChequeRegistry, LCBGRegistry
from tools.schemas import (
    TrackChequeClearingInput,
    TrackLCBGInput,
)
from tools.reconciliation_tools import track_cheque_clearing, track_lc_bank_guarantee
from tests.test_helpers import TEST_DATABASE_URL

_ENGINE = create_engine(TEST_DATABASE_URL, echo=False)
_ADMIN_ENGINE = create_engine(TEST_DATABASE_URL, echo=False, pool_pre_ping=True)


def _reset_schema():
    """Drop and recreate the public schema to fully clean PostgreSQL state."""
    _ENGINE.dispose()
    with _ADMIN_ENGINE.connect() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()
    Base.metadata.create_all(bind=_ENGINE)


class TestTrackChequeClearing:
    """Tests for track_cheque_clearing (Tool 5) — cheque lifecycle management."""

    def setup_method(self):
        _reset_schema()
        SessionLocal = sessionmaker(bind=_ENGINE)
        self.session = SessionLocal()

    def teardown_method(self):
        self.session.close()
        _ENGINE.dispose()

    # --- Tool 5: track_cheque_clearing ---

    def test_issue_cheque(self):
        """Issue a new cheque generates CHQ-NNN ID and returns issued status."""
        result = track_cheque_clearing(TrackChequeClearingInput(
            action="issue",
            vendor_name="ABC Vendor",
            amount=Decimal("50000.00"),
            issue_date=date(2026, 7, 1),
            bank_account_id="BA-001",
        ), self.session)
        assert result.action_performed == "issue"
        assert result.cheque_id.startswith("CHQ-")
        assert result.current_state.status == "issued"
        assert result.current_state.vendor_name == "ABC Vendor"
        assert result.current_state.amount == Decimal("50000.00")
        assert result.current_state.issue_date == date(2026, 7, 1)
        assert result.current_state.warning is None

        # Verify persisted
        db_record = self.session.query(ChequeRegistry).filter_by(cheque_id=result.cheque_id).first()
        assert db_record is not None
        assert db_record.status == "issued"
        assert db_record.vendor_name == "ABC Vendor"

    def test_clear_cheque(self):
        """Clearing an issued cheque updates status and sets clearing_date."""
        # First issue
        issue_result = track_cheque_clearing(TrackChequeClearingInput(
            action="issue",
            vendor_name="ABC Vendor",
            amount=Decimal("50000.00"),
            issue_date=date(2026, 6, 15),
            bank_account_id="BA-001",
        ), self.session)
        cheque_id = issue_result.cheque_id

        # Now clear
        result = track_cheque_clearing(TrackChequeClearingInput(
            action="clear",
            cheque_id=cheque_id,
        ), self.session)
        assert result.action_performed == "clear"
        assert result.current_state.status == "cleared"
        assert result.current_state.clearing_date == date.today()
        assert result.current_state.days_outstanding is None

    def test_bounce_cheque(self):
        """Bouncing a cheque sets status to bounced with warning."""
        issue_result = track_cheque_clearing(TrackChequeClearingInput(
            action="issue",
            vendor_name="ABC Vendor",
            amount=Decimal("50000.00"),
            issue_date=date(2026, 7, 1),
            bank_account_id="BA-001",
        ), self.session)
        cheque_id = issue_result.cheque_id

        result = track_cheque_clearing(TrackChequeClearingInput(
            action="bounce",
            cheque_id=cheque_id,
        ), self.session)
        assert result.action_performed == "bounce"
        assert result.current_state.status == "bounced"
        assert result.current_state.clearing_date is None
        assert "bounced" in (result.current_state.warning or "").lower()

    def test_reconcile_cheque(self):
        """Reconcile sets status to reconciled."""
        issue_result = track_cheque_clearing(TrackChequeClearingInput(
            action="issue",
            vendor_name="ABC Vendor",
            amount=Decimal("50000.00"),
            issue_date=date(2026, 7, 1),
            bank_account_id="BA-001",
        ), self.session)
        cheque_id = issue_result.cheque_id
        # Clear first
        track_cheque_clearing(TrackChequeClearingInput(
            action="clear", cheque_id=cheque_id,
        ), self.session)

        result = track_cheque_clearing(TrackChequeClearingInput(
            action="reconcile",
            cheque_id=cheque_id,
        ), self.session)
        assert result.action_performed == "reconcile"
        assert result.current_state.status == "reconciled"

    def test_cheque_status(self):
        """Status action returns current state without modifying."""
        issue_result = track_cheque_clearing(TrackChequeClearingInput(
            action="issue",
            vendor_name="ABC Vendor",
            amount=Decimal("50000.00"),
            issue_date=date(2026, 7, 1),
            bank_account_id="BA-001",
        ), self.session)
        cheque_id = issue_result.cheque_id

        result = track_cheque_clearing(TrackChequeClearingInput(
            action="status",
            cheque_id=cheque_id,
        ), self.session)
        assert result.action_performed == "status"
        assert result.current_state.status == "issued"

        # Verify no state change
        db_record = self.session.query(ChequeRegistry).filter_by(cheque_id=cheque_id).first()
        assert db_record.status == "issued"

    def test_duplicate_cheque_id_warning(self):
        """Issuing with an existing cheque_id returns warning instead of error."""
        result1 = track_cheque_clearing(TrackChequeClearingInput(
            action="issue",
            cheque_id="CHQ-DUP-001",
            vendor_name="Vendor A",
            amount=Decimal("50000.00"),
            issue_date=date(2026, 7, 1),
            bank_account_id="BA-001",
        ), self.session)
        assert result1.action_performed == "issue"
        assert result1.current_state.status == "issued"

        result2 = track_cheque_clearing(TrackChequeClearingInput(
            action="issue",
            cheque_id="CHQ-DUP-001",
            vendor_name="Vendor B",
            amount=Decimal("30000.00"),
            issue_date=date(2026, 7, 2),
            bank_account_id="BA-002",
        ), self.session)
        assert result2.action_performed == "issue"
        assert "already issued" in (result2.current_state.warning or "").lower()
        # Should still return original data
        assert result2.current_state.vendor_name == "Vendor A"

    def test_non_existent_cheque_raises_value_error(self):
        """Operations on non-existent cheques raise ValueError."""
        try:
            track_cheque_clearing(TrackChequeClearingInput(
                action="clear",
                cheque_id="CHQ-NONEXISTENT",
            ), self.session)
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "not found" in str(e)

    def test_stale_cheque_warning(self):
        """Cheque issued >180 days ago and not cleared gets stale warning on status."""
        issue_result = track_cheque_clearing(TrackChequeClearingInput(
            action="issue",
            vendor_name="Old Vendor",
            amount=Decimal("10000.00"),
            issue_date=date.today() - timedelta(days=200),
            bank_account_id="BA-001",
        ), self.session)
        cheque_id = issue_result.cheque_id

        result = track_cheque_clearing(TrackChequeClearingInput(
            action="status",
            cheque_id=cheque_id,
        ), self.session)
        assert result.current_state.status == "issued"
        assert result.current_state.warning is not None
        assert "stale" in result.current_state.warning.lower()

    def test_amount_warning(self):
        """Cheque amount > 1M triggers high-value warning on issue."""
        result = track_cheque_clearing(TrackChequeClearingInput(
            action="issue",
            vendor_name="Big Vendor",
            amount=Decimal("1500000.00"),
            issue_date=date(2026, 7, 1),
            bank_account_id="BA-001",
        ), self.session)
        assert result.current_state.warning is not None
        assert "1M" in result.current_state.warning or "exceeds" in result.current_state.warning.lower()


class TestTrackLCBG:
    """Tests for track_lc_bank_guarantee (Tool 6) — LC/BG lifecycle management."""

    def setup_method(self):
        _reset_schema()
        SessionLocal = sessionmaker(bind=_ENGINE)
        self.session = SessionLocal()

    def teardown_method(self):
        self.session.close()
        _ENGINE.dispose()

    # --- Tool 6: track_lc_bank_guarantee ---

    def test_issue_lc(self):
        """Issuing an LC generates LC-YYYYMM-NNN and returns active status."""
        result = track_lc_bank_guarantee(TrackLCBGInput(
            action="issue",
            type="LC",
            beneficiary="Supplier Co",
            amount=Decimal("1000000.00"),
            issue_date=date(2026, 7, 1),
            expiry_date=date(2026, 12, 31),
        ), self.session)
        assert result.action_performed == "issue"
        assert result.details.lc_id.startswith("LC-")
        assert result.details.type == "LC"
        assert result.details.status == "active"
        assert result.details.beneficiary == "Supplier Co"
        assert result.details.amount == Decimal("1000000.00")
        assert result.details.issue_date == date(2026, 7, 1)
        assert result.details.expiry_date == date(2026, 12, 31)
        assert result.needs_approval is True

        db_record = self.session.query(LCBGRegistry).filter_by(lc_id=result.details.lc_id).first()
        assert db_record is not None
        assert db_record.status == "active"
        assert db_record.type == "LC"

    def test_issue_bg(self):
        """Issuing a BG generates BG-YYYYMM-NNN and returns active status."""
        result = track_lc_bank_guarantee(TrackLCBGInput(
            action="issue",
            type="BG",
            beneficiary="Contractor Ltd",
            amount=Decimal("500000.00"),
            issue_date=date(2026, 7, 15),
            expiry_date=date(2027, 1, 15),
        ), self.session)
        assert result.action_performed == "issue"
        assert result.details.lc_id.startswith("BG-")
        assert result.details.type == "BG"
        assert result.details.status == "active"

    def test_amend_lc(self):
        """Amending an LC updates amount and beneficiary, status becomes amended."""
        issue_result = track_lc_bank_guarantee(TrackLCBGInput(
            action="issue",
            type="LC",
            beneficiary="Supplier Co",
            amount=Decimal("1000000.00"),
            issue_date=date(2026, 7, 1),
            expiry_date=date(2026, 12, 31),
        ), self.session)
        lc_id = issue_result.details.lc_id

        result = track_lc_bank_guarantee(TrackLCBGInput(
            action="amend",
            lc_id=lc_id,
            amount=Decimal("1200000.00"),
            beneficiary="Supplier Co Updated",
        ), self.session)
        assert result.action_performed == "amend"
        assert result.details.status == "amended"
        assert result.details.amount == Decimal("1200000.00")
        assert result.details.beneficiary == "Supplier Co Updated"

        # Verify notes contain previous version
        db_record = self.session.query(LCBGRegistry).filter_by(lc_id=lc_id).first()
        assert db_record.notes is not None
        assert "Previously" in db_record.notes

    def test_expire_lc(self):
        """Expiring an LC sets status to expired."""
        issue_result = track_lc_bank_guarantee(TrackLCBGInput(
            action="issue",
            type="LC",
            beneficiary="Supplier Co",
            amount=Decimal("500000.00"),
            issue_date=date(2026, 7, 1),
            expiry_date=date(2026, 12, 31),
        ), self.session)
        lc_id = issue_result.details.lc_id

        result = track_lc_bank_guarantee(TrackLCBGInput(
            action="expire",
            lc_id=lc_id,
        ), self.session)
        assert result.action_performed == "expire"
        assert result.details.status == "expired"
        assert result.details.days_to_expiry is None

    def test_close_lc(self):
        """Closing an LC before expiry adds early closure note."""
        issue_result = track_lc_bank_guarantee(TrackLCBGInput(
            action="issue",
            type="LC",
            beneficiary="Supplier Co",
            amount=Decimal("500000.00"),
            issue_date=date(2026, 7, 1),
            expiry_date=date(2026, 12, 31),
        ), self.session)
        lc_id = issue_result.details.lc_id

        result = track_lc_bank_guarantee(TrackLCBGInput(
            action="close",
            lc_id=lc_id,
        ), self.session)
        assert result.action_performed == "close"
        assert result.details.status == "closed"

        db_record = self.session.query(LCBGRegistry).filter_by(lc_id=lc_id).first()
        assert db_record.notes is not None
        assert "early" in db_record.notes.lower()

    def test_past_expiry_date_error(self):
        """Issuing LC with past expiry_date raises ValueError."""
        try:
            track_lc_bank_guarantee(TrackLCBGInput(
                action="issue",
                type="LC",
                beneficiary="Supplier Co",
                amount=Decimal("500000.00"),
                issue_date=date(2026, 1, 1),
                expiry_date=date(2025, 12, 31),
            ), self.session)
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "past" in str(e).lower()

    def test_non_existent_lc_raises_value_error(self):
        """Operations on non-existent LC/BG raise ValueError."""
        try:
            track_lc_bank_guarantee(TrackLCBGInput(
                action="amend",
                lc_id="LC-NONEXISTENT",
                amount=Decimal("100000.00"),
            ), self.session)
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "not found" in str(e)

    def test_expiring_within_30_days_warning(self):
        """Issuing LC expiring within 30 days returns a warning."""
        near_expiry = date.today() + timedelta(days=15)
        result = track_lc_bank_guarantee(TrackLCBGInput(
            action="issue",
            type="LC",
            beneficiary="Urgent Supplier",
            amount=Decimal("200000.00"),
            issue_date=date.today(),
            expiry_date=near_expiry,
        ), self.session)
        assert result.warning is not None
        assert "30 days" in result.warning

    def test_multiple_lc_same_beneficiary_notes(self):
        """Multiple active LCs for same beneficiary adds notes about it."""
        # Issue first LC
        result1 = track_lc_bank_guarantee(TrackLCBGInput(
            action="issue",
            type="LC",
            beneficiary="Common Supplier",
            amount=Decimal("300000.00"),
            issue_date=date(2026, 7, 1),
            expiry_date=date(2026, 12, 31),
        ), self.session)

        # Issue second LC for same beneficiary
        result2 = track_lc_bank_guarantee(TrackLCBGInput(
            action="issue",
            type="LC",
            beneficiary="Common Supplier",
            amount=Decimal("500000.00"),
            issue_date=date(2026, 7, 15),
            expiry_date=date(2027, 1, 15),
        ), self.session)
        assert result2.details.status == "active"

        db_record = self.session.query(LCBGRegistry).filter_by(
            lc_id=result2.details.lc_id
        ).first()
        assert db_record.notes is not None
        assert "Multiple" in db_record.notes
        assert result1.details.lc_id in db_record.notes
