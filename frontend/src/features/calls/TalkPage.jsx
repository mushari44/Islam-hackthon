// Talk page (seeker): choose a language, request a call, wait, talk, rate. Owner: Eman (calls).
import "./strings.js";
import "./calls.css";
import { useCallback, useEffect, useState } from "react";
import { api, seekerToken } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { navigate } from "../../core/router.jsx";
import { Icon, Notice, errorText, toast, usePolling } from "../../core/ui.jsx";
import { NewMuslimPrompt } from "../community/public.js";
import CallPanel, { Clock, useClock } from "./CallPanel.jsx";

const ACTIVE = "sabeeli.call";
const LANGS = ["ar", "en"];   // the languages we support for now
const remember = (id) => { try { id ? sessionStorage.setItem(ACTIVE, String(id)) : sessionStorage.removeItem(ACTIVE); } catch { /* ignore */ } };
const recall = () => { try { return Number(sessionStorage.getItem(ACTIVE)) || null; } catch { return null; } };

/** Optional: pick one da'i by name. Da'is this seeker talked to before come first, marked "talked before". */
function DaaiPicker({ lang, gender, value, onChange }) {
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
      {value && !shown.find((p) => p.id === value)?.online && <p className="small muted">{t("talk.offline_note")}</p>}
    </>
  );
}

function Choose({ query, initialDaai, initialLang, onRequested }) {
  const { t, lang: uiLang, fmtNum, langName } = useI18n();
  const [lang, setLang] = useState(initialLang || query.lang || uiLang);
  const [gender, setGender] = useState("");
  const [daai, setDaai] = useState(initialDaai || (query.daai ? Number(query.daai) : null));
  const [availability, setAvailability] = useState({});
  const [busy, setBusy] = useState(false);
  usePolling(async () => setAvailability((await api.pGet("/api/availability")).languages || {}), 8000);

  const request = async () => {
    setBusy(true);
    try {
      const res = await api.post("/api/calls", { lang, gender_pref: gender, referral_id: query.ref ? Number(query.ref) : null, daai_id: daai });
      remember(res.id);
      onRequested(res.id);
      navigate("/talk"); // a referral is used once; a later "new call" starts without it
    } catch (err) {
      toast(errorText(err, t), "error");
      setBusy(false);
    }
  };

  return (
    <div className="card stack talk-card">
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
      <div className="tabs tabs-fit" role="radiogroup">
        {[["", "talk.any"], ["m", "talk.male"], ["f", "talk.female"]].map(([v, k]) => (
          <button key={v || "any"} type="button" role="radio" aria-checked={gender === v} aria-selected={gender === v} onClick={() => setGender(v)}>{t(k)}</button>
        ))}
      </div>
      <DaaiPicker lang={lang} gender={gender} value={daai} onChange={setDaai} />
      {query.card && <Notice kind="mint" icon="check">{t("talk.with_card")}</Notice>}
      {query.chat && <Notice kind="mint" icon="chat">{t("talk.with_chat")}</Notice>}
      <div className="row">
        <button type="button" className="btn btn-primary btn-lg" disabled={busy} onClick={request}><Icon name="talk" />{t("talk.call")}</button>
      </div>
      <p className="faint">{t("talk.safety")}</p>
    </div>
  );
}

function Waiting({ id, onAccepted, onExpired, onCancelled }) {
  const { t, fmtNum } = useI18n();
  const [queue, setQueue] = useState(0);
  const [named, setNamed] = useState(false);
  const sec = useClock(true);
  usePolling(async () => {
    const st = await api.get(`/api/calls/${id}`);
    setQueue(st.queue_position || 0);
    setNamed(Boolean(st.daai_pref));
    if (st.status === "accepted") onAccepted(st);
    else if (st.status === "expired") onExpired();
    else if (st.status === "cancelled" || st.status === "ended") onCancelled();
  }, 2000, [id], true, { background: true });
  const cancel = async () => { await api.post(`/api/calls/${id}/cancel`, {}).catch(() => {}); onCancelled(); };
  return (
    <div className="card stack center waiting">
      <div className="pulse"><Icon name="talk" size={40} /></div>
      <h3>{t(named ? "talk.waiting_named" : "talk.waiting")}</h3>
      {queue > 0 && <p className="muted">{t("talk.queue", { n: fmtNum(queue) })}</p>}
      <p className="faint"><Clock sec={sec} /></p>
      <div className="row" style={{ justifyContent: "center" }}><button type="button" className="btn btn-danger-soft" onClick={cancel}>{t("talk.cancel")}</button></div>
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
      <div className="row" style={{ justifyContent: "center" }}>
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

  useEffect(() => { seekerToken().then(setToken); }, []);
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

  let body = null;
  if (view.name === "choose") {
    body = <Choose query={query} initialDaai={view.daai} initialLang={view.lang} key={view.daai || "any"} onRequested={(id) => setView({ name: "waiting", id })} />;
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
      {body}
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
