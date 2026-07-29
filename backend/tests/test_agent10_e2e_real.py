"""Agent 10 E2E test — real Groq API through Orchestrator.

Tests all 4 tools: 2 non-approval + 2 approval.
"""
import sys, os, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

if sys.platform == "win32":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1, errors="replace", closefd=False)

from datetime import date, timedelta
from decimal import Decimal

from db.models import (
    JournalEntry, SystemConfig, SystemBackupLog,
)
from agent_defs.orchestrator import run_orchestrator


def seed_data():
    from db.database import init_db, get_session
    init_db()
    s = get_session()
    for t in [JournalEntry, SystemConfig, SystemBackupLog]:
        s.query(t).delete()
    s.commit()

    today = date.today()

    # System config
    s.add(SystemConfig(config_key="company_name", config_value="AI Accountant Inc", description="Company legal name", updated_at=today))
    s.add(SystemConfig(config_key="default_currency", config_value="PKR", description="Default currency", updated_at=today))
    s.add(SystemConfig(config_key="backup_enabled", config_value="true", description="Automatic backups enabled", updated_at=today))
    s.add(SystemConfig(config_key="fiscal_year_end", config_value="2026-12-31", description="Fiscal year end", updated_at=today))
    s.add(SystemConfig(config_key="retention_days", config_value="90", description="Data retention", updated_at=today))

    # Backup logs
    s.add(SystemBackupLog(backup_id="BK-001", backup_type="backup", status="completed", triggered_by="system",
        triggered_at=today - timedelta(days=7), completed_at=today - timedelta(days=7), size_bytes=2048000, notes="Weekly backup", parameters='{}'))
    s.add(SystemBackupLog(backup_id="BK-002", backup_type="backup", status="completed", triggered_by="system",
        triggered_at=today - timedelta(days=3), completed_at=today - timedelta(days=3), size_bytes=4096000, notes="Daily backup", parameters='{}'))
    s.add(SystemBackupLog(backup_id="BK-003", backup_type="export_data", status="failed", triggered_by="admin",
        triggered_at=today - timedelta(days=1), notes="Export attempt", parameters='{"scope":"all"}'))

    s.commit()
    s.close()
    print("  Seed data ready")


async def run_e2e():
    print("=" * 70)
    print("E2E TEST: Agent 10 (System Admin)")
    print("Orchestrator -> System Admin Agent -> 4 tools")
    print("=" * 70)

    results = []

    async def test(seq, name, query):
        print(f"\n  [{seq}/4] {name}")
        print(f"  Q: {query[:100]}...")
        start = asyncio.get_event_loop().time()
        try:
            resp = await run_orchestrator(query)
            elapsed = asyncio.get_event_loop().time() - start
            safe = resp[:400].encode("utf-8", errors="replace").decode("utf-8", errors="replace")
            ok = len(resp) > 20 and "Error" not in resp[:50]
            print(f"  {'PASS' if ok else 'FAIL'} ({elapsed:.1f}s)")
            print(f"  -> {safe}")
            results.append((seq, name, ok, elapsed))
        except Exception as e:
            elapsed = asyncio.get_event_loop().time() - start
            print(f"  FAIL ({elapsed:.1f}s): {type(e).__name__}: {e}")
            results.append((seq, name, False, elapsed))
        await asyncio.sleep(3)

    seed_data()

    # Tool 1: check_system_status (No approval)
    await test(1, "System Status",
        "Run a full system health check including database, providers, and agents")

    # Tool 2: get_usage_statistics (No approval)
    await test(2, "Usage Statistics",
        "Show me usage statistics for the last 30 days")

    # Tool 3: manage_system_preferences (Approval)
    await test(3, "View Preferences",
        "Show me all current system settings and company preferences")

    # Tool 4: schedule_system_task (Approval)
    await test(4, "Schedule Task",
        "Schedule a database backup task now")

    print("\n" + "=" * 70)
    passed = sum(1 for _, _, ok, _ in results if ok)
    print(f"RESULTS: {passed}/{len(results)} passed")
    for seq, name, ok, lat in results:
        print(f"  {'PASS' if ok else 'FAIL'}: Tool {seq} {name} ({lat:.1f}s)")
    print("=" * 70)
    return passed == len(results)


if __name__ == "__main__":
    success = asyncio.run(run_e2e())
    sys.exit(0 if success else 1)
