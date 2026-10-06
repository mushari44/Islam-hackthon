// Talk page (seeker): call now (choose a language, request a call, wait) or book a time with a da'i, then talk
// and rate. Owner: Eman (calls).
import "./strings.js";
import "./calls.css";
import { useCallback, useEffect, useState } from "react";
import { api, seekerToken } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { navigate } from "../../core/router.jsx";
import { Icon, Notice, Spinner, errorText, rovingKeys, toast, usePolling } from "../../core/ui.jsx";
import { useAccount } from "../account/public.js";
import { NewMuslimPrompt } from "../community/public.js";
import BookFlow from "./BookFlow.jsx";
import CallPanel, { Clock, MIC_PROBLEMS, useClock, useLeaveWarning } from "./CallPanel.jsx";
import MyBookings, { BookingRoom } from "./MyBookings.jsx";
import { requestMic } from "./room.js";

const ACTIVE = "sabeeli.call";
const LANGS = ["ar", "en"];   // the languages we support for now
const remember = (id) => { try { id ? sessionStorage.setItem(ACTIVE, String(id)) : sessionStorage.removeItem(ACTIVE); } catch { /* ignore */ } };
const recall = () => { try { return Number(sessionStorage.getItem(ACTIVE)) || null; } catch { return null; } };

/** Optional: pick one da'i by name. Da'is this seeker talked to before come first, marked "talked before". */
function DaaiPicker({ lang, gender, value, onChange, onBook }) {
  const { t, lang: uiLang } = useI18n();
  const [people, setPeople] = useState(null);   // null until the list for this language has loaded
  const [past, setPast] = useState([]);
  useEffect(() => { api.get("/api/calls").then((p) => setPast(p.map((x) => x.daai.id))).catch(() => {}); }, []);
  useEffect(() => setPeople(null), [lang]);
  usePolling(async () => setPeople(await api.pGet(`/api/daais?lang=${lang}&ui=${uiLang}`)), 15000, [lang, uiLang]);
  const shown = (people || []).filter((p) => !gender || p.gender === gender)
    .sort((a, b) => (past.includes(b.id) - past.includes(a.id)) || (b.online - a.online));
  useEffect(() => {
    if (value && people && !shown.some((p) => p.id === value)) onChange(null);   // no longer matches the language or gender
  }, [value, people, gender]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!shown.length) return null;
  return (
    <>
      <h3>{t("talk.who")}</h3>
      <div className="daai-pick" role="radiogroup" aria-label={t("talk.who")}>
        <button type="button" role="radio" className="daai-option" aria-checked={!value} onClick={() => onChange(null)}>
          <strong>{t("talk.anyone")}</strong><span className="small muted">{t("talk.anyone_hint")}</span>
        </button>
        {shown.map((p) => (
          <button key={p.id} type="button" role="radio" className="daai-option" aria-checked={value === p.id} onClick={() => onChange(p.id)}>
            <strong>{p.name}</strong>
            <span className="small"><span className={`dot ${p.online ? "on" : ""}`} /> {t(p.online ? "talk.online" : "talk.offline")}
              {p.city ? ` · ${p.city}` : ""}</span>
            {past.includes(p.id) && <span className="badge badge-mint">{t("talk.before")}</span>}
            {p.bio && <span className="small muted daai-bio">{p.bio}</span>}
          </button>
        ))}
      </div>
      {value && !shown.find((p) => p.id === value)?.online && (
        <div className="stack" style={{ gap: 6 }}>
          <p className="small muted">{t("talk.offline_note")}</p>
          {shown.find((p) => p.id === value)?.bookable && (
            <div className="row"><button type="button" className="btn btn-sm" onClick={() => onBook(value, lang)}><Icon name="calendar" />{t("talk.book_instead")}</button></div>
          )}
        </div>
      )}
    </>
  );
}

const MODES = [["now", "talk.mode_now", "talk"], ["book", "talk.mode_book", "calendar"], ["bookings", "talk.mode_mine", "clock"]];

/** "Call now", "Book a time" or "My bookings", kept in the URL so a link or the account menu can open one.
 * A referral card or shared chat chosen on the way here (ref, card, chat) stays with whichever tab is picked. */
function ModeTabs({ mode, query }) {
  const { t } = useI18n();
  const go = (key) => {
    const q = new URLSearchParams();
    if (key !== "now") q.set("mode", key);
    if (key !== "bookings") for (const k of ["ref", "card", "chat"]) if (query[k]) q.set(k, query[k]);
    navigate(q.toString() ? `/talk?${q}` : "/talk");
  };
  return (
    <div className="tabs talk-modes" role="tablist" aria-label={t("talk.modes")}>
      {MODES.map(([key, label, icon]) => (
        <button key={key} type="button" role="tab" aria-selected={mode === key} tabIndex={mode === key ? 0 : -1} onKeyDown={rovingKeys} onClick={() => go(key)}>
          <Icon name={icon} />{t(label)}
        </button>
      ))}
    </div>
  );
}

