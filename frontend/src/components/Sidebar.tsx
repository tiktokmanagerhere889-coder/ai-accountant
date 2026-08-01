import React from "react";
import { AGENTS_DATA, AgentDef } from "./agentsData";
import { LayoutDashboard, LayoutGrid, Settings, User, BookOpen } from "lucide-react";

interface SidebarProps {
  currentView: string;
  onSelectView: (view: string) => void;
  onOpenSettings: () => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export default function Sidebar({
  currentView,
  onSelectView,
  onOpenSettings,
  collapsed,
  onToggleCollapse,
}: SidebarProps) {
  const categories = [
    { id: "operations", label: "Operations" },
    { id: "reporting", label: "Reporting" },
    { id: "compliance", label: "Compliance" },
    { id: "advisory", label: "Advisory" },
  ];

  return (
    <div
      className={`flex flex-col border-r h-full transition-all duration-300 bg-surface-light dark:bg-surface-dark border-gray-200 dark:border-gray-800 ${
        collapsed ? "w-16" : "w-64"
      }`}
    >
      {/* Navigation Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-800">
        {!collapsed && (
          <span className="font-semibold text-gray-800 dark:text-gray-200 uppercase tracking-widest text-xs">
            Navigation
          </span>
        )}
        <div className="flex items-center gap-1">
          {/* Mobile hamburger toggle */}
          <button
            onClick={onToggleCollapse}
            aria-label="Toggle Sidebar"
            className="lg:hidden p-1.5 rounded bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              {collapsed ? (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              )}
            </svg>
          </button>
          {/* Desktop collapse toggle */}
          <button
            onClick={onToggleCollapse}
            aria-label="Toggle Sidebar Collapse"
            className="hidden lg:block p-1.5 rounded bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400"
          >
            <ChevronIcon collapsed={collapsed} />
          </button>
        </div>
      </div>

      {/* Main Navigation Items */}
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
        {categories.map((cat) => {
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
