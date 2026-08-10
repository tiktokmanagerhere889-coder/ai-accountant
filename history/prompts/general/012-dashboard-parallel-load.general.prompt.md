---
id: 012
title: Dashboard parallel data loading fix
stage: general
date: 2026-08-11
surface: agent
model: best
feature: none
branch: main
user: Hassan
command: "Dashboard ka data-loading abhi 8 tool-calls ko sequentially (ek ke baad ek) await kar raha hai ... Promise.all ... before/after comparison ... samples/ aur scripts/generate_demo_xlsx.py COMMIT karo ... chhoti README-note"
labels: ["dashboard", "performance", "parallel-loading", "demo", "docs"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
 - frontend/src/components/Dashboard.tsx (refactored fetchDashboardStats to fire 10 independent calls in parallel via Promise.all; replaced global loading flag with per-card auditStatus)
 - README.md (added Demo Data & Scripts table)
 - .gitignore (added ~$* Office temp/lock pattern)
tests:
 - "npx tsc --noEmit -> clean"
 - "Playwright @1440x900 measure: before 39.2s -> after 5.4s all-cards-populated (parallel reproducible 5.4-6.2s)"
 - "No console/page errors on parallel build"
---

## Prompt

Dashboard ka data-loading abhi 8 tool-calls ko sequentially (ek ke baad ek) await kar raha hai, jisse total load time 30-60 second tak ja sakta hai. Yeh demo ke liye risky hai. Fix: Dashboard.tsx mein jahan bhi yeh 8 calls hain, confirm karo yeh ek dusre se independent hain (kisi ek ka result doosre ko input nahi chahiye), agar haan toh sabko Promise.all([...]) mein wrap karo taake sab PARALLEL mein fire hon, sequential nahi. Har card apna individual loading-state rakhe (jo already hai), taake jo pehle aa jaye wo turant dikhe, baaki load hote rahein — user ko ek sath sab ka wait na karna pade. Fix ke baad, page-load se lekar 'sab cards populate' tak ka time measure karo (before/after comparison), mujhe dikhao kitna better hua. Iske baad: samples/ aur scripts/generate_demo_xlsx.py — yeh demo-data generate karne ke kaam aate hain, isliye COMMIT karo (kaam ke hain, hataane ki zarurat nahi), lekin ek chhoti README-note likh do unke upar ke folder mein ke yeh kis liye hain.

## Response snapshot

Refactored fetchDashboardStats in Dashboard.tsx: all 10 data sources are
independent (each result feeds only its own card setState), so replaced the
sequential await chain with `await Promise.all([...])` of 10 self-contained
try/catch async IIFEs. Each card keeps its own loading state and populates the
instant its call returns; a slow/failing call no longer blocks or resets the
others. The global `loading` flag (which only gated the Audit card) was
replaced with a dedicated `auditStatus` so that card loads independently too.

Measured with Playwright (1440x900, backend+frontend live):
  before (sequential, HEAD 452aaa4): 39.2s to all-cards-populated
  after  (parallel, 2de137d):        5.4s (reproducible 5.4-6.2s)
  => ~7.3x faster. Slowest cards (trial balance, ledger) went from ~38-39s to
  ~5.5-5.7s because they no longer queue behind the whole chain.

Also committed samples/ + scripts/generate_demo_xlsx.py with a short
'Demo Data & Scripts' README table, and gitignored MS Office temp/lock files
(~$*). Two commits: 2de137d (perf) and fc43928 (docs).

## Outcome

- ✅ Impact: Dashboard paints every stat card ~7x faster — safe for live demo.
  All cards independent; per-card skeletons preserved; one slow call can't
  stall the page. Demo assets now version-controlled with docs.
- 🧪 Tests: tsc clean; Playwright before/after measured 39.2s -> 5.4s
  (parallel reproducible across 3 runs); no console/page errors after fix.
- 📁 Files: frontend/src/components/Dashboard.tsx, README.md, .gitignore
  (commits 2de137d, fc43928).
- 🔁 Next prompts: none required.
- 🧠 Reflection: Parallelizing independent async work is the single biggest
  dashboard win; card independence (each own try/catch + status) is what makes
  parallel safe. HMR served both old and new bundles during stash flip-flop —
  verify which build is served by markers (auditStatus vs setLoading(true)).

## Evaluation notes (flywheel)

- Failure modes observed: playwright page.evaluate with a STRING returns the
  unevaluated function value (undefined) — must pass a real function; DOM
  serialization from page.evaluate can't be queried client-side — run the
  whole poll inside the browser; global hasSkeleton gate blocked per-card
  detection because Area/Line chart skeletons outlive metric cards — detect
  each card independently.
- Graders run and results (PASS/FAIL): tsc PASS; before/after measurement
  PASS (39.2s -> 5.4s); console-errors check PASS (none on parallel build).
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): null
