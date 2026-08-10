import React, { useEffect } from "react";
import { AGENTS_DATA } from "./agentsData";
import { LayoutDashboard, LayoutGrid, Settings, User, BookOpen, MessageSquare, X } from "lucide-react";

const CATEGORIES = [
  { id: "operations", label: "Operations" },
  { id: "reporting", label: "Reporting" },
  { id: "compliance", label: "Compliance" },
  { id: "advisory", label: "Advisory" },
];

interface SidebarProps {
  currentView: string;
  onSelectView: (view: string) => void;
  onOpenSettings: () => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
  mobileOpen: boolean;
  onMobileOpenChange: (open: boolean) => void;
}

export default function Sidebar({
  currentView,
  onSelectView,
  onOpenSettings,
  collapsed,
  onToggleCollapse,
  mobileOpen,
  onMobileOpenChange,
}: SidebarProps) {
  // Close the mobile drawer on Escape. The shell is overflow-hidden, so the
  // fixed overlay covers content while the drawer is open.
  useEffect(() => {
    if (!mobileOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onMobileOpenChange(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mobileOpen, onMobileOpenChange]);

  // Selecting a view or opening settings from the drawer also closes it.
  const handleMobileSelect = (view: string) => {
    onSelectView(view);
    onMobileOpenChange(false);
  };
  const handleMobileSettings = () => {
    onOpenSettings();
    onMobileOpenChange(false);
  };

  return (
    <>
      {/* Desktop rail (lg+) — keeps the collapsed/expanded icon-rail behavior */}
      <div
        className={`hidden lg:flex flex-col border-r h-full transition-all duration-300 bg-surface-light dark:bg-surface-dark border-gray-200 dark:border-gray-800 ${
          collapsed ? "w-16" : "w-64"
        }`}
      >
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-800">
          {!collapsed && (
            <span className="font-semibold text-gray-800 dark:text-gray-200 uppercase tracking-widest text-xs">
              Navigation
            </span>
          )}
          <button
            onClick={onToggleCollapse}
            aria-label="Toggle Sidebar Collapse"
            className="ml-auto p-1.5 rounded bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400"
          >
            <ChevronIcon collapsed={collapsed} />
          </button>
        </div>
        <SidebarNav
          collapsed={collapsed}
          currentView={currentView}
          onSelectView={onSelectView}
        />

        {/* Pinned Bottom Area */}
        <div className="p-3 border-t border-gray-200 dark:border-gray-800">
          <button
            onClick={onOpenSettings}
            aria-label={collapsed ? "Settings" : undefined}
            className="w-full flex items-center gap-3 px-3 py-2 rounded text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            <Settings className="w-5 h-5 flex-shrink-0" />
            {!collapsed && <span>API Key Settings</span>}
          </button>
        </div>
      </div>

      {/* Mobile drawer (< lg) — slide-in overlay panel + backdrop per spec §4.
          Sidebar mounts once in page.tsx around the main content, so this
          drawer is shared by every view (Dashboard, Chat, Agents, Ledger,
          Reconciliation, Tax, ...). */}
      <div
        className={`fixed inset-0 z-50 lg:hidden ${mobileOpen ? "" : "pointer-events-none"}`}
        aria-hidden={!mobileOpen}
      >
        <div
          className={`absolute inset-0 bg-black/50 transition-opacity duration-300 ${
            mobileOpen ? "opacity-100" : "opacity-0"
          }`}
          onClick={() => onMobileOpenChange(false)}
        />
        <div
          className={`absolute inset-y-0 left-0 w-64 max-w-[80vw] flex flex-col bg-surface-light dark:bg-surface-dark border-r border-gray-200 dark:border-gray-800 shadow-xl transition-transform duration-300 ${
            mobileOpen ? "translate-x-0" : "-translate-x-full"
          }`}
        >
          <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-800">
            <span className="font-semibold text-gray-800 dark:text-gray-200 uppercase tracking-widest text-xs">
              Navigation
            </span>
            <button
              onClick={() => onMobileOpenChange(false)}
              aria-label="Close Navigation"
              className="p-2.5 rounded bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <SidebarNav
            collapsed={false}
            currentView={currentView}
            onSelectView={handleMobileSelect}
          />

          {/* Pinned Bottom Area */}
          <div className="p-3 border-t border-gray-200 dark:border-gray-800">
            <button
              onClick={handleMobileSettings}
              className="w-full flex items-center gap-3 px-3 py-2 rounded text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            >
              <Settings className="w-5 h-5 flex-shrink-0" />
              <span>API Key Settings</span>
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

function SidebarNav({
  collapsed,
  currentView,
  onSelectView,
}: {
  collapsed: boolean;
  currentView: string;
  onSelectView: (view: string) => void;
}) {
  return (
    <div className="flex-1 overflow-y-auto py-4 space-y-4 px-3">
      {/* Dashboard Link */}
      <div>
        <button
          onClick={() => onSelectView("dashboard")}
          className={`w-full flex items-center gap-3 px-3 py-2 rounded text-sm transition-colors ${
            currentView === "dashboard"
              ? "bg-accent-light text-white font-medium"
              : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
          }`}
        >
          <LayoutDashboard className="w-5 h-5 flex-shrink-0" />
          {!collapsed && <span>Dashboard Overview</span>}
        </button>
      </div>

      {/* Chat Link */}
      <div>
        <button
          onClick={() => onSelectView("chat")}
          className={`w-full flex items-center gap-3 px-3 py-2 rounded text-sm transition-colors ${
            currentView === "chat"
              ? "bg-accent-light text-white font-medium"
              : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
          }`}
        >
          <MessageSquare className="w-5 h-5 flex-shrink-0" />
          {!collapsed && <span>Chat</span>}
        </button>
      </div>

      {/* Agents Link */}
      <div>
        <button
          onClick={() => onSelectView("agents")}
          className={`w-full flex items-center gap-3 px-3 py-2 rounded text-sm transition-colors ${
            currentView === "agents"
              ? "bg-accent-light text-white font-medium"
              : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
          }`}
        >
          <LayoutGrid className="w-5 h-5 flex-shrink-0" />
          {!collapsed && <span>Agents</span>}
        </button>
      </div>

      {/* Direct features */}
      {!collapsed && (
        <div className="text-[10px] uppercase font-bold text-gray-400 dark:text-gray-500 tracking-wider mt-2 px-3">
          Features
        </div>
      )}
      <div className="space-y-1">
        <button
          onClick={() => onSelectView("audit-trail")}
          className={`w-full flex items-center gap-3 px-3 py-1.5 rounded text-xs transition-colors ${
            currentView === "audit-trail"
              ? "bg-accent-light/20 text-accent-light font-medium"
              : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
          }`}
        >
          <BookOpen className="w-4 h-4 flex-shrink-0" />
          {!collapsed && <span>Audit Trails</span>}
        </button>
        <button
          onClick={() => onSelectView("roles")}
          className={`w-full flex items-center gap-3 px-3 py-1.5 rounded text-xs transition-colors ${
            currentView === "roles"
              ? "bg-accent-light/20 text-accent-light font-medium"
              : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
          }`}
        >
          <User className="w-4 h-4 flex-shrink-0" />
          {!collapsed && <span>User Roles CRUD</span>}
        </button>
      </div>

      {/* Categories of Agents */}
      {CATEGORIES.map((cat) => {
        const agents = AGENTS_DATA.filter((a) => a.category === cat.id);
        if (agents.length === 0) return null;

        return (
          <div key={cat.id} className="space-y-1">
            {!collapsed && (
              <div className="text-[10px] uppercase font-bold text-gray-400 dark:text-gray-500 tracking-wider px-3">
                {cat.label}
              </div>
            )}
            {agents.map((agent) => {
              const Icon = agent.icon;
              return (
                <button
                  key={agent.id}
                  onClick={() => onSelectView(agent.id)}
                  className={`w-full flex items-center gap-3 px-3 py-2 rounded text-sm transition-colors ${
                    currentView === agent.id
                      ? "bg-accent-light text-white font-medium"
                      : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
                  }`}
                >
                  <Icon className="w-5 h-5 flex-shrink-0" />
                  {!collapsed && <span className="truncate">{agent.name}</span>}
                </button>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}

function ChevronIcon({ collapsed }: { collapsed: boolean }) {
  return collapsed ? (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
    </svg>
  ) : (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
    </svg>
  );
}
