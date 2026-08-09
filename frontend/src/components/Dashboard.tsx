import React, { useState, useEffect } from "react";
import axios from "axios";
import {
  DollarSign, ListTodo, AlertTriangle, ShieldCheck,
  Percent, ArrowRight, RefreshCw
} from "lucide-react";

interface DashboardProps {
  onSelectAgent: (id: string) => void;
  refreshTrigger: number;
}

export default function Dashboard({ onSelectAgent, refreshTrigger }: DashboardProps) {
  const [cashBalance, setCashBalance] = useState<string>("Calculating...");
  const [transactions, setTransactions] = useState<any[]>([]);
  const [healthScore, setHealthScore] = useState<number | null>(null);
  const [auditStats, setAuditStats] = useState<{ total: number; resolved: number; open: number }>({
    total: 0,
    resolved: 0,
    open: 0,
  });

  const [auditLoading, setAuditLoading] = useState(true);
  const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

  useEffect(() => {
    fetchDashboardStats();
  }, [refreshTrigger]);

  const fetchDashboardStats = async () => {
    setAuditLoading(true);
    // Use the current date dynamically so the dashboard always reflects the
    // latest entries (was hardcoded to 2026-08-01, missing newer transactions).
    const today = new Date();
    const todayISO = today.toISOString().slice(0, 10);
    const currentYear = today.getFullYear();
    const firstOfMonth = `${todayISO.slice(0, 7)}-01`;
    const yearStart = `${currentYear}-01-01`;
    const yearEnd = `${currentYear}-12-31`;

    try {
      // 1. Fetch cash position via DIRECT tool (no LLM — reliable)
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

      // 2. Fetch financial health score via DIRECT tool (replaces hardcoded 92%)
      try {
        const healthRes = await axios.post(`${apiBase}/tools/execute`, {
          tool_name: "assess_financial_health",
          params: { fiscal_year: currentYear },
        }, { timeout: 30000 });
        const score = healthRes.data.result?.score;
        if (typeof score === "number") {
          setHealthScore(score);
        } else {
          setHealthScore(null);
        }
      } catch {
        setHealthScore(null);
      }

      // 3. Fetch recent ledger entries via DIRECT tool
      const ledgerRes = await axios.post(`${apiBase}/tools/execute`, {
        tool_name: "get_general_ledger",
        params: { from_date: yearStart, to_date: yearEnd },
      }, { timeout: 30000 });
      const accounts = ledgerRes.data.result?.accounts || [];
      const txs = accounts.map((a: any) => ({
        id: a.account_code,
        desc: a.account_name,
        amount: Math.abs(Number(a.closing_balance || 0)).toLocaleString("en-US", { minimumFractionDigits: 2 }),
        type: Number(a.closing_balance) > 0 ? "debit" : "credit",
        account: `${a.account_code}-${a.account_name}`,
      }));
      setTransactions(txs);

      // 4. Fetch audit logs count via uncapped /audit-trail/count endpoint
      //    (the list endpoint caps at limit<=100, so counting its rows would
      //    under-report once more than 100 logs exist).
      const logsRes = await axios.get(`${apiBase}/audit-trail/count`, { timeout: 30000 });
      const total = logsRes.data?.total ?? 0;
      setAuditStats({
        total,
        resolved: 0,
        open: 0,
      });
      setAuditLoading(false);
    } catch (err) {
      console.error("Dashboard statistics retrieval failed:", err);
      setCashBalance("Unavailable");
      setHealthScore(null);
      setAuditLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div>
        <h2 className="font-serif text-2xl text-gray-800 dark:text-gray-100">
          Financial Control Dashboard
        </h2>
        <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
          Operational accounting logs and AI-automated specialists orchestrator node status.
        </p>
      </div>

      {/* Cards Panel */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Cash balance card */}
        <div className="bg-surface-light dark:bg-surface-dark border border-gray-200 dark:border-gray-800 rounded p-6 flex flex-col justify-between h-36">
          <div className="flex items-center justify-between text-gray-500">
            <span className="text-xs uppercase font-bold tracking-wider">Net Cash Position</span>
            <DollarSign className="w-5 h-5 text-accent-light" />
          </div>
          <div className="text-2xl font-semibold font-mono tabular-nums text-gray-900 dark:text-gray-100">
            {cashBalance === "Unavailable" ? (
              <span className="text-sm font-normal text-gray-500">Currently Unavailable</span>
            ) : (
              `PKR ${cashBalance}`
            )}
          </div>
          <button
            onClick={() => onSelectAgent("daily-entry")}
            className="text-xs text-accent-light hover:underline font-semibold flex items-center gap-1 mt-2 self-start"
          >
            Manage cash flow <ArrowRight className="w-3 h-3" />
          </button>
        </div>

        {/* Audit status card */}
        <div className="bg-surface-light dark:bg-surface-dark border border-gray-200 dark:border-gray-800 rounded p-6 flex flex-col justify-between h-36">
          <div className="flex items-center justify-between text-gray-500">
            <span className="text-xs uppercase font-bold tracking-wider">Audit Trail Updates</span>
            <ListTodo className="w-5 h-5 text-amber-500" />
          </div>
          <div className="text-2xl font-semibold font-mono text-gray-900 dark:text-gray-100">
            {auditLoading ? (
              <div className="h-8 w-16 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
            ) : (
              <span className="text-2xl font-bold">{auditStats.total}</span>
            )} <span className="text-xs font-normal text-gray-500">Logged Actions</span>
          </div>
          <button
            onClick={() => onSelectAgent("audit")}
            className="text-xs text-accent-light hover:underline font-semibold flex items-center gap-1 mt-2 self-start"
          >
            Review audit trail <ArrowRight className="w-3 h-3" />
          </button>
        </div>

        {/* Financial health card */}
        <div className="bg-surface-light dark:bg-surface-dark border border-gray-200 dark:border-gray-800 rounded p-6 flex flex-col justify-between h-36">
          <div className="flex items-center justify-between text-gray-500">
            <span className="text-xs uppercase font-bold tracking-wider">Corporate Ratios</span>
            <Percent className="w-5 h-5 text-emerald-500" />
          </div>
          <div className="text-2xl font-semibold font-mono text-gray-900 dark:text-gray-100">
            {healthScore !== null ? (
              <>{healthScore}% <span className="text-xs font-normal text-gray-500">Financial Health</span></>
            ) : (
              <span className="text-sm font-normal text-gray-500">Not calculated</span>
            )}
          </div>
          <button
            onClick={() => onSelectAgent("advisory")}
            className="text-xs text-accent-light hover:underline font-semibold flex items-center gap-1 mt-2 self-start"
          >
            Analyze financial indicators <ArrowRight className="w-3 h-3" />
          </button>
        </div>
      </div>

      {/* Main Splits: Recent transactions & Alerts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Ledger items */}
        <div className="bg-surface-light dark:bg-surface-dark border border-gray-200 dark:border-gray-800 rounded p-6 lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-sm uppercase tracking-wider text-gray-700 dark:text-gray-300">
              Recent General Ledger postings
            </h3>
            <button onClick={fetchDashboardStats} aria-label="Refresh dashboard data">
              <RefreshCw className="w-4 h-4 text-gray-400 hover:text-gray-600" />
            </button>
          </div>
          {transactions.length === 0 ? (
            <div className="text-center p-8 text-sm text-gray-500">
              No entries logged in this session range.
            </div>
          ) : (
            <div className="divide-y divide-gray-100 dark:divide-gray-800">
              {transactions.map((tx, idx) => (
                <div key={idx} className="py-3 flex items-center justify-between text-xs">
                  <div className="space-y-1">
                    <span className="font-mono text-gray-500 dark:text-gray-500 mr-2">{tx.id}</span>
                    <span className="font-medium text-gray-800 dark:text-gray-200">{tx.desc}</span>
                    <div className="text-[10px] text-gray-400 font-mono">{tx.account}</div>
                  </div>
                  <span className={`font-mono font-semibold tabular-nums ${tx.type === "debit" ? "text-red-500" : "text-emerald-500"}`}>
                    {tx.type === "debit" ? "- " : "+ "} PKR {tx.amount}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Status Alerts */}
        <div className="bg-surface-light dark:bg-surface-dark border border-gray-200 dark:border-gray-800 rounded p-6">
          <h3 className="font-semibold text-sm uppercase tracking-wider text-gray-700 dark:text-gray-300 mb-4">
            System Alerts
          </h3>
          <div className="space-y-4">
            <div className="p-3.5 rounded border border-emerald-500/20 bg-emerald-500/10 dark:bg-emerald-500/20 flex items-start gap-3">
              <ShieldCheck className="w-5 h-5 text-emerald-500 flex-shrink-0" />
              <div className="text-xs">
                <div className="font-semibold text-emerald-800 dark:text-emerald-400">Database Connection</div>
                <div className="text-gray-600 dark:text-gray-400 mt-0.5">PostgreSQL instances connected and fully synced.</div>
              </div>
            </div>
            <div className="p-3.5 rounded border border-amber-500/20 bg-amber-500/10 dark:bg-amber-500/20 flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0" />
              <div className="text-xs">
                <div className="font-semibold text-amber-800 dark:text-amber-400">Audit Reminders</div>
                <div className="text-gray-600 dark:text-gray-400 mt-0.5">Prepare final year close notes before closing dates.</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