function Choose({ query, initialDaai, initialLang, onRequested, onBook }) {
  const { t, lang: uiLang, fmtNum, langName } = useI18n();
  const [lang, setLang] = useState(initialLang || query.lang || uiLang);
  const [gender, setGender] = useState(["m", "f"].includes(query.gender) ? query.gender : "");
  const [daai, setDaai] = useState(initialDaai || (query.daai ? Number(query.daai) : null));
  const [availability, setAvailability] = useState({});
  const [busy, setBusy] = useState(false);
  const { account, loaded } = useAccount();
  const signedOut = loaded && !account;
  usePolling(async () => setAvailability((await api.pGet("/api/availability")).languages || {}), 8000);

  // Calling needs an account. Signing in brings the seeker back here with what they chose (and the referral card).
  const signIn = () => {
    const q = new URLSearchParams({ lang });
    if (gender) q.set("gender", gender);
    if (daai) q.set("daai", String(daai));
    for (const k of ["ref", "card", "chat"]) if (query[k]) q.set(k, query[k]);
    return `#/account?next=${encodeURIComponent(`/talk?${q}`)}`;
  };

  const request = async () => {
    setBusy(true);
    try {
      const res = await api.post("/api/calls", { lang, gender_pref: gender, referral_id: query.ref ? Number(query.ref) : null, daai_id: daai });
      remember(res.id);
      onRequested(res.id);
      navigate("/talk"); // a referral is used once; a later "new call" starts without it
    } catch (err) {
      if (err.status === 403 && err.detail === "sign in to call") { window.location.hash = signIn(); return; }
      toast(errorText(err, t), "error");
      setBusy(false);
    }
  };

  return (
    <div className="card stack talk-card">
      {signedOut && (
        <Notice kind="warn" icon="lock">
          <div className="stack">
            <span>{t("talk.need_account")}</span>
            <div className="row"><a className="btn btn-primary btn-sm" href={signIn()}>{t("acc.signin_btn")}</a></div>
          </div>
        </Notice>
      )}
      <h3>{t("talk.lang")}</h3>
      <div className="lang-grid">
        {LANGS.map((code) => {
          const n = availability[code]?.total || 0;
          return (
            <button key={code} type="button" className="lang-option" aria-pressed={lang === code} onClick={() => setLang(code)}>
              <span className="lang-name">{langName(code)}</span>
              <span className="small"><span className={`dot ${n ? "on" : ""}`} /> {n ? t("talk.available", { n: fmtNum(n) }) : t("talk.none")}</span>
            </button>
          );
        })}
      </div>
      <h3>{t("talk.gender")}</h3>
      <div className="tabs tabs-fit" role="radiogroup" aria-label={t("talk.gender")}>
        {[["", "talk.any"], ["m", "talk.male"], ["f", "talk.female"]].map(([v, k]) => (
          <button key={v || "any"} type="button" role="radio" aria-checked={gender === v} tabIndex={gender === v ? 0 : -1} onKeyDown={rovingKeys} onClick={() => setGender(v)}>{t(k)}</button>
        ))}
      </div>
      <DaaiPicker lang={lang} gender={gender} value={daai} onChange={setDaai} onBook={onBook} />
      {!(availability[lang]?.total) && (
        <Notice icon="calendar">
          <div className="row spread"><span>{t("talk.none_book")}</span>
            <button type="button" className="btn btn-sm" onClick={() => onBook(daai, lang)}><Icon name="calendar" />{t("talk.mode_book")}</button></div>
        </Notice>
      )}
      {query.card && <Notice kind="mint" icon="check">{t("talk.with_card")}</Notice>}
      {query.chat && <Notice kind="mint" icon="chat">{t("talk.with_chat")}</Notice>}
      <div className="row">
        {signedOut
          ? <a className="btn btn-primary btn-lg" href={signIn()}><Icon name="lock" />{t("talk.signin_call")}</a>
          : <button type="button" className="btn btn-primary btn-lg" disabled={busy || !loaded} onClick={request}><Icon name="talk" />{t("talk.call")}</button>}
      </div>
      <p className="faint">{t("talk.safety")}</p>
    </div>
  );
}

/** Asks for the microphone while the seeker waits, so the browser's prompt (or a blocked mic) is dealt with
 * before the da'i joins. The test stream is stopped at once; the call asks again and the browser remembers. */
