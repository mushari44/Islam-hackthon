// Da'i console, "Call log" tab: every call the da'i answered in a month, with dates, and the numbers
// the referral experiment needs.
// Owner: Eman. Numbers only: call audio is never recorded, and nothing here identifies the seeker. The one exception
// is the Ask chat a seeker chose to share with this da'i, which opens on demand (and is gone once they delete it).
import "./daai.css";
import { useState } from "react";
import { api } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { Icon, Spinner, errorText, toast, usePolling } from "../../core/ui.jsx";
import { LoadError } from "./bits.jsx";
import { openSharedChat } from "./CallsTab.jsx";
import NewMuslimButton from "./NewMuslimButton.jsx";

function duration(n, t, fmtNum) {
  if (n == null) return "—";
  return n < 60 ? t("unit.s", { n: fmtNum(n) }) : t("unit.m", { n: fmtNum(Math.round(n / 60)) });
}

function YesNo({ value, good }) {
  const { t } = useI18n();
  if (value == null) return <span className="faint">—</span>;
  const ok = value === good;
  return <span className={`badge ${ok ? "badge-mint" : "badge-warn"}`}>{t(value ? "common.yes" : "common.no")}</span>;
}

function Stat({ icon, value, label }) {
  return (
    <div className="card log-stat">
      <Icon name={icon} />
      <strong>{value}</strong>
      <span className="faint">{label}</span>
    </div>
  );
}

function HistoryTab() {
  const { t, langName, fmtNum, fmtDate, fmtTime } = useI18n();
  const showChat = async (id) => {
    try {
      const call = await api.dGet(`/api/daai/calls/${id}`);
      if (call.chat) openSharedChat(call.chat, t);
      else toast(t("dl.chat_gone"), "info");   // the seeker deleted that chat
    } catch (err) { toast(errorText(err, t), "error"); }
  };
  const [month, setMonth] = useState("");
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(null);
  const load = async () => {
    try { setData(await api.dGet(`/api/daai/calls${month ? `?month=${month}` : ""}`)); setFailed(null); } catch (err) { setFailed(err); }
  };
  usePolling(load, 20000, [month]);
  // A later refresh that fails keeps the table on screen; only a first load that fails shows the error.
  if (!data) return failed ? <LoadError err={failed} onRetry={() => { setFailed(null); load(); }} /> : <Spinner />;
  const { calls, summary: s } = data;
  const monthName = (m) => fmtDate(`${m}-15T12:00:00Z`, { month: "long", year: "numeric" });

  return (
    <div className="stack">
      <div className="log-stats">
        <Stat icon="talk" value={fmtNum(s.calls)} label={t("dl.calls")} />
        <Stat icon="clock" value={fmtNum(s.minutes)} label={t("dl.minutes")} />
        <Stat icon="check" value={s.rated ? t("dl.of", { a: fmtNum(s.no_reexplain), b: fmtNum(s.rated) }) : "—"} label={t("dl.no_reexplain")} />
        <Stat icon="heart" value={s.avg_rating != null ? `${fmtNum(s.avg_rating)} / ${fmtNum(5)}` : "—"} label={t("dl.rating")} />
        <Stat icon="sparkle" value={fmtNum(s.new_muslims || 0)} label={t("nm.stat")} />
      </div>

      <section className="card stack">
        <div className="row spread">
          <h3>{t("dl.title", { m: monthName(data.month) })}</h3>
          <label className="row">
            <span className="faint">{t("dl.month")}</span>
            <select className="select log-month" value={data.month} onChange={(e) => { setData(null); setMonth(e.target.value); }}>
              {data.months.map((m) => <option key={m} value={m}>{monthName(m)}</option>)}
            </select>
          </label>
        </div>
        <p className="small muted"><Icon name="shield" size={16} /> {t("dl.privacy")}</p>
        {calls.length === 0 ? (
          <div className="empty"><Icon name="talk" /><p>{t("dl.empty")}</p></div>
        ) : (
          <div className="log-scroll">
            <table className="log-table">
              <thead>
                <tr>
                  <th>{t("dl.when")}</th><th>{t("dl.lang")}</th><th>{t("dl.length")}</th><th>{t("nm.col")}</th><th>{t("dl.arm")}</th>
                  <th>{t("dl.understood")}</th><th>{t("dl.reexplain")}</th><th>{t("dl.accurate")}</th>
                  <th>{t("dl.stars")}</th><th>{t("dl.chat")}</th><th>{t("dl.note")}</th>
                </tr>
              </thead>
              <tbody>
                {calls.map((c) => (
                  <tr key={c.id}>
                    <td>{fmtDate(c.accepted_at, { weekday: "short", day: "numeric", month: "short" })} · {fmtTime(c.accepted_at)}</td>
                    <td>{langName(c.lang)}</td>
                    <td>{duration(c.duration_seconds, t, fmtNum)}</td>
                    <td><NewMuslimButton callId={c.id} status={c.new_muslim ?? null} compact /></td>
                    <td><span className="badge badge-purple">{t(`dc.arm.${c.referral_mode}`)}</span></td>
                    <td>{duration(c.seconds_to_understand, t, fmtNum)}</td>
                    <td><YesNo value={c.reexplain_needed} good={false} /></td>
                    <td>{c.referral_mode === "direct" || c.referral_mode === "none" ? <span className="faint">—</span> : <YesNo value={c.card_accurate} good={true} />}</td>
                    <td>{c.seeker_rating ? fmtNum(c.seeker_rating) : <span className="faint">—</span>}</td>
                    <td>{c.has_chat ? <button type="button" className="btn btn-sm btn-ghost" onClick={() => showChat(c.id)}><Icon name="chat" />{t("dl.chat_show")}</button> : <span className="faint">—</span>}</td>
                    <td className="log-note">{c.note || <span className="faint">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

export const historyTab = { key: "history", labelKey: "dl.tab", component: HistoryTab };
