// Seeker account page: sign in, sign up, recover, and "my account". Owner: Eman.
// Accounts are optional: a username and password, plus an optional email, place and age band (see features/auth on the backend).
import "./strings.js";
import "./account.css";
import { useEffect, useState } from "react";
import { api } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { Icon, errorText, toast } from "../../core/ui.jsx";
import { COUNTRIES, countryName } from "../community/public.js";
import { setAccount, useAccount } from "./store.js";

function accError(err, t) {
  if (err && err.status === 422) return t("acc.err.invalid");
  const key = err && typeof err.detail === "string" ? `acc.err.${err.detail}` : "";
  return key && t(key) !== key ? t(key) : errorText(err, t);
}

function Field({ id, label, hint, ...props }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input id={id} className="input" {...props} />
      {hint && <span className="faint">{hint}</span>}
    </div>
  );
}

function RecoveryCode({ code, onDone }) {
  const { t } = useI18n();
  const copy = async () => {
    try { await navigator.clipboard.writeText(code); toast(t("acc.copied"), "success"); } catch { /* the code stays selectable */ }
  };
  return (
    <section className="card stack account-card code-card" aria-live="polite">
      <h2>{t("acc.code_title")}</h2>
      <p className="muted">{t("acc.code_lead")}</p>
      <p className="recovery-code" dir="ltr">{code}</p>
      <div className="row">
        <button type="button" className="btn" onClick={copy}><Icon name="link" />{t("acc.copy")}</button>
        <button type="button" className="btn btn-primary" onClick={onDone}><Icon name="check" />{t("acc.saved_code")}</button>
      </div>
    </section>
  );
}

function SignedOut({ onCode }) {
  const { t } = useI18n();
  const [mode, setMode] = useState("signin");          // signin | signup | forgot
  const [step, setStep] = useState("ask");             // forgot: ask -> email (code sent) | recovery (use backup code)
  const [f, setF] = useState({ username: "", password: "", email: "", code: "" });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const pick = (m) => { setMode(m); setStep("ask"); };
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (mode === "signin") {
        const r = await api.post("/api/account/signin", { username: f.username, password: f.password });
        setAccount(r.account);
        toast(t("acc.welcome", { u: r.account.username }), "success");
      } else if (mode === "signup") {
        const r = await api.post("/api/account/signup", { username: f.username, password: f.password, email: f.email });
        onCode(r.recovery_code, r.account);
      } else if (step === "ask") {
        const r = await api.post("/api/account/forgot", { login: f.username });
        setStep(r.via === "email" ? "email" : "recovery");
      } else if (step === "email") {
        const r = await api.post("/api/account/reset", { login: f.username, code: f.code, new_password: f.password });
        setAccount(r.account);
        toast(t("acc.reset_done"), "success");
      } else {
        const r = await api.post("/api/account/recover", { username: f.username, recovery_code: f.code, new_password: f.password });
        onCode(r.recovery_code, r.account);
      }
    } catch (err) {
      toast(accError(err, t), "error");
    } finally {
      setBusy(false);
    }
  };
  const forgot = mode === "forgot";
  const askOnly = forgot && step === "ask";
  return (
    <section className="card stack account-card">
      <div className="tabs" role="tablist">
        {["signin", "signup", "forgot"].map((m) => (
          <button key={m} type="button" role="tab" aria-selected={mode === m} onClick={() => pick(m)}>{t(`acc.${m}`)}</button>
        ))}
      </div>
      <form className="stack" onSubmit={submit}>
        {forgot && !askOnly && <p className="small muted">{t(`acc.forgot_${step}`)}</p>}
        <Field id="acc-user" label={forgot ? t("acc.login") : t("acc.username")} hint={mode === "signup" ? t("acc.username_hint") : null}
          autoComplete="username" required minLength={3} maxLength={forgot ? 254 : 24} value={f.username} onChange={set("username")}
          readOnly={forgot && !askOnly} />
        {mode === "signup" && (
          <Field id="acc-email" type="email" dir="ltr" label={t("acc.email_optional")} hint={t("acc.email_hint")}
            autoComplete="email" maxLength={254} value={f.email} onChange={set("email")} />
        )}
        {forgot && !askOnly && (
          <Field id="acc-code" label={step === "email" ? t("acc.email_code") : t("acc.code")} dir="ltr" autoComplete="one-time-code"
            inputMode={step === "email" ? "numeric" : "text"} required value={f.code} onChange={set("code")} />
        )}
        {!askOnly && (
          <Field id="acc-pass" type="password" label={forgot ? t("acc.new_password") : t("acc.password")}
            hint={mode === "signin" ? null : t("acc.password_hint")}
            autoComplete={mode === "signin" ? "current-password" : "new-password"} required minLength={mode === "signin" ? 1 : 8}
            value={f.password} onChange={set("password")} />
        )}
        {mode === "signup" && <p className="small muted">{t("acc.keep_note")}</p>}
        <div className="row">
          <button type="submit" className="btn btn-primary" disabled={busy}>
            <Icon name={mode === "signin" ? "lock" : askOnly ? "send" : "check"} />
            {t(mode === "signin" ? "acc.do_signin" : mode === "signup" ? "acc.do_signup" : askOnly ? "acc.send_code" : "acc.do_recover")}
          </button>
          {forgot && step === "email" && (
            <button type="button" className="btn btn-ghost" onClick={() => setStep("recovery")}>{t("acc.use_recovery")}</button>
          )}
        </div>
      </form>
    </section>
  );
}

