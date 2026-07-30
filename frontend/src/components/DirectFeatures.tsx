import React, { useState, useEffect } from "react";
import axios from "axios";
import { Plus, Loader2 } from "lucide-react";

export interface AuditRecord {
  audit_id: string;
  user_id: string;
  action: string;
  table_name: string;
  record_id: string;
  timestamp: string;
}

export interface UserRole {
  role_id: string;
  role_name: string;
  permissions: string[];
}

export interface BackupRecord {
  backup_id: string;
  backup_type: string;
  status: string;
  triggered_by: string;
  triggered_at: string;
  completed_at: string | null;
  size_bytes: number | null;
  notes: string;
}

export default function DirectFeatures({ view }: { view: "audit-trail" | "roles" }) {
  const [audits, setAudits] = useState<AuditRecord[]>([]);
  const [roles, setRoles] = useState<UserRole[]>([]);
  const [backups, setBackups] = useState<BackupRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);

  // Audit Form state
  const [auditUserId, setAuditUserId] = useState("");
  const [auditAction, setAuditAction] = useState("");
  const [auditTable, setAuditTable] = useState("");
  const [auditRecordId, setAuditRecordId] = useState("");

  // Role Form state
  const [roleName, setRoleName] = useState("");
  const [rolePermissions, setRolePermissions] = useState("");

  const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

  useEffect(() => {
    fetchData();
  }, [view]);

  const fetchData = async () => {
    setLoading(true);
    try {
      if (view === "audit-trail") {
        const res = await axios.get(`${apiBase}/audit-trail`);
        setAudits(res.data);
      } else if (view === "roles") {
        const res = await axios.get(`${apiBase}/roles`);
        setRoles(res.data);
      }
    } catch (err) {
      console.error("Fetch failed", err);
      setFormError("Failed to load data");
    } finally {
      setLoading(false);
    }
  };

  const handleCreateAudit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setFormSuccess(null);
    try {
      await axios.post(`${apiBase}/audit-trail`, {
        user_id: auditUserId,
        action: auditAction,
        table_name: auditTable,
        record_id: auditRecordId,
      });
      setFormSuccess("Audit trail created successfully");
      setAuditUserId("");
      setAuditAction("");
      setAuditTable("");
      setAuditRecordId("");
      fetchData();
    } catch (err) {
      setFormError((err as any).response?.data?.detail || (err as Error).message || "Failed to create audit trail");
    }
  };

  const handleCreateRole = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setFormSuccess(null);
    const perms = rolePermissions.split(",").map((p) => p.trim()).filter(Boolean);
    try {
      await axios.post(`${apiBase}/roles`, {
        role_name: roleName,
        permissions: perms,
      });
      setFormSuccess("Role created successfully");
      setRoleName("");
      setRolePermissions("");
      fetchData();
    } catch (err) {
      setFormError((err as any).response?.data?.detail || (err as Error).message || "Failed to create role");
    }
  };

  return (
    <div className="space-y-8">
      {formError && (
        <div className="mb-4 p-3 rounded bg-red-500/10 border border-red-500/20 text-red-700 dark:text-red-400 text-sm">
          {formError}
        </div>
      )}
      {formSuccess && (
        <div className="mb-4 p-3 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-700 dark:text-emerald-400 text-sm">
          {formSuccess}
        </div>
      )}
      {view === "audit-trail" ? (
        <div className="space-y-6">
          <div>
            <h2 className="font-serif text-2xl text-gray-800 dark:text-gray-100 flex items-center gap-2">
              Audit Trails log
            </h2>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
              Verbatim system modification entries & database audits log records.
            </p>
          </div>

          {/* Creation Form */}
          <div className="bg-surface-light dark:bg-surface-dark border border-gray-200 dark:border-gray-800 rounded p-6">
            <h3 className="font-semibold text-gray-800 dark:text-gray-200 mb-4 text-sm uppercase tracking-wider">
              Log Custom Audit Trail
            </h3>
            <form onSubmit={handleCreateAudit} className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <label className="block text-[10px] font-bold text-gray-700 dark:text-gray-300 uppercase tracking-wide mb-1">
                  User ID
                </label>
                <input
                  required
                  type="text"
                  value={auditUserId}
                  onChange={(e) => setAuditUserId(e.target.value)}
                  placeholder="e.g. USR-123"
                  className="w-full text-xs px-3 py-2 rounded bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-800 dark:text-gray-200 focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-light focus:border-accent-light"
                />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-gray-700 dark:text-gray-300 uppercase tracking-wide mb-1">
                  Action
                </label>
                <input
                  required
                  type="text"
                  value={auditAction}
                  onChange={(e) => setAuditAction(e.target.value)}
                  placeholder="e.g. UPDATE_LEDGER"
                  className="w-full text-xs px-3 py-2 rounded bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-800 dark:text-gray-200 focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-light focus:border-accent-light"
                />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-gray-700 dark:text-gray-300 uppercase tracking-wide mb-1">
                  Table Name
                </label>
                <input
                  required
                  type="text"
                  value={auditTable}
                  onChange={(e) => setAuditTable(e.target.value)}
                  placeholder="e.g. journal_entries"
                  className="w-full text-xs px-3 py-2 rounded bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-800 dark:text-gray-200 focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-light focus:border-accent-light"
                />
              </div>
              <div className="flex items-end gap-2">
                <div className="flex-1">
                  <label className="block text-[10px] font-bold text-gray-700 dark:text-gray-300 uppercase tracking-wide mb-1">
                    Record ID
                  </label>
                  <input
                    required
                    type="text"
                    value={auditRecordId}
                    onChange={(e) => setAuditRecordId(e.target.value)}
                    placeholder="e.g. JE-902"
                    className="w-full text-xs px-3 py-2 rounded bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-800 dark:text-gray-200 focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-light focus:border-accent-light"
                  />
                </div>
                <button
                  type="submit"
                  className="px-4 py-2 text-xs rounded bg-accent-light hover:bg-accent-light/95 text-white font-medium flex items-center gap-1 flex-shrink-0"
                >
                  <Plus className="w-3.5 h-3.5" /> Log
                </button>
              </div>
            </form>
          </div>

          {/* Audit List Table */}
          <div className="border border-gray-200 dark:border-gray-800 rounded overflow-hidden">
            <div className="bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-4 py-3 flex items-center justify-between">
              <span className="font-semibold text-xs uppercase tracking-wider text-gray-600 dark:text-gray-400">
                Log Database records
              </span>
              <button
                onClick={fetchData}
                className="text-xs text-accent-light hover:underline font-medium px-2 py-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
              >
                Refresh
              </button>
            </div>
            {loading ? (
              <div className="p-8 text-center flex justify-center items-center gap-2 text-gray-500">
                <Loader2 className="w-5 h-5 animate-spin text-accent-light" />
                <span>Loading Audit Trails...</span>
              </div>
            ) : audits.length === 0 ? (
              <p className="p-8 text-center text-sm text-gray-500">No logs found.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="bg-gray-100 dark:bg-gray-800/40 text-gray-600 dark:text-gray-400 font-medium">
                    <th className="p-3">Audit ID</th>
                    <th className="p-3">User</th>
                    <th className="p-3">Action</th>
                    <th className="p-3">Table</th>
                    <th className="p-3">Record ID</th>
                    <th className="p-3 text-right">Timestamp</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-gray-800">
                  {audits.map((a) => (
                    <tr key={a.audit_id} className="hover:bg-gray-50 dark:hover:bg-gray-800/20">
                      <td className="p-3 font-semibold text-gray-800 dark:text-gray-300 font-mono">
                        {a.audit_id}
                      </td>
                      <td className="p-3 text-gray-700 dark:text-gray-400">{a.user_id}</td>
                      <td className="p-3 font-semibold text-accent-light">{a.action}</td>
                      <td className="p-3 text-gray-600 dark:text-gray-500 font-mono">{a.table_name}</td>
                      <td className="p-3 text-gray-700 dark:text-gray-400 font-mono">{a.record_id}</td>
                      <td className="p-3 text-right text-gray-500 font-mono tabular-nums">
                        {new Date(a.timestamp).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="space-y-6">
          <div>
            <h2 className="font-serif text-2xl text-gray-800 dark:text-gray-100 flex items-center gap-2">
              User Roles CRUD
            </h2>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
              Configure system roles, access policies and permissions checklists.
            </p>
          </div>

          {/* Creation Form */}
          <div className="bg-surface-light dark:bg-surface-dark border border-gray-200 dark:border-gray-800 rounded p-6">
            <h3 className="font-semibold text-gray-800 dark:text-gray-200 mb-4 text-sm uppercase tracking-wider">
              Create New Role
            </h3>
            <form onSubmit={handleCreateRole} className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-[10px] font-bold text-gray-700 dark:text-gray-300 uppercase tracking-wide mb-1">
                  Role Name
                </label>
                <input
                  required
                  type="text"
                  value={roleName}
                  onChange={(e) => setRoleName(e.target.value)}
                  placeholder="e.g. Finance_Manager"
                  className="w-full text-xs px-3 py-2 rounded bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-800 dark:text-gray-200 focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-light focus:border-accent-light"
                />
              </div>
              <div className="md:col-span-2 flex items-end gap-2">
                <div className="flex-1">
                  <label className="block text-[10px] font-bold text-gray-700 dark:text-gray-300 uppercase tracking-wide mb-1">
                    Permissions (Comma-separated)
                  </label>
                  <input
                    required
                    type="text"
                    value={rolePermissions}
                    onChange={(e) => setRolePermissions(e.target.value)}
                    placeholder="e.g. read_ledger, approve_close, manage_backups"
                    className="w-full text-xs px-3 py-2 rounded bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-800 dark:text-gray-200 focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-light focus:border-accent-light"
                  />
                </div>
                <button
                  type="submit"
                  className="px-4 py-2 text-xs rounded bg-accent-light hover:bg-accent-light/95 text-white font-medium flex items-center gap-1 flex-shrink-0"
                >
                  <Plus className="w-3.5 h-3.5" /> Add Role
                </button>
              </div>
            </form>
          </div>

          {/* Roles Table */}
          <div className="border border-gray-200 dark:border-gray-800 rounded overflow-hidden">
            <div className="bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-4 py-3 flex items-center justify-between">
              <span className="font-semibold text-xs uppercase tracking-wider text-gray-600 dark:text-gray-400">
                Registered System Roles
              </span>
              <button
                onClick={fetchData}
                className="text-xs text-accent-light hover:underline font-medium px-2 py-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
              >
                Refresh
              </button>
            </div>
            {loading ? (
              <div className="p-8 text-center flex justify-center items-center gap-2 text-gray-500">
                <Loader2 className="w-5 h-5 animate-spin text-accent-light" />
                <span>Loading Roles...</span>
              </div>
            ) : roles.length === 0 ? (
              <p className="p-8 text-center text-sm text-gray-500">No roles defined yet.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="bg-gray-100 dark:bg-gray-800/40 text-gray-600 dark:text-gray-400 font-medium">
                    <th className="p-3">Role ID</th>
                    <th className="p-3">Role Name</th>
                    <th className="p-3">Permissions Schema</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-gray-800">
                  {roles.map((r) => (
                    <tr key={r.role_id} className="hover:bg-gray-50 dark:hover:bg-gray-800/20">
                      <td className="p-3 font-semibold text-gray-800 dark:text-gray-300 font-mono">
                        {r.role_id}
                      </td>
                      <td className="p-3 font-semibold text-gray-700 dark:text-gray-400">
                        {r.role_name}
                      </td>
                      <td className="p-3">
                        <div className="flex flex-wrap gap-1.5">
                          {r.permissions.map((p, idx) => (
                            <span
                              key={idx}
                              className="px-2 py-0.5 rounded bg-accent-light/10 text-accent-light text-[10px] font-semibold border border-accent-light/20"
                            >
                              {p}
                            </span>
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
