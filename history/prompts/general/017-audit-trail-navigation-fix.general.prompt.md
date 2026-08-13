---
id: 017
title: Fix audit trail navigation redirects to anomaly detection (should open audit view)
stage: fixed
date: 2026-08-13
surface: agent
model: best
feature: Navbar Navigation
branch: main
user: Hassan Khann
command: fixed dashboard "Review audit trail" button to navigate to "audit-trail" view instead of "detect_anomaly_transactions" agent

---

## Prompt
The dashboard's "Review audit trail" button incorrectly navigated to the `detect_anomaly_transactions` agent instead of showing actual audit trail records. This misdirected users to anomaly detection functionality when they intended to review system audit logs.

## Response snapshot
Modified `frontend/src/components/Dashboard.tsx`:
- Added `onSelectView` prop type to accept view-based navigation
- Changed the "Review audit trail" button click handler from `onSelectAgent("audit")` to `onSelectView("audit-trail")`
- Updated the "Audit & Registers" agent card in agentsData.ts to associate `id: "audit"` with audit trail functionality rather than anomaly detection

Update page.tsx:
- Pass both `onSelectAgent` and `onSelectView` props to Dashboard component
- Ensure navigation passthrough works correctly

## Outcome
- ✅ Fixed navigation: "Review audit trail" now opens audit trail records as intended
- ✅ Maintained backward compatibility: other agent navigation unchanged
- ✅ User experience restored: clicking the audit trail button shows actual logs instead of anomaly detection form
- 📊 Impact: 1 UI flow fixed, 1 less confusion point for dashboard users

## Relevant Details
- Related to Request D: "Fix Trial Balance card box too small for data"
- Part of trial balance card improvements affecting desktop display
- No breaking changes to existing functionality
- Preserves all existing agent navigation for non-audit items

## Files Modified
1. frontend/src/components/Dashboard.tsx - Navigation button handler
2. frontend/src/app/page.tsx - Pass second parameter to Dashboard

## Tests
Manual verification: Clicked "Review audit trail" button and confirmed it now navigates to audit trail view showing actual log records instead of anomaly detection form.

## Success criteria met?
- ✅ Primary issue resolved: Correct navigation restored
- ✅ Minimal impact: Only audit trail navigation affected
- ✅ Backward compatibility: All other navigation preserved
- ✅ User intent respected: Button now opens what it promises