'use client';

import { useEffect } from 'react';

interface ShortcutConfig {
  /** Called with the index 0..8 when the user presses 1..9 — page is responsible for bounding to the actual surface count. */
  onSurfaceNumber: (index: number) => void;
  onPaletteOpen: () => void;
  onInspectorClose: () => void;
  onOverlayClose: () => void;
  isPaletteOpen: boolean;
  isOverlayOpen: boolean;
}

export function useBenchShortcuts(cfg: ShortcutConfig) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Skip if typing in an input/textarea/contenteditable
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      const isTyping = tag === 'INPUT' || tag === 'TEXTAREA' || target?.isContentEditable;

      // ⌘K / Ctrl+K — palette
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        cfg.onPaletteOpen();
        return;
      }

      // ⌘[ — close inspector
      if ((e.metaKey || e.ctrlKey) && e.key === '[') {
        e.preventDefault();
        cfg.onInspectorClose();
        return;
      }

      // Esc — close overlay (palette has its own Esc handler; don't double-handle)
      if (e.key === 'Escape' && cfg.isOverlayOpen && !cfg.isPaletteOpen) {
        cfg.onOverlayClose();
        return;
      }

      // 1..9 → surface (only when not typing and no modifier).
      // Page-level handler bounds the index to the actual surface count.
      if (!isTyping && !e.metaKey && !e.ctrlKey && !e.altKey && !e.shiftKey) {
        if (e.key >= '1' && e.key <= '9') {
          e.preventDefault();
          cfg.onSurfaceNumber(parseInt(e.key, 10) - 1);
        }
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [cfg]);
}
