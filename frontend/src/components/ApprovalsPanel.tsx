"use client";

import React, { useCallback, useEffect, useState } from "react";
import axios from "axios";
import {
  Bell,
  Check,
  CheckCircle2,
  Clock,
  Edit3,
  History,
  Loader2,
  RefreshCw,
  ShieldAlert,
  X,
  XCircle,
} from "lucide-react";

interface ApprovalRecord {
  approval_id: string;
  tool_name: string;
  params: Record<string, any> | null;
  submitted_by?: string | null;
  status: string;
  created_at?: string | null;
  resolved_at?: string | null;
  rejection_reason?: string | null;
  edited_params?: Record<string, any> | null;
  result?: any;
  formatted_result?: string | null;
}

export interface ApprovalResolvedEvent {
  approvalId: string;
  toolName: string;
  message?: string;
  result?: any;
  formatted_result?: string | null;
}

interface ApprovalsPanelProps {
  open: boolean;
  onClose: () => void;
  onPendingCountChange?: (count: number) => void;
  onApproved?: (evt: ApprovalResolvedEvent) => void;
}

const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

function formatParams(params: Record<string, any> | null): string {
  if (!params || Object.keys(params).length === 0) return "No parameters";
  return Object.entries(params)
    .map(([k, v]) => {
      const val = typeof v === "object" ? JSON.stringify(v) : String(v);
      return `${k}: ${val}`;
    })
    .join("\n");
}

function shortResult(result: any): string {
  if (result === null || result === undefined) return "";
  if (typeof result === "string") return result;
  try {
    return JSON.stringify(result);
  } catch {
    return String(result);
  }
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    pending: "bg-amber-500/10 text-amber-500 border-amber-500/20",
    approved: "bg-emerald-500/10 text-emerald-500 border-emerald-500/20",
    edited: "bg-teal-500/10 text-teal-500 border-teal-500/20",
    rejected: "bg-red-500/10 text-red-500 border-red-500/20",
  };
  return (
    <span
      className={`text-[10px] px-2 py-0.5 rounded border font-bold uppercase tracking-wider ${styles[status] || "bg-gray-500/10 text-gray-500 border-gray-500/20"}`}
    >
      {status}
    </span>
  );
}

