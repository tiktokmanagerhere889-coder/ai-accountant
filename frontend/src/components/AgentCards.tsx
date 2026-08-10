"use client";

import React, { useRef, useState } from "react";
import { ChevronDown, Sparkles, MousePointerClick } from "lucide-react";
import { AGENTS_DATA } from "./agentsData";

const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export function downloadExport(format: "xlsx" | "csv", agent?: string) {
  const url = `${apiBase}/export/${format}${agent ? `?agent=${agent}` : ""}`;
  const filename = agent ? `${agent}.${format}` : `all-data.${format}`;
  // Anchor with download attribute — reliable cross-browser download.
  // _self navigation can misfire on some browsers; this triggers a real
  // download without leaving the page.
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

export default function AgentCards() {
  const [expandedAgent, setExpandedAgent] = useState<string | null>(null);

  // Single click always toggles the tools list. Export is only via the
  // per-card XLSX/CSV buttons (no double-click ambiguity).
  const toggleExpand = (agentId: string) => {
    setExpandedAgent((prev) => (prev === agentId ? null : agentId));
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-serif text-2xl text-gray-800 dark:text-gray-100 flex items-center gap-2">
          Agents
        </h2>
        <p className="text-sm text-gray-600 dark:text-gray-400 mt-1 flex items-center gap-1.5">
          <MousePointerClick className="w-3.5 h-3.5" />
          Click a card to view its tools. Use the XLSX / CSV buttons to export that agent&apos;s data.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {AGENTS_DATA.map((agent) => {
          const Icon = agent.icon;
          const expanded = expandedAgent === agent.id;

          return (
            <div
              key={agent.id}
              onClick={() => toggleExpand(agent.id)}
              className={`group cursor-pointer rounded-lg border bg-surface-light dark:bg-surface-dark border-gray-200 dark:border-gray-800 transition-all select-none ${
                expanded
                  ? "ring-2 ring-accent-light border-accent-light shadow-md"
                  : "hover:border-accent-light/60 hover:shadow-md"
              }`}
            >
              {/* Card header */}
              <div className="flex items-center gap-3 px-4 py-3">
                <div className="p-2 rounded bg-accent-light/10 text-accent-light flex-shrink-0">
                  <Icon className="w-5 h-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-sm text-gray-800 dark:text-gray-200 truncate">
                    {agent.name}
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400 truncate">
                    {agent.role}
                  </div>
                </div>
                <ChevronDown
                  className={`w-4 h-4 text-gray-400 transition-transform flex-shrink-0 ${
                    expanded ? "rotate-180" : "group-hover:text-accent-light"
                  }`}
                />
              </div>

              {/* Tools list (expanded) */}
              {expanded && (
                <div className="border-t border-gray-200 dark:border-gray-800 px-4 py-3 space-y-2">
                  <div className="text-[10px] uppercase font-bold text-gray-400 dark:text-gray-500 tracking-wider">
                    Tools ({agent.tools.length})
                  </div>
                  {agent.tools.map((tool) => (
                    <div key={tool.name} className="flex items-start gap-2 text-xs">
                      <span className="font-mono font-medium text-gray-800 dark:text-gray-200 flex-shrink-0">
                        {tool.name}
                      </span>
                      <span className="text-gray-500 dark:text-gray-400 flex-1 min-w-0">
                        — {tool.description}
                      </span>
                      {tool.aiOnly && (
                        <span className="flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-500 border border-amber-500/20 font-bold uppercase tracking-wider flex-shrink-0">
                          <Sparkles className="w-2.5 h-2.5" /> AI
                        </span>
                      )}
                    </div>
                  ))}
                  {/* Per-card export buttons (stopPropagation so card click doesn't toggle) */}
                  <div className="flex items-center gap-2 pt-2 border-t border-gray-200 dark:border-gray-800">
                    <span className="text-[10px] text-gray-400 dark:text-gray-500 uppercase tracking-wider font-bold">
                      Export
                    </span>
                    <button
                      onClick={(e) => { e.stopPropagation(); downloadExport("xlsx", agent.id); }}
                      className="text-[11px] px-2.5 py-2 rounded bg-accent-light/10 text-accent-light hover:bg-accent-light/20 font-semibold"
                    >
                      XLSX
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); downloadExport("csv", agent.id); }}
                      className="text-[11px] px-2.5 py-2 rounded bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 font-semibold"
                    >
                      CSV
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