function EmailCard({ account }) {
  const { t } = useI18n();
  const [email, setEmail] = useState(account.email || "");
  const save = async (e) => {
    e.preventDefault();
    try { setAccount((await api.post("/api/account/profile", { email })).account); toast(t("acc.saved"), "success"); }
    catch (err) { toast(accError(err, t), "error"); }
  };
  return (
    <form className="card stack" onSubmit={save}>
      <h3>{t("acc.email_title")}</h3>
      <p className="small muted">{t("acc.email_hint")}</p>
      <div className="row email-row">
        <input id="acc-email-edit" className="input" type="email" dir="ltr" aria-label={t("acc.email_title")} autoComplete="email"
          maxLength={254} value={email} onChange={(e) => setEmail(e.target.value)} />
        <button type="submit" className="btn btn-primary" disabled={email === (account.email || "")}><Icon name="check" />{t("acc.save")}</button>
      </div>
    </form>
  );
}

function Place({ account }) {
  const { t, lang } = useI18n();
  const [country, setCountry] = useState(account.country || "");
  const [city, setCity] = useState(account.city || "");
  const [places, setPlaces] = useState([]);
  useEffect(() => { api.get("/api/community/places").then(setPlaces).catch(() => {}); }, []);
  const cities = (places.find((p) => p.country === country) || {}).cities || [];
  const ordered = ["SA", ...COUNTRIES.filter((c) => c !== "SA")];
  const save = async (e) => {
    e.preventDefault();
    try { setAccount((await api.post("/api/account/profile", { country, city })).account); toast(t("acc.saved"), "success"); }
    catch (err) { toast(accError(err, t), "error"); }
  };
  return (
    <form className="card stack" onSubmit={save}>
      <h3>{t("acc.place")}</h3>
      <p className="small muted">{t("acc.place_lead")}</p>
      <div className="grid grid-2">
        <div className="field">
          <label htmlFor="acc-country">{t("acc.country")}</label>
          <select id="acc-country" className="select" value={country} onChange={(e) => { setCountry(e.target.value); setCity(""); }}>
            <option value="">{t("acc.any")}</option>
            {ordered.map((c) => <option key={c} value={c}>{countryName(c, lang)}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="acc-city">{t("acc.city")}</label>
          <input id="acc-city" className="input" list="acc-cities" maxLength={64} disabled={!country} value={city} onChange={(e) => setCity(e.target.value)} />
          <datalist id="acc-cities">{cities.map((c) => <option key={c} value={c} />)}</datalist>
        </div>
      </div>
      <div className="row"><button type="submit" className="btn btn-primary"><Icon name="check" />{t("acc.save")}</button></div>
    </form>
  );
}

// Optional age bands; keep in step with AGE_BANDS in backend/app/features/auth/routes.py.
const AGE_BANDS = ["u18", "18_24", "25_34", "35_44", "45_54", "55p"];

function AgeCard({ account }) {
  const { t } = useI18n();
  const [band, setBand] = useState(account.age_band || "");
  const save = async (e) => {
    e.preventDefault();
    try { setAccount((await api.post("/api/account/profile", { age_band: band })).account); toast(t("acc.saved"), "success"); }
    catch (err) { toast(accError(err, t), "error"); }
  };
  return (
    <form className="card stack" onSubmit={save}>
      <h3>{t("acc.age")}</h3>
      <p className="small muted">{t("acc.age_lead")}</p>
      <div className="row email-row">
        <select id="acc-age" className="select" aria-label={t("acc.age")} value={band} onChange={(e) => setBand(e.target.value)}>
          <option value="">{t("acc.age_none")}</option>
          {AGE_BANDS.map((b) => <option key={b} value={b}>{t(`acc.age.${b}`)}</option>)}
        </select>
        <button type="submit" className="btn btn-primary" disabled={band === (account.age_band || "")}><Icon name="check" />{t("acc.save")}</button>
      </div>
      {band === "u18" && <p className="small muted">{t("acc.age_minor")}</p>}
    </form>
  );
}

function Activity() {
  const { t, lang, fmtDate } = useI18n();
  const [data, setData] = useState(null);
  useEffect(() => {
    Promise.all([api.get(`/api/meetups?ui=${lang}`), api.get(`/api/groups?ui=${lang}`)])
      .then(([meetups, groups]) => setData({ events: meetups.filter((m) => m.my_rsvp), groups: groups.filter((g) => g.membership) }))
      .catch(() => setData({ events: [], groups: [] }));
  }, [lang]);
  if (!data) return null;
  return (
    <section className="card stack">
      <h3>{t("acc.activity")}</h3>
      <div className="grid grid-2">
        <div className="stack">
          <strong>{t("acc.my_events")}</strong>
          {data.events.length ? (
            <ul className="activity-list">
              {data.events.map((m) => (
                <li key={m.id}><Icon name="calendar" size={16} /><a href="#/community?tab=meetups">{m.title}</a>
                  <span className="faint">{fmtDate(m.starts_at, { day: "numeric", month: "short" })}</span></li>
              ))}
            </ul>
          ) : <p className="faint">{t("acc.no_events")}</p>}
        </div>
        <div className="stack">
          <strong>{t("acc.my_groups")}</strong>
          {data.groups.length ? (
            <ul className="activity-list">
              {data.groups.map((g) => <li key={g.id}><Icon name="chat" size={16} /><a href={`#/groups/${g.id}`}>{g.title}</a></li>)}
            </ul>
          ) : <p className="faint">{t("acc.no_groups")}</p>}
        </div>
      </div>
      {!data.events.length && !data.groups.length && <a className="btn btn-sm account-browse" href="#/community"><Icon name="community" />{t("acc.browse")}</a>}
    </section>
  );
}

function SavedChats() {
  const { t, fmtNum } = useI18n();
  const [count, setCount] = useState(null);
  const [sure, setSure] = useState(false);
  useEffect(() => { api.get("/api/ask/history?limit=200").then((h) => setCount(h.turns.length)).catch(() => setCount(0)); }, []);
  const clear = async () => {
    try {
      await api.del("/api/ask/history");
      try { sessionStorage.removeItem("sabeeli.chat"); } catch { /* ignore */ }
      setCount(0); setSure(false); toast(t("acc.chats_deleted"), "success");
    } catch (err) { toast(accError(err, t), "error"); }
  };
  if (count === null) return null;
  return (
    <section className="card stack">
      <h3>{t("acc.chats")}</h3>
      <p className="small muted">{count ? t("acc.chats_lead", { n: fmtNum(count) }) : t("acc.chats_none")}</p>
      {count > 0 && (
        <div className="row">
          <a className="btn btn-sm" href="#/ask"><Icon name="chat" />{t("acc.chats_open")}</a>
          {sure ? (
            <>
              <button type="button" className="btn btn-sm btn-danger" onClick={clear}><Icon name="trash" />{t("acc.chats_confirm")}</button>
              <button type="button" className="btn btn-sm btn-ghost" onClick={() => setSure(false)}>{t("common.cancel")}</button>
            </>
          ) : <button type="button" className="btn btn-sm btn-ghost danger-text" onClick={() => setSure(true)}><Icon name="trash" />{t("acc.chats_delete")}</button>}
        </div>
      )}
    </section>
  );
}

function Security() {
  const { t } = useI18n();
  const [pw, setPw] = useState({ password: "", new_password: "" });
  const [del, setDel] = useState(null);
  const change = async (e) => {
    e.preventDefault();
    try { await api.post("/api/account/password", pw); setPw({ password: "", new_password: "" }); toast(t("acc.password_changed"), "success"); }
    catch (err) { toast(accError(err, t), "error"); }
  };
  const signout = async () => {
    await api.post("/api/account/signout", {}).catch(() => {});
    setAccount(null);
    toast(t("acc.signed_out"));
  };
  const remove = async (e) => {
    e.preventDefault();
    try { await api.post("/api/account/delete", { password: del }); setAccount(null); toast(t("acc.deleted")); }
    catch (err) { toast(accError(err, t), "error"); }
  };
  return (
    <section className="card stack">
      <h3>{t("acc.security")}</h3>
      <form className="grid grid-2" onSubmit={change}>
        <Field id="acc-cur" type="password" label={t("acc.current_password")} autoComplete="current-password" required
          value={pw.password} onChange={(e) => setPw({ ...pw, password: e.target.value })} />
        <Field id="acc-new" type="password" label={t("acc.new_password")} hint={t("acc.password_hint")} autoComplete="new-password"
          required minLength={8} value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} />
        <div className="row"><button type="submit" className="btn"><Icon name="lock" />{t("acc.change_password")}</button></div>
      </form>
      <div className="row spread account-actions">
        <button type="button" className="btn btn-ghost" onClick={signout}><Icon name="logout" />{t("acc.signout")}</button>
        {del === null && <button type="button" className="btn btn-ghost danger-text" onClick={() => setDel("")}><Icon name="trash" />{t("acc.delete")}</button>}
      </div>
      {del !== null && (
        <form className="stack danger-zone" onSubmit={remove}>
          <p className="small">{t("acc.delete_lead")}</p>
          <Field id="acc-del" type="password" label={t("acc.delete_confirm")} autoComplete="current-password" required
            value={del} onChange={(e) => setDel(e.target.value)} />
          <div className="row">
            <button type="submit" className="btn btn-danger"><Icon name="trash" />{t("acc.do_delete")}</button>
            <button type="button" className="btn btn-ghost" onClick={() => setDel(null)}>{t("common.cancel")}</button>
          </div>
        </form>
      )}
    </section>
  );
}

export default function AccountPage() {
  const { t, fmtDate } = useI18n();
  const { account, loaded } = useAccount();
  const [code, setCode] = useState(null);
  if (!loaded) return null;
  if (code) {
    return (
      <>
        <div className="page-head"><h1>{t("acc.mine")}</h1></div>
        <RecoveryCode code={code.code} onDone={() => { setAccount(code.account); setCode(null); }} />
      </>
    );
  }
  if (!account) {
    return (
      <>
        <div className="page-head"><h1>{t("acc.signin")}</h1></div>
        <SignedOut onCode={(c, acc) => setCode({ code: c, account: acc })} />
      </>
    );
  }
  return (
    <>
      <div className="page-head account-head">
        <span className="account-avatar" aria-hidden="true">{account.username.charAt(0).toUpperCase()}</span>
        <div><h1>{t("acc.welcome", { u: account.username })}</h1><p>{t("acc.since", { d: fmtDate(account.created_at, { month: "long", year: "numeric" }) })}</p></div>
      </div>
      <div className="stack">
        <Activity />
        <SavedChats />
        <Place account={account} />
        <AgeCard account={account} />
        <EmailCard account={account} />
        <Security />
      </div>
    </>
  );
}
