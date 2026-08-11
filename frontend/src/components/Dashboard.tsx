import React, { useState, useEffect, useMemo, useCallback } from "react";
import axios from "axios";
import {
  AlertTriangle, DollarSign, ListTodo,
  Percent, ArrowRight, RefreshCw, Scale, ShieldAlert, ArrowUpRight, ArrowDownRight
} from "lucide-react";
import { RingChart } from "@/components/charts/ring-chart";
import { Ring } from "@/components/charts/ring";
import { RingCenter } from "@/components/charts/ring-center";
import { RadarChart } from "@/components/charts/radar-chart";
import { RadarGrid } from "@/components/charts/radar-grid";
import { RadarAxis } from "@/components/charts/radar-axis";
import { RadarLabels } from "@/components/charts/radar-labels";
import { RadarArea } from "@/components/charts/radar-area";
import { AreaChart } from "@/components/charts/area-chart";
import { Area } from "@/components/charts/area";
import { Grid } from "@/components/charts/grid";
import { XAxis } from "@/components/charts/x-axis";
import { ChartTooltip } from "@/components/charts/tooltip/chart-tooltip";
import { LineChart } from "@/components/charts/line-chart";
import { Line } from "@/components/charts/line";
import { useCountUp } from "@/components/useCountUp";

interface DashboardProps {
  onSelectAgent: (id: string) => void;
  onOpenApprovals: () => void;
  refreshTrigger: number;
}

type SnapshotPoint = Record<string, unknown> & { date: string; closing_balance: number; };
type TrendPoint = Record<string, unknown> & { date: Date; revenue: number; expenses: number; };
type RadarPoint = Record<string, unknown> & { category: string; value: number; };
type LedgerEntry = {
  entry_id: string;
  description: string;
  posted_date: string;
  debit_account: string;
  debit_amount: number;
  credit_account: string;
  credit_amount: number;
};

const RADAR_CATEGORIES = ["liquidity", "profitability", "leverage", "efficiency"] as const;
const CATEGORY_LABELS: Record<string, string> = {
  liquidity: "Liquidity",
  profitability: "Profitability",
  leverage: "Leverage",
  efficiency: "Efficiency",
};
// Categorical hue order (validated colorblind-safe in both themes).
const CHART_COLORS = [
  "var(--chart-1)", // teal
  "var(--chart-2)", // amber
  "var(--chart-3)", // indigo
  "var(--chart-4)", // rose
  "var(--chart-5)", // violet
];

function parseRatioValue(value: string | number | null | undefined): number {
  if (value === null || value === undefined || value === "") return 0;
  const num = typeof value === "number" ? value : parseFloat(value);
  return Number.isFinite(num) ? num : 0;
}

// Map an FBR audit risk band to the semantic text token used to color the score.
function riskBandColor(band: string): string {
  switch (band.toLowerCase()) {
    case "low": return "text-success-light dark:text-success-dark";
    case "medium": return "text-warning-light dark:text-warning-dark";
    default: return "text-danger-light dark:text-danger-dark"; // high, critical
  }
}

// Convert a ratio % string like "60.00" (percent) into a 0-100 score.
// Direction comes from the benchmark operator ("< X" = lower is better,
// "> X" = higher is better), which covers every ratio in
// calculate_financial_ratios — including Expense Ratio ("< 80%"), which is
// NOT in the leverage category and was previously scored inverted.
function ratioToIndex(value: number, benchmark: string): number {
  const lowerIsBetter = benchmark.trim().startsWith("<");
  // Benchmark like "> 1.0", "< 0.5", "> 10%".
  const benchNum = parseRatioValue(benchmark.replace(/[<>=%\s]/g, ""));
  if (benchNum <= 0) return 0;
  // For % ratios, value is already a percent (60.00). For ratios like 1.00, treat as percent of 1.0 max.
  const isPercent = benchmark.includes("%");
  const max = isPercent ? 100 : Math.max(1, benchNum * 2);
  // Clamp the raw score before rounding so extreme values (-877.5%, +977.5%)
  // saturate at 0 / 100 instead of distorting or breaking the radar polygon.
  const raw = lowerIsBetter ? 1 - value / max : value / max;
  const clamped = Math.min(1, Math.max(0, raw));
  return Math.round(clamped * 100);
}

