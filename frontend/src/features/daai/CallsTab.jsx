// Da'i console, calls tab: incoming requests, the referral card, the call, feedback, experiment results.
// Owner: Eman. Mounted by DaaiConsole.jsx.
import "./strings.js";
import { useEffect, useState } from "react";
import { api, daaiAuth } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { Icon, errorText, openSheet, toast, usePolling } from "../../core/ui.jsx";
import { CallPanel } from "../calls/public.jsx";
import { Answer, SourceCard } from "../rag/public.js";

// Arabic counts change form with the number (1, 2, 3-10, 11+), so pick the right string.
function callCount(n, t, fmtNum) {
  const form = n === 1 ? "one" : n === 2 ? "two" : n >= 3 && n <= 10 ? "few" : "many";
  return t(`dc.calls_${form}`, { n: fmtNum(n) });
}

function secs(n, fmtNum, t) {
  return n < 60 ? t("unit.s", { n: fmtNum(n) }) : t("unit.m", { n: fmtNum(Math.floor(n / 60)) });
}

function Queue({ onActive }) {
  const { t, fmtNum, langName } = useI18n();
  const [waiting, setWaiting] = useState([]);
  usePolling(async () => {
    const data = await api.dGet("/api/daai/requests");
    if (data.active.length) onActive(data.active[0].id);
    else setWaiting(data.waiting);
  }, 3000, [], true, { background: true });
  useEffect(() => {
    // a da'i often waits in another tab: show waiting requests in the tab title
    const base = document.title.replace(/^\(\d+\) /, "");
    document.title = waiting.length ? `(${waiting.length}) ${base}` : base;
    return () => { document.title = document.title.replace(/^\(\d+\) /, ""); };
  }, [waiting.length]);
  const accept = async (id) => {
    try { await api.dPost(`/api/daai/requests/${id}/accept`, {}); onActive(id); } catch (err) {
      toast(err.status === 409 ? t("dc.taken") : errorText(err, t), "error");
    }
  };
  return (
    <section className="card stack">
      <h3>{t("dc.queue")}</h3>
      {waiting.length === 0 ? <p className="muted">{t("dc.queue_empty")}</p> : waiting.map((r) => (
        <div className="queue-item" key={r.id}>
          <div><strong>{langName(r.lang)}</strong> <span className="faint">{t("dc.waiting", { s: secs(r.waiting_seconds, fmtNum, t) })}</span></div>
          <span className={`badge ${r.has_card ? "badge-mint" : ""}`}>{r.has_card ? t("dc.card") : t("dc.no_card")}</span>
          {r.has_chat && <span className="badge badge-mint">{t("dc.chat_badge")}</span>}
          {r.for_you && <span className="badge badge-purple">{t("dc.for_you")}</span>}
          <button type="button" className="btn btn-primary btn-sm" onClick={() => accept(r.id)}><Icon name="talk" />{t("dc.accept")}</button>
        </div>
      ))}
    </section>
  );
}

/** Every message of the chat the seeker shared with their OK: their questions and the cited answers as they saw them. */
function ChatTranscript({ turns }) {
  const { t } = useI18n();
  return (
    <div className="stack shared-chat">
      <p className="small muted">{t("dc.chat_hint")}</p>
      {turns.map((x, i) => (
        <div className="shared-turn stack" key={i}>
          <div className="shared-q">
            <span className="faint small">{t("dc.seeker_asked")}</span>
            {x.had_image && <p className="faint small">{t("dc.photo")}</p>}
            {x.question && <p dir="auto">{x.question}</p>}
          </div>
          <Answer answer={x.answer} compact />
        </div>
      ))}
    </div>
  );
}

/** Opens the whole shared conversation in a wide sheet (the call screen and the call log both use it). */
export function openSharedChat(turns, t) {
  return openSheet({ title: t("dc.chat_title"), wide: true, render: () => <ChatTranscript turns={turns} /> });
}

/** On the call screen: the questions at a glance, and the whole conversation with its answers on demand. */
function SharedChat({ turns }) {
  const { t, fmtNum } = useI18n();
  return (
    <div className="shared-chat stack">
      <div className="row spread">
        <strong>{t("dc.chat_title")} <span className="faint">{t("dc.chat_count", { n: fmtNum(turns.length) })}</span></strong>
        <button type="button" className="btn btn-sm" onClick={() => openSharedChat(turns, t)}><Icon name="chat" />{t("dc.chat_show")}</button>
      </div>
      <ol className="shared-questions">
        {turns.map((x, i) => <li key={i} dir="auto">{x.question || t("dc.photo")}</li>)}
      </ol>
    </div>
  );
}

function CardView({ call }) {
  const { t, langName } = useI18n();
  const [understood, setUnderstood] = useState(call.understood);
  const card = call.card;
  const mark = async () => {
    try { await api.dPost(`/api/daai/calls/${call.id}/understood`, {}); setUnderstood(true); } catch (err) { toast(errorText(err, t), "error"); }
  };
  return (
    <section className="card stack">
      <h3>{t("dc.card_title")}</h3>
      <div className="row"><span className="badge">{langName(call.lang)}</span><span className="badge badge-purple">{t(`dc.arm.${call.referral_mode}`)}</span></div>
      {!card ? (!call.chat && <p className="muted">{t("dc.no_card_long")}</p>) : (
        <div className="stack">
          {card.question && <div><div className="faint">{t("dc.question")}</div><p dir="auto">{card.question}</p></div>}
          {card.context && <div><div className="faint">{t("dc.context")}</div><p dir="auto">{card.context}</p></div>}
          {(card.explained || []).length > 0 && (
            <div>
              <div className="faint">{t("dc.explained")}</div>
              <ul>{card.explained.map((e, i) => <li key={i} dir="auto">{e.point}</li>)}</ul>
              <div className="stack">{Object.values(call.card_sources || {}).map((c) => <SourceCard key={c.id} card={c} compact />)}</div>
            </div>
          )}
          {card.unclear && <div><div className="faint">{t("dc.unclear")}</div><p dir="auto">{card.unclear}</p></div>}
        </div>
      )}
      {call.chat && <SharedChat turns={call.chat} />}
      <div className="row">
        <button type="button" className="btn btn-accent" disabled={understood} onClick={mark}>
          <Icon name="check" />{understood ? t("dc.understood_done") : t("dc.understood")}
        </button>
      </div>
    </section>
  );
}

