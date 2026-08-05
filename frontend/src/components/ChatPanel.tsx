import React, { useState, useEffect, useRef } from "react";
import axios from "axios";
import { Send, Check, X, ShieldAlert, Loader2, Sparkles, Wand2 } from "lucide-react";

interface ToolCallInfo {
  toolName: string;
  recordId?: string;
  summary: string;
  status?: "executed" | "queued";
}

interface Message {
  sender: "user" | "ai";
  text: string;
  toolCalls?: ToolCallInfo[];
  suggestions?: string[];
  approvalCard?: {
    toolName: string;
    description: string;
    params: Record<string, any>;
    approvalId: string;
  };
}

interface ChatPanelProps {
  onTransactionLogged?: () => void;
}

// Quick-suggestion chips shown before any message is sent
const QUICK_SUGGESTIONS = [
  "Show Trial Balance",
  "Generate P&L",
  "Check Cash Position",
  "Show AP Aging",
  "Run Anomaly Check",
  "Calculate Financial Ratios",
];

// Extract tool-call info from an orchestrator response (JSON blocks with tool/entry ids)
function extractToolCalls(response: string): ToolCallInfo[] {
  const calls: ToolCallInfo[] = [];
  // Match JSON blocks containing tool name and/or record ids
  const blocks = response.match(/\{[\s\S]*?\}/g) || [];
  for (const block of blocks) {
    try {
      const obj = JSON.parse(block);
      const toolName = obj.tool || obj.tool_name;
      if (!toolName) continue;
      const idKey = Object.keys(obj).find((k) =>
        /^(.*_id|entry_id|asset_id|run_id|task_id|accrual_id|cheque_id|provision_id|filing_id)$/i.test(k)
      );
      calls.push({
        toolName: String(toolName),
        recordId: idKey ? String(obj[idKey]) : undefined,
        summary: obj.message || obj.status || obj.description || "Tool executed",
      });
    } catch {
      // not JSON — skip
    }
  }
  return calls;
}

// Pick 2-3 relevant follow-up suggestions based on what was just asked/done
function followUpSuggestions(userMessage: string, toolCalls: ToolCallInfo[]): string[] {
  const msg = userMessage.toLowerCase();
  const pool: string[] = [];

  if (msg.includes("trial balance") || msg.includes("balance")) pool.push("Show Balance Sheet");
  if (msg.includes("p&l") || msg.includes("profit") || msg.includes("loss")) pool.push("Show Cash Flow Statement");
  if (msg.includes("cash")) pool.push("Forecast Cash Flow (30 days)");
  if (msg.includes("ap") || msg.includes("payable") || msg.includes("aging")) pool.push("Review Unpaid Bills");
  if (msg.includes("anomaly") || msg.includes("audit")) pool.push("Get Compliance Deadlines");
  if (msg.includes("ratio") || msg.includes("financial health")) pool.push("Assess Financial Health");
  if (toolCalls.length && /journal|entry|asset|cheque|accrual/i.test(toolCalls.map(t => t.toolName).join(" "))) {
    pool.push("View General Ledger");
  }

  // Fallbacks if nothing matched
  if (pool.length < 2) {
    const fallbacks = ["Generate P&L", "Check Cash Position", "Show Trial Balance"];
    for (const f of fallbacks) {
      if (!pool.includes(f)) pool.push(f);
      if (pool.length >= 3) break;
    }
  }
  return pool.slice(0, 3);
}

