import React, { useState } from "react";
import axios from "axios";
import { AgentDef } from "./agentsData";
import { Play, ShieldAlert, AlertCircle, CheckCircle2, Plus, X } from "lucide-react";

interface AgentFormsProps {
  agent: AgentDef;
  onToolExecuted: (output: any) => void;
}

// Extract a human-friendly summary + record ID from a tool result
function summarizeResult(result: any): { summary: string; recordId?: string } {
  if (!result || typeof result !== "object") {
    return { summary: "Completed successfully." };
  }
  // Common ID fields across tools
  const idKey = Object.keys(result).find((k) =>
    /^(id|.*_id|entry_id|asset_id|journal_entry_id|accrual_id|cheque_id|lc_id|run_id|task_id|provision_id|flag_id|reconciliation_id|filing_id|report_id|register_id)$/i.test(k)
  );
  const recordId = idKey ? String(result[idKey]) : undefined;

  // Pick a short summary: message field, or first non-id value
  const msg = result.message || result.summary || result.status;
  let summary: string;
  if (typeof msg === "string") summary = msg;
  else if (typeof result.total_outstanding !== "undefined") summary = `Total outstanding: ${result.total_outstanding}`;
  else if (typeof result.total_revenue !== "undefined") summary = `Revenue: ${result.total_revenue}`;
  else if (typeof result.net_income !== "undefined") summary = `Net income: ${result.net_income}`;
  else if (typeof result.closing_balance !== "undefined") summary = `Closing balance: ${result.closing_balance}`;
  else summary = "Completed successfully.";

  return { summary, recordId };
}

export default function AgentForms({ agent, onToolExecuted }: AgentFormsProps) {
  const [activeTool, setActiveTool] = useState(agent.tools[0]?.name || "");
  const [formData, setFormData] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<{ summary: string; recordId?: string } | null>(null);
  const [output, setOutput] = useState<string | null>(null);
  const [executionMode, setExecutionMode] = useState<"ai" | "direct">("direct");
  // Custom fields for tools that support them (e.g. record_bank_transaction)
  const [customFields, setCustomFields] = useState<{ name: string; value: string }[]>([]);

  const selectedTool = agent.tools.find((t) => t.name === activeTool);

  const addCustomField = () => {
    setCustomFields((prev) => [...prev, { name: "", value: "" }]);
  };

  const removeCustomField = (idx: number) => {
    setCustomFields((prev) => prev.filter((_, i) => i !== idx));
  };

  const updateCustomField = (idx: number, key: "name" | "value", val: string) => {
    setCustomFields((prev) => prev.map((f, i) => (i === idx ? { ...f, [key]: val } : f)));
  };

  const handleInputChange = (name: string, value: string) => {
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleRunTool = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedTool) return;
    setLoading(true);
    setError(null);
    setSuccess(null);

    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

    try {
      if (executionMode === "direct") {
        // Direct execution — bypass LLM
        const params: Record<string, any> = {};
        selectedTool.inputs.forEach((inp) => {
          const value = formData[inp.name] || inp.default || "";
          if (value) params[inp.name] = value;
        });

        // Attach custom fields if any were filled (name + value)
        const filledCustom = customFields.filter((f) => f.name.trim() && f.value.trim());
        if (filledCustom.length) {
          const cf: Record<string, string> = {};
          filledCustom.forEach((f) => { cf[f.name.trim()] = f.value.trim(); });
          params.custom_fields = cf;
        }

        const response = await axios.post(`${apiBase}/tools/execute`, {
          tool_name: selectedTool.name,
          params,
        }, { timeout: 30000 });

        if (response.data.success) {
          const { summary, recordId } = summarizeResult(response.data.result);
          setSuccess({ summary, recordId });
          setOutput(JSON.stringify(response.data.result, null, 2));
        } else {
          setError(response.data.error || "Tool execution failed");
          setOutput(null);
        }

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
        setSuccess({ summary: "AI response received. See output below for details." });
        setOutput(response.data.response);
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
      <div className="flex flex-wrap border-b border-gray-200 dark:border-gray-800 gap-0.5 pb-px">
        {agent.tools.map((tool) => (
          <button
            key={tool.name}
            onClick={() => {
              setActiveTool(tool.name);
              setFormData({});
              setError(null);
              setSuccess(null);
              setOutput(null);
              setCustomFields([]);
            }}
            className={`px-3 py-2 text-sm font-medium transition-all border-b-2 ${
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

            {/* Custom fields (name/value pairs) — for record_bank_transaction etc */}
            {customFields.map((cf, idx) => (
              <div key={idx} className="flex items-center gap-2">
                <input
                  type="text"
                  value={cf.name}
                  onChange={(e) => updateCustomField(idx, "name", e.target.value)}
                  placeholder="Field name (e.g. Payee)"
                  className="flex-1 text-sm px-3 py-2 rounded bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-800 dark:text-gray-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-light"
                />
                <input
                  type="text"
                  value={cf.value}
                  onChange={(e) => updateCustomField(idx, "value", e.target.value)}
                  placeholder="Field value"
                  className="flex-1 text-sm px-3 py-2 rounded bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-800 dark:text-gray-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-light"
                />
                <button
                  type="button"
                  onClick={() => removeCustomField(idx)}
                  aria-label="Remove custom field"
                  className="p-2 rounded text-gray-400 hover:text-red-500 hover:bg-red-500/10 transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ))}
            <div className="flex justify-start">
              <button
                type="button"
                onClick={addCustomField}
                className="flex items-center gap-1.5 text-xs font-medium text-accent-light hover:underline"
              >
                <Plus className="w-3.5 h-3.5" /> Add custom field
              </button>
            </div>

            {error && (
              <div className="flex items-center gap-2 p-3 text-sm rounded bg-red-500/10 text-red-500 border border-red-500/20">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {success && (
              <div className="flex items-start gap-2 p-3 text-sm rounded bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-500/20">
                <CheckCircle2 className="w-4 h-4 mt-0.5 flex-shrink-0" />
                <div className="space-y-0.5">
                  <div className="font-medium">
                    {selectedTool.name} executed
                  </div>
                  <div>{success.summary}</div>
                  {success.recordId && (
                    <div className="font-mono text-xs opacity-90">
                      Record: {success.recordId}
                    </div>
                  )}
                </div>
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

          {/* Tool output display */}
          {output && (
            <div className="pt-4 border-t border-gray-200 dark:border-gray-800">
              <div className="text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-2">
                Tool Output
              </div>
              <pre className="p-3 rounded bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 text-xs text-gray-800 dark:text-gray-200 overflow-x-auto max-h-96 overflow-y-auto">
                {output}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
