"use client";

import React, { useState, useEffect, useRef } from "react";
import axios from "axios";
import { Sun, Moon, Calendar, Database, Download, FileDown } from "lucide-react";
import Sidebar from "@/components/Sidebar";
import ChatPanel from "@/components/ChatPanel";
import Dashboard from "@/components/Dashboard";
import AgentForms from "@/components/AgentForms";
import DirectFeatures from "@/components/DirectFeatures";
import SettingsModal from "@/components/SettingsModal";
import AgentCards, { downloadExport } from "@/components/AgentCards";
import ApprovalBadge from "@/components/ApprovalBadge";
import ApprovalsPanel, { type ApprovalResolvedEvent } from "@/components/ApprovalsPanel";
import { AGENTS_DATA } from "@/components/agentsData";

class ErrorBoundary extends React.Component<{children: React.ReactNode}, {hasError: boolean}> {
  constructor(props: {children: React.ReactNode}) {
    super(props);
    this.state = { hasError: false };
  }
  static getDerivedStateFromError() { return { hasError: true }; }
  render() {
    if (this.state.hasError) {
      return (
        <div className="flex items-center justify-center h-screen bg-surface-light dark:bg-surface-dark text-gray-800 dark:text-gray-200">
          <div className="text-center p-8">
            <h2 className="text-xl font-semibold mb-2">Something went wrong</h2>
            <p className="text-gray-500">Please refresh the page to try again.</p>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function Home() {
  const [currentView, setCurrentView] = useState("dashboard");
  const [darkMode, setDarkMode] = useState(true);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [dbHealthy, setDbHealthy] = useState(true);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [exportOpen, setExportOpen] = useState(false);
  const [approvalsOpen, setApprovalsOpen] = useState(false);
  const [pendingApprovalCount, setPendingApprovalCount] = useState(0);
  const [approvalRefreshTick, setApprovalRefreshTick] = useState(0);
  // Last approval resolved from the Notifications panel — forwarded to ChatPanel
  // so the result also appears in the chat thread (not only panel history).
  const [lastApproval, setLastApproval] = useState<ApprovalResolvedEvent | null>(null);
  const exportRef = useRef<HTMLDivElement | null>(null);

  const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

  // Check DB status on mount
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const response = await axios.get(`${apiBase}/health`, { timeout: 30000 });
        setDbHealthy(response.data.database === "healthy");
      } catch (err) {
        setDbHealthy(false);
      }
    };
    checkHealth();
    const interval = setInterval(checkHealth, 10000);
    return () => clearInterval(interval);
  }, []);

  // Fetch pending approval count on mount, when a tool is queued, and every 10s
  useEffect(() => {
    const fetchPendingCount = async () => {
      try {
        const response = await axios.get(`${apiBase}/approvals/pending`, { timeout: 15000 });
        setPendingApprovalCount(response.data.approvals?.length || 0);
      } catch (err) {
        // Backend not reachable — keep current count
      }
    };
    fetchPendingCount();
    const interval = setInterval(fetchPendingCount, 10000);
    return () => clearInterval(interval);
  }, [approvalRefreshTick]);

  // Theme effect
  useEffect(() => {
    const root = window.document.documentElement;
    if (darkMode) {
      root.classList.add("dark");
    } else {
      root.classList.remove("dark");
    }
  }, [darkMode]);

