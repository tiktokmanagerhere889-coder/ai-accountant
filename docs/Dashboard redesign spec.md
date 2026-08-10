# Dashboard Redesign Spec — Charts, Theme, Layout

## 1. Libraries — confirmed compatible

- **bklit-ui** (https://github.com/bklit/bklit-ui) — shadcn/ui registry, installs via `npx shadcn add @bklit/<chart-name>`. Built on Next.js + Tailwind + Visx + Motion. Drops directly into the existing stack, no conflicting setup.
- **anime.js** (already integrated as a plugin) — used for everything OUTSIDE the charts themselves (number count-ups, card entrance stagger, approval-banner/bell pulse). bklit-ui's charts animate internally via Motion; anime.js never touches chart-internal DOM. No conflict.
- **Not used:** bklit-ui has no bar-chart component. AR/AP Aging stays as a table (already implemented) — do not force it into Line/Area/Ring/Radar.

## 2. Chart-to-data mapping

| Chart | Component | Data source | Notes |
|---|---|---|---|
| Ring (dual) | `@bklit/ring-chart` | `assess_financial_health` (score) + `assess_fbr_audit_risk` (score) | Two concentric rings, one widget. Color: health ring = success/danger by threshold; FBR ring = amber/red by risk_band |
| Area | `@bklit/area-chart` | New: daily cash-balance snapshot (see 2a below) | Last 30 days by default, toggle to 90 |
| Line | `@bklit/line-chart` | `generate_profit_loss` — monthly revenue vs expense, last 6-12 months | Two series, legend toggle to show/hide either line |
| Radar | `@bklit/radar-chart` | `calculate_financial_ratios` — 4 axes: liquidity, profitability, leverage, efficiency | Normalize each ratio to a 0-100 scale for the radar (document the normalization formula used) |

### 2a. New requirement: daily cash-balance snapshot

`check_cash_position` currently returns a point-in-time balance, no history. For the Area chart to work:
- New table `cash_snapshots` (date, closing_balance) — or reuse `system_backup_log`-style idempotent seeding pattern
- A daily job (or a lazy on-read snapshot: if today's row doesn't exist when dashboard loads, compute + insert it) populates one row/day
- This is new scope — flag it before building, it's not just a frontend chart wiring task

## 3. Theme tokens

Semantic hues (danger/warning/success) stay the SAME hue across both themes — only the background tint and text shade shift. Brand teal is identical in both modes.

### Dark theme
| Token | Value | Use |
|---|---|---|
| `--bg-page` | `#0B0F14` | Page background (not pure black) |
| `--bg-card` | `#131A22` | Card surface |
| `--text-primary` | `#E8EAED` | Main text |
| `--text-secondary` | `#8B94A3` | Muted/labels |
| `--accent` | `#1D9E75` | Brand teal — nav highlight, primary buttons |
| `--danger` | `#E24B4A` | High FBR risk, negative cash, errors |
| `--warning` | `#EF9F27` | Pending approvals, upcoming deadlines |
| `--success` | `#639922` | Positive indicators — kept distinct from accent teal |

### Light theme
| Token | Value | Use |
|---|---|---|
| `--bg-page` | `#F7F8FA` | Page background (not pure white) |
| `--bg-card` | `#FFFFFF` | Card surface, 1px `#E5E7EB` border |
| `--text-primary` | `#1A1D21` | Main text |
| `--text-secondary` | `#5F6772` | Muted/labels |
| `--accent` | `#1D9E75` | Same teal as dark — brand consistency |
| `--danger` | `#C6362F` | Slightly deeper red for AA contrast on white |
| `--warning` | `#B57516` | Deeper amber for AA contrast on white |
| `--success` | `#4C7A1B` | Deeper green for AA contrast on white |

Implement as CSS custom properties, toggle via a `data-theme="dark|light"` attribute on `<html>`, persisted to localStorage. Every chart's color prop reads from these tokens (not hardcoded) so charts re-theme automatically on toggle.

## 4. Dashboard layout (top to bottom)

1. Header: page title + theme toggle + notification bell (pulses via anime.js when pending-approval count > 0)
2. Pending Approvals banner (warning-colored, count + CTA)
3. Metric cards row: Net Cash Position (number, anime.js count-up) · Trial Balance status badge
4. Chart row 1: Dual Ring (Health + FBR Risk) · Radar (financial ratios) — side by side
5. Chart row 2: Area (cash trend) · Line (revenue vs expense trend) — side by side
6. Lower row: Recent AI Activity (list, from `/audit-trail`) · Compliance Deadlines (list)

Mobile (`max-width: 768px`): every row collapses to single column, charts resize to full width, sidebar becomes bottom tab bar or hamburger drawer.

## 5. Build order

1. Theme tokens + toggle (foundational, everything else depends on it)
2. Metric cards + anime.js count-up (low risk, ships fast, immediately visible)
3. Cash-snapshot table + daily-populate logic (backend prerequisite for Area chart)
4. Install bklit-ui components one at a time: Ring → Radar → Area → Line, wiring each to its real endpoint before moving to the next
5. Layout assembly + mobile responsive pass
6. Screenshot both themes, both viewports, for final review