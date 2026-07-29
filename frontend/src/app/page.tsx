"use client";

import React, { useState, useEffect } from "react";
import axios from "axios";
import { Sun, Moon, Calendar, Database } from "lucide-react";
import Sidebar from "@/components/Sidebar";
import ChatPanel from "@/components/ChatPanel";
import Dashboard from "@/components/Dashboard";
import AgentForms from "@/components/AgentForms";
import DirectFeatures from "@/components/DirectFeatures";
import SettingsModal from "@/components/SettingsModal";
import { AGENTS_DATA } from "@/components/agentsData";

export default function Home() {
  const [currentView, setCurrentView] = useState("dashboard");
  const [darkMode, setDarkMode] = useState(true);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [dbHealthy, setDbHealthy] = useState(true);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const apiBase = "http://127.0.0.1:8000";

  // Check DB status on mount
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const response = await axios.get(`${apiBase}/health`);
        setDbHealthy(response.data.database === "healthy");
      } catch (err) {
        setDbHealthy(false);
      }
    };
    checkHealth();
    const interval = setInterval(checkHealth, 10000);
    return () => clearInterval(interval);
  }, []);

  // Theme effect
  useEffect(() => {
    const root = window.document.documentElement;
    if (darkMode) {
      root.classList.add("dark");
    } else {
      root.classList.remove("dark");
    }
  }, [darkMode]);

  const selectedAgent = AGENTS_DATA.find((a) => a.id === currentView);

  return (
    <div className={`min-h-screen flex flex-col font-sans bg-background-light dark:bg-background-dark text-gray-800 dark:text-gray-200 transition-colors duration-200`}>
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
        </div>
      </header>

      {/* Primary Panels splits */}
      <div className="flex flex-1 overflow-hidden">
        {/* Navigation Sidebar */}
        <Sidebar
          currentView={currentView}
          onSelectView={setCurrentView}
          onOpenSettings={() => setSettingsOpen(true)}
          collapsed={sidebarCollapsed}
          onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
        />

        {/* Center Panel (Main contents) */}
        <main className="flex-1 overflow-y-auto p-8 max-w-5xl mx-auto w-full">
          {currentView === "dashboard" && (
            <Dashboard
              onSelectAgent={setCurrentView}
              refreshTrigger={refreshTrigger}
            />
          )}

          {currentView === "audit-trail" && <DirectFeatures view="audit-trail" />}

          {currentView === "roles" && <DirectFeatures view="roles" />}

          {selectedAgent && (
            <AgentForms
              agent={selectedAgent}
              onToolExecuted={() => {
                // Refresh dashboard statistics on any transaction update
                setRefreshTrigger((prev) => prev + 1);
              }}
            />
          )}
        </main>

        {/* Right AI Chat box */}
        <ChatPanel onTransactionLogged={() => setRefreshTrigger((prev) => prev + 1)} />
      </div>

      {/* Settings preferences modal */}
      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
    </div>
  );
}