export default function ApprovalsPanel({ open, onClose, onPendingCountChange, onApproved }: ApprovalsPanelProps) {
  const [approvals, setApprovals] = useState<ApprovalRecord[]>([]);
  const [history, setHistory] = useState<ApprovalRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // approval_id -> editable JSON text of params
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [paramsError, setParamsError] = useState<Record<string, string>>({});
  // approval_id -> reject reason
  const [rejectReasons, setRejectReasons] = useState<Record<string, string>>({});
  // approval_id -> "approving" | "rejecting"
  const [actioning, setActioning] = useState<Record<string, string>>({});
  // How to display approved tool results: "text" (plain English) or "json" (raw)
  const [resultViewMode, setResultViewMode] = useState<"text" | "json">("text");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [pendingRes, historyRes] = await Promise.all([
        axios.get(`${apiBase}/approvals/pending`, { timeout: 15000 }),
        axios.get(`${apiBase}/approvals/history?limit=50`, { timeout: 15000 }),
      ]);
      const pending: ApprovalRecord[] = pendingRes.data.approvals || [];
      const resolved: ApprovalRecord[] = historyRes.data.approvals || [];
      setApprovals(pending);
      setHistory(resolved);
      setEdits((prev) => {
        const next = { ...prev };
        pending.forEach((a) => {
          if (next[a.approval_id] === undefined) {
            next[a.approval_id] = JSON.stringify(a.params || {}, null, 2);
          }
        });
        return next;
      });
      onPendingCountChange?.(pending.length);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || "Failed to load approvals");
    } finally {
      setLoading(false);
    }
  }, [onPendingCountChange]);

  // Fetch on open and every 10s while open (picks up newly queued items)
  useEffect(() => {
    if (!open) return;
    refresh();
    const interval = setInterval(refresh, 10000);
    return () => clearInterval(interval);
  }, [open, refresh]);

  const handleApprove = async (approval: ApprovalRecord) => {
    const editedText = edits[approval.approval_id];
    let editedParams: Record<string, any> | undefined;
    if (editedText !== undefined && editedText.trim() !== "") {
      try {
        editedParams = JSON.parse(editedText);
      } catch {
        setParamsError((prev) => ({ ...prev, [approval.approval_id]: "Invalid JSON — fix params before approving." }));
        return;
      }
    }
    setActioning((prev) => ({ ...prev, [approval.approval_id]: "approving" }));
    setError(null);
    try {
      const res = await axios.post(
        `${apiBase}/approvals/${approval.approval_id}/approve`,
        { edited_params: editedParams },
        { timeout: 60000 }
      );
      await refresh();
      // Bridge to the active chat so the result also appears as a chat message,
      // not only in this panel's history.
      const payload = res.data;
      onApproved?.({
        approvalId: approval.approval_id,
        toolName: approval.tool_name,
        message: payload?.message,
        result: payload?.result,
        formatted_result: payload?.approval?.formatted_result ?? payload?.formatted_result ?? null,
      });
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || "Approval failed");
    } finally {
      setActioning((prev) => {
        const next = { ...prev };
        delete next[approval.approval_id];
        return next;
      });
    }
  };

  const handleReject = async (approval: ApprovalRecord) => {
    const reason = (rejectReasons[approval.approval_id] || "").trim();
    setActioning((prev) => ({ ...prev, [approval.approval_id]: "rejecting" }));
    setError(null);
    try {
      await axios.post(
        `${apiBase}/approvals/${approval.approval_id}/reject`,
        { reason },
        { timeout: 15000 }
      );
      await refresh();
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || "Rejection failed");
    } finally {
      setActioning((prev) => {
        const next = { ...prev };
        delete next[approval.approval_id];
        return next;
      });
    }
  };

  return (
    <>
      {/* Backdrop */}
      <div
        className={`fixed inset-0 bg-black/40 transition-opacity duration-300 z-40 ${
          open ? "opacity-100" : "opacity-0 pointer-events-none"
        }`}
        onClick={onClose}
        aria-hidden="true"
      />
      {/* Slide-in panel */}
      <aside
        className={`fixed right-0 top-0 h-full w-full sm:w-[480px] bg-surface-light dark:bg-surface-dark border-l border-gray-200 dark:border-gray-800 shadow-2xl z-50 transition-transform duration-300 flex flex-col ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
        aria-label="Notifications and Approvals"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-800 flex-shrink-0">
          <div className="flex items-center gap-2">
            <Bell className="w-5 h-5 text-amber-500" />
            <span className="font-serif font-semibold text-gray-800 dark:text-gray-100">
              Notifications &amp; Approvals
            </span>
            <span className="text-[10px] px-2 py-0.5 rounded bg-amber-500/10 text-amber-500 border border-amber-500/20 font-bold uppercase">
              {approvals.length} pending
            </span>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={refresh}
              disabled={loading}
              aria-label="Refresh Approvals"
              title="Refresh"
              className="p-2 rounded bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400 disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            </button>
            <button
              onClick={onClose}
              aria-label="Close Approvals"
              className="p-2 rounded bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {error && (
          <div className="flex items-center gap-2 p-3 mx-5 mt-4 text-sm rounded bg-red-500/10 text-red-500 border border-red-500/20">
            <XCircle className="w-4 h-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Pending list */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {approvals.length === 0 && !loading ? (
            <div className="flex flex-col items-center justify-center py-16 text-center space-y-2">
              <div className="p-4 rounded-full bg-emerald-500/10">
                <CheckCircle2 className="w-8 h-8 text-emerald-500" />
              </div>
              <div className="text-sm font-medium text-gray-700 dark:text-gray-300">
                No pending approvals
              </div>
              <div className="text-xs text-gray-500">
                Approval-required tools in direct mode are queued here.
              </div>
            </div>
          ) : (
            approvals.map((approval) => {
              const busy = actioning[approval.approval_id];
              return (
                <div
                  key={approval.approval_id}
                  className="rounded border border-gray-200 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-900/40 p-4 space-y-3"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <ShieldAlert className="w-4 h-4 text-amber-500 flex-shrink-0" />
                        <span className="font-mono text-xs font-bold text-gray-800 dark:text-gray-100 truncate">
                          {approval.tool_name}
                        </span>
                      </div>
                      <div className="mt-1 flex items-center gap-2 text-[10px] text-gray-500 font-mono">
                        <span>{approval.approval_id}</span>
                        {approval.submitted_by && <span>· {approval.submitted_by}</span>}
                      </div>
                      <div className="mt-0.5 flex items-center gap-1 text-[10px] text-gray-400">
                        <Clock className="w-3 h-3" />
                        {approval.created_at ? new Date(approval.created_at).toLocaleString() : ""}
                      </div>
                    </div>
                    <StatusBadge status={approval.status} />
                  </div>

                  {/* Readable params summary */}
                  <div className="text-xs text-gray-700 dark:text-gray-300 whitespace-pre-wrap font-mono bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded p-2 max-h-40 overflow-y-auto">
                    {formatParams(approval.params)}
                  </div>

                  {/* Editable params */}
                  <div className="space-y-1.5">
                    <label className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-gray-500">
                      <Edit3 className="w-3 h-3" /> Edit params before approving
                    </label>
                    <textarea
                      rows={4}
                      value={edits[approval.approval_id] || ""}
                      onChange={(e) => {
                        setEdits((prev) => ({ ...prev, [approval.approval_id]: e.target.value }));
                        setParamsError((prev) => ({ ...prev, [approval.approval_id]: "" }));
                      }}
                      spellCheck={false}
                      className="w-full text-xs font-mono px-2.5 py-2 rounded bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-800 dark:text-gray-200 focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-light"
                    />
                    {paramsError[approval.approval_id] && (
                      <div className="text-[11px] text-red-500">{paramsError[approval.approval_id]}</div>
                    )}
                  </div>

                  {/* Reject reason */}
                  <input
                    type="text"
                    value={rejectReasons[approval.approval_id] || ""}
                    onChange={(e) =>
                      setRejectReasons((prev) => ({ ...prev, [approval.approval_id]: e.target.value }))
                    }
                    placeholder="Rejection reason (optional)"
                    className="w-full text-xs px-2.5 py-1.5 rounded bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-800 dark:text-gray-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-light"
                  />

                  <div className="flex gap-2 justify-end pt-1">
                    <button
                      onClick={() => handleReject(approval)}
                      disabled={!!busy}
                      className="flex items-center gap-1.5 px-4 py-2.5 rounded border border-gray-300 dark:border-gray-600 hover:bg-gray-200 dark:hover:bg-gray-700 font-medium text-xs text-gray-700 dark:text-gray-300 disabled:opacity-50"
                    >
                      {busy === "rejecting" ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <X className="w-3.5 h-3.5" />
                      )}
                      Reject
                    </button>
                    <button
                      onClick={() => handleApprove(approval)}
                      disabled={!!busy}
                      className="flex items-center gap-1.5 px-4 py-2.5 rounded bg-emerald-600 hover:bg-emerald-700 text-white font-medium text-xs disabled:opacity-50"
                    >
                      {busy === "approving" ? (
                        <>
                          <Loader2 className="w-3.5 h-3.5 animate-spin" /> Running...
                        </>
                      ) : (
                        <>
                          <Check className="w-3.5 h-3.5" /> Approve &amp; Execute
                        </>
                      )}
                    </button>
                  </div>
                </div>
              );
            })
          )}

          {/* History */}
          <div className="pt-2">
            <div className="flex items-center justify-between pb-2">
              <div className="flex items-center gap-2">
                <History className="w-4 h-4 text-gray-500" />
                <span className="text-[10px] uppercase font-bold tracking-wider text-gray-500">
                  Approval History
                </span>
              </div>
              {/* Result view mode toggle: plain text or JSON */}
              <div className="flex items-center gap-1 rounded border border-gray-200 dark:border-gray-700 p-0.5">
                <button
                  onClick={() => setResultViewMode("text")}
                  className={`px-2 py-0.5 text-[10px] font-semibold rounded transition-colors ${
                    resultViewMode === "text"
                      ? "bg-accent-light text-white"
                      : "text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
                  }`}
                >
                  Text
                </button>
                <button
                  onClick={() => setResultViewMode("json")}
                  className={`px-2 py-0.5 text-[10px] font-semibold rounded transition-colors ${
                    resultViewMode === "json"
                      ? "bg-accent-light text-white"
                      : "text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
                  }`}
                >
                  JSON
                </button>
              </div>
            </div>
            {history.length === 0 ? (
              <div className="text-xs text-gray-500 py-2">No resolved approvals yet.</div>
            ) : (
              <div className="space-y-2">
                {history.map((item) => (
                  <div
                    key={item.approval_id}
                    className="rounded border border-gray-200 dark:border-gray-800 p-3 space-y-1.5"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-xs font-bold text-gray-800 dark:text-gray-100 truncate">
                        {item.tool_name}
                      </span>
                      <StatusBadge status={item.status} />
                    </div>
                    <div className="text-[10px] text-gray-500 font-mono flex items-center gap-2">
                      <span>{item.approval_id}</span>
                      {item.resolved_at && (
                        <span>· {new Date(item.resolved_at).toLocaleString()}</span>
                      )}
                    </div>
                    {item.status === "rejected" && item.rejection_reason && (
                      <div className="text-[11px] text-red-500 bg-red-500/5 border border-red-500/20 rounded px-2 py-1">
                        Reason: {item.rejection_reason}
                      </div>
                    )}
                    {item.status !== "rejected" && item.result !== null && item.result !== undefined && (
                      <div className="text-[11px] text-gray-600 dark:text-gray-400 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded p-2 font-mono max-h-40 overflow-y-auto break-all whitespace-pre-wrap">
                        {resultViewMode === "text" && item.formatted_result
                          ? item.formatted_result
                          : resultViewMode === "text"
                            ? shortResult(item.result)
                            : JSON.stringify(item.result, null, 2)}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </aside>
    </>
  );
}
