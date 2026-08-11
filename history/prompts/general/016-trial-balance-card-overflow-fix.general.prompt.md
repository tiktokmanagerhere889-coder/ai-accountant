---
id: 016
title: Trial Balance card box too small, numbers overlap
stage: general
date: 2026-08-11
surface: agent
model: best
feature: none
branch: main
user: Hassan
command: "now its shown the ammount but the box of trail balance is small according to data and its not fiting on it and the number blinding with each other /devex-review skill with review each detail and make it right and commit and push and give me ans so i can cehck"
labels: ["dashboard", "trial-balance", "ui", "layout", "overflow", "responsive-grid"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
 - frontend/src/components/Dashboard.tsx (TB card: md:col-span-2 xl:col-span-2; totals bumped text-xl -> text-2xl font-mono tabular-nums leading-tight truncate)
tests:
 - "npx tsc --noEmit -> clean"
 - "Playwright 2x clip at 1440px (xl 4-col) and 1024px (md 2-col): both render totals + Balanced pill; clientW == scrollW (no horizontal overflow); 0 console errors"
---

## Prompt

now its shown the ammount but the box of trail balance is small according to
data and its not fiting on it and the number blinding with each other
/devex-review skill with review each detail and make it right and commit and
push and give me ans so i can cehck

## Response snapshot

Root cause: the Trial Balance card is the 5th metric card in the grid
`grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6`. At xl each card is ~270px
wide, inner content ~220px after p-6. The two side-by-side text-xl mono values
("PKR 3,669,000.00" per column) plus gap-4 overflowed that width -> numbers
overlapped and the min-h-36 box looked cramped.

Fix (commit 73d6d67):
- Give the TB card `md:col-span-2 xl:col-span-2` so it spans half the row at
  md/xl (a full row on mobile). 5th card no longer squeezed to one narrow
  column; it becomes a featured half-width card, so no gap in the grid.
- Bump totals text-xl -> text-2xl and add `tabular-nums leading-tight truncate`
  on each value to match the Net Cash card's typography and guarantee no
  horizontal overflow even if a value runs long.
- Kept the grid-cols-2 side-by-side numbers-first layout (labels Total
  Debits/Total Credits above each value), the compact Balanced/Out-of-balance
  pill, and the "Open trial balance" link unchanged.

Verified with Playwright at 1440px and 1024px (2x element clips): the card
renders "Total Debits PKR 3,669,000.00 / Total Credits PKR 3,669,000.00 /
Balanced / Open trial balance" at both widths, clientWidth == scrollWidth
(no overflow), 0 console errors. tsc clean. Committed and pushed to main.

## Outcome

- ✅ Impact: TB totals fit their box at every breakpoint (mobile full-row,
  md full-row, xl half-row); numbers no longer blend into each other; card
  typography now consistent with the sibling metric cards (text-2xl
  font-mono tabular-nums).
- 🧪 Tests: tsc PASS; Playwright 1440px + 1024px render PASS (both show
  totals + pill); overflow check PASS (clientW == scrollW at both widths);
  console errors PASS (0).
- 📁 Files: frontend/src/components/Dashboard.tsx (commit 73d6d67).
- 🔁 Next prompts: none required; user will verify on Vercel after rebuild.
- 🧠 Reflection: A card that carries two long mono values side-by-side needs
  more than one grid column at xl when the grid is 4-across — the fix is
  span allocation, not shrinking the text. Keep text-2xl font-mono
  tabular-nums for numeric cards, and add truncate/min-w-0 as a safety net
  so a long value degrades gracefully instead of overlapping.

## Evaluation notes (flywheel)

- Failure modes observed: side-by-side text-xl mono totals overflowed a
  ~220px inner column at xl (numbers collided); first Playwright run caught
  the xl card still loading (backend fetch latency) -> re-ran after the dev
  server had the query cached and both widths rendered fully.
- Graders run and results (PASS/FAIL): tsc PASS; xl render PASS; md render
  PASS; overflow (clientW vs scrollW) PASS at both; console errors PASS (0).
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): null