function MicCheck() {
  const { t } = useI18n();
  const [mic, setMic] = useState("checking");   // "checking" | "ready" | a key of MIC_PROBLEMS
  const check = useCallback(async () => {
    setMic("checking");
    const res = await requestMic();
    res.stream?.getTracks().forEach((track) => track.stop());
    setMic(res.stream ? "ready" : res.problem);
  }, []);
  useEffect(() => { check(); }, [check]);
  return (
    <div role="status" className="small">
      {mic === "checking" && <p className="mic-check muted">{t("talk.mic_checking")}</p>}
      {mic === "ready" && <p className="mic-check muted"><Icon name="mic" size={16} />{t("talk.mic_ready")}</p>}
      {MIC_PROBLEMS[mic] && (
        <p className="mic-check">
          <Icon name="micOff" size={16} /><span>{t(MIC_PROBLEMS[mic])}</span>
          <button type="button" className="btn btn-sm" onClick={check}>{t("talk.mic_retry")}</button>
        </p>
      )}
    </div>
  );
}

function Waiting({ id, onAccepted, onExpired, onCancelled }) {
  const { t, fmtNum } = useI18n();
  const [queue, setQueue] = useState(0);
  const [named, setNamed] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const sec = useClock(true);
  useLeaveWarning(!cancelling);
  usePolling(async () => {
    if (cancelling) return;   // the cancel decides what comes next
    const st = await api.get(`/api/calls/${id}`);
    setQueue(st.queue_position || 0);
    setNamed(Boolean(st.daai_pref));
    if (st.status === "accepted") onAccepted(st);
    else if (st.status === "expired") onExpired();
    else if (st.status === "cancelled" || st.status === "ended") onCancelled();
  }, 2000, [id], true, { background: true });
  const cancel = async () => {
    setCancelling(true);
    try { await api.post(`/api/calls/${id}/cancel`, {}); } catch (err) {
      toast(errorText(err, t), "error");   // the request is still waiting: stay here
      setCancelling(false);
      return;
    }
    onCancelled();
  };
  return (
    <div className="card stack center waiting">
      <div className="pulse"><Icon name="talk" size={40} /></div>
      <h3>{t(named ? "talk.waiting_named" : "talk.waiting")}</h3>
      {queue > 0 && <p className="muted">{t("talk.queue", { n: fmtNum(queue) })}</p>}
      <p className="faint"><Clock sec={sec} /></p>
      <MicCheck />
      <div className="row" style={{ justifyContent: "center" }}><button type="button" className="btn btn-danger-soft" disabled={cancelling} onClick={cancel}>{t("talk.cancel")}</button></div>
    </div>
  );
}

function Ended({ id, daai, onAgain }) {
  const { t } = useI18n();
  const [rated, setRated] = useState(false);
  const rate = async (n) => { await api.post(`/api/calls/${id}/rate`, { rating: n }).catch(() => {}); setRated(true); };
  return (
    <>
    {/* the da'i may confirm the seeker embraced Islam during the call or just after it */}
    <NewMuslimPrompt poll />
    <div className="card stack center">
      <h3>{t("talk.ended")}</h3>
      <p className="muted">{t("talk.rate")}</p>
      {rated ? <p className="muted">{t("talk.rated")}</p> : (
        <div className="row stars" style={{ justifyContent: "center" }}>
          {[1, 2, 3, 4, 5].map((n) => <button key={n} type="button" className="icon-btn" aria-label={t("talk.rate_n", { n })} title={t("talk.rate_n", { n })} onClick={() => rate(n)}><Icon name="heart" size={22} /></button>)}
        </div>
      )}
      <div className="row talk-end-actions">
        <a className="btn btn-primary" href="#/ask">{t("talk.back_ask")}</a>
        <button type="button" className="btn" onClick={() => onAgain(null)}>{t("talk.again")}</button>
        {daai && <button type="button" className="btn" onClick={() => onAgain(daai.id, daai.lang)}><Icon name="talk" />{t("talk.again_same", { name: daai.name })}</button>}
      </div>
    </div>
    </>
  );
}

