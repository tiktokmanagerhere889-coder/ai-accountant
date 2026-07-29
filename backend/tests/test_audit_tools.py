"""Tests for Audit & Regulatory tools (Agent 8).

Tests all 4 tools with PostgreSQL isolation per test class.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from db.models import Base, JournalEntry, FlaggedEntry, StatutoryRegister, ComplianceDeadline
from tools.audit_tools import (
    detect_anomaly_transactions, get_compliance_deadlines,
    support_internal_audit, maintain_statutory_registers,
)
from tools.schemas import (
    DetectAnomalyTransactionsInput, DetectAnomalyTransactionsOutput,
    GetComplianceDeadlinesInput, GetComplianceDeadlinesOutput,
    SupportInternalAuditInput, SupportInternalAuditOutput,
    MaintainStatutoryRegistersInput, MaintainStatutoryRegistersOutput,
)
from tests.test_helpers import TEST_DATABASE_URL


def _seed_basic_journal(session: Session):
    """Seed minimal journal entries for anomaly tests."""
    session.add(JournalEntry(
        entry_id="JE-001", description="Normal payroll",
        posted_date=date(2026, 7, 15), reference="PAY-001",
        debit_account="6100-Salary Expense", debit_amount=Decimal("150000.00"),
        credit_account="1000-Cash", credit_amount=Decimal("150000.00"),
        status="posted",
    ))
    # Round amount (multiple of 1000)
    session.add(JournalEntry(
        entry_id="JE-002", description="Large round payment",
        posted_date=date(2026, 7, 10), reference="INV-001",
        debit_account="5000-COGS", debit_amount=Decimal("500000.00"),
        credit_account="2000-Accounts Payable", credit_amount=Decimal("500000.00"),
        status="posted",
    ))
    # Weekend posting (Saturday)
    session.add(JournalEntry(
        entry_id="JE-003", description="Weekend transaction",
        posted_date=date(2026, 7, 11), reference="INV-002",  # Saturday
        debit_account="6000-Rent Expense", debit_amount=Decimal("50000.00"),
        credit_account="1000-Cash", credit_amount=Decimal("50000.00"),
        status="posted",
    ))
    # Duplicate of JE-001 on same date
    session.add(JournalEntry(
        entry_id="JE-004", description="Normal payroll",
        posted_date=date(2026, 7, 15), reference="PAY-002",
        debit_account="6100-Salary Expense", debit_amount=Decimal("150000.00"),
        credit_account="1000-Cash", credit_amount=Decimal("150000.00"),
        status="posted",
    ))
    # Unusual account: debit to equity
    session.add(JournalEntry(
        entry_id="JE-005", description="Equity adjustment",
        posted_date=date(2026, 7, 20), reference="ADJ-001",
        debit_account="3100-Retained Earnings", debit_amount=Decimal("25000.00"),
        credit_account="1000-Cash", credit_amount=Decimal("25000.00"),
        status="posted",
    ))
    session.commit()


def _seed_deadlines(session: Session):
    """Seed compliance deadlines."""
    today = date.today()
    session.add(ComplianceDeadline(
        deadline_id="DL-001", deadline_type="tax_filing",
        description="Sales tax filing for June 2026",
        due_date=today + timedelta(days=5),
        responsible_person="Accountant",
        status="upcoming", reminder_days=7, fiscal_year=2026,
    ))
    session.add(ComplianceDeadline(
        deadline_id="DL-002", deadline_type="statutory_filing",
        description="Annual return filing",
        due_date=today + timedelta(days=90),
        responsible_person="Company Secretary",
        status="upcoming", reminder_days=30, fiscal_year=2026,
    ))
    # Overdue
    session.add(ComplianceDeadline(
        deadline_id="DL-003", deadline_type="audit",
        description="Q2 audit report submission",
        due_date=today - timedelta(days=10),
        responsible_person="Auditor",
        status="upcoming", reminder_days=14, fiscal_year=2026,
    ))
    # Completed
    session.add(ComplianceDeadline(
        deadline_id="DL-004", deadline_type="tax_filing",
        description="Income tax filing FY2025",
        due_date=today - timedelta(days=60),
        responsible_person="Accountant",
        status="completed", reminder_days=30, fiscal_year=2025,
    ))
    session.commit()


# ===========================================================================
# Tool 1: Detect Anomaly Transactions
# ===========================================================================
class TestDetectAnomalyTransactions:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_basic_journal(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_round_amount_detected(self):
        """JE-002 (500000) should be flagged as round_amount."""
        inp = DetectAnomalyTransactionsInput(
            from_date=date(2026, 7, 1), to_date=date(2026, 7, 31),
            anomaly_types=["round_amount"],
        )
        r = detect_anomaly_transactions(inp, self.session)
        assert r.total_anomalies >= 1
        assert any(a.anomaly_type == "round_amount" for a in r.anomalies)
        assert any(a.entry_id == "JE-002" for a in r.anomalies)

    def test_weekend_posting_detected(self):
        """JE-003 (Saturday) should be flagged as weekend_posting."""
        inp = DetectAnomalyTransactionsInput(
            from_date=date(2026, 7, 1), to_date=date(2026, 7, 31),
            anomaly_types=["weekend_posting"],
        )
        r = detect_anomaly_transactions(inp, self.session)
        assert r.total_anomalies >= 1
        assert any(a.anomaly_type == "weekend_posting" for a in r.anomalies)
        assert any(a.entry_id == "JE-003" for a in r.anomalies)

    def test_duplicate_amount_detected(self):
        """JE-004 duplicates JE-001 amount/date/description."""
        inp = DetectAnomalyTransactionsInput(
            from_date=date(2026, 7, 1), to_date=date(2026, 7, 31),
            anomaly_types=["duplicate_amount"],
        )
        r = detect_anomaly_transactions(inp, self.session)
        assert r.total_anomalies >= 1
        assert any(a.anomaly_type == "duplicate_amount" for a in r.anomalies)

    def test_unusual_account_detected(self):
        """JE-005 debits equity account -> flagged."""
        inp = DetectAnomalyTransactionsInput(
            from_date=date(2026, 7, 1), to_date=date(2026, 7, 31),
            anomaly_types=["unusual_account"],
        )
        r = detect_anomaly_transactions(inp, self.session)
        assert r.total_anomalies >= 1
        assert any(a.anomaly_type == "unusual_account" for a in r.anomalies)
        assert any(a.entry_id == "JE-005" for a in r.anomalies)

    def test_all_detectors_run(self):
        """All 4 detectors run when no anomaly_types filter."""
        inp = DetectAnomalyTransactionsInput(
            from_date=date(2026, 7, 1), to_date=date(2026, 7, 31),
        )
        r = detect_anomaly_transactions(inp, self.session)
        assert r.total_anomalies >= 4  # at least one per detector type

    def test_empty_date_range(self):
        """No entries in range -> clean status."""
        inp = DetectAnomalyTransactionsInput(
            from_date=date(2025, 1, 1), to_date=date(2025, 1, 31),
        )
        r = detect_anomaly_transactions(inp, self.session)
        assert r.total_anomalies == 0
        assert r.status == "clean"

    def test_threshold_filter(self):
        """Only entries >= threshold flagged."""
        inp = DetectAnomalyTransactionsInput(
            from_date=date(2026, 7, 1), to_date=date(2026, 7, 31),
            threshold=Decimal("200000"),
        )
        r = detect_anomaly_transactions(inp, self.session)
        assert r.total_anomalies >= 0
        # JE-002 (500000) should still be found
        assert any(a.entry_id == "JE-002" for a in r.anomalies)


# ===========================================================================
# Tool 2: Get Compliance Deadlines
# ===========================================================================
class TestGetComplianceDeadlines:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_deadlines(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_all_deadlines(self):
        """No filters -> returns all deadlines."""
        inp = GetComplianceDeadlinesInput()
        r = get_compliance_deadlines(inp, self.session)
        assert len(r.deadlines) == 4
        assert r.overdue_count >= 1

    def test_filter_by_fiscal_year(self):
        """Filter by fiscal_year 2026 -> 3 entries."""
        inp = GetComplianceDeadlinesInput(fiscal_year=2026)
        r = get_compliance_deadlines(inp, self.session)
        assert len(r.deadlines) == 3

    def test_filter_by_type(self):
        """Filter tax_filing -> 2 entries."""
        inp = GetComplianceDeadlinesInput(deadline_type="tax_filing")
        r = get_compliance_deadlines(inp, self.session)
        assert len(r.deadlines) == 2

    def test_filter_by_status_completed(self):
        """Filter completed -> 1 entry."""
        inp = GetComplianceDeadlinesInput(status="completed")
        r = get_compliance_deadlines(inp, self.session)
        assert len(r.deadlines) == 1
        assert r.deadlines[0].deadline_id == "DL-004"

    def test_reminder_days_filter(self):
        """reminder_days=7 -> only deadlines due within 7 days."""
        inp = GetComplianceDeadlinesInput(reminder_days=7)
        r = get_compliance_deadlines(inp, self.session)
        # DL-001 due in 5 days should appear
        assert any(d.deadline_id == "DL-001" for d in r.deadlines)
        # DL-002 due in 90 days should not
        assert not any(d.deadline_id == "DL-002" for d in r.deadlines)

    def test_no_deadlines_configured(self):
        """Empty table -> suggestion message."""
        # Clean all
        self.session.query(ComplianceDeadline).delete()
        self.session.commit()
        inp = GetComplianceDeadlinesInput()
        r = get_compliance_deadlines(inp, self.session)
        assert len(r.deadlines) == 0
        assert "No compliance deadlines configured" in r.summary


# ===========================================================================
# Tool 3: Support Internal Audit
# ===========================================================================
class TestSupportInternalAudit:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_basic_journal(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_audit_flags_found(self):
        """Full audit for FY2026 should find multiple flags."""
        inp = SupportInternalAuditInput(
            fiscal_year=2026, min_severity=None, include_resolved=False,
        )
        r = support_internal_audit(inp, self.session)
        assert r.total_flagged >= 1
        assert r.audit_id.startswith("AUD-")
        assert r.needs_approval is True

    def test_audit_no_entries(self):
        """Fiscal year with no entries -> empty result."""
        inp = SupportInternalAuditInput(fiscal_year=2025)
        r = support_internal_audit(inp, self.session)
        assert r.total_flagged == 0
        assert "No journal entries found" in r.summary

    def test_audit_persists_to_flagged_entries(self):
        """Flags should be stored in flagged_entries table."""
        inp = SupportInternalAuditInput(fiscal_year=2026)
        support_internal_audit(inp, self.session)
        count = self.session.query(FlaggedEntry).count()
        assert count >= 1

    def test_audit_min_severity_filter(self):
        """min_severity=high -> only high severity flags."""
        inp = SupportInternalAuditInput(
            fiscal_year=2026, min_severity="high",
        )
        r = support_internal_audit(inp, self.session)
        for f in r.flagged_entries:
            assert f.severity in ("high", "critical")

    def test_audit_period_filter(self):
        """Period filter restricts date range."""
        # July = period 7, should find entries
        inp = SupportInternalAuditInput(fiscal_year=2026, period=7)
        r = support_internal_audit(inp, self.session)
        assert r.total_flagged >= 1


# ===========================================================================
# Tool 4: Maintain Statutory Registers
# ===========================================================================
class TestMaintainStatutoryRegisters:
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

    def test_add_entry(self):
        """Add a director register entry."""
        inp = MaintainStatutoryRegistersInput(
            action="add", register_type="directors",
            entry_date=date(2026, 7, 1),
            description="Appointment of Ali Khan as CEO",
            reference_number="DIR-001",
        )
        r = maintain_statutory_registers(inp, self.session)
        assert r.action_performed == "add"
        assert r.register_id.startswith("REG-DIR-")
        assert r.status == "pending_approval"
        assert r.needs_approval is True

    def test_add_with_amount(self):
        """Add a members register entry with amount."""
        inp = MaintainStatutoryRegistersInput(
            action="add", register_type="members",
            entry_date=date(2026, 7, 15),
            description="Share issuance to Sara Khan",
            reference_number="SHR-001",
            amount=Decimal("1000000.00"),
        )
        r = maintain_statutory_registers(inp, self.session)
        assert r.action_performed == "add"
        assert r.amount == Decimal("1000000.00")

    def test_view_entries(self):
        """View entries in a register."""
        # Add one first
        self.test_add_entry()
        inp = MaintainStatutoryRegistersInput(
            action="view", register_type="directors",
            entry_date=date(2026, 7, 1),
            description="View",
        )
        r = maintain_statutory_registers(inp, self.session)
        assert r.action_performed == "view"
        assert "Found" in r.message
        assert r.needs_approval is False

    def test_view_empty_register(self):
        """View empty register -> appropriate message."""
        inp = MaintainStatutoryRegistersInput(
            action="view", register_type="charges",
            entry_date=date(2026, 7, 1),
            description="View",
        )
        r = maintain_statutory_registers(inp, self.session)
        assert r.action_performed == "view"
        assert "No entries found" in r.description
        assert r.status == "empty"

    def test_update_entry(self):
        """Update an existing register entry."""
        # Add first
        self.test_add_entry()
        existing = self.session.query(StatutoryRegister).first()
        inp = MaintainStatutoryRegistersInput(
            action="update", register_type="directors",
            entry_date=date(2026, 7, 1),
            description="Updated: Ali Khan as CEO with extended term",
            reference_number="DIR-001-UPD",
            register_id=existing.register_id,
        )
        r = maintain_statutory_registers(inp, self.session)
        assert r.action_performed == "update"
        assert "updated" in r.message.lower()
        assert r.needs_approval is True

    def test_delete_entry(self):
        """Delete an existing register entry."""
        self.test_add_entry()
        existing = self.session.query(StatutoryRegister).first()
        inp = MaintainStatutoryRegistersInput(
            action="delete", register_type="directors",
            entry_date=date(2026, 7, 1),
            description="Delete",
            register_id=existing.register_id,
        )
        r = maintain_statutory_registers(inp, self.session)
        assert r.action_performed == "delete"
        assert r.status == "deleted"
        # Verify deleted
        assert self.session.query(StatutoryRegister).count() == 0

    def test_invalid_action(self):
        """Invalid action -> ValueError."""
        import pytest
        inp = MaintainStatutoryRegistersInput(
            action="invalid", register_type="directors",
            entry_date=date(2026, 7, 1),
            description="Test",
        )
        with pytest.raises(ValueError, match="Invalid action"):
            maintain_statutory_registers(inp, self.session)

    def test_invalid_register_type(self):
        """Invalid register_type -> ValueError."""
        import pytest
        inp = MaintainStatutoryRegistersInput(
            action="add", register_type="invalid_type",
            entry_date=date(2026, 7, 1),
            description="Test",
        )
        with pytest.raises(ValueError, match="Invalid register_type"):
            maintain_statutory_registers(inp, self.session)

    def test_delete_nonexistent(self):
        """Delete non-existent register_id -> ValueError."""
        import pytest
        inp = MaintainStatutoryRegistersInput(
            action="delete", register_type="directors",
            entry_date=date(2026, 7, 1),
            description="Delete",
            register_id="REG-NONEXISTENT",
        )
        with pytest.raises(ValueError, match="not found"):
            maintain_statutory_registers(inp, self.session)

    def test_duplicate_reference_note(self):
        """Add with duplicate reference -> note appended to message."""
        self.test_add_entry()
        inp = MaintainStatutoryRegistersInput(
            action="add", register_type="directors",
            entry_date=date(2026, 8, 1),
            description="Another director appointment",
            reference_number="DIR-001",
        )
        r = maintain_statutory_registers(inp, self.session)
        assert "already exists" in r.message


# ===========================================================================
# Full E2E Sequence
# ===========================================================================
class TestE2EAuditSequence:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_basic_journal(self.session)
        _seed_deadlines(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_full_audit_sequence(self):
        """Run all 4 tools in order as a complete workflow."""
        # 1. Detect anomalies
        anom = detect_anomaly_transactions(
            DetectAnomalyTransactionsInput(from_date=date(2026, 7, 1), to_date=date(2026, 7, 31)),
            self.session,
        )
        assert anom.total_anomalies > 0
        assert "anomalies_detected" in anom.status

        # 2. Get compliance deadlines
        dl = get_compliance_deadlines(
            GetComplianceDeadlinesInput(fiscal_year=2026),
            self.session,
        )
        assert len(dl.deadlines) == 3

        # 3. Run internal audit
        audit = support_internal_audit(
            SupportInternalAuditInput(fiscal_year=2026),
            self.session,
        )
        assert audit.total_flagged > 0
        assert audit.audit_id.startswith("AUD-")

        # 4. Add a statutory register entry
        reg = maintain_statutory_registers(
            MaintainStatutoryRegistersInput(
                action="add", register_type="beneficial_owners",
                entry_date=date(2026, 7, 20),
                description="Beneficial ownership declaration - Omar Khan",
                reference_number="BO-001",
            ),
            self.session,
        )
        assert reg.action_performed == "add"
        assert reg.register_id.startswith("REG-BEN-")
        assert reg.needs_approval is True

        # Verify persistence
        assert self.session.query(FlaggedEntry).count() > 0
        assert self.session.query(StatutoryRegister).count() == 1
