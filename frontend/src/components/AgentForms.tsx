import React, { useState } from "react";
import axios from "axios";
import { AgentDef } from "./agentsData";
import { Play, ShieldAlert, Check, X, AlertCircle } from "lucide-react";

interface AgentFormsProps {
  agent: AgentDef;
  onToolExecuted: (output: any) => void;
}

export default function AgentForms({ agent, onToolExecuted }: AgentFormsProps) {
  const [activeTool, setActiveTool] = useState(agent.tools[0]?.name || "");
  const [formData, setFormData] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [executionMode, setExecutionMode] = useState<"ai" | "direct">("direct");

  const selectedTool = agent.tools.find((t) => t.name === activeTool);

  const handleInputChange = (name: string, value: string) => {
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleRunTool = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedTool) return;
    setLoading(true);
    setError(null);

    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

    try {
      if (executionMode === "direct") {
        // Direct execution — bypass LLM
        const params: Record<string, string> = {};
        selectedTool.inputs.forEach((inp) => {
          const value = formData[inp.name] || inp.default || "";
          if (value) params[inp.name] = value;
        });

        const response = await axios.post(`${apiBase}/tools/execute`, {
          tool_name: selectedTool.name,
          params,
        }, { timeout: 30000 });

        onToolExecuted({
          tool: selectedTool.name,
          output: JSON.stringify(response.data.result, null, 2),
          timestamp: new Date().toLocaleTimeString(),
        });
      } else {
        // AI execution — via orchestrator
        let instruction = `Run the tool ${selectedTool.name} with parameters: `;
        const paramList = selectedTool.inputs.map((inp) => {
          const value = formData[inp.name] || inp.default || "";
          return `${inp.name}: "${value}"`;
        });
        instruction += paramList.join(", ");

        const response = await axios.post(`${apiBase}/chat`, { message: instruction }, { timeout: 30000 });
        onToolExecuted({
          tool: selectedTool.name,
          output: response.data.response,
          timestamp: new Date().toLocaleTimeString(),
        });
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || err.response?.data?.error || err.message || "Failed to execute tool");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Title & Header */}
      <div>
        <h2 className="font-serif text-2xl text-gray-800 dark:text-gray-100 flex items-center gap-2">
          {agent.name}
        </h2>
        <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">{agent.role}</p>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-200 dark:border-gray-800 overflow-x-auto pb-px">
        {agent.tools.map((tool) => (
          <button
            key={tool.name}
            onClick={() => {
              setActiveTool(tool.name);
              setFormData({});
              setError(null);
            }}
            className={`px-4 py-2 text-sm font-medium transition-all border-b-2 whitespace-nowrap ${
              activeTool === tool.name
                ? "border-accent-light text-accent-light"
                : "border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200"
            }`}
          >
            {tool.name}
          </button>
        ))}
      </div>

      {/* Selected Tool Info & Form */}
      {selectedTool && (
        <div className="bg-surface-light dark:bg-surface-dark border border-gray-200 dark:border-gray-800 rounded p-6 space-y-6">
          <div className="space-y-2">
            <h3 className="font-semibold text-gray-800 dark:text-gray-200 text-lg flex items-center gap-2">
              <span>{selectedTool.name}</span>
              {selectedTool.approval && (
                <span className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded bg-amber-500/10 text-amber-500 border border-amber-500/20 font-bold uppercase tracking-wider">
                  <ShieldAlert className="w-3 h-3" /> Approval Required
                </span>
              )}
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {selectedTool.description}
            </p>
          </div>

          <form onSubmit={handleRunTool} className="space-y-4">
            {selectedTool.inputs.map((input) => (
              <div key={input.name} className="space-y-1.5">
                <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider">
                  {input.name.replace(/_/g, " ")} {input.required && <span className="text-red-500">*</span>}
                </label>
                {input.type === "textarea" ? (
                  <textarea
                    required={input.required}
                    value={formData[input.name] || ""}
                    onChange={(e) => handleInputChange(input.name, e.target.value)}
                    placeholder={input.placeholder}
                    rows={4}
                    className="w-full text-sm px-3 py-2 rounded bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-800 dark:text-gray-200 focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-light focus:border-accent-light"
                  />
                ) : (
                  <input
                    type={input.type}
                    required={input.required}
                    value={formData[input.name] || ""}
                    onChange={(e) => handleInputChange(input.name, e.target.value)}
                    placeholder={input.placeholder}
                    className="w-full text-sm px-3 py-2 rounded bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-800 dark:text-gray-200 focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-light focus:border-accent-light"
                  />
                )}
              </div>
            ))}

            {error && (
              <div className="flex items-center gap-2 p-3 text-sm rounded bg-red-500/10 text-red-500 border border-red-500/20">
                <AlertCircle className="w-4 h-4" />
                <span>{error}</span>
              </div>
            )}

            {!selectedTool.aiOnly && (
              <div className="flex items-center gap-2 pt-2">
                <span className="text-xs text-gray-500 font-medium">Execute mode:</span>
                <button
                  type="button"
                  onClick={() => setExecutionMode("direct")}
                  className={`px-3 py-1.5 text-xs rounded font-medium transition-colors ${
                    executionMode === "direct"
                      ? "bg-accent-light text-white"
                      : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700"
                  }`}
                >
                  Execute Direct
                </button>
                <button
                  type="button"
                  onClick={() => setExecutionMode("ai")}
                  className={`px-3 py-1.5 text-xs rounded font-medium transition-colors ${
                    executionMode === "ai"
                      ? "bg-accent-light text-white"
                      : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700"
                  }`}
                >
                  Execute with AI
                </button>
              </div>
            )}
            {selectedTool.aiOnly && (
              <div className="pt-2">
                <span className="text-[10px] px-2 py-1 rounded bg-amber-500/10 text-amber-500 border border-amber-500/20 font-semibold inline-flex items-center gap-1">
                  <span>⚡</span> AI Required — this tool only works with AI execution
                </span>
              </div>
            )}

            <div className="pt-4 border-t border-gray-200 dark:border-gray-800 flex justify-end">
              <button
                type="submit"
                disabled={loading}
                className="flex items-center gap-2 px-5 py-2.5 rounded bg-accent-light hover:bg-accent-light/95 text-white font-medium text-sm transition-colors disabled:opacity-50"
              >
                {loading ? (
                  <span>Running...</span>
                ) : (
                  <>
                    <Play className="w-4 h-4" /> Execute Tool
                  </>
                )}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
