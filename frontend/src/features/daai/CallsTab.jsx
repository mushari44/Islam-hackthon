// Da'i console, calls tab: incoming requests, the referral card, the call, feedback, experiment results.
// Owner: Eman. Mounted by DaaiConsole.jsx.
import "./strings.js";
import "./daai.css";
import { useEffect, useState } from "react";
import { api, daaiAuth } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { Icon, Spinner, errorText, openSheet, toast, usePolling } from "../../core/ui.jsx";
import { CallPanel } from "../calls/public.jsx";
import { Answer, SourceCard } from "../rag/public.js";
import NewMuslimButton from "./NewMuslimButton.jsx";

// Arabic counts change form with the number (1, 2, 3-10, 11+), so pick the right string.
function callCount(n, t, fmtNum) {
  const form = n === 1 ? "one" : n === 2 ? "two" : n >= 3 && n <= 10 ? "few" : "many";
  return t(`dc.calls_${form}`, { n: fmtNum(n) });
}

function secs(n, fmtNum, t) {
  return n < 60 ? t("unit.s", { n: fmtNum(n) }) : t("unit.m", { n: fmtNum(Math.floor(n / 60)) });
}

// A share as a percentage in the UI language (Arabic digits and the Arabic percent sign in Arabic), with the same
// locales as fmtNum in core/i18n.jsx.
function pct(x, lang) {
  return new Intl.NumberFormat(lang === "ar" ? "ar-SA-u-nu-arab" : "en-GB", { style: "percent", maximumFractionDigits: 0 }).format(x);
}

/** Booked calls that start within 15 minutes (or are running): Start opens the room 5 minutes before. */
function BookedSoon({ items, onStarted }) {
  const { t, langName, fmtTime, fmtNum } = useI18n();
  const [starting, setStarting] = useState(null);
  const start = async (id) => {
    setStarting(id);
    try { const r = await api.dPost(`/api/daai/bookings/${id}/start`, {}); await onStarted(r.call_id); } catch (err) { toast(errorText(err, t), "error"); }
    setStarting(null);
  };
  return (
    <section className="card stack booked-soon">
      <h3><Icon name="calendar" /> {t("ds.soon_title")}</h3>
      {items.map((b) => (
        <div className="queue-item" key={b.id}>
          <div className="stack" style={{ gap: 2 }}>
            <strong>{fmtTime(b.starts_at)} – {fmtTime(b.ends_at)} · {langName(b.lang)}</strong>
            <span className="small muted">{t("ds.minutes", { n: fmtNum(b.minutes) })}{b.note ? " · " : ""}{b.note && <span dir="auto">{b.note}</span>}</span>
          </div>
          {b.has_card && <span className="badge badge-mint">{t("dc.card")}</span>}
          {b.seeker_waiting && <span className="badge badge-purple">{t("ds.seeker_waiting")}</span>}
          {b.can_start
            ? <button type="button" className="btn btn-primary btn-sm" disabled={starting !== null} onClick={() => start(b.id)}><Icon name="talk" />{t(starting === b.id ? "dc.accepting" : "ds.start")}</button>
            : <span className="small faint">{t("ds.start_at", { time: fmtTime(new Date(new Date(b.starts_at).getTime() - 5 * 60000).toISOString()) })}</span>}
        </div>
      ))}
      <p className="small muted">{t("ds.quiet")}</p>
    </section>
  );
}