export default function TalkPage({ query }) {
  const { t, lang } = useI18n();
  const [view, setView] = useState({ name: "loading" });
  const [token, setToken] = useState(null);
  const [tokenError, setTokenError] = useState(null);

  // The call's audio room needs this browser's anonymous session; offline, say so and offer a retry.
  const loadToken = () => { setTokenError(null); seekerToken().then(setToken).catch(setTokenError); };
  useEffect(() => { loadToken(); }, []);
  useEffect(() => {
    const active = recall();
    if (!active) { setView({ name: "choose" }); return; }
    api.get(`/api/calls/${active}`).then((st) => {
      if (st.status === "waiting") setView({ name: "waiting", id: active });
      else if (st.status === "accepted") setView({ name: "call", id: active, st });
      else { remember(null); setView({ name: "choose" }); }
    }).catch(() => { remember(null); setView({ name: "choose" }); });
  }, []);

  const ended = useCallback((id, daai) => { remember(null); setView({ name: "ended", id, daai }); }, []);
  // A booking link (the reminder banner, the calendar entry, "Join") opens that booking's waiting room.
  useEffect(() => {
    if (query.booking && !recall()) setView({ name: "room", booking: Number(query.booking) });
  }, [query.booking]);
  const mode = MODES.some(([k]) => k === query.mode) ? query.mode : "now";
  useEffect(() => { setView((v) => (v.name === "room" && !query.booking ? { name: "choose" } : v)); }, [query.booking]);
  const joinBookedCall = async (cid) => {
    try {
      const st = await api.get(`/api/calls/${cid}`);
      if (st.status !== "accepted") return;
      remember(cid);
      setView({ name: "call", id: cid, st });
      navigate("/talk");
    } catch { /* the next poll tries again */ }
  };
  const bookAgain = (daai, lang) => { setView({ name: "choose", daai, lang }); navigate("/talk?mode=book"); };

  let body = <Spinner />;   // checking for a call in progress, or waiting for the session the call needs
  if (view.name === "choose") {
    let inner;
    if (mode === "book") {
      inner = <BookFlow query={query} initialDaai={view.daai} initialLang={view.lang} key={`b${view.daai || "any"}${query.reschedule || ""}`}
        onMine={() => navigate("/talk?mode=bookings")} />;
    } else if (mode === "bookings") {
      inner = <MyBookings onJoin={(id) => navigate(`/talk?booking=${id}`)} onBook={() => navigate("/talk?mode=book")} onBookAgain={bookAgain}
        onReschedule={(id) => navigate(`/talk?mode=book&reschedule=${id}`)} />;
    } else {
      inner = <Choose query={query} initialDaai={view.daai} initialLang={view.lang} key={view.daai || "any"} onRequested={(id) => setView({ name: "waiting", id })}
        onBook={bookAgain} />;
    }
    body = <><ModeTabs mode={mode} query={query} />{inner}</>;
  }
  if (view.name === "room") {
    body = (
      <BookingRoom id={view.booking} onCall={joinBookedCall} onLeave={() => navigate("/talk?mode=bookings")}
        onCallNow={() => { setView({ name: "choose" }); navigate("/talk"); }} onBookAgain={bookAgain} />
    );
  }
  if (view.name === "waiting") {
    body = (
      <Waiting id={view.id}
        onAccepted={(st) => setView({ name: "call", id: view.id, st })}
        onExpired={() => { remember(null); setView({ name: "expired" }); }}
        onCancelled={() => { remember(null); setView({ name: "choose" }); }} />
    );
  }
  if (view.name === "expired") {
    body = (
      <div className="card stack">
        <p>{t("talk.expired")}</p>
        <div className="row">
          <button type="button" className="btn btn-primary" onClick={() => setView({ name: "choose" })}>{t("talk.again")}</button>
          <a className="btn" href="#/community">{t("nav.community")}</a>
        </div>
      </div>
    );
  }
  if (view.name === "call" && token) {
    const d = view.st.daai;
    const name = d ? (lang === "ar" ? d.name : d.name_en || d.name) : "";
    body = (
      <>
        <EndWatcher id={view.id} onEnded={() => ended(view.id, d && { id: d.id, name, lang: view.st.lang })} />
        <CallPanel callId={view.id} role="seeker" token={token} title={t("talk.connected_with", { name })}
          historyPath={`/api/calls/${view.id}/messages`} onEnded={() => ended(view.id, d && { id: d.id, name, lang: view.st.lang })} />
      </>
    );
  }
  if (view.name === "ended") body = <Ended id={view.id} daai={view.daai} onAgain={(daai, lang) => setView({ name: "choose", daai, lang })} />;

  return (
    <div className="talk">
      <div className="page-head"><h1>{t("talk.title")}</h1><p>{t("talk.lead")}</p></div>
      {tokenError && !token ? (
        <Notice kind="warn" icon="alert">
          <div className="row"><span>{errorText(tokenError, t)}</span><button type="button" className="btn btn-sm" onClick={loadToken}>{t("common.retry")}</button></div>
        </Notice>
      ) : body}
    </div>
  );
}

/** Polls the call status so the seeker's screen ends even if the signalling socket missed it. */
function EndWatcher({ id, onEnded }) {
  usePolling(async () => {
    const st = await api.get(`/api/calls/${id}`);
    if (st.status === "ended") onEnded();
  }, 4000, [id]);
  return null;
}
