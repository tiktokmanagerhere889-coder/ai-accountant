import React, { useState, useEffect, useRef } from "react";
import axios from "axios";
import { Send, Check, X, ShieldAlert, Loader2, Sparkles } from "lucide-react";

interface Message {
  sender: "user" | "ai";
  text: string;
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

export default function ChatPanel({ onTransactionLogged }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      sender: "ai",
      text: "Hello! I am your AI Accounting Assistant. You can ask me to perform financial tasks, draft balances, analyze budgets, or record double entries using plain English.",
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
      const response = await axios.post(`${apiBase}/chat`, { message: userMessage });
      const data = response.data;

      // Basic fallback extraction parser if the response indicates approval needed
      let approvalData = null;
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

      setMessages((prev) => [
        ...prev,
        {
          sender: "ai",
          text: cleanMarkdownJSON(data.response),
          approvalCard: approvalData || undefined,
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

  const handleApproval = async (approved: boolean, cardData: any) => {
    setLoading(true);
    try {
      const response = await axios.post(`${apiBase}/chat`, {
        message: approved ? `approve the task ${cardData.toolName}` : `reject the task ${cardData.toolName}`
      });

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
    <div className="flex flex-col h-full bg-surface-light dark:bg-surface-dark border-l border-gray-200 dark:border-gray-800 w-96 flex-shrink-0">
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
          className="flex-1 px-3 py-2 text-sm rounded bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-800 dark:text-gray-200 focus:outline-none focus:border-accent-light"
        />
        <button
          onClick={handleSend}
          aria-label="Send Message"
          className="p-2.5 rounded bg-accent-light hover:bg-accent-light/90 text-white transition-colors"
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
