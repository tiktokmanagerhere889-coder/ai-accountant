import { useEffect, useRef, useState } from "react";
import { animate } from "animejs";

type AnimationHandle = { cancel?: () => void };

/**
 * Animate a numeric value from 0 to `value` (or previous -> new) using anime.js.
 * Returns the current animated value, or null until animation completes.
 * Used for metric count-up on dashboard cards.
 */
export function useCountUp(
  value: number | null,
  { duration = 800, delay = 0 }: { duration?: number; delay?: number } = {}
) {
  const [display, setDisplay] = useState<number | null>(null);
  const fromRef = useRef(0);
  const animRef = useRef<AnimationHandle | null>(null);

  useEffect(() => {
    if (value === null || typeof value !== "number") {
      setDisplay(null);
      return;
    }
    // Cancel any in-flight animation before starting a new one
    animRef.current?.cancel?.();
    const from = fromRef.current;
    // anime.js v4 requires an object target (JSTarget = Record<string, any>),
    // so we animate a transient object property rather than a raw number.
    const target = { value: from };
    const anim = animate(target, {
      value,
      duration,
      delay,
      ease: "outExpo",
      onUpdate: () => {
        setDisplay(target.value);
      },
      onComplete: () => {
        setDisplay(value);
        fromRef.current = value;
      },
    }) as unknown as AnimationHandle;
    animRef.current = anim;
    return () => {
      anim.cancel?.();
    };
  }, [value, duration, delay]);

  return display;
}
