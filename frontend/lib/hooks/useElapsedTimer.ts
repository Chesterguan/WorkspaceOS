// ─── Elapsed timer hook ───────────────────────────────────────────────────────
// Counts up in 1-second increments while `running` is true.
// Resets to 0 each time `running` transitions from false → true.

import { useState, useEffect, useRef } from "react";

/**
 * Returns a `"MM:SS"` string that counts up for as long as `running` is true.
 * Automatically clears the interval on unmount or when `running` goes false.
 */
export function useElapsedTimer(running: boolean): string {
  const [elapsed, setElapsed] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (running) {
      setElapsed(0);
      intervalRef.current = setInterval(() => setElapsed((s) => s + 1), 1000);
    } else {
      if (intervalRef.current) clearInterval(intervalRef.current);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [running]);

  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}