export default function Dashboard({ onSelectAgent, onOpenApprovals, refreshTrigger }: DashboardProps) {
  const [cashBalance, setCashBalance] = useState<string>("Calculating...");
  const [healthScore, setHealthScore] = useState<number | null>(null);
  const [auditStats, setAuditStats] = useState<{ total: number; resolved: number; open: number }>({
    total: 0,
    resolved: 0,
    open: 0,
  });
  const [cashSnapshots, setCashSnapshots] = useState<SnapshotPoint[]>([]);
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [ratios, setRatios] = useState<RadarPoint[]>([]);
  const [pendingApprovals, setPendingApprovals] = useState(0);
  const [riskScore, setRiskScore] = useState<number | null>(null);
  const [riskBand, setRiskBand] = useState<string | null>(null);
  const [tbInBalance, setTbInBalance] = useState<boolean | null>(null);
  const [tbDifference, setTbDifference] = useState<number | null>(null);
  const [tbDebits, setTbDebits] = useState<number | null>(null);
  const [tbCredits, setTbCredits] = useState<number | null>(null);
  const [tbStatus, setTbStatus] = useState<"loading" | "ready" | "error">("loading");
  const [recentLedger, setRecentLedger] = useState<LedgerEntry[]>([]);
  const [ledgerStatus, setLedgerStatus] = useState<"loading" | "ready" | "error">("loading");
  const [auditStatus, setAuditStatus] = useState<"loading" | "ready" | "error">("loading");

  const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

  const fetchDashboardStats = useCallback(async () => {
    setTbStatus("loading");
    setLedgerStatus("loading");
    setAuditStatus("loading");
    const today = new Date();
    const todayISO = today.toISOString().slice(0, 10);
    const currentYear = today.getFullYear();

    // All 10 data sources are independent — no call's result feeds another —
    // so they fire in PARALLEL via Promise.all. Each has its own try/catch and
    // sets only its own state, so a slow or failing call never blocks or
    // resets the other cards: whichever finishes first renders immediately.
    await Promise.all([
      // 1. Cash position
      (async () => {
        try {
          const cashRes = await axios.post(`${apiBase}/tools/execute`, {
            tool_name: "check_cash_position",
            params: { as_of_date: todayISO, account_id: "ALL" },
          }, { timeout: 30000 });
          const cashData = cashRes.data.result;
          if (cashData && typeof cashData.closing_balance !== "undefined") {
            setCashBalance(Number(cashData.closing_balance).toLocaleString("en-US", { minimumFractionDigits: 2 }));
          } else {
            setCashBalance("Unavailable");
          }
        } catch {
          setCashBalance("Unavailable");
        }
      })(),

      // 2. Financial health score (Ring)
      (async () => {
        try {
          const healthRes = await axios.post(`${apiBase}/tools/execute`, {
            tool_name: "assess_financial_health",
            params: { fiscal_year: currentYear },
          }, { timeout: 30000 });
          const score = healthRes.data.result?.score;
          if (typeof score === "number") setHealthScore(score);
          else setHealthScore(null);
        } catch {
          setHealthScore(null);
        }
      })(),

      // 3. Cash snapshots (Area)
      (async () => {
        try {
          const snapRes = await axios.get(`${apiBase}/cash-snapshots`, { timeout: 30000 });
          const snapshots = snapRes.data?.snapshots || [];
          setCashSnapshots(snapshots);
        } catch {
          setCashSnapshots([]);
        }
      })(),

      // 4. Monthly trend (Line) — bypass approval (read-only custom report)
      (async () => {
        try {
          const trendRes = await axios.post(`${apiBase}/tools/execute`, {
            tool_name: "generate_custom_report",
            params: { report_type: "trend", fiscal_year: currentYear, report_title: "Monthly Trend" },
            bypass_approval: true,
          }, { timeout: 30000 });
          const sections = trendRes.data?.result?.sections || [];
          const months = sections[0]?.data?.months || [];
          setTrend(months.map((m: any) => ({
            date: new Date(`${m.month}-01T00:00:00`),
            revenue: parseRatioValue(m.revenue),
            expenses: parseRatioValue(m.expenses),
          })));
        } catch {
          setTrend([]);
        }
      })(),

      // 5. Financial ratios (Radar)
      (async () => {
        try {
          const ratioRes = await axios.post(`${apiBase}/tools/execute`, {
            tool_name: "calculate_financial_ratios",
            params: { fiscal_year: currentYear },
          }, { timeout: 30000 });
          const list = ratioRes.data?.result?.ratios || [];
          const byCat = new Map<string, number[]>();
          for (const r of list) {
            const cat = r?.category;
            if (!cat) continue;
            if (!byCat.has(cat)) byCat.set(cat, []);
            byCat.get(cat)!.push(ratioToIndex(parseRatioValue(r.value), r.benchmark || ""));
          }
          setRatios(
            RADAR_CATEGORIES
              .filter((c) => byCat.has(c))
              .map((c) => {
                const vals = byCat.get(c)!;
                const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
                return { category: c, value: Math.round(avg) };
              })
          );
        } catch {
          setRatios([]);
        }
      })(),

      // 6. Audit count
      (async () => {
        try {
          const logsRes = await axios.get(`${apiBase}/audit-trail/count`, { timeout: 30000 });
          const total = logsRes.data?.total ?? 0;
          setAuditStats({ total, resolved: 0, open: 0 });
          setAuditStatus("ready");
        } catch {
          setAuditStatus("error");
        }
      })(),

      // 7. Pending approvals count (banner)
      (async () => {
        try {
          const pendingRes = await axios.get(`${apiBase}/approvals/pending`, { timeout: 15000 });
          setPendingApprovals(pendingRes.data?.approvals?.length || 0);
        } catch {
          // backend unreachable — keep current count
        }
      })(),

      // 8. FBR audit risk (metric card)
      (async () => {
        try {
          const fbrRes = await axios.post(`${apiBase}/tools/execute`, {
            tool_name: "assess_fbr_audit_risk",
            params: { fiscal_year: currentYear },
          }, { timeout: 30000 });
          const result = fbrRes.data?.result;
          if (result && typeof result.risk_score !== "undefined") {
            setRiskScore(Number(result.risk_score));
            setRiskBand(result.risk_band || null);
          } else {
            setRiskScore(null);
            setRiskBand(null);
          }
        } catch {
          setRiskScore(null);
          setRiskBand(null);
        }
      })(),

      // 9. Trial balance (metric card)
      (async () => {
        try {
          const tbRes = await axios.post(`${apiBase}/tools/execute`, {
            tool_name: "generate_trial_balance",
            params: { as_of_date: todayISO },
          }, { timeout: 30000 });
          const result = tbRes.data?.result;
          if (result && typeof result.in_balance !== "undefined") {
            setTbInBalance(Boolean(result.in_balance));
            setTbDifference(typeof result.difference !== "undefined" ? Number(result.difference) : null);
            setTbDebits(typeof result.total_debits !== "undefined" ? Number(result.total_debits) : null);
            setTbCredits(typeof result.total_credits !== "undefined" ? Number(result.total_credits) : null);
            setTbStatus("ready");
          } else {
            setTbStatus("error");
          }
        } catch {
          setTbStatus("error");
        }
      })(),

      // 10. Recent General Ledger postings
      (async () => {
        try {
          const ledgerRes = await axios.get(`${apiBase}/ledger/entries?limit=10`, { timeout: 15000 });
          setRecentLedger(ledgerRes.data?.entries || []);
          setLedgerStatus("ready");
        } catch {
          setRecentLedger([]);
          setLedgerStatus("error");
        }
      })(),
    ]);
  }, [apiBase]);

  useEffect(() => {
    fetchDashboardStats();
  }, [refreshTrigger, fetchDashboardStats]);

  // Count-up animations
  const animatedCash = useCountUp(
    cashBalance !== "Calculating..." && cashBalance !== "Unavailable" && cashBalance !== ""
      ? parseFloat(cashBalance.replace(/,/g, ""))
      : null
  );
  const animatedHealth = useCountUp(healthScore);
  const animatedAudit = useCountUp(auditStats.total);
  const animatedRisk = useCountUp(riskScore);

  // Ring data. Clamp the score to [0, 100] so an out-of-range backend value
  // (score > maxValue) can't push the arc past the ring's end angle.
  const ringData = useMemo(() => {
    if (healthScore === null) return [];
    const clamped = Math.min(100, Math.max(0, healthScore));
    return [{ label: "Health Score", value: clamped, maxValue: 100, color: CHART_COLORS[0] }];
  }, [healthScore]);

  // Radar data
  const radarData = useMemo(() => {
    if (!ratios.length) return [];
    return [{
      label: "FY Performance",
      color: CHART_COLORS[0],
      values: Object.fromEntries(ratios.map((r) => [r.category, r.value])),
    }];
  }, [ratios]);
  const radarMetrics = useMemo(() =>
    RADAR_CATEGORIES.filter((c) => ratios.some((r) => r.category === c))
      .map((c) => ({ key: c, label: CATEGORY_LABELS[c] })),
    [ratios]
  );

  // Stable identity for the Area chart: map cashSnapshots through useMemo so
  // every Dashboard render passes the SAME array reference. Without this, the
  // inline .map() created a fresh array each render, and the chart's
  // phase-orchestrator effect (setPlotData on targetData change) re-ran on it
  // forever — "Maximum update depth exceeded" during fast re-render churn.
  const snapshotChartData = useMemo(
    () => cashSnapshots.map((s) => ({ date: s.date, balance: s.closing_balance })),
    [cashSnapshots]
  );

  const hasTrend = trend.length > 0;
  const hasSnapshots = cashSnapshots.length > 0;
  const hasRadar = radarMetrics.length > 0;
  const hasRing = ringData.length > 0;

  return (
    <div className="space-y-6">
      {/* Pending Approvals Banner */}
      {pendingApprovals > 0 && (
        <div className="flex items-center justify-between gap-4 bg-warning-light/10 dark:bg-warning-dark/10 text-warning-light dark:text-warning-dark border border-warning-light/40 dark:border-warning-dark/40 rounded px-4 py-3">
          <div className="flex items-center gap-3 min-w-0">
            <AlertTriangle className="w-5 h-5 animate-pulse flex-shrink-0" />
            <span className="text-sm font-semibold">
              {pendingApprovals} pending approval{pendingApprovals === 1 ? "" : "s"} awaiting review
            </span>
          </div>
          <button
            onClick={onOpenApprovals}
            className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider bg-warning-light/20 dark:bg-warning-dark/20 text-warning-light dark:text-warning-dark border border-warning-light/40 dark:border-warning-dark/40 rounded px-3 py-1.5 hover:bg-warning-light/30 dark:hover:bg-warning-dark/30 transition-colors flex-shrink-0"
          >
            Review approvals <ArrowRight className="w-3 h-3" />
          </button>
        </div>
      )}

      {/* Top Banner */}
      <div>
        <h2 className="font-serif text-2xl text-gray-800 dark:text-gray-100">
          Financial Control Dashboard
        </h2>
        <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
          Operational accounting logs and AI-automated specialists orchestrator node status.
        </p>
      </div>

      {/* Metric Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6">
        <div className="bg-surface-light dark:bg-surface-dark border border-gray-200 dark:border-gray-800 rounded p-6 flex flex-col justify-between min-h-36">
          <div className="flex items-center justify-between text-gray-500">
            <span className="text-xs uppercase font-bold tracking-wider">Net Cash Position</span>
            <DollarSign className="w-5 h-5 text-accent-light" />
          </div>
          <div className="text-2xl font-semibold font-mono tabular-nums text-gray-900 dark:text-gray-100">
            {cashBalance === "Unavailable" ? (
              <span className="text-sm font-normal text-gray-500">Currently Unavailable</span>
            ) : (
              <>PKR {animatedCash !== null ? animatedCash.toLocaleString("en-US", { minimumFractionDigits: 2 }) : "…"}</>
            )}
          </div>
          <button onClick={() => onSelectAgent("daily-entry")}
            className="text-xs text-accent-light hover:underline font-semibold flex items-center gap-1 mt-2 self-start">
            Manage cash flow <ArrowRight className="w-3 h-3" />
          </button>
        </div>

        <div className="bg-surface-light dark:bg-surface-dark border border-gray-200 dark:border-gray-800 rounded p-6 flex flex-col justify-between min-h-36">
          <div className="flex items-center justify-between text-gray-500">
            <span className="text-xs uppercase font-bold tracking-wider">Audit Trail Updates</span>
            <ListTodo className="w-5 h-5 text-warning-light dark:text-warning-dark" />
          </div>
          <div className="text-2xl font-semibold font-mono text-gray-900 dark:text-gray-100">
            {auditStatus === "loading" ? (
              <div className="h-8 w-16 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
            ) : (
              <span className="text-2xl font-bold">{animatedAudit ?? 0}</span>
            )} <span className="text-xs font-normal text-gray-500">Logged Actions</span>
          </div>
          <button onClick={() => onSelectAgent("audit")}
            className="text-xs text-accent-light hover:underline font-semibold flex items-center gap-1 mt-2 self-start">
            Review audit trail <ArrowRight className="w-3 h-3" />
          </button>
        </div>

        <div className="bg-surface-light dark:bg-surface-dark border border-gray-200 dark:border-gray-800 rounded p-6 flex flex-col justify-between min-h-36">
          <div className="flex items-center justify-between text-gray-500">
            <span className="text-xs uppercase font-bold tracking-wider">Corporate Ratios</span>
            <Percent className="w-5 h-5 text-success-light dark:text-success-dark" />
          </div>
          <div className="text-2xl font-semibold font-mono text-gray-900 dark:text-gray-100">
            {animatedHealth !== null ? (
              <>{Math.round(animatedHealth)}% <span className="text-xs font-normal text-gray-500">Financial Health</span></>
            ) : (
              <span className="text-sm font-normal text-gray-500">Not calculated</span>
            )}
          </div>
          <button onClick={() => onSelectAgent("advisory")}
            className="text-xs text-accent-light hover:underline font-semibold flex items-center gap-1 mt-2 self-start">
            Analyze financial indicators <ArrowRight className="w-3 h-3" />
          </button>
        </div>

        <div className="bg-surface-light dark:bg-surface-dark border border-gray-200 dark:border-gray-800 rounded p-6 flex flex-col justify-between min-h-36">
          <div className="flex items-center justify-between text-gray-500">
            <span className="text-xs uppercase font-bold tracking-wider">FBR Audit Risk</span>
            <ShieldAlert className="w-5 h-5 text-warning-light dark:text-warning-dark" />
          </div>
          <div className={`text-2xl font-semibold font-mono ${riskScore !== null && riskBand ? riskBandColor(riskBand) : "text-gray-900 dark:text-gray-100"}`}>
            {riskScore !== null && riskBand ? (
              <>{animatedRisk !== null ? Math.round(animatedRisk) : "…"} <span className="text-xs font-normal uppercase">{riskBand}</span></>
            ) : (
              <span className="text-sm font-normal text-gray-500">Not calculated</span>
            )}
          </div>
          <button onClick={() => onSelectAgent("tax")}
            className="text-xs text-accent-light hover:underline font-semibold flex items-center gap-1 mt-2 self-start">
            Review FBR risk <ArrowRight className="w-3 h-3" />
          </button>
        </div>

        <div className="bg-surface-light dark:bg-surface-dark border border-gray-200 dark:border-gray-800 rounded p-6 flex flex-col justify-between min-h-36">
          <div className="flex items-center justify-between text-gray-500">
            <span className="text-xs uppercase font-bold tracking-wider">Trial Balance</span>
            <Scale className="w-5 h-5 text-accent-light" />
          </div>
          {tbStatus === "loading" ? (
            <div className="grid grid-cols-2 gap-4 mt-2">
              <div className="h-8 w-24 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
              <div className="h-8 w-24 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
            </div>
          ) : tbStatus === "error" || tbInBalance === null ? (
            <span className="text-sm font-normal text-gray-500">Unavailable</span>
          ) : (
            <>
              {/* Numbers-first: both totals prominent, side by side */}
              <div className="grid grid-cols-2 gap-4 mt-2">
                <div>
                  <div className="text-[10px] uppercase font-bold tracking-wider text-gray-500">Total Debits</div>
                  <div className="text-xl font-semibold font-mono text-gray-900 dark:text-gray-100">
                    PKR {tbDebits === null ? "—" : tbDebits.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] uppercase font-bold tracking-wider text-gray-500">Total Credits</div>
                  <div className="text-xl font-semibold font-mono text-gray-900 dark:text-gray-100">
                    PKR {tbCredits === null ? "—" : tbCredits.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                  </div>
                </div>
              </div>
              {/* Compact status pill (replaces the old full-width check text) */}
              {tbInBalance ? (
                <span className="inline-flex items-center gap-1.5 mt-3 self-start text-xs font-semibold px-2.5 py-1 rounded-full bg-success-light/10 dark:bg-success-dark/10 text-success-light dark:text-success-dark border border-success-light/20 dark:border-success-dark/20">
                  <span className="w-1.5 h-1.5 rounded-full bg-current" />
                  Balanced
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 mt-3 self-start text-xs font-semibold px-2.5 py-1 rounded-full bg-danger-light/10 dark:bg-danger-dark/10 text-danger-light dark:text-danger-dark border border-danger-light/20 dark:border-danger-dark/20">
                  ⚠
                  <span>Out of Balance by PKR {tbDifference === null ? "—" : tbDifference.toLocaleString("en-US", { minimumFractionDigits: 2 })}</span>
                </span>
              )}
            </>
          )}
          <button onClick={() => onSelectAgent("year-end")}
            className="text-xs text-accent-light hover:underline font-semibold flex items-center gap-1 mt-2 self-start">
            Open trial balance <ArrowRight className="w-3 h-3" />
          </button>
        </div>
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Cash flow trend (Area) */}
        <div className="bg-surface-light dark:bg-surface-dark border border-gray-200 dark:border-gray-800 rounded p-6">
          <h3 className="font-semibold text-sm uppercase tracking-wider text-gray-700 dark:text-gray-300 mb-4">
            Cash Position Trend
          </h3>
          {hasSnapshots ? (
            <AreaChart data={snapshotChartData} xDataKey="date" aspectRatio="2 / 1">
              <Grid horizontal />
              <Area dataKey="balance" fill="var(--chart-line-primary)" />
              <XAxis />
              <ChartTooltip />
            </AreaChart>
          ) : (
            <div className="text-center p-8 text-sm text-gray-500">No cash snapshot data.</div>
          )}
        </div>

        {/* Financial health (Ring) */}
        <div className="bg-surface-light dark:bg-surface-dark border border-gray-200 dark:border-gray-800 rounded p-6 flex flex-col items-center">
          <h3 className="font-semibold text-sm uppercase tracking-wider text-gray-700 dark:text-gray-300 mb-2 self-start">
            Financial Health Score
          </h3>
          {hasRing ? (
            <RingChart data={ringData} className="mt-2">
              <Ring index={0} />
              <RingCenter defaultLabel="Health Score" />
            </RingChart>
          ) : (
            <div className="text-center p-8 text-sm text-gray-500">No health data.</div>
          )}
        </div>

        {/* Radar ratios */}
        <div className="bg-surface-light dark:bg-surface-dark border border-gray-200 dark:border-gray-800 rounded p-6">
          <h3 className="font-semibold text-sm uppercase tracking-wider text-gray-700 dark:text-gray-300 mb-4">
            Financial Ratios
          </h3>
          {hasRadar ? (
            <RadarChart data={radarData} metrics={radarMetrics} className="mx-auto">
              <RadarGrid />
              <RadarAxis />
              <RadarLabels />
              {radarData.map((item, index) => (
                <RadarArea key={item.label} index={index} />
              ))}
            </RadarChart>
          ) : (
            <div className="text-center p-8 text-sm text-gray-500">No ratio data.</div>
          )}
        </div>

        {/* Monthly trend (Line) */}
        <div className="bg-surface-light dark:bg-surface-dark border border-gray-200 dark:border-gray-800 rounded p-6">
          <h3 className="font-semibold text-sm uppercase tracking-wider text-gray-700 dark:text-gray-300 mb-4">
            Monthly Revenue vs Expenses
          </h3>
          {hasTrend ? (
            <LineChart data={trend} xDataKey="date" aspectRatio="2 / 1">
              <Grid horizontal />
              <Line dataKey="revenue" stroke="var(--chart-line-primary)" />
              <Line dataKey="expenses" stroke="var(--chart-line-secondary)" />
              <XAxis />
              <ChartTooltip />
            </LineChart>
          ) : (
            <div className="text-center p-8 text-sm text-gray-500">No trend data.</div>
          )}
        </div>
      </div>

      {/* Recent General Ledger postings */}
      <div className="grid grid-cols-1 gap-6">
        <div className="bg-surface-light dark:bg-surface-dark border border-gray-200 dark:border-gray-800 rounded p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-sm uppercase tracking-wider text-gray-700 dark:text-gray-300">
              Recent General Ledger postings
            </h3>
            <button onClick={fetchDashboardStats} aria-label="Refresh dashboard data">
              <RefreshCw className="w-4 h-4 text-gray-400 hover:text-gray-600" />
            </button>
          </div>
          {ledgerStatus === "loading" && (
            <div className="text-center p-8 text-sm text-gray-500">Loading postings…</div>
          )}
          {ledgerStatus === "error" && (
            <div className="text-center p-8 text-sm text-gray-500">
              Recent postings are unavailable right now.
            </div>
          )}
          {ledgerStatus === "ready" && recentLedger.length === 0 && (
            <div className="text-center p-8 text-sm text-gray-500">No postings yet.</div>
          )}
          {ledgerStatus === "ready" && recentLedger.length > 0 && (
            <ul className="divide-y divide-gray-200 dark:divide-gray-800">
              {recentLedger.map((entry) => (
                <li key={entry.entry_id} className="py-3">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">
                        {entry.description}
                      </p>
                      <p className="text-xs text-gray-400 mt-0.5">
                        {entry.posted_date} · {entry.entry_id}
                      </p>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
                        <ArrowDownRight className="w-3 h-3 text-success-light dark:text-success-dark" />
                        <span className="font-mono">{Number(entry.debit_amount).toLocaleString()}</span>
                      </div>
                      <div className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                        <ArrowUpRight className="w-3 h-3 text-danger-light dark:text-danger-dark" />
                        <span className="font-mono">{Number(entry.credit_amount).toLocaleString()}</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-x-4 gap-y-0.5 mt-1.5 text-[11px] text-gray-400">
                    <span>Dr: {entry.debit_account}</span>
                    <span>Cr: {entry.credit_account}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