function Feedback({ id, hadCard, onDone }) {
  const { t } = useI18n();
  const [re, setRe] = useState(null);
  const [acc, setAcc] = useState(null);
  const [note, setNote] = useState("");
  const pick = (name, value, set, withNa, label) => (
    <div className="row" role="radiogroup" aria-label={label}>
      {[["yes", "common.yes"], ["no", "common.no"], ...(withNa ? [["na", "dc.na"]] : [])].map(([v, k]) => (
        <label className="check" key={v}><input type="radio" name={name} checked={value === v} onChange={() => set(v)} /><span>{t(k)}</span></label>
      ))}
    </div>
  );
  const val = (v) => (v === "yes" ? true : v === "no" ? false : null);
  const submit = async (e) => {
    e.preventDefault();
    await api.dPost(`/api/daai/calls/${id}/end`, { reexplain_needed: val(re), card_accurate: val(acc), note }).catch(() => {});
    onDone();
  };
  return (
    <form className="card stack" onSubmit={submit}>
      <h3>{t("dc.feedback")}</h3>
      <div className="field"><label>{t("dc.reexplain")}</label>{pick("re", re, setRe, false, t("dc.reexplain"))}</div>
      {hadCard && <div className="field"><label>{t("dc.accurate")}</label>{pick("acc", acc, setAcc, true, t("dc.accurate"))}</div>}
      <div className="field"><label htmlFor="dc-note">{t("dc.note")}</label>
        <textarea id="dc-note" className="textarea" rows={2} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} /></div>
      <div className="row"><button type="submit" className="btn btn-primary">{t("dc.submit")}</button></div>
    </form>
  );
}

function Experiment({ me }) {
  const { t, fmtNum } = useI18n();
  const [data, setData] = useState(null);
  usePolling(async () => setData(await api.dGet("/api/daai/experiment")), 15000);
  if (!data) return null;
  const toggle = async (e) => {
    await api.dPost("/api/daai/experiment", { enabled: e.target.checked }).catch(() => {});
    setData(await api.dGet("/api/daai/experiment"));
  };
  return (
    <section className="card stack">
      <h3>{t("dc.exp")}</h3>
      <p className="small muted">{data.enabled ? t("dc.exp_on") : t("dc.exp_off")}</p>
      {me.role === "admin" && (
        <label className="row"><span className="switch"><input type="checkbox" checked={data.enabled} onChange={toggle} /><span /></span><span>{t("dc.exp_toggle")}</span></label>
      )}
      <div className="exp-grid">
        {Object.entries(data.arms || {}).map(([arm, s]) => (
          <div className="exp-arm" key={arm}>
            <strong>{t(`dc.arm.${arm}`)}</strong>
            <div className="faint">{callCount(s.calls, t, fmtNum)}</div>
            {s.no_reexplain_rate != null && <div>{fmtNum(Math.round(s.no_reexplain_rate * 100))}% {t("dc.no_reexplain")}</div>}
            {s.card_accurate_rate != null && <div>{fmtNum(Math.round(s.card_accurate_rate * 100))}% {t("dc.accuracy")}</div>}
            {s.median_seconds_to_understand != null && <div>{secs(Math.round(s.median_seconds_to_understand), fmtNum, t)} {t("dc.median")}</div>}
          </div>
        ))}
      </div>
    </section>
  );
}

/** Notices a call the seeker ended even if the signalling socket missed it. */
function EndWatcher({ id, onEnded }) {
  usePolling(async () => {
    const call = await api.dGet(`/api/daai/calls/${id}`);
    if (call.status === "ended") onEnded();
  }, 4000, [id]);
  return null;
}

export default function CallsTab({ me }) {
  const { t } = useI18n();
  const [view, setView] = useState({ name: "queue" });

  const openCall = async (id) => {
    try { setView({ name: "call", call: await api.dGet(`/api/daai/calls/${id}`) }); } catch (err) { toast(errorText(err, t), "error"); }
  };

  if (view.name === "call") {
    const { call } = view;
    return (
      <div className="stack">
        <EndWatcher id={call.id} onEnded={() => setView({ name: "feedback", id: call.id, hadCard: Boolean(call.card) })} />
        <CardView call={call} />
        <CallPanel callId={call.id} role="daai" token={daaiAuth.token} title={t("dc.active")}
          onEnded={() => setView({ name: "feedback", id: call.id, hadCard: Boolean(call.card) })} />
      </div>
    );
  }
  if (view.name === "feedback") {
    return <Feedback id={view.id} hadCard={view.hadCard} onDone={() => setView({ name: "queue" })} />;
  }
  return (
    <div className="stack">
      <Queue onActive={openCall} />
      <Experiment me={me} />
    </div>
  );
}

export const callsTab = { key: "calls", labelKey: "dc.tab", component: CallsTab };
