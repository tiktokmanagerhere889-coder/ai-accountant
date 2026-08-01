"use client";

import React from "react";
import { Bell } from "lucide-react";

interface ApprovalBadgeProps {
  count: number;
  onClick: () => void;
}

export default function ApprovalBadge({ count, onClick }: ApprovalBadgeProps) {
  return (
    <button
      onClick={onClick}
      aria-label="Pending Approvals"
      title="Pending Approvals"
      className="relative flex items-center gap-1.5 p-2 rounded bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400 font-medium"
    >
      <Bell className="w-4 h-4" />
      {count > 0 && (
        <span className="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] flex items-center justify-center px-1 text-[10px] font-bold text-white bg-amber-500 rounded-full border border-surface-light dark:border-surface-dark">
          {count > 99 ? "99+" : count}
        </span>
      )}
    </button>
  );
}
