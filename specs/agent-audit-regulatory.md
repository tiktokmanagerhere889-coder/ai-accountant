# Agent: Audit & Regulatory Agent

**Role:** Anomaly detection, internal audit support, statutory records, and compliance deadline tracking. 5 tools, 3 requiring human approval.

---

## Account Numbering Scheme

Consistent with Agents 2, 4, 5, 6, 7:

| Prefix | Category |
|--------|----------|
| `1xxx` | **Assets** — cash (1000), receivables (1200), fixed assets |
| `2xxx` | **Liabilities** — payables (2000), loans, tax payable |
| `3xxx` | **Equity** — capital, retained earnings |
| `4xxx` | **Revenue** — sales, service income |
| `5xxx`, `6xxx`, `8xxx` | **Expenses** — operating costs, salaries, rent |

**Agent 8 specific accounts:**
- Audit findings / adjustments → no new accounts needed, reads from existing `journal_entries`
- Statutory registers → new table, not tied to account prefixes

---

## New DB Tables Needed

| Table | Purpose |
|-------|---------|
| `flagged_entries` | Stores flagged/anomalous entries from audit scans (entry_id, flag_type, reason, severity, flagged_by, flagged_at, status) |
| `statutory_registers` | Statutory register records (register_type, entry_date, description, reference_number, amount, status, filed_date) |
| `compliance_deadlines` | Compliance deadline tracking (deadline_type, description, due_date, responsible_person, status, reminder_days, fiscal_year) |

---

## Tool: support_internal_audit

- **Approval:** **Yes** — accountant reviews flagged entries, decides action
- **Input:** `fiscal_year` (int), `period` (Optional[int]), `min_severity` (Optional[str] — "low", "medium", "high", "critical"), `include_resolved` (bool, default False)
- **Output:** `audit_id` (str), `flagged_entries` (list: entry_id, description, amount, flag_type, reason, severity, status), `total_flagged` (int), `summary` (str), `needs_approval` (bool)
- **DB tables:** `journal_entries` (read — for ledger data), `flagged_entries` (read/write)
- **Edge cases:** No entries for period → empty results. All entries clean → "no issues found". Resolved flags excluded by default. min_severity filters out lower-severity flags.
- **Logic:** Scans journal_entries for audit-relevant patterns: (1) entries without proper reference numbers, (2) entries posted on weekends/holidays, (3) entries with round amounts (ending in 000), (4) unusually large entries (>3σ from mean), (5) accounts with infrequent activity suddenly posting. Each pattern assigned severity. Results stored in `flagged_entries`.
- **Deduplication:** Re-running the audit never duplicates rows. Each `(entry_id, flag_type)` is created once; later runs report the existing open flag without inserting. Resolved flags (`confirmed`/`waived`) are excluded by default and only returned with `include_resolved=True`.
- **New DB table needed:** `flagged_entries` (id, entry_id, flag_type, reason, severity, flagged_by, flagged_at, resolved_at, resolved_by, resolution_note, status)
- **Example:** User: "Run internal audit for FY 2026" → flags entries with missing references, weekend postings, anomalous amounts

## Tool: resolve_flagged_entry

- **Approval:** **Yes** — the accountant's decision on each flag
- **Input:** `entry_id` (str), `flag_type` (str), `action` (str — "confirm" | "waive"), `notes` (Optional[str]), `resolved_by` (Optional[str])
- **Output:** `entry_id`, `flag_type`, `action`, `status` ("confirmed"/"waived"), `resolved_at` (date), `resolved_by`, `notes`, `message`, `needs_approval` (bool)
- **DB tables:** `flagged_entries` (write)
- **Edge cases:** unknown `entry_id`/`flag_type` → ValueError. Already-resolved flag → ValueError. invalid action → ValueError.
- **Logic:** `confirm` marks a flag as a real issue (stays visible as confirmed); `waive` marks it reviewed-not-an-issue. Sets `resolved_at`, `resolved_by`, `resolution_note`. The record stays in `flagged_entries` so re-runs do not re-flag it.
- **Example:** User: "Waive the missing_reference flag on JE-2026-0001" → flag status set to waived with timestamp.

## Tool: detect_anomaly_transactions