function Queue({ me, onActive, onWaiting, onBookings }) {
  const { t, fmtNum, langName } = useI18n();
  const [booked, setBooked] = useState([]);
  const [waiting, setWaiting] = useState(null);   // null until the first answer
  const [failed, setFailed] = useState(null);
  const [accepting, setAccepting] = useState(null);
  usePolling(async () => {
    try {
      const data = await api.dGet("/api/daai/requests");
      setFailed(null);
      setBooked(data.booked || []);
      onBookings?.(data.bookings_today || 0);
      if (data.active.length) onActive(data.active[0].id);
      else setWaiting(data.waiting);
    } catch (err) { setFailed(err); }
  }, 3000, [], true, { background: true });
  const count = waiting ? waiting.length : 0;
  useEffect(() => { onWaiting?.(count); }, [count]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => onWaiting?.(0), []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    // A da'i often waits in another browser tab: show waiting requests in its title. Set again after every poll,
    // since the shell rewrites the title when the route changes (a console tab switch).
    const base = document.title.replace(/^\(\d+\) /, "");
    document.title = count ? `(${count}) ${base}` : base;
    return () => { document.title = document.title.replace(/^\(\d+\) /, ""); };
  }, [waiting]); // eslint-disable-line react-hooks/exhaustive-deps
  const accept = async (id) => {
    setAccepting(id);   // a second click would only meet our own acceptance and report "taken"
    try { await api.dPost(`/api/daai/requests/${id}/accept`, {}); await onActive(id); } catch (err) {
      toast(err.status === 409 ? t("dc.taken") : errorText(err, t), "error");
    } finally { setAccepting(null); }
  };
  let body;
  if (!waiting) body = failed ? <p className="muted">{errorText(failed, t)}</p> : <Spinner />;
  else if (!waiting.length) body = <p className="muted">{t(me.available ? "dc.queue_empty" : "dc.queue_off")}</p>;
  return (
    <>
    {booked.length > 0 && <BookedSoon items={booked} onStarted={onActive} />}
    <section className="card stack">
      <h3>{t("dc.queue")}</h3>
      {body || waiting.map((r) => (
        <div className="queue-item" key={r.id}>
          <div><strong>{langName(r.lang)}</strong> <span className="faint">{t("dc.waiting", { s: secs(r.waiting_seconds, fmtNum, t) })}</span></div>
          <span className={`badge ${r.has_card ? "badge-mint" : ""}`}>{r.has_card ? t("dc.card") : t("dc.no_card")}</span>
          {r.has_chat && <span className="badge badge-mint">{t("dc.chat_badge")}</span>}
          {r.for_you && <span className="badge badge-purple">{t("dc.for_you")}</span>}
          <button type="button" className="btn btn-primary btn-sm" disabled={accepting !== null} onClick={() => accept(r.id)}>
            <Icon name="talk" />{t(accepting === r.id ? "dc.accepting" : "dc.accept")}
          </button>
        </div>
      ))}
    </section>
    </>
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
  const [marking, setMarking] = useState(false);
  const card = call.card;
  const mark = async () => {
    setMarking(true);
    try { await api.dPost(`/api/daai/calls/${call.id}/understood`, {}); setUnderstood(true); } catch (err) { toast(errorText(err, t), "error"); }
    setMarking(false);
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
        <button type="button" className="btn btn-accent" disabled={understood || marking} onClick={mark}>
          <Icon name="check" />{understood ? t("dc.understood_done") : t("dc.understood")}
        </button>
        <NewMuslimButton callId={call.id} status={call.new_muslim ?? null} />
      </div>
    </section>
  );
}

function Feedback({ id, hadCard, onDone }) {
  const { t } = useI18n();
  const [re, setRe] = useState(null);
  const [acc, setAcc] = useState(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
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
    setBusy(true);
    try {
      await api.dPost(`/api/daai/calls/${id}/end`, { reexplain_needed: val(re), card_accurate: val(acc), note });
    } catch (err) {
      toast(errorText(err, t), "error");   // keep the form so the answers aren't lost
      setBusy(false);
      return;
    }
    toast(t("dc.saved"), "success");
    onDone();
  };
  return (
    <form className="card stack" onSubmit={submit}>
      <h3>{t("dc.feedback")}</h3>
      <div className="field"><span className="field-label">{t("dc.reexplain")}</span>{pick("re", re, setRe, false, t("dc.reexplain"))}</div>
      {hadCard && <div className="field"><span className="field-label">{t("dc.accurate")}</span>{pick("acc", acc, setAcc, true, t("dc.accurate"))}</div>}
      <div className="field"><label htmlFor="dc-note">{t("dc.note")}</label>
        <textarea id="dc-note" className="textarea" rows={2} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} /></div>
      <div className="field"><span className="field-label">{t("nm.after_call")}</span><div className="row"><NewMuslimButton callId={id} /></div></div>
      <div className="row"><button type="submit" className="btn btn-primary" disabled={busy}>{t("dc.submit")}</button></div>
    </form>
  );
}

