// "New Muslim": after a da'i confirms in a call that the seeker embraced Islam, the seeker decides whether their
// groups hear the news (one welcome message in each, and a badge next to their nickname). Nothing is shared without
// their yes, and saying no (now or later) deletes the record. Owner: Mushari (community).
import "./strings.js";
import "./community.css";
import { useEffect, useState } from "react";
import { api } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { Icon, errorText, toast, usePolling } from "../../core/ui.jsx";

/**
 * poll: keep checking (the call's end screen, where the da'i may press it a moment later).
 * manage: once shared, also show the badge's state with a way to take it back (account and community pages).
 */
export function NewMuslimPrompt({ poll = false, manage = false, onChange }) {
  const { t, lang } = useI18n();
  const [info, setInfo] = useState(null);
  const [busy, setBusy] = useState(false);
  const [sure, setSure] = useState(false);
  const load = () => api.get(`/api/community/new-muslim?ui=${lang}`).then(setInfo).catch(() => {});
  useEffect(() => { load(); }, [lang]); // eslint-disable-line react-hooks/exhaustive-deps
  usePolling(load, 5000, [lang], poll && (!info || info.status === "none"));

  const answer = async (share) => {
    setBusy(true);
    try {
      const res = await api.post(`/api/community/new-muslim?ui=${lang}`, { share });
      setInfo(res);
      setSure(false);
      toast(t(share ? "gnm.shared_done" : "gnm.removed_done"), "success");
      onChange?.();
    } catch (err) { toast(errorText(err, t), "error"); } finally { setBusy(false); }
  };

  if (!info || info.status === "none") return null;
  if (info.status === "shared") {
    if (!manage) return null;
    return (
      <section className="card nm-card nm-shared stack">
        <div className="row"><span className="badge badge-mint">{t("gnm.badge")}</span><span className="muted">{t("gnm.shared_state")}</span></div>
        {sure ? (
          <div className="row">
            <span className="small">{t("gnm.remove_q")}</span>
            <button type="button" className="btn btn-sm" disabled={busy} onClick={() => answer(false)}>{t("gnm.remove_yes")}</button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setSure(false)}>{t("common.cancel")}</button>
          </div>
        ) : (
          <div className="row"><button type="button" className="btn btn-ghost btn-sm" onClick={() => setSure(true)}>{t("gnm.remove")}</button></div>
        )}
      </section>
    );
  }
  const groups = info.groups || [];
  return (
    <section className="card nm-card stack" aria-live="polite">
      <h3>🎉 {t("gnm.title")}</h3>
      <p>{info.daai ? t("gnm.lead", { name: info.daai }) : t("gnm.lead_anon")}</p>
      <p>{t("gnm.ask")}</p>
      <p className="small muted">
        {groups.length ? t("gnm.what_groups", { groups: groups.map((g) => (lang === "ar" ? `«${g}»` : `“${g}”`)).join(lang === "ar" ? "، " : ", ") }) : t("gnm.what_none")}
      </p>
      <p className="small muted"><Icon name="shield" size={16} /> {t("gnm.your_choice")}</p>
      <div className="row">
        <button type="button" className="btn btn-accent" disabled={busy} onClick={() => answer(true)}><Icon name="users" />{t("gnm.share")}</button>
        <button type="button" className="btn" disabled={busy} onClick={() => answer(false)}>{t("gnm.keep")}</button>
      </div>
    </section>
  );
}
