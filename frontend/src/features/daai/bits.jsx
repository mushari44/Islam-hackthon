// Small pieces the da'i console tabs share: a two-step button for actions that are hard to undo, and the
// "couldn't load" notice with a retry. Owner: Eman.
import "./strings.js";
import "./daai.css";
import { useEffect, useState } from "react";
import { useI18n } from "../../core/i18n.jsx";
import { Icon, Notice, errorText } from "../../core/ui.jsx";

/**
 * The first click asks `question` with a red `yes` button and a Cancel (or `no`) button; only the second click runs
 * onYes(). With ask={false} the first click runs it straight away. onYes handles its own errors.
 */
export function AskFirst({ label, icon, question, yes, no, onYes, ask = true, className = "btn btn-sm btn-danger-soft", disabled = false }) {
  const { t } = useI18n();
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try { await onYes(); } finally { setBusy(false); setAsking(false); }
  };
  if (!asking) {
    return (
      <button type="button" className={className} disabled={disabled || busy} onClick={() => (ask ? setAsking(true) : run())}>
        {icon && <Icon name={icon} />}{label}
      </button>
    );
  }
  return (
    <span className="row daai-ask" role="group" aria-label={question}>
      <span className="small">{question}</span>
      <button type="button" className="btn btn-sm btn-danger" disabled={busy} onClick={run}>{yes || label}</button>
      <button type="button" className="btn btn-sm btn-ghost" autoFocus disabled={busy} onClick={() => setAsking(false)}>{no || t("common.cancel")}</button>
    </span>
  );
}

/** While `on`, the browser asks "Leave site?" before a reload or close would lose what is on screen. */
export function useLeaveWarning(on) {
  useEffect(() => {
    if (!on) return undefined;
    const warn = (e) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [on]);
}

/** Shown in place of a list that failed to load. */
export function LoadError({ err, onRetry }) {
  const { t } = useI18n();
  return (
    <Notice kind="warn" icon="alert">
      <div className="row"><span>{errorText(err, t)}</span><button type="button" className="btn btn-sm" onClick={onRetry}>{t("common.retry")}</button></div>
    </Notice>
  );
}
