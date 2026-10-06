// Shared UI pieces: icons, sheets (modals), toasts, spinner, notices, polling. Shared core.
import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { LOGO, PATHS } from "./icons.js";
import { useI18n } from "./i18n.jsx";

export function Icon({ name, size = 18, className = "" }) {
  return (
    <svg className={`icon ${className}`} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: PATHS[name] || PATHS.info }} />
  );
}

export function Logo({ size = 38 }) {
  return <span className="brand-mark" style={{ width: size, height: size }} dangerouslySetInnerHTML={{ __html: LOGO }} />;
}

export function Spinner({ label }) {
  return <div className="row" role="status"><div className="spinner" />{label && <span className="muted small">{label}</span>}</div>;
}

export function Notice({ kind = "", icon = "info", children }) {
  return <div className={`notice ${kind ? `notice-${kind}` : ""}`}><Icon name={icon} size={20} /><div>{children}</div></div>;
}

export function errorText(err, t) {
  if (err && err.status === 0) return t("common.offline");
  if (err && typeof err.detail === "string" && err.status && err.status < 500) {
    const key = `err.${err.detail}`;
    const text = t(key);
    if (text !== key) return text;   // known server message, translated in core/i18n.jsx
  }
  return t("common.error");
}

/** Calls fn every ms while mounted. Paused while the tab is hidden unless `background` is set. */
export function usePolling(fn, ms, deps = [], enabled = true, { background = false } = {}) {
  const saved = useRef(fn);
  saved.current = fn;
  useEffect(() => {
    if (!enabled) return undefined;
    let stop = false;
    let timer;
    const loop = async () => {
      if (stop) return;
      if (background || !document.hidden) {
        try { await saved.current(); } catch { /* keep polling */ }
      }
      if (!stop) timer = setTimeout(loop, ms);
    };
    loop();
    return () => { stop = true; clearTimeout(timer); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ms, enabled, background, ...deps]);
}

// ---------------------------------------------------------------------------
// Tab title. The shell names each route; a page whose title comes from data (a group's name, say)
// calls useTitle(text) to replace that name while it is shown.

let pageTitle = null;
const titleListeners = new Set();
const announceTitle = () => titleListeners.forEach((fn) => fn(pageTitle));

/** Set the tab title to "<text> · <app name>" while the calling page is mounted. Empty text keeps the route's name. */
export function useTitle(text) {
  useEffect(() => {
    if (!text) return undefined;
    pageTitle = text;
    announceTitle();
    return () => { if (pageTitle === text) { pageTitle = null; announceTitle(); } };
  }, [text]);
}

/** For the shell: the title a page set with useTitle, or null. */
export function usePageTitle() {
  const [title, setTitle] = useState(pageTitle);
  useEffect(() => { titleListeners.add(setTitle); setTitle(pageTitle); return () => { titleListeners.delete(setTitle); }; }, []);
  return title;
}

// ---------------------------------------------------------------------------
// Toasts

let pushToast = null;
// Errors stay longer (people need time to read what went wrong) and can be closed by hand, like other toasts.
export function toast(message, kind = "info", ms = kind === "error" ? 6500 : 3200) {
  if (pushToast) pushToast({ id: Math.random(), message, kind, ms });
}

export function ToastHost() {
  const { t } = useI18n();
  const [items, setItems] = useState([]);
  const drop = (id) => setItems((list) => list.filter((x) => x.id !== id));
  useEffect(() => {
    pushToast = (item) => {
      setItems((list) => [...list.slice(-2), item]);   // at most three at once: older ones make way
      setTimeout(() => drop(item.id), item.ms);
    };
    return () => { pushToast = null; };
  }, []);
  return (
    <div className="toasts" aria-live="polite">
      {items.map((x) => (
        <div key={x.id} className={`toast ${x.kind === "error" ? "error" : ""}`} role={x.kind === "error" ? "alert" : "status"}>
          <span>{x.message}</span>
          <button type="button" className="toast-close" aria-label={t("common.close")} onClick={() => drop(x.id)}><Icon name="x" size={14} /></button>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sheets (modal dialogs). openSheet({title, render: (close) => <Body/>, wide}) returns close().

let setSheets = null;
let nextSheet = 1;

export function openSheet({ title, render, wide = false, onClose }) {
  const id = nextSheet++;
  const close = () => {
    if (setSheets) setSheets((list) => list.filter((s) => s.id !== id));
    if (onClose) onClose();
  };
  if (setSheets) setSheets((list) => [...list, { id, title, render, wide, close }]);
  return close;
}

export function SheetHost() {
  const [sheets, set] = useState([]);
  useEffect(() => { setSheets = set; return () => { setSheets = null; }; }, []);
  return sheets.map((s) => <Sheet key={s.id} title={s.title} wide={s.wide} onClose={s.close}>{s.render(s.close)}</Sheet>);
}

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';
let openSheets = 0;   // the page behind stops scrolling while any sheet is open

export function Sheet({ title, wide, onClose, children }) {
  const { t } = useI18n();
  const titleId = useId();
  const panel = useRef(null);
  useEffect(() => {
    if (openSheets++ === 0) document.body.classList.add("sheet-open");
    return () => { if (--openSheets === 0) document.body.classList.remove("sheet-open"); };
  }, []);
  useEffect(() => {
    const prev = document.activeElement;
    const onKey = (e) => {
      const open = document.querySelectorAll(".sheet");   // sheets stack: keys act on the top one only
      if (open[open.length - 1] !== panel.current) return;
      if (e.key === "Escape") { onClose(); return; }
      if (e.key !== "Tab") return;
      // Keep Tab inside the dialog, as a modal should.
      const items = [...panel.current.querySelectorAll(FOCUSABLE)].filter((el) => el.offsetParent !== null);
      if (!items.length) return;
      const first = items[0]; const last = items[items.length - 1];
      if (e.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKey);
    const focusable = panel.current?.querySelector("input, textarea, select, button:not(.icon-btn)");
    (focusable || panel.current)?.focus();
    return () => { document.removeEventListener("keydown", onKey); prev?.focus?.(); };
  }, [onClose]);
  return createPortal(
    <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="sheet" role="dialog" aria-modal="true" aria-labelledby={titleId} ref={panel} tabIndex={-1}
        style={wide ? { width: "min(820px, 100%)" } : undefined}>
        <div className="sheet-head">
          <h2 id={titleId} dir="auto">{title}</h2>
          <button type="button" className="icon-btn" aria-label={t("common.close")} onClick={onClose}><Icon name="x" size={20} /></button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}
