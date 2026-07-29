"""Tests for System Admin tools (Agent 10).

Tests all 4 tools with PostgreSQL isolation per test class.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from db.models import Base, SystemConfig, SystemBackupLog
from tools.system_admin_tools import (
    check_system_status, get_usage_statistics,
    manage_system_preferences, schedule_system_task,
)
from tools.schemas import (
    CheckSystemStatusInput, CheckSystemStatusOutput,
    GetUsageStatisticsInput, GetUsageStatisticsOutput,
    ManageSystemPreferencesInput, ManageSystemPreferencesOutput,
    ScheduleSystemTaskInput, ScheduleSystemTaskOutput,
)
from tests.test_helpers import TEST_DATABASE_URL


def _seed_config(session: Session):
    """Seed default system config."""
    today = date.today()
    session.add(SystemConfig(config_key="company_name", config_value="Test Company", description="Company name", updated_at=today))
    session.add(SystemConfig(config_key="default_currency", config_value="PKR", description="Default currency", updated_at=today))
    session.add(SystemConfig(config_key="backup_enabled", config_value="true", description="Backup enabled", updated_at=today))
    session.commit()


def _seed_backup_logs(session: Session):
    """Seed backup log entries."""
    today = date.today()
    session.add(SystemBackupLog(
        backup_id="BAK-001", backup_type="backup", status="completed",
        triggered_by="system", triggered_at=today - timedelta(days=5),
        completed_at=today - timedelta(days=5), size_bytes=1024000,
        notes="Scheduled backup", parameters='{}',
    ))
    session.add(SystemBackupLog(
        backup_id="BAK-002", backup_type="backup", status="completed",
        triggered_by="system", triggered_at=today - timedelta(days=3),
        completed_at=today - timedelta(days=3), size_bytes=2048000,
        notes="Scheduled backup", parameters='{}',
    ))
    session.add(SystemBackupLog(
        backup_id="BAK-003", backup_type="export_data", status="failed",
        triggered_by="admin", triggered_at=today - timedelta(days=1),
        notes="Manual export attempt", parameters='{"scope":"all"}',
    ))
    session.commit()


# ===========================================================================
# Tool 1: Check System Status
# ===========================================================================
class TestCheckSystemStatus:
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

    def test_all_checks(self):
        """All checks (database, providers, agents) should run."""
        inp = CheckSystemStatusInput(check_type=["all"])
        r = check_system_status(inp, self.session)
        assert r.overall_status in ("healthy", "degraded", "unhealthy")
        assert len(r.checks) >= 3  # db + providers + agents
        # Database should always be healthy
        db_check = next(c for c in r.checks if c.name == "database")
        assert db_check.status == "healthy"

    def test_database_only(self):
        """Only database check."""
        inp = CheckSystemStatusInput(check_type=["database"])
        r = check_system_status(inp, self.session)
        assert len(r.checks) == 1
        assert r.checks[0].name == "database"

    def test_providers_only(self):
        """Only providers check."""
        inp = CheckSystemStatusInput(check_type=["providers"])
        r = check_system_status(inp, self.session)
        assert len(r.checks) == 1
        assert r.checks[0].name == "providers"

    def test_agents_only(self):
        """Only agents check."""
        inp = CheckSystemStatusInput(check_type=["agents"])
        r = check_system_status(inp, self.session)
        assert len(r.checks) == 1
        assert r.checks[0].name == "agents"

    def test_default_is_all(self):
        """Empty check_type runs all checks."""
        inp = CheckSystemStatusInput()
        r = check_system_status(inp, self.session)
        assert len(r.checks) >= 3


# ===========================================================================
# Tool 2: Get Usage Statistics
# ===========================================================================
class TestGetUsageStatistics:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_backup_logs(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_all_logs(self):
        """Returns all backup logs in date range."""
        inp = GetUsageStatisticsInput(
            from_date=date(2026, 1, 1), to_date=date(2026, 12, 31),
        )
        r = get_usage_statistics(inp, self.session)
        assert r.total_requests == 3
        assert r.success_count == 2
        assert r.failure_count == 1

    def test_no_data(self):
        """Empty date range -> empty results."""
        inp = GetUsageStatisticsInput(
            from_date=date(2025, 1, 1), to_date=date(2025, 1, 31),
        )
        r = get_usage_statistics(inp, self.session)
        assert r.total_requests == 0

    def test_breakdown_by_type(self):
        """Breakdown by backup_type."""
        inp = GetUsageStatisticsInput(
            from_date=date(2026, 1, 1), to_date=date(2026, 12, 31),
        )
        r = get_usage_statistics(inp, self.session)
        assert len(r.breakdown) >= 2  # backup and export_data
        backup_type = next(b for b in r.breakdown if b.dimension == "backup")
        assert backup_type.requests == 2


# ===========================================================================
# Tool 3: Manage System Preferences
# ===========================================================================
class TestManageSystemPreferences:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_config(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_view_all(self):
        """View all settings."""
        inp = ManageSystemPreferencesInput(action="view")
        r = manage_system_preferences(inp, self.session)
        assert r.action_performed == "view"
        assert len(r.settings) >= 3
        assert r.settings.get("company_name") == "Test Company"

    def test_view_single(self):
        """View single setting by key."""
        inp = ManageSystemPreferencesInput(action="view", setting_key="company_name")
        r = manage_system_preferences(inp, self.session)
        assert r.action_performed == "view"
        assert r.settings.get("company_name") == "Test Company"

    def test_view_nonexistent(self):
        """View non-existent key -> message."""
        inp = ManageSystemPreferencesInput(action="view", setting_key="nonexistent")
        r = manage_system_preferences(inp, self.session)
        assert "not found" in r.message

    def test_update_existing(self):
        """Update an existing setting."""
        inp = ManageSystemPreferencesInput(
            action="update",
            settings={"company_name": "New Company Inc."},
        )
        r = manage_system_preferences(inp, self.session)
        assert r.action_performed == "update"
        assert "company_name" in r.changed_keys
        assert r.needs_approval is True

    def test_update_new_key(self):
        """Update with new key -> creates with warning."""
        inp = ManageSystemPreferencesInput(
            action="update",
            settings={"new_setting": "new_value"},
        )
        r = manage_system_preferences(inp, self.session)
        assert "new_setting" in r.changed_keys
        assert "verify" in r.message

    def test_update_empty(self):
        """Update with no settings -> returns current config."""
        inp = ManageSystemPreferencesInput(action="update")
        r = manage_system_preferences(inp, self.session)
        assert r.action_performed == "update"
        assert len(r.changed_keys) == 0

    def test_reset_setting(self):
        """Reset a setting."""
        inp = ManageSystemPreferencesInput(action="reset", setting_key="company_name")
        r = manage_system_preferences(inp, self.session)
        assert r.action_performed == "reset"
        assert "company_name" in r.changed_keys

    def test_reset_nonexistent(self):
        """Reset non-existent setting -> ValueError."""
        import pytest
        inp = ManageSystemPreferencesInput(action="reset", setting_key="nonexistent")
        with pytest.raises(ValueError, match="not found"):
            manage_system_preferences(inp, self.session)

    def test_invalid_action(self):
        """Invalid action -> ValueError."""
        import pytest
        inp = ManageSystemPreferencesInput(action="invalid")
        with pytest.raises(ValueError, match="Invalid action"):
            manage_system_preferences(inp, self.session)


# ===========================================================================
# Tool 4: Schedule System Task
# ===========================================================================
class TestScheduleSystemTask:
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

    def test_schedule_backup(self):
        """Schedule a backup task."""
        inp = ScheduleSystemTaskInput(task_type="backup", schedule_time="now")
        r = schedule_system_task(inp, self.session)
        assert r.task_id.startswith("TASK-")
        assert r.task_type == "backup"
        assert r.status == "scheduled"
        assert r.needs_approval is True

    def test_schedule_export(self):
        """Schedule an export task with parameters."""
        inp = ScheduleSystemTaskInput(
            task_type="export_data",
            schedule_time="off_peak",
            parameters={"scope": "journal_entries"},
        )
        r = schedule_system_task(inp, self.session)
        assert r.task_type == "export_data"
        assert "off-peak" in r.message

    def test_schedule_maintenance(self):
        """Schedule maintenance task."""
        inp = ScheduleSystemTaskInput(task_type="maintenance")
        r = schedule_system_task(inp, self.session)
        assert r.task_type == "maintenance"
        assert r.status == "scheduled"

    def test_invalid_task_type(self):
        """Invalid task_type -> ValueError."""
        import pytest
        inp = ScheduleSystemTaskInput(task_type="invalid_type")
        with pytest.raises(ValueError, match="Invalid task_type"):
            schedule_system_task(inp, self.session)

    def test_task_persisted(self):
        """Task is persisted to system_backup_log."""
        inp = ScheduleSystemTaskInput(task_type="cleanup")
        schedule_system_task(inp, self.session)
        count = self.session.query(SystemBackupLog).count()
        assert count == 1
        log = self.session.query(SystemBackupLog).first()
        assert log.backup_type == "cleanup"
        assert log.status == "scheduled"


# ===========================================================================
# Full E2E Sequence
# ===========================================================================
class TestE2ESystemAdminSequence:
    def setup_method(self):
        self.engine = create_engine(TEST_DATABASE_URL, echo=False)
        with self.engine.connect() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
            c.commit()
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(bind=self.engine)
        _seed_config(self.session)
        _seed_backup_logs(self.session)

    def teardown_method(self):
        self.session.close()
        self.engine.dispose()

    def test_full_admin_sequence(self):
        """Run all 4 tools in order."""
        # 1. Check system status
        status = check_system_status(
            CheckSystemStatusInput(check_type=["all"]),
            self.session,
        )
        assert len(status.checks) >= 3

        # 2. Get usage stats
        stats = get_usage_statistics(
            GetUsageStatisticsInput(from_date=date(2026, 1, 1), to_date=date(2026, 12, 31)),
            self.session,
        )
        assert stats.total_requests == 3

        # 3. Manage preferences (view)
        prefs = manage_system_preferences(
            ManageSystemPreferencesInput(action="view"),
            self.session,
        )
        assert len(prefs.settings) >= 3

        # 4. Schedule a task
        task = schedule_system_task(
            ScheduleSystemTaskInput(task_type="backup", schedule_time="now",
                                    notes="Test backup"),
            self.session,
        )
        assert task.task_id.startswith("TASK-")
        assert task.needs_approval is True

        # Verify persistence
        assert self.session.query(SystemBackupLog).count() == 4  # 3 seed + 1 new