- **Approval:** No — automated, pattern-based detection only; flags for human review
- **Input:** `from_date` (date), `to_date` (date), `anomaly_types` (Optional[list[str]] — "round_amount", "weekend_posting", "duplicate_amount", "unusual_account", "high_frequency"), `threshold` (Optional[Decimal] — minimum amount threshold to flag)
- **Output:** `anomalies` (list: entry_id, description, amount, anomaly_type, confidence, reasoning, suggested_review), `total_anomalies` (int), `total_amount_flagged` (Decimal), `period_from`, `period_to`
- **DB tables:** `journal_entries` (read — for transaction data)
- **Edge cases:** No anomalies found → empty list with "clean" status. threshold = 0 → flags everything meeting pattern criteria. Date range with no entries → empty results. Very large date range → performance note.
- **Logic:** Four detectors run in sequence:
  1. Round amount detector: flag entries where amount % 1000 == 0 (potential round-tripping)
  2. Weekend detector: flag entries with posted_date on Saturday/Sunday
  3. Duplicate detector: flag entries with same amount + same date + same description
  4. Unusual account detector: flag entries where debit/credit account is outside the normal pattern for that entry's description category
  Each detector assigns a confidence (high/medium/low). Deduplicates across detectors.
- **Example:** User: "Detect anomalies in July 2026" → flags 2 weekend postings, 1 round-amount entry (500000), 0 duplicates

## Tool: maintain_statutory_registers

- **Approval:** **Yes** — register changes require accountant oversight
- **Input:** `action` (str — "add", "update", "delete", "view"), `register_type` (str — "directors", "members", "charges", "contracts", "beneficial_owners"), `entry_date` (date), `description` (str), `reference_number` (Optional[str]), `amount` (Optional[Decimal]), `register_id` (Optional[str] — for update/delete)
- **Output:** `register_id` (str), `action_performed` (str), `register_type`, `entry_date`, `description`, `reference_number`, `amount`, `status` (str), `message` (str), `needs_approval` (bool)
- **DB tables:** `statutory_registers` (read/write)
- **Edge cases:** action=delete with non-existent register_id → raises ValueError. action=add with duplicate reference_number → warning but allows (reference note appended). view with no entries → empty with description of which registers exist. update on resolved register → reopens it.
- **New DB table needed:** `statutory_registers` (id, register_id, register_type, entry_date, description, reference_number, amount, status, filed_date, created_at, updated_at)
- **Example:** User: "Add director register entry: Ali Khan appointed 2026-07-01, reference DIR-001" → new register record pending approval

## Tool: get_compliance_deadlines

- **Approval:** No — read-only dashboard/reminder
- **Input:** `fiscal_year` (Optional[int]), `deadline_type` (Optional[str] — "tax_filing", "statutory_filing", "audit", "annual_return", "other"), `status` (Optional[str] — "upcoming", "overdue", "completed"), `reminder_days` (Optional[int] — show deadlines due within this many days)
- **Output:** `deadlines` (list: deadline_id, deadline_type, description, due_date, days_remaining, status, responsible_person), `overdue_count` (int), `upcoming_count` (int), `summary` (str)
- **DB tables:** `compliance_deadlines` (read)
- **Edge cases:** No deadlines configured → returns empty with suggestion to configure. All deadlines completed → "all caught up" message. Overdue deadlines → highlighted with severity. No fiscal_year filter → shows all upcoming.
- **New DB table needed:** `compliance_deadlines` (id, deadline_id, deadline_type, description, due_date, responsible_person, status, reminder_days, fiscal_year)
- **Example:** User: "Show upcoming compliance deadlines" → 3 upcoming: sales tax filing due Jul 20 (5 days), income tax due Sep 30 (77 days), annual return due Dec 31 (159 days)

---

## Agent-Level Behavior

- **Routing:** "internal audit", "audit support", "audit review", "anomaly", "fraud detection", "suspicious transaction", "confirm flag", "waive flag", "resolve flag", "statutory register", "register of directors", "register of members", "register of charges", "compliance deadline", "filing deadline", "due date", "regulatory filing", "compliance reminder"
- **3 human-approval tools:** `support_internal_audit`, `resolve_flagged_entry`, `maintain_statutory_registers`
- **2 non-approval tools:** `detect_anomaly_transactions`, `get_compliance_deadlines`
- **All audit flagging:** read-only detection; accountant decides resolution via `resolve_flagged_entry`
