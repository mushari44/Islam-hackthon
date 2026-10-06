// Minimal hash router. Shared core.
import { useEffect, useState } from "react";

export function currentPath() { return window.location.hash.slice(1) || "/"; }

/** Go to a path. `replace` swaps the current history entry (e.g. filters kept in the address) instead of adding one. */
export function navigate(path, { replace = false } = {}) {
  if (window.location.hash === `#${path}`) return;
  if (replace) window.location.replace(`#${path}`);
  else window.location.hash = path;
}

// Scroll positions per history entry, so Back and Forward return where the reader was.
// Each entry gets a key in history.state; an entry without one is a fresh navigation.
const positions = new Map();
let nextKey = Date.now();
const entryKey = () => (window.history.state && window.history.state.sabeeliKey) || null;
function stampEntry() {
  if (!entryKey()) {
    try { window.history.replaceState({ ...(window.history.state || {}), sabeeliKey: String(++nextKey) }, ""); } catch { /* ignore */ }
  }
  return entryKey();
}
const pathOf = (full) => full.split("?")[0];

function restoreScroll(y) {
  // The page may still be loading its content: try again shortly if it isn't tall enough yet.
  requestAnimationFrame(() => {
    window.scrollTo({ top: y });
    if (Math.abs(window.scrollY - y) > 2) setTimeout(() => window.scrollTo({ top: y }), 300);
  });
}

/** Re-renders on hash change; returns {path, query}. */
export function useHashPath() {
  const [full, setFull] = useState(currentPath());
  useEffect(() => {
    try { window.history.scrollRestoration = "manual"; } catch { /* old browser */ }
    let last = currentPath();
    stampEntry();
    const onScroll = () => { const k = entryKey(); if (k) positions.set(k, window.scrollY); };
    const on = () => {
      const next = currentPath();
      const samePath = pathOf(next) === pathOf(last);
      const known = entryKey();    // set only on entries visited before: this is Back or Forward
      last = next;
      const key = stampEntry();
      setFull(next);
      if (samePath) return;        // only the query changed (a tab, a filter): stay where the reader is
      if (known) { restoreScroll(positions.get(key) || 0); return; }
      window.scrollTo({ top: 0 });
      // A new page: move focus to the content so screen readers start there, unless the page focused a field itself.
      requestAnimationFrame(() => {
        const main = document.getElementById("main");
        if (main && !main.contains(document.activeElement)) main.focus({ preventScroll: true });
      });
    };
    window.addEventListener("hashchange", on);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => { window.removeEventListener("hashchange", on); window.removeEventListener("scroll", onScroll); };
  }, []);
  const [path, qs = ""] = full.split("?");
  return { path, query: Object.fromEntries(new URLSearchParams(qs)) };
}

/** match("/groups/:id", "/groups/3") -> {id: "3"} | null */
export function match(pattern, path) {
  const keys = [];
  const rx = new RegExp("^" + pattern.replace(/:([a-z]+)/g, (_, k) => { keys.push(k); return "([^/]+)"; }) + "/?$");
  const m = path.match(rx);
  if (!m) return null;
  return Object.fromEntries(keys.map((k, i) => [k, decodeURIComponent(m[i + 1])]));
}
