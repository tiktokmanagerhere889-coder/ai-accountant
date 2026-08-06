import React, { useState, useEffect, useRef } from "react";
import axios from "axios";
import { Send, Check, X, ShieldAlert, Loader2, Sparkles, Wand2, Plus, Trash2, MessageSquare, ImagePlus } from "lucide-react";

// Import tool descriptions from agentsData
import { AGENTS_DATA } from "./agentsData";

interface ToolCallInfo {
  toolName: string;
  recordId?: string;
  summary: string;
  status?: "executed" | "queued";
}

interface Message {
  sender: "user" | "ai";
  text: string;
  image?: { data: string; filename: string; mime?: string };
  toolCalls?: ToolCallInfo[];
  suggestions?: string[];
  approvalCard?: {
    toolName: string;
    description: string;
    params: Record<string, any>;
    approvalId: string;
  };
}

interface ApprovalResolvedEvent {
  approvalId: string;
  toolName: string;
  message?: string;
  result?: any;
  formatted_result?: string | null;
}

interface ChatPanelProps {
  onTransactionLogged?: () => void;
  fullPage?: boolean;
  externalApproval?: ApprovalResolvedEvent | null;
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

export default function ChatPanel({ onTransactionLogged, fullPage = false, externalApproval = null }: ChatPanelProps) {
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
  const [conversationId, setConversationId] = useState<string>(() => {
    if (typeof window !== "undefined") {
      return localStorage.getItem("chat-conversation-id") || `conv-${Date.now()}`;
    }
    return `conv-${Date.now()}`;
  });
  const [conversations, setConversations] = useState<any[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

  // Send an image message (receipt/query image) as an attachment to /chat.
  const sendImage = async (file: File) => {
    if (loading) return;
    const reader = new FileReader();
    reader.onload = async () => {
      const base64 = String(reader.result || "").split(",")[1] || "";
      setMessages((prev) => [
        ...prev,
        {
          sender: "user",
          text: `📷 ${file.name}${file.type.startsWith("image/") ? "" : " (attachment)"}`,
          image: { data: base64, filename: file.name, mime: file.type },
        },
      ]);
      setLoading(true);
      try {
        const response = await axios.post(
          `${apiBase}/chat`,
          {
            message: "",
            conversation_id: conversationId,
            image: { data: base64, filename: file.name },
          },
          { timeout: 60000 }
        );
        const data = response.data;
        if (data.conversation_id) {
          setConversationId(data.conversation_id);
          localStorage.setItem("chat-conversation-id", data.conversation_id);
        }
        const toolCalls = (data.tool_calls?.length ? data.tool_calls : extractToolCalls(data.response)) as ToolCallInfo[];
        // Build the approval card for queued tools (same as handleSend), so the
        // image upload surfaces an inline Approve/Reject in the chat thread.
        let approvalData: { toolName: string; description: string; params: Record<string, any>; approvalId: string } | null = null;
        const queuedTool = toolCalls.find((tc) => tc.status === "queued");
        if (queuedTool) {
          const idMatch = queuedTool.summary.match(/\(([A-Za-z0-9-]+)\)/);
          const toolInfo = AGENTS_DATA.flatMap((a) => a.tools).find((t) => t.name === queuedTool.toolName);
          approvalData = {
            toolName: queuedTool.toolName,
            description: toolInfo?.description || queuedTool.summary,
            params: {},
            approvalId: idMatch ? idMatch[1] : uuidv4(),
          };
        }
        setMessages((prev) => [
          ...prev,
          {
            sender: "ai",
            text: cleanMarkdownJSON(data.response),
            toolCalls: toolCalls.length ? toolCalls : undefined,
            approvalCard: approvalData || undefined,
          },
        ]);
        if (data.response.includes("JE-")) onTransactionLogged?.();
      } catch (error: any) {
        console.error(error);
        setMessages((prev) => [
          ...prev,
          { sender: "ai", text: `Error processing image: ${error.response?.data?.detail || error.message || "Unknown error"}` },
        ]);
      } finally {
        setLoading(false);
      }
    };
    reader.readAsDataURL(file);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      sendImage(file);
      e.target.value = "";
    }
  };

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
      const response = await axios.post(`${apiBase}/chat`, { message: userMessage, conversation_id: conversationId }, { timeout: 60000 });
      const data = response.data;
      if (data.conversation_id) {
        setConversationId(data.conversation_id);
        localStorage.setItem("chat-conversation-id", data.conversation_id);
      }

      // Approval detection from the structured tool_calls field: a queued tool
      // carries approval_id in its summary ("Action queued for approval (APR-..)").
      const toolCalls = (data.tool_calls?.length ? data.tool_calls : extractToolCalls(data.response)) as ToolCallInfo[];
      let approvalData: { toolName: string; description: string; params: Record<string, any>; approvalId: string } | null = null;
      const queuedTool = toolCalls.find((tc) => tc.status === "queued");
      if (queuedTool) {
        const idMatch = queuedTool.summary.match(/\(([A-Za-z0-9-]+)\)/);
        // Get the actual tool description from agentsData
        const toolInfo = AGENTS_DATA.flatMap((a) => a.tools).find((t) => t.name === queuedTool.toolName);
        approvalData = {
          toolName: queuedTool.toolName,
          description: toolInfo?.description || queuedTool.summary, // Use actual tool description
          params: {},
          approvalId: idMatch ? idMatch[1] : uuidv4(),
        };
      }

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

  // When an approval is resolved from the Notifications panel (not the inline
  // chat card), append the result to the active chat thread so it shows in
  // chat, not only in the panel's history. Consume each event exactly once.
  const consumedExternal = useRef<Set<string>>(new Set());
  useEffect(() => {
    if (!externalApproval) return;
    if (consumedExternal.current.has(externalApproval.approvalId)) return;
    consumedExternal.current.add(externalApproval.approvalId);
    const formatted =
      externalApproval.formatted_result ||
      (externalApproval.result && typeof externalApproval.result === "object"
        ? (externalApproval.result as any).formatted_result
        : null);
    const resultBlock =
      formatted && typeof formatted === "string"
        ? `\n\n${formatted}`
        : externalApproval.result && typeof externalApproval.result === "object"
          ? `\n\n${JSON.stringify(externalApproval.result, null, 2)}`
          : "";
    setMessages((prev) => [
      ...prev,
      {
        sender: "ai",
        text: `✅ Approved action: ${externalApproval.toolName}.\n\n${
          externalApproval.message || "The action was approved and executed."
        }${resultBlock}`,
      },
    ]);
    onTransactionLogged?.();
  }, [externalApproval]);

  // Load conversation list once (for the full-page ChatGPT-style sidebar)
  useEffect(() => {
    if (!fullPage) return;
    const fetchConvs = async () => {
      try {
        const res = await axios.get(`${apiBase}/conversations`, { timeout: 15000 });
        setConversations(res.data.conversations || []);
      } catch (err) {
        // backend may not have the endpoint — silent
      }
    };
    fetchConvs();
  }, [fullPage, apiBase]);

  const startNewChat = async () => {
    const id = `conv-${Date.now()}`;
    setConversationId(id);
    localStorage.setItem("chat-conversation-id", id);
    setMessages([
      {
        sender: "ai",
        text: "Hello! I am your AI Accounting Assistant. You can ask me to perform financial tasks, draft balances, analyze budgets, or record double entries using plain English.",
        suggestions: QUICK_SUGGESTIONS,
      },
    ]);
    // Register the conversation on the backend so it appears in history
    try {
      const res = await axios.post(`${apiBase}/conversations`, {}, { timeout: 15000 });
      if (res.data.conversation_id) {
        setConversationId(res.data.conversation_id);
        localStorage.setItem("chat-conversation-id", res.data.conversation_id);
      }
    } catch (err) {
      // silent — backend will create on first /chat anyway
    }
    const res2 = await axios.get(`${apiBase}/conversations`, { timeout: 15000 });
    setConversations(res2.data.conversations || []);
  };

  const openConversation = async (id: string) => {
    setConversationId(id);
    localStorage.setItem("chat-conversation-id", id);
    try {
      const res = await axios.get(`${apiBase}/conversations/${id}/messages`, { timeout: 15000 });
      const msgs = res.data.messages || [];
      if (msgs.length === 0) {
        setMessages([
          {
            sender: "ai",
            text: "Hello! I am your AI Accounting Assistant. You can ask me to perform financial tasks, draft balances, analyze budgets, or record double entries using plain English.",
            suggestions: QUICK_SUGGESTIONS,
          },
        ]);
        return;
      }
      setMessages(
        msgs.map((m: any) => ({
          sender: m.role === "user" ? "user" : "ai",
          text: m.content,
          toolCalls: m.tool_calls?.length ? m.tool_calls : undefined,
        }))
      );
    } catch (err) {
      console.error(err);
    }
  };

  const deleteConversation = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await axios.delete(`${apiBase}/conversations/${id}`, { timeout: 15000 });
      const res = await axios.get(`${apiBase}/conversations`, { timeout: 15000 });
      setConversations(res.data.conversations || []);
      if (id === conversationId) startNewChat();
    } catch (err) {
      console.error(err);
    }
  };

  const sendSuggestion = async (text: string) => {
    if (!text.trim() || loading) return;
    setInput("");
    setMessages((prev) => [...prev, { sender: "user", text }]);
    setLoading(true);
    try {
      const response = await axios.post(`${apiBase}/chat`, { message: text, conversation_id: conversationId }, { timeout: 60000 });
      const data = response.data;
      if (data.conversation_id) {
        setConversationId(data.conversation_id);
        localStorage.setItem("chat-conversation-id", data.conversation_id);
      }
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
      const endpoint = approved
        ? `${apiBase}/approvals/${cardData.approvalId}/approve`
        : `${apiBase}/approvals/${cardData.approvalId}/reject`;
      const response = await axios.post(endpoint, {}, { timeout: 60000 });
      const data = response.data;

      // Update the card's tool-call status to reflect the outcome in-thread.
      const outcome = approved
        ? (data?.status === "executed" ? "executed" : "approved")
        : "rejected";

      // Build a readable result block from the tool output so the user sees
      // what actually happened (e.g. receipt vendor/amount/date), not just
      // "approved and executed".
      const resultBlock = (() => {
        // Prefer the backend's plain-English formatter output (covers forecast,
        // loan schedule, and any approval tool with a dedicated formatter).
        const formatted = data?.approval?.formatted_result || data?.formatted_result;
        if (formatted && typeof formatted === "string") return `\n\n${formatted}`;
        const r = data?.result;
        if (!r || typeof r !== "object") return "";
        const parts: string[] = [];
        if (r.vendor_name) parts.push(`Vendor: ${r.vendor_name}`);
        if (r.total_amount !== undefined && r.total_amount !== null) parts.push(`Amount: ${r.total_amount}`);
        if (r.date) parts.push(`Date: ${r.date}`);
        if (r.currency) parts.push(`Currency: ${r.currency}`);
        if (r.extraction_id) parts.push(`Extraction ID: ${r.extraction_id}`);
        if (r.status) parts.push(`Status: ${r.status}`);
        if (r.entry_id) parts.push(`Entry ID: ${r.entry_id}`);
        if (r.message) parts.push(String(r.message));
        return parts.length ? `\n\n${parts.join("\n")}` : "";
      })();

      setMessages((prev) => [
        ...prev,
        {
          sender: "ai",
          text: approved
            ? `✅ Approved action: ${cardData.toolName}.\n\n${data?.message || data?.response || data?.detail || "The action was approved and executed."}${resultBlock}`
            : `❌ Rejected action: ${cardData.toolName}.`,
        }
      ]);

      // Clean current card from message block + mark its tool-call done
      setMessages((prev) =>
        prev.map((msg) =>
          msg.approvalCard?.approvalId === cardData.approvalId
            ? {
                ...msg,
                approvalCard: undefined,
                toolCalls: (msg.toolCalls || []).map((tc) =>
                  tc.toolName === cardData.toolName ? { ...tc, status: outcome as any } : tc
                ),
              }
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

  // Full-page mode: ChatGPT-style layout (left history sidebar + main chat).
  // Drawer mode: compact right panel.
  return (
    <div className={`flex h-full bg-surface-light dark:bg-surface-dark ${fullPage ? "w-full border-l-0" : "border-l border-gray-200 dark:border-gray-800 w-full lg:w-80 xl:w-96 flex-shrink-0"}`}>
      {fullPage && (
        <div className="hidden md:flex flex-col w-64 border-r border-gray-200 dark:border-gray-800 bg-surface-light dark:bg-surface-dark flex-shrink-0">
          {/* New Chat button */}
          <div className="p-3 border-b border-gray-200 dark:border-gray-800">
            <button
              onClick={startNewChat}
              className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded bg-accent-light hover:bg-accent-light/90 text-white text-sm font-medium transition-colors"
            >
              <Plus className="w-4 h-4" /> New Chat
            </button>
          </div>
          {/* Conversation history */}
          <div className="flex-1 min-h-0 overflow-y-auto p-2 space-y-1">
            {conversations.map((c) => (
              <div
                key={c.conversation_id}
                onClick={() => openConversation(c.conversation_id)}
                className={`group flex items-center gap-2 px-3 py-2 rounded text-xs cursor-pointer transition-colors ${
                  c.conversation_id === conversationId
                    ? "bg-accent-light/15 text-accent-light font-medium"
                    : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
                }`}
              >
                <MessageSquare className="w-3.5 h-3.5 flex-shrink-0" />
                <span className="truncate flex-1">{c.title || "New Chat"}</span>
                <button
                  onClick={(e) => deleteConversation(c.conversation_id, e)}
                  className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-500"
                  aria-label="Delete conversation"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            ))}
            {conversations.length === 0 && (
              <p className="px-3 py-2 text-[11px] text-gray-400">No conversations yet.</p>
            )}
          </div>
        </div>
      )}

      {/* Main chat column */}
      <div className="flex flex-col flex-1 min-w-0">
      {/* Header */}
      <div className="p-4 border-b border-gray-200 dark:border-gray-800 flex items-center gap-2">
        <Sparkles className="w-5 h-5 text-accent-light" />
        <span className="font-serif font-semibold text-gray-800 dark:text-gray-200">
          Assistant AI
        </span>
      </div>

      {/* Messages view */}
      <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4">
        {messages.map((msg, index) => (
          <div key={index} className={`flex flex-col ${msg.sender === "user" ? "items-end" : "items-start"}`}>
            <div
              className={`p-3 rounded text-sm max-w-[85%] whitespace-pre-line leading-relaxed ${
                msg.sender === "user"
                  ? "bg-accent-light text-white rounded-br-none"
                  : "bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-300 rounded-bl-none border border-gray-200 dark:border-gray-700/50"
              }`}
            >
              {msg.image && (
                <div className="mb-2 flex items-center gap-2">
                  <img
                    src={`data:${msg.image.mime || "image/png"};base64,${msg.image.data}`}
                    alt={msg.image.filename}
                    className="max-h-56 max-w-full rounded border border-gray-300 dark:border-gray-600"
                  />
                </div>
              )}
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
          ref={fileInputRef}
          type="file"
          accept="image/png,image/jpeg,.png,.jpg,.jpeg"
          className="hidden"
          onChange={handleFileSelect}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={loading}
          aria-label="Attach receipt image"
          title="Upload receipt image"
          className="p-2.5 rounded bg-gray-200/70 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-accent-light/15 hover:text-accent-light transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <ImagePlus className="w-4 h-4" />
        </button>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          placeholder="Ask AI Accountant... (or attach a receipt)"
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
    </div>
  );
}