  // Close export dropdown on outside click
  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (exportRef.current && !exportRef.current.contains(e.target as Node)) {
        setExportOpen(false);
      }
    };
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, []);

  const selectedAgent = AGENTS_DATA.find((a) => a.id === currentView);

  return (
    <ErrorBoundary>
      <div className={`h-screen flex flex-col overflow-hidden font-sans bg-background-light dark:bg-background-dark text-gray-800 dark:text-gray-200`}>
      {/* Top Bar */}
      <header className="flex items-center justify-between px-6 py-3 border-b bg-surface-light dark:bg-surface-dark border-gray-200 dark:border-gray-800 flex-shrink-0 z-10">
        <div className="flex items-center gap-3">
          <span className="font-serif font-bold text-lg tracking-wide uppercase text-accent-light">
            AI Accountant
          </span>
          <span className="text-[10px] uppercase font-bold text-gray-400 border border-gray-200 dark:border-gray-800 px-2 py-0.5 rounded">
            Orchestration Node v1
          </span>
        </div>

        <div className="flex items-center gap-6 text-xs font-semibold text-gray-500">
          {/* PostgreSQL status */}
          <div className="flex items-center gap-2">
            <Database className="w-3.5 h-3.5" />
            <span>Database Connection:</span>
            <span className={`w-2.5 h-2.5 rounded-full ${dbHealthy ? "bg-emerald-500 animate-pulse" : "bg-red-500"}`} />
            <span className={dbHealthy ? "text-emerald-500" : "text-red-500"}>
              {dbHealthy ? "ONLINE" : "OFFLINE"}
            </span>
          </div>

          <div className="flex items-center gap-1.5 border-l border-gray-200 dark:border-gray-800 pl-6">
            <Calendar className="w-3.5 h-3.5" />
            <span>{new Date().toLocaleDateString("en-US", { weekday: "short", year: "numeric", month: "short", day: "numeric" })}</span>
          </div>

          {/* Theme Switcher Toggle */}
          <button
            onClick={() => setDarkMode(!darkMode)}
            aria-label="Toggle Theme Mode"
            className="p-2 rounded bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400"
          >
            {darkMode ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>

          {/* Notifications / Approvals badge */}
          <ApprovalBadge count={pendingApprovalCount} onClick={() => setApprovalsOpen(true)} />

          {/* Export Dropdown */}
          <div className="relative" ref={exportRef}>
            <button
              onClick={() => setExportOpen(!exportOpen)}
              aria-label="Export Data"
              className="flex items-center gap-1.5 p-2 rounded bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400 font-medium"
            >
              <Download className="w-4 h-4" />
              <span className="hidden sm:inline">Export</span>
            </button>

            {exportOpen && (
              <div className="absolute right-0 mt-2 w-72 max-h-[70vh] overflow-y-auto rounded border bg-surface-light dark:bg-surface-dark border-gray-200 dark:border-gray-800 shadow-lg z-50 py-2 text-sm">
                <ExportRow
                  label="All Data"
                  agent="all"
                  onSelect={() => setExportOpen(false)}
                />

                <div className="border-t border-gray-200 dark:border-gray-800 my-1" />

                {AGENTS_DATA.map((agent) => (
                  <ExportRow
                    key={agent.id}
                    label={agent.name}
                    agent={agent.id}
                    onSelect={() => setExportOpen(false)}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Primary Panels splits */}
      <div className="flex flex-1 overflow-hidden flex-col lg:flex-row">
        {/* Navigation Sidebar */}
        <Sidebar
          currentView={currentView}
          onSelectView={setCurrentView}
          onOpenSettings={() => setSettingsOpen(true)}
          collapsed={sidebarCollapsed}
          onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
        />

        {/* Center Panel (Main contents) */}
        {currentView === "chat" ? (
          <main className="flex-1 overflow-hidden flex">
            <ChatPanel
              fullPage
              externalApproval={lastApproval}
              onTransactionLogged={() => setRefreshTrigger((prev) => prev + 1)}
            />
          </main>
        ) : (
        <main className="flex-1 overflow-y-auto p-8 w-full lg:max-w-5xl mx-auto">
          {currentView === "dashboard" && (
            <Dashboard
              onSelectAgent={setCurrentView}
              refreshTrigger={refreshTrigger}
            />
          )}

          {currentView === "agents" && <AgentCards />}

          {currentView === "audit-trail" && <DirectFeatures view="audit-trail" />}

          {currentView === "roles" && <DirectFeatures view="roles" />}

          {selectedAgent && (
            <AgentForms
              agent={selectedAgent}
              onToolExecuted={() => {
                // Refresh dashboard statistics on any transaction update
                setRefreshTrigger((prev) => prev + 1);
              }}
              onQueuedForApproval={() => {
                // Refresh the pending approval badge immediately
                setApprovalRefreshTick((prev) => prev + 1);
              }}
            />
          )}
        </main>
        )}
      </div>

      {/* Settings preferences modal */}
      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}

      {/* Notifications & Approvals panel */}
      <ApprovalsPanel
        open={approvalsOpen}
        onClose={() => setApprovalsOpen(false)}
        onPendingCountChange={setPendingApprovalCount}
        onApproved={(evt) => setLastApproval(evt)}
      />
    </div>
    </ErrorBoundary>
  );
}

// One export dropdown row: label + [XLSX] [CSV] mini-buttons
function ExportRow({
  label,
  agent,
  onSelect,
}: {
  label: string;
  agent: string;
  onSelect: () => void;
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => {
        downloadExport("xlsx", agent);
        onSelect();
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          downloadExport("xlsx", agent);
          onSelect();
        }
      }}
      className="flex items-center justify-between gap-3 px-4 py-2 hover:bg-gray-100 dark:hover:bg-gray-800 cursor-pointer"
    >
      <span className="flex items-center gap-2 font-medium text-gray-800 dark:text-gray-200 min-w-0">
        <FileDown className="w-4 h-4 text-gray-400 flex-shrink-0" />
        <span className="truncate">{label}</span>
      </span>
      <span className="flex items-center gap-1 flex-shrink-0">
        <ExportMiniButton
          format="xlsx"
          agent={agent}
          onSelect={onSelect}
        />
        <ExportMiniButton
          format="csv"
          agent={agent}
          onSelect={onSelect}
        />
      </span>
    </div>
  );
}

function ExportMiniButton({
  format,
  agent,
  onSelect,
}: {
  format: "xlsx" | "csv";
  agent: string;
  onSelect: () => void;
}) {
  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        downloadExport(format, agent);
        onSelect();
      }}
      className="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase bg-gray-100 hover:bg-accent-light hover:text-white dark:bg-gray-800 dark:hover:bg-accent-light text-gray-500 dark:text-gray-400 border border-gray-200 dark:border-gray-700 transition-colors"
    >
      {format.toUpperCase()}
    </button>
  );
}
