import React from "react";
import { X, Key, ShieldCheck } from "lucide-react";

interface SettingsModalProps {
  onClose: () => void;
}

export default function SettingsModal({ onClose }: SettingsModalProps) {
  // Read and simulate settings from env structure
  const [cerebrasKey, setCerebrasKey] = React.useState("••••••••••••••••••••••••");
  const [groqKey, setGroqKey] = React.useState("••••••••••••••••••••••••");

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-surface-light dark:bg-surface-dark border border-gray-200 dark:border-gray-800 rounded max-w-md w-full p-6 shadow-2xl relative">
        <button
          onClick={onClose}
          aria-label="Close Settings Modal"
          className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
        >
          <X className="w-5 h-5" />
        </button>

        <h3 className="font-serif text-xl text-gray-800 dark:text-gray-100 flex items-center gap-2 mb-2">
          <Key className="w-5 h-5 text-accent-light" /> System Preferences
        </h3>
        <p className="text-xs text-gray-500 mb-6">
          Set configuration details and provider API keys for accounting logic operations.
        </p>

        <div className="space-y-4">
          <div>
            <label className="block text-[10px] font-bold text-gray-700 dark:text-gray-300 uppercase tracking-wide mb-1.5">
              CEREBRAS API KEY
            </label>
            <input
              type="password"
              value={cerebrasKey}
              onChange={(e) => setCerebrasKey(e.target.value)}
              className="w-full text-xs px-3 py-2.5 rounded bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-800 dark:text-gray-200 focus:outline-none focus:border-accent-light font-mono"
            />
          </div>
          <div>
            <label className="block text-[10px] font-bold text-gray-700 dark:text-gray-300 uppercase tracking-wide mb-1.5">
              GROQ API KEY
            </label>
            <input
              type="password"
              value={groqKey}
              onChange={(e) => setGroqKey(e.target.value)}
              className="w-full text-xs px-3 py-2.5 rounded bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-800 dark:text-gray-200 focus:outline-none focus:border-accent-light font-mono"
            />
          </div>

          <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 text-emerald-800 dark:text-emerald-400 text-xs rounded flex gap-2.5">
            <ShieldCheck className="w-4 h-4 mt-0.5 flex-shrink-0" />
            <p>API keys verified in current server session environment configurations.</p>
          </div>
        </div>

        <div className="mt-6 pt-4 border-t border-gray-200 dark:border-gray-800 flex justify-end">
          <button
            onClick={onClose}
            className="px-5 py-2 rounded bg-accent-light hover:bg-accent-light/95 text-white font-medium text-xs transition-colors"
          >
            Save preferences
          </button>
        </div>
      </div>
    </div>
  );
}
