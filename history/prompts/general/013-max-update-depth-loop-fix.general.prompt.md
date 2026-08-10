---
id: 013
title: Fix Maximum update depth exceeded render loop
stage: general
date: 2026-08-11
surface: agent
model: best
feature: none
branch: main
user: Hassan
command: "'Maximum update depth exceeded' warning ka exact source dhoondo (count-up/refresh effect loop mein) — file/line do. Yeh classic sign hai ke koi useEffect apne trigger-dependency ko khud update kar raha hai (infinite loop). Fix karo (usually dependency-array sahi karna, ya effect ke andar condition lagana taake dobara-dobara na chale). Fix ke baad confirm karo warning console se gayab ho gayi hai — page ko kuch der (30+ second) khula chhod kar dekho, warning wapas toh nahi aa rahi."
labels: ["dashboard", "react", "infinite-loop", "useMemo", "charts", "warning"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
 - frontend/src/components/Dashboard.tsx (memoized Area chart data via useMemo: snapshotChartData; removed inline cashSnapshots.map(...) on every render)
tests:
 - "npx tsc --noEmit -> clean"
 - "Playwright 35s idle settle -> 0 console warnings/errors"
 - "Playwright 40s with 4 refresh clicks (re-run all 10 calls) -> 0 warnings"
 - "Playwright 14 reloads + 42 churn cycles -> 0 warnings"
---

## Prompt

'Maximum update depth exceeded' warning ka exact source dhoondo (count-up/
refresh effect loop mein) — file/line do. Yeh classic sign hai ke koi
useEffect apne trigger-dependency ko khud update kar raha hai (infinite
loop). Fix karo (usually dependency-array sahi karna, ya effect ke andar
condition lagana taake dobara-dobara na chale). Fix ke baad confirm karo
warning console se gayab ho gayi hai — page ko kuch der (30+ second) khula
chhod kar dekho, warning wapas toh nahi aa rahi.

## Response snapshot

Root cause found — NOT in useCountUp or any count-up/refresh loop. The loop
was in the Area chart data identity:

Dashboard.tsx rendered:
  <AreaChart data={cashSnapshots.map(...)} ...>
An inline .map() created a NEW array reference on every Dashboard render.
time-series-chart-shell.tsx passes that as targetData into
useChartPhaseOrchestrator, whose effect (use-chart-phase-orchestrator.ts:105)
runs on every targetData change and calls setPlotData(targetData) -> Dashboard
re-renders -> new .map() array -> effect re-runs -> setPlotData: an update
loop. React surfaced it as "Maximum update depth exceeded" whenever render
churn was fast enough to hit the ~50-depth cap (count-up animations + refresh
re-running all 10 calls = fast churn). Ring/Radar/Line charts were safe
because ringData/radarData/trend were already memoized/stable.

Fix: memoize the mapped array:
  const snapshotChartData = useMemo(
    () => cashSnapshots.map((s) => ({ date: s.date, balance: s.closing_balance })),
    [cashSnapshots]
  );
and pass snapshotChartData to <AreaChart>. Identity now stable unless
cashSnapshots actually changes, so the orchestrator effect sees the same
array and does not loop.

Verified after fix: 35s idle, 40s with refresh churn, 14 reloads + 42 churn
cycles — all 0 console warnings/errors. Previously the warning fired ~1/10
loads during churn.

## Outcome

- ✅ Impact: "Maximum update depth exceeded" gone; Area chart no longer
  re-renders in a loop under fast churn (count-up/refresh).
- 🧪 Tests: tsc clean; 3 churn modes all 0 warnings/errors.
- 📁 Files: frontend/src/components/Dashboard.tsx (commit 7e85909).
- 🔁 Next prompts: none required.
- 🧠 Reflection: The "classic infinite-loop" wasn't an effect directly
  updating its own dependency — it was an inline array prop feeding a child
  effect. "Effect updates trigger-dependency" manifests subtly via memoized
  props: memoize any array/object prop passed into an effect-driven child,
  or the child's own setState closes the loop. Always check inline .map()/
  object-literal props before blaming useCountUp.

## Evaluation notes (flywheel)

- Failure modes observed: warning is rare (~1/10 loads) and appears only
  during churn, so single-load repro misses it; truncating the console
  message at 200 chars discarded React's component stack — capture full text;
  HMR hot-swap during stash flip-flop itself caused a transient warning.
- Graders run and results (PASS/FAIL): tsc PASS; idle-settle PASS (0);
  refresh-churn PASS (0); reload-churn PASS (0).
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): null
