# Agent: System Admin Agent

**Role:** System administration, health monitoring, configuration management, and maintenance scheduling. 4 tools, 2 requiring human approval.

---

## Account Numbering Scheme

Not applicable — Agent 10 does not interact with chart of accounts or journal entries. All tools manage system-level configuration and infrastructure.

---

## New DB Tables Needed

| Table | Purpose |
|-------|---------|
| `system_config` | Key-value configuration store for company settings, preferences, defaults (config_key, config_value, description, updated_at) |
| `system_backup_log` | Backup/export history records (backup_id, backup_type, status, triggered_by, triggered_at, completed_at, size_bytes, notes) |

---

## Tool: check_system_status

- **Approval:** No — read-only health check
- **Input:** `check_type` (Optional[list[str]] — "database", "providers", "agents", "all"; default "all")
- **Output:** `overall_status` (str — "healthy", "degraded", "unhealthy"), `checks` (list: name, status, detail, latency_ms), `summary` (str)
- **DB tables:** None (uses infrastructure queries: DB SELECT 1, provider API availability check)
- **Edge cases:** All providers down → degraded status with details. DB unreachable → unhealthy status. Partial provider failure → degraded with which providers are down. No checks specified → runs all.
- **Logic:** Runs requested checks in sequence:
  1. **database:** Execute `SELECT 1` against PostgreSQL, measure latency. Returns status and response time.
  2. **providers:** Check if API keys are configured (Groq, Cerebras). If key exists, attempt lightweight probe. Returns available/unavailable per provider.
  3. **agents:** Verify that all 9 agent modules import correctly. Returns count of loaded vs total.
  Each check returns individual status + latency. Overall = healthy if all pass, degraded if ≥1 failure but critical (DB) still up, unhealthy if DB fails.
- **Example:** User: "Check system status" → Overall: HEALTHY. DB: OK (5ms), Providers: Groq OK, Cerebras OK, Agents: 9/9 loaded.

## Tool: get_usage_statistics

- **Approval:** No — read-only analytics
- **Input:** `from_date` (date), `to_date` (date), `group_by` (Optional[str] — "provider", "agent", "day"; default "provider"), `include_detail` (bool, default False)
- **Output:** `period` (str), `total_requests` (int), `success_count` (int), `failure_count` (int), `avg_latency_ms` (Decimal), `breakdown` (list: dimension, requests, successes, failures, avg_latency), `recommendations` (list[str]), `summary` (str)
- **DB tables:** `system_backup_log` (read — only if backup stats requested); primarily uses orchestration runtime data
- **Edge cases:** No data in period → empty breakdown. Single provider used → breakdown reflects that. Very high failure rate → recommendation to check provider.
- **Logic:** Analyzes system usage patterns. Groups by selected dimension (provider, agent, day). Computes success/failure counts and average latency per group. Generates recommendations based on patterns:
  - If failure rate > 10%: "Provider X has high failure rate — consider fallback or check API key"
  - If usage > 1000 requests in period: "High usage detected — consider rate limiting"
  - If one provider handles > 80% traffic: "Usage concentrated on single provider — no issues detected" or "Consider load balancing if latency increases"
- **Example:** User: "Show me usage stats for last 30 days" → 150 requests, 142 success (94.7%), 8 failures, avg 3.2s. Provider breakdown: Groq 140/150.

## Tool: manage_system_preferences

- **Approval:** **Yes** — system configuration changes require oversight
- **Input:** `action` (str — "view", "update", "reset"), `settings` (Optional[dict] — key-value pairs to update), `setting_key` (Optional[str] — specific key to view or reset)
- **Output:** `action_performed` (str), `settings` (dict — current state after operation), `changed_keys` (list[str] — keys that were modified), `message` (str), `needs_approval` (bool)
- **DB tables:** `system_config` (read/write)
- **Edge cases:** action=update with empty settings → returns current config with no changes. action=update with unknown key → creates new entry with warning. action=reset with non-existent key → raises ValueError. action=view with key → returns single value. action=view without key → returns all config.
- **Logic:** CRUD for system configuration stored in `system_config` table:
  - **view:** Reads from `system_config`. If `setting_key` provided, returns that single entry. Otherwise returns all entries as dict.
  - **update:** Accepts settings dict. For each key-value pair: if key exists, updates config_value and updated_at. If key doesn't exist, inserts new row with note "newly created — verify". Returns list of changed (added/updated) keys.
  - **reset:** Removes entry by key (if exists) or resets to default. Requires setting_key.
  Default settings seeded on first run: company_name, fiscal_year_end, default_currency (PKR), default_timezone, backup_enabled, retention_days.
- **New DB table needed:** `system_config` (id, config_key (unique), config_value, description, updated_at)
- **Example:** User: "Update company name to ABC Corp" → Settings updated: company_name changed to 'ABC Corp'. Requires approval.

## Tool: schedule_system_task

- **Approval:** **Yes** — task scheduling requires confirmation
- **Input:** `task_type` (str — "backup", "export_data", "maintenance", "cleanup"), `schedule_time` (Optional[str] — "now", "off_peak", specific datetime), `parameters` (Optional[dict] — task-specific params), `notes` (Optional[str])
- **Output:** `task_id` (str), `task_type`, `status` (str — "scheduled", "running", "completed", "failed"), `scheduled_for` (str), `estimated_completion` (str), `message` (str), `needs_approval` (bool)
- **DB tables:** `system_backup_log` (read/write)
- **Edge cases:** schedule_time="now" with no backup configuration → schedules immediately with defaults. Duplicate task (same type already running) → warning but allows. Backup with no data → notes limited scope.
- **Logic:** Schedules a system maintenance task:
  1. Generates task_id = `TASK-{uuid[:8]}`
  2. Records task in `system_backup_log` with initial status "scheduled"
  3. For type="backup": notes scope (full/system/data-only), estimates completion based on DB size
  4. For type="export_data": notes which data to export (journal_entries, contacts, budgets, all)
  5. For type="maintenance": notes maintenance window impact
  6. For type="cleanup": notes what will be cleaned (old backups, temp data)
  Returns task details with estimated completion time. Actual execution depends on scheduler; this tool creates the schedule entry. Status transitions: scheduled → running → completed/failed.
- **New DB table needed:** `system_backup_log` (id, backup_id, backup_type, status, triggered_by, triggered_at, completed_at, size_bytes, notes, parameters)
- **Example:** User: "Schedule a database backup now" → Task TASK-A1B2C3D4: Backup scheduled immediately. Estimated completion: 2 minutes.

---

## Agent-Level Behavior

- **Routing:** "system status", "health check", "is everything working", "usage stats", "api usage", "system preferences", "company settings", "configuration", "change settings", "schedule backup", "backup data", "system task", "maintenance", "admin"
- **2 human-approval tools:** `manage_system_preferences`, `schedule_system_task`
- **2 non-approval tools:** `check_system_status`, `get_usage_statistics`
- **All config changes:** require approval; read-only checks do not
