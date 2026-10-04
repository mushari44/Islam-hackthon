// "Became Muslim": during a call or after it, the da'i confirms the seeker embraced Islam. The seeker is then asked
// whether their groups may hear the news; nothing is announced without their yes.
// Owner: Eman (built in the "new Muslim" thread with mushari's OK). Used by CallsTab.jsx and HistoryTab.jsx.
import "./strings.js";
import { useEffect, useState } from "react";
import { api } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { Icon, errorText, openSheet, toast } from "../../core/ui.jsx";

function Confirm({ close, onYes }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const yes = async () => { setBusy(true); try { await onYes(); close(); } finally { setBusy(false); } };
  return (
    <div className="stack">
      <p>{t("nm.confirm_q")}</p>
      <p className="small muted"><Icon name="shield" size={16} /> {t("nm.confirm_note")}</p>
      <div className="row">
        <button type="button" className="btn btn-accent" disabled={busy} onClick={yes}><Icon name="check" />{t("nm.confirm_yes")}</button>
        <button type="button" className="btn" onClick={close}>{t("common.cancel")}</button>
      </div>
    </div>
  );
}

/** status: null | "pending" | "shared" (DaaiCall.new_muslim); left out, it is fetched (the after-call form).
 * `compact` for the call log table. */
export default function NewMuslimButton({ callId, status: initial, compact = false }) {
  const { t } = useI18n();
  const [status, setStatus] = useState(initial ?? null);
  useEffect(() => {
    if (initial !== undefined) { setStatus(initial); return undefined; }
    let alive = true;
    api.dGet(`/api/daai/calls/${callId}`).then((c) => alive && setStatus(c.new_muslim ?? null)).catch(() => {});
    return () => { alive = false; };
  }, [callId, initial]);
  const path = `/api/daai/calls/${callId}/new-muslim`;
  const confirm = () => openSheet({
    title: t("nm.confirm_title"),
    render: (close) => <Confirm close={close} onYes={async () => {
      try { setStatus((await api.dPost(path, {})).new_muslim); toast(t("nm.done"), "success"); } catch (err) { toast(errorText(err, t), "error"); }
    }} />,
  });
  const undo = async () => {
    try { await api.del(path, { as: "daai" }); setStatus(null); } catch (err) {
      toast(err.status === 409 ? t("nm.undo_late") : errorText(err, t), "error");
    }
  };
  if (status === "shared") return <span className="badge badge-mint">🎉 {t(compact ? "nm.badge_shared_short" : "nm.badge_shared")}</span>;
  if (status === "pending") {
    return (
      <span className="row nm-row">
        <span className="badge badge-purple">{t(compact ? "nm.badge_pending_short" : "nm.badge_pending")}</span>
        <button type="button" className="btn btn-ghost btn-sm" onClick={undo}>{t("nm.undo")}</button>
      </span>
    );
  }
  return (
    <button type="button" className={`btn btn-sm ${compact ? "btn-ghost" : ""}`} onClick={confirm}>
      <Icon name="sparkle" />{t(compact ? "nm.button_short" : "nm.button")}
    </button>
  );
}
