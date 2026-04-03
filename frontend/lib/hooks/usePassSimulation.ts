// ─── Pass simulation hook ─────────────────────────────────────────────────────
// Advances an "active pass" indicator every ~12 s during paper generation so the
// user can see progress through the 5-pass adaptive review pipeline.

import { useState, useRef } from "react";

export interface UsePassSimulationReturn {
  /** 0-based index of the currently active pass, or null when not running. */
  activePassIndex: number | null;
  /** Begin the simulation, resetting to pass 0. */
  start: () => void;
  /** Stop the simulation and clear the active pass. */
  stop: () => void;
}

export function usePassSimulation(): UsePassSimulationReturn {
  const [activePassIndex, setActivePassIndex] = useState<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  function start() {
    let idx = 0;
    setActivePassIndex(0);
    timerRef.current = setInterval(() => {
      idx++;
      if (idx < 5) {
        setActivePassIndex(idx);
      } else {
        if (timerRef.current) clearInterval(timerRef.current);
      }
    }, 12_000);
  }

  function stop() {
    if (timerRef.current) clearInterval(timerRef.current);
    setActivePassIndex(null);
  }

  return { activePassIndex, start, stop };
}
