'use client';

import { useEffect, useRef, useState } from 'react';

export interface SelectionState {
  text: string;
  rect: DOMRect | null;
}

const EMPTY: SelectionState = { text: '', rect: null };

/**
 * Track the user's text selection within a target element.
 *
 * - Returns { text, rect } where text is the trimmed selection and rect is
 *   its bounding client rect (for positioning a floating button).
 * - Empty when there is no selection, the selection is collapsed, or the
 *   selection is outside the target element.
 * - Pass `containerRef` so selections elsewhere on the page (other components,
 *   text inputs, etc.) don't trigger.
 */
export function useTextSelection(
  containerRef: React.RefObject<HTMLElement | null>,
  minChars = 5,
): SelectionState {
  const [state, setState] = useState<SelectionState>(EMPTY);
  const lastTextRef = useRef('');

  useEffect(() => {
    const handler = () => {
      const sel = window.getSelection();
      if (!sel || sel.rangeCount === 0 || sel.isCollapsed) {
        if (lastTextRef.current !== '') {
          lastTextRef.current = '';
          setState(EMPTY);
        }
        return;
      }
      const text = sel.toString().trim();
      if (text.length < minChars) {
        if (lastTextRef.current !== '') {
          lastTextRef.current = '';
          setState(EMPTY);
        }
        return;
      }
      const range = sel.getRangeAt(0);
      // Reject selections outside our container
      if (containerRef.current && !containerRef.current.contains(range.commonAncestorContainer)) {
        if (lastTextRef.current !== '') {
          lastTextRef.current = '';
          setState(EMPTY);
        }
        return;
      }
      const rect = range.getBoundingClientRect();
      // Defensive: if rect is empty (selection across non-rendered nodes), bail
      if (rect.width === 0 && rect.height === 0) {
        return;
      }
      if (text !== lastTextRef.current) {
        lastTextRef.current = text;
        setState({ text, rect });
      }
    };

    document.addEventListener('selectionchange', handler);
    return () => document.removeEventListener('selectionchange', handler);
  }, [containerRef, minChars]);

  return state;
}
