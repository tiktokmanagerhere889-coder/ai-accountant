"use client";

import React, { useEffect, useRef } from "react";
import { Bell } from "lucide-react";
import { animate } from "animejs";

type AnimationHandle = { cancel?: () => void };

interface ApprovalBadgeProps {
  count: number;
  onClick: () => void;
}

export default function ApprovalBadge({ count, onClick }: ApprovalBadgeProps) {
  const badgeRef = useRef<HTMLSpanElement | null>(null);
  const animRef = useRef<AnimationHandle | null>(null);

  // Subtle repeating pulse on the count badge while there are pending approvals.
  // The badge only renders when count > 0, so the animation target and the gate
  // are the same condition. Cleaned up on count change / unmount (StrictMode-safe).
  useEffect(() => {
    const badge = badgeRef.current;
    if (count <= 0 || !badge) {
      return;
    }
    // Cancel any in-flight animation before starting a new one
    animRef.current?.cancel?.();
    const anim = animate(badge, {
      scale: [
        { to: 1.15, duration: 200 },
        { to: 1, duration: 200 },
      ],
      ease: "inOutQuad",
      loop: true,
      loopDelay: 2100,
    }) as unknown as AnimationHandle;
    animRef.current = anim;
    return () => {
      anim.cancel?.();
    };
  }, [count]);

  return (
    <button
      onClick={onClick}
      aria-label="Pending Approvals"
      title="Pending Approvals"
      className="relative flex items-center gap-1.5 p-2.5 rounded bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400 font-medium"
    >
      <Bell className="w-4 h-4" />
      {count > 0 && (
        <span
          ref={badgeRef}
          className="absolute -top-1.5 -right-1.5 min-w-[20px] h-[20px] flex items-center justify-center px-1 text-[10px] font-bold text-white bg-amber-500 rounded-full border border-surface-light dark:border-surface-dark"
        >
          {count > 99 ? "99+" : count}
        </span>
      )}
    </button>
  );
}