function Experiment({ me }) {
  const { t, lang, fmtNum } = useI18n();
  const [data, setData] = useState(null);
  const [switching, setSwitching] = useState(false);
  usePolling(async () => setData(await api.dGet("/api/daai/experiment")), 15000);
  if (!data) return null;
  const toggle = async (e) => {
    setSwitching(true);
    try {
      await api.dPost("/api/daai/experiment", { enabled: e.target.checked });
      setData(await api.dGet("/api/daai/experiment"));
    } catch (err) { toast(errorText(err, t), "error"); }
    setSwitching(false);
  };
  return (
    <section className="card stack">
      <h3>{t("dc.exp")}</h3>
      <p className="small muted">{data.enabled ? t("dc.exp_on") : t("dc.exp_off")}</p>
      {me.role === "admin" && (
        <label className={`row${switching ? " daai-busy" : ""}`}>
          <span className="switch"><input type="checkbox" checked={data.enabled} disabled={switching} onChange={toggle} /><span /></span><span>{t("dc.exp_toggle")}</span>
        </label>
      )}
      <div className="exp-grid">
        {Object.entries(data.arms || {}).map(([arm, s]) => (
          <div className="exp-arm" key={arm}>
            <strong>{t(`dc.arm.${arm}`)}</strong>
            <div className="faint">{callCount(s.calls, t, fmtNum)}</div>
            {s.no_reexplain_rate != null && <div>{pct(s.no_reexplain_rate, lang)} {t("dc.no_reexplain")}</div>}
            {s.card_accurate_rate != null && <div>{pct(s.card_accurate_rate, lang)} {t("dc.accuracy")}</div>}
            {s.median_seconds_to_understand != null && <div>{secs(Math.round(s.median_seconds_to_understand), fmtNum, t)} {t("dc.median")}</div>}
          </div>
        ))}
      </div>
    </section>
  );
}

/** On a booked call's screen: its time, whether the seeker has come, and "the seeker didn't come" after 10 minutes. */
function BookedCallBar({ callId, initial, onNoShow }) {
  const { t, fmtTime } = useI18n();
  const [b, setB] = useState(initial);
  const [now, setNow] = useState(Date.now());
  const [busy, setBusy] = useState(false);
  usePolling(async () => {
    const call = await api.dGet(`/api/daai/calls/${callId}`);
    if (call.booking) setB(call.booking);
    setNow(Date.now());
  }, 5000, [callId]);
  const noShow = async () => {
    setBusy(true);
    try { await api.dPost(`/api/daai/bookings/${b.id}/no-show`, {}); toast(t("ds.no_show_done"), "success"); onNoShow(); } catch (err) { toast(errorText(err, t), "error"); }
    setBusy(false);
  };
  const late = now >= new Date(b.no_show_from).getTime();
  return (
    <div className="notice notice-mint booked-bar">
      <Icon name="calendar" size={20} />
      <div className="row spread" style={{ flex: 1 }}>
        <span>
          <strong>{t("ds.booked_call", { from: fmtTime(b.starts_at), to: fmtTime(b.ends_at) })}</strong>
          {" · "}{b.seeker_waiting ? t("ds.seeker_came") : t("ds.seeker_not_yet")}
        </span>
        {!b.seeker_waiting && late && (
          <button type="button" className="btn btn-sm btn-danger-soft" disabled={busy} onClick={noShow}>{t("ds.no_show")}</button>
        )}
      </div>
    </div>
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

/** onCall(id | null): the call in progress, so the console can ask before signing out. onWaiting(n): requests waiting. */
export default function CallsTab({ me, onCall, onWaiting, onBookings }) {
  const { t } = useI18n();
  const [view, setView] = useState({ name: "queue" });
  const inCall = view.name === "call" ? view.call.id : null;
  useEffect(() => { onCall?.(inCall); }, [inCall]); // eslint-disable-line react-hooks/exhaustive-deps

  const openCall = async (id) => {
    try { setView({ name: "call", call: await api.dGet(`/api/daai/calls/${id}`) }); } catch (err) { toast(errorText(err, t), "error"); }
  };

  if (view.name === "call") {
    const { call } = view;
    return (
      <div className="stack">
        <EndWatcher id={call.id} onEnded={() => setView({ name: "feedback", id: call.id, hadCard: Boolean(call.card) })} />
        {call.booking && <BookedCallBar callId={call.id} initial={call.booking} onNoShow={() => setView({ name: "queue" })} />}
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
      <Queue me={me} onActive={openCall} onWaiting={onWaiting} onBookings={onBookings} />
      <Experiment me={me} />
    </div>
  );
}

export const callsTab = { key: "calls", labelKey: "dc.tab", component: CallsTab };
