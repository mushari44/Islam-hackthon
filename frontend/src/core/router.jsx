// Minimal hash router. Shared core.
import { useEffect, useState } from "react";

export function currentPath() { return window.location.hash.slice(1) || "/"; }

export function navigate(path) {
  if (window.location.hash !== `#${path}`) window.location.hash = path;
}

/** Re-renders on hash change; returns {path, query}. */
export function useHashPath() {
  const [full, setFull] = useState(currentPath());
  useEffect(() => {
    const on = () => { setFull(currentPath()); window.scrollTo({ top: 0 }); };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
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