export default function ChatPanel({ onTransactionLogged }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      sender: "ai",
      text: "Hello! I am your AI Accounting Assistant. You can ask me to perform financial tasks, draft balances, analyze budgets, or record double entries using plain English.",
      suggestions: QUICK_SUGGESTIONS,
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMessage = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { sender: "user", text: userMessage }]);
    setLoading(true);

    try {
      const response = await axios.post(`${apiBase}/chat`, { message: userMessage }, { timeout: 60000 });
      const data = response.data;

      // Basic fallback extraction parser if the response indicates approval needed
      let approvalData: { toolName: string; description: string; params: Record<string, any>; approvalId: string } | null = null;
      if (
        data.response.includes('"needs_approval": true') ||
        data.response.includes("needs_approval: true") ||
        data.response.includes('"needs_approval": 1')
      ) {
        // Try parsing JSON block out of response
        try {
          const jsonMatch = data.response.match(/\{[\s\S]*?\}/);
          if (jsonMatch) {
            const parsed = JSON.parse(jsonMatch[0]);
            approvalData = {
              toolName: parsed.tool || "Accounting Tool",
              description: parsed.message || parsed.description || "Action needs human confirmation.",
              params: parsed.parameters || parsed,
              approvalId: parsed.approval_id || uuidv4(),
            };
          }
        } catch (err) {
          // Log parsing error silently
        }
      }

      // Extract tool-call info + suggest follow-ups.
      // Prefer the backend's structured tool_calls field; fall back to text parsing.
      const toolCalls = (data.tool_calls?.length ? data.tool_calls : extractToolCalls(data.response)) as ToolCallInfo[];
      const suggestions = followUpSuggestions(userMessage, toolCalls);

      setMessages((prev) => [
        ...prev,
        {
          sender: "ai",
          text: cleanMarkdownJSON(data.response),
          approvalCard: approvalData || undefined,
          toolCalls: toolCalls.length ? toolCalls : undefined,
          suggestions,
        },
      ]);

      // If it contains journal entry logging details, trigger page refresh of balances
      if (data.response.includes("JE-") || data.response.includes("Journal entry")) {
        onTransactionLogged?.();
      }
    } catch (error: any) {
      console.error(error);
      setMessages((prev) => [
        ...prev,
        {
          sender: "ai",
          text: `Error connecting to AI service: ${error.response?.data?.detail || error.message || "Unknown error"}`,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const sendSuggestion = async (text: string) => {
    if (!text.trim() || loading) return;
    setInput("");
    setMessages((prev) => [...prev, { sender: "user", text }]);
    setLoading(true);
    try {
      const response = await axios.post(`${apiBase}/chat`, { message: text }, { timeout: 60000 });
      const data = response.data;
      const toolCalls = (data.tool_calls?.length ? data.tool_calls : extractToolCalls(data.response)) as ToolCallInfo[];
      const suggestions = followUpSuggestions(text, toolCalls);
      setMessages((prev) => [
        ...prev,
        {
          sender: "ai",
          text: cleanMarkdownJSON(data.response),
          toolCalls: toolCalls.length ? toolCalls : undefined,
          suggestions,
        },
      ]);
    } catch (error: any) {
      console.error(error);
      setMessages((prev) => [
        ...prev,
        {
          sender: "ai",
          text: `Error connecting to AI service: ${error.response?.data?.detail || error.message || "Unknown error"}`,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleApproval = async (approved: boolean, cardData: any) => {
    setLoading(true);
    try {
      const response = await axios.post(`${apiBase}/chat`, {
        message: approved ? `approve the task ${cardData.toolName}` : `reject the task ${cardData.toolName}`
      }, { timeout: 30000 });

      setMessages((prev) => [
        ...prev,
        {
          sender: "ai",
          text: approved
            ? `Approved action: ${cardData.toolName}. Response:\n\n${cleanMarkdownJSON(response.data.response)}`
            : `Rejected action: ${cardData.toolName}.`,
        }
      ]);

      // Clean current card from message block
      setMessages((prev) =>
        prev.map((msg) =>
          msg.approvalCard?.approvalId === cardData.approvalId
            ? { ...msg, approvalCard: undefined }
            : msg
        )
      );

      onTransactionLogged?.();
    } catch (error: any) {
      console.error(error);
      setMessages((prev) => [
        ...prev,
        {
          sender: "ai",
          text: `Approval failed: ${error.response?.data?.detail || error.message}`,
        }
      ]);
    } finally {
      setLoading(false);
    }
  };

  function uuidv4() {
    return "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (c) =>
      (
        Number(c) ^
        (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (Number(c) / 4)))
      ).toString(16)
    );
  }

  function cleanMarkdownJSON(text: string): string {
    // strip out long raw JSON schema blocks if they contaminate AI response
    return text.replace(/```json[\s\S]*?```/g, (match) => {
      if (match.includes("needs_approval")) {
        return "*[Approval card rendered below]*";
      }
      return match;
    });
  }

  return (
    <div className="flex flex-col h-full bg-surface-light dark:bg-surface-dark border-l border-gray-200 dark:border-gray-800 w-full lg:w-80 xl:w-96 flex-shrink-0">
      {/* Header */}
      <div className="p-4 border-b border-gray-200 dark:border-gray-800 flex items-center gap-2">
        <Sparkles className="w-5 h-5 text-accent-light" />
        <span className="font-serif font-semibold text-gray-800 dark:text-gray-200">
          Assistant AI
        </span>
      </div>

      {/* Messages view */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg, index) => (
          <div key={index} className={`flex flex-col ${msg.sender === "user" ? "items-end" : "items-start"}`}>
            <div
              className={`p-3 rounded text-sm max-w-[85%] whitespace-pre-line leading-relaxed ${
                msg.sender === "user"
                  ? "bg-accent-light text-white rounded-br-none"
                  : "bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-300 rounded-bl-none border border-gray-200 dark:border-gray-700/50"
              }`}
            >
              {msg.text}
            </div>

            {/* Tool-call feedback (real data confirmation) */}
            {msg.toolCalls && msg.toolCalls.length > 0 && (
              <div className="mt-2 w-[85%] space-y-1.5">
                {msg.toolCalls.map((tc, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-2 px-3 py-2 rounded bg-accent-light/5 border border-accent-light/20 text-xs text-gray-700 dark:text-gray-300"
                  >
                    <Wand2 className="w-3.5 h-3.5 text-accent-light flex-shrink-0" />
                    <div className="min-w-0">
                      <span className="font-medium text-accent-light">{tc.toolName}</span>
                      {" — "}
                      <span className="text-gray-500 dark:text-gray-400">{tc.summary}</span>
                      {tc.status === "queued" && (
                        <span className="ml-1.5 text-[10px] px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-600 dark:text-amber-400 font-semibold uppercase">
                          queued
                        </span>
                      )}
                      {tc.recordId && (
                        <span className="ml-1.5 font-mono text-[10px] px-1.5 py-0.5 rounded bg-accent-light/10 text-accent-light">
                          {tc.recordId}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Follow-up suggestion chips */}
            {msg.suggestions && msg.suggestions.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5 w-[85%]">
                {msg.suggestions.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => sendSuggestion(s)}
                    disabled={loading}
                    className="px-2.5 py-1 text-[11px] rounded-full border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:border-accent-light hover:text-accent-light transition-colors"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}

            {/* Approval Render */}
            {msg.approvalCard && (
              <div className="mt-3 p-4 rounded border-l-4 border-amber-500 bg-amber-500/10 text-gray-800 dark:text-gray-200 text-xs w-[85%] space-y-3">
                <div className="flex items-center gap-2 font-semibold">
                  <ShieldAlert className="w-4 h-4 text-amber-500" />
                  <span>Human Approval Required</span>
                </div>
                <div className="font-semibold text-gray-900 dark:text-gray-100 uppercase">
                  {msg.approvalCard.toolName}
                </div>
                <p className="text-gray-600 dark:text-gray-400">
                  {msg.approvalCard.description}
                </p>
                <div className="flex gap-2 justify-end pt-2 border-t border-gray-200 dark:border-gray-700">
                  <button
                    onClick={() => handleApproval(false, msg.approvalCard)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-gray-300 dark:border-gray-600 hover:bg-gray-200 dark:hover:bg-gray-700 font-medium text-gray-700 dark:text-gray-300"
                  >
                    <X className="w-3.5 h-3.5" /> Reject
                  </button>
                  <button
                    onClick={() => handleApproval(true, msg.approvalCard)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-amber-600 hover:bg-amber-700 text-white font-medium"
                  >
                    <Check className="w-3.5 h-3.5" /> Approve
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div className="flex justify-start items-center gap-2 text-xs text-gray-500">
            <Loader2 className="w-3.5 h-3.5 animate-spin text-accent-light" />
            <span>AI is writing...</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="p-3 border-t border-gray-200 dark:border-gray-800 flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          placeholder="Ask AI Accountant..."
          className="flex-1 px-3 py-2 text-sm rounded bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-800 dark:text-gray-200 focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-light focus:border-accent-light"
        />
        <button
          onClick={handleSend}
          disabled={loading}
          aria-label="Send Message"
          className="p-2.5 rounded bg-accent-light hover:bg-accent-light/90 text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
