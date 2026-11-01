import { useEffect, useRef } from "react";

export type Shortcuts = Record<string, () => void>;

function typing(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable;
}

/**
 * Single-key shortcuts (and "g" then another key). They do nothing while typing in a box, while
 * a dialog is open, or with a modifier held, so they never fight the browser or a screen reader.
 */
export function useShortcuts(shortcuts: Shortcuts, enabled = true): void {
  const latest = useRef(shortcuts);
  useEffect(() => {
    latest.current = shortcuts;
  });

  useEffect(() => {
    if (!enabled) return;
    let waiting = false;
    let timer: number | undefined;
    function onKey(event: KeyboardEvent) {
      if (event.ctrlKey || event.metaKey || event.altKey || typing(event.target)) return;
      if (document.querySelector("dialog[open]")) return;
      const key = event.key;
      const chord = waiting ? `g ${key}` : key;
      if (waiting) {
        waiting = false;
        window.clearTimeout(timer);
      } else if (key === "g") {
        waiting = true;
        timer = window.setTimeout(() => (waiting = false), 1200);
        return;
      }
      const handler = latest.current[chord];
      if (handler) {
        event.preventDefault();
        handler();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.clearTimeout(timer);
    };
  }, [enabled]);
}
