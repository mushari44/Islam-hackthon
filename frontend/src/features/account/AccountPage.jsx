// Account page: the sign-in card (seekers and da'is), sign up, and "my account". Owner: Eman.
// Accounts are optional: a username, a password, the seeker's sex and age band, and an optional email and place
// (see features/auth on the backend).
import "./strings.js";
import "./account.css";
import { useEffect, useState } from "react";
import { api } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { navigate, useHashPath } from "../../core/router.jsx";
import { Icon, errorText, toast } from "../../core/ui.jsx";
import { COUNTRIES, NewMuslimPrompt, countryName } from "../community/public.js";
import { AboutFields, CompleteAbout, needsAbout } from "./fields.jsx";
import { setAccount, setDaaiToken, useAccount } from "./store.js";

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

// Built on first use: community imports this feature too, so nothing from it is read while the modules load.
const ordered = () => ["SA", ...COUNTRIES.filter((c) => c !== "SA")];

/** Country and city (city only once a country is chosen); cities other members use are suggested. */
function PlaceFields({ f, setF, prefix }) {
  const { t, lang } = useI18n();
  const [places, setPlaces] = useState([]);
  useEffect(() => { api.get("/api/community/places").then(setPlaces).catch(() => {}); }, []);
  const cities = (places.find((p) => p.country === f.country) || {}).cities || [];
  return (
    <div className="grid grid-2">
      <div className="field">
        <label htmlFor={`${prefix}-country`}>{t("acc.country")}</label>
        <select id={`${prefix}-country`} className="select" value={f.country} onChange={(e) => setF({ ...f, country: e.target.value, city: "" })}>
          <option value="">{t("acc.no_country")}</option>
          {ordered().map((c) => <option key={c} value={c}>{countryName(c, lang)}</option>)}
        </select>
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-city`}>{t("acc.city")}</label>
        <input id={`${prefix}-city`} className="input" list={`${prefix}-cities`} maxLength={64} disabled={!f.country}
          value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })} />
        <datalist id={`${prefix}-cities`}>{cities.map((c) => <option key={c} value={c} />)}</datalist>
      </div>
    </div>
  );
}

const ROLE_KEY = "sabeeli.signin_as";      // how this device signed in last time: "user" or "daai"
function lastRole() { try { return localStorage.getItem(ROLE_KEY) === "daai" ? "daai" : "user"; } catch { return "user"; } }
function rememberRole(role) { try { localStorage.setItem(ROLE_KEY, role); } catch { /* private mode */ } }

const DAAI_ERRORS = { 401: "acc.err.daai_bad", 403: "acc.err.daai_disabled", 429: "acc.err.daai_too_many" };

/**
 * The one sign-in card for seekers and da'is: a switch at the top says who is signing in, and the same username and
 * password go to the matching sign-in. Only seekers can sign up here; da'i accounts are added by the reviewer.
 * role ("user" | "daai") preselects the switch, else the way this device signed in last time.
 * onDaaiSignIn(me) runs after a da'i signs in; without it the card opens the da'i console.
 */
export function SignInCard({ role: preset, onDaaiSignIn }) {
  const { t, lang, setLang } = useI18n();
  const { account } = useAccount();
  const { path } = useHashPath();
  const [role, setRole] = useState(() => preset || lastRole());
  const [mode, setMode] = useState("signin");          // signin | signup (seekers only)
  // The interface language by default; sex and age band are left for the seeker to pick (no default, no "prefer not to say").
  const [f, setF] = useState({ username: "", password: "", email: "", lang, country: "", city: "", age_band: "", gender: "" });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const daai = role === "daai" || Boolean(account);     // a seeker who is already signed in only needs the da'i sign-in
  const signup = !daai && mode === "signup";
  const pick = (r) => { setRole(r); setMode("signin"); };
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (daai) {
        const r = await api.post("/api/daai/login", { username: f.username, password: f.password }, { as: "none" });
        setDaaiToken(r.token);
        rememberRole("daai");
        if (onDaaiSignIn) onDaaiSignIn(r.me); else navigate("/daai");
        return;
      }
      const r = signup
        ? await api.post("/api/account/signup", {
          username: f.username, password: f.password, email: f.email, lang: f.lang,
          country: f.country, city: f.city, age_band: f.age_band, gender: f.gender,
        })
        : await api.post("/api/account/signin", { username: f.username, password: f.password });
      if (r.account.lang) setLang(r.account.lang);       // the account's language follows the seeker to this device
      setAccount(r.account);
      rememberRole("user");
      toast(t("acc.welcome", { u: r.account.username }), "success");
      if (!path.startsWith("/account")) navigate("/account");
    } catch (err) {
      toast(daai ? (DAAI_ERRORS[err.status] ? t(DAAI_ERRORS[err.status]) : errorText(err, t)) : accError(err, t), "error");
    } finally {
      setBusy(false);
    }
  };
  // A plain login card: title, who is signing in, the fields, one full-width button, and a link to sign up (seekers only).
  // Password reset needs email (SMTP), which isn't set up, so there is no "forgot password" link.
  return (
    <section className={`card auth-card${signup ? " is-signup" : ""}`} aria-labelledby="auth-title">
      <div className="auth-head">
        <span className="auth-icon" aria-hidden="true"><Icon name={signup ? "users" : "lock"} size={22} /></span>
        <h1 id="auth-title">{t(signup ? "acc.signup_title" : "acc.signin_title")}</h1>
        {signup && <p className="muted">{t("acc.signup_lead")}</p>}
      </div>
      {!signup && !account && (
        <div className="tabs tabs-fit auth-role" role="radiogroup" aria-label={t("acc.role_label")}>
          {[["user", "acc.role_user"], ["daai", "acc.role_daai"]].map(([r, k]) => (
            <button key={r} type="button" role="radio" aria-checked={role === r} aria-selected={role === r} onClick={() => pick(r)}>{t(k)}</button>
          ))}
        </div>
      )}
      {!signup && <p className="auth-lead muted">{t(daai ? "acc.daai_lead" : "acc.signin_lead")}</p>}
      <form className="stack" onSubmit={submit}>
        <Field id="acc-user" label={t("acc.username")} hint={signup ? t("acc.username_hint") : null}
          autoComplete="username" required minLength={daai ? 1 : 3} maxLength={daai ? 64 : 24} value={f.username} onChange={set("username")} />
        {signup && (
          <Field id="acc-email" type="email" dir="ltr" label={t("acc.email_optional")} hint={t("acc.email_hint")}
            autoComplete="email" maxLength={254} value={f.email} onChange={set("email")} />
        )}
        <Field id="acc-pass" type="password" label={t("acc.password")} hint={signup ? t("acc.password_hint") : null}
          autoComplete={signup ? "new-password" : "current-password"} required minLength={signup ? 8 : 1}
          value={f.password} onChange={set("password")} />
        {signup && (
          <fieldset className="stack about-fields">
            <legend>{t("acc.about")}</legend>
            <p className="small muted">{t("acc.about_lead")}</p>
            <AboutFields f={f} set={set} prefix="su" />
            <PlaceFields f={f} setF={setF} prefix="su" />
          </fieldset>
        )}
        {signup && <p className="small muted">{t("acc.keep_note")}</p>}
        <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
          {t(signup ? "acc.do_signup" : "acc.do_signin")}
        </button>
      </form>
      {daai ? (
        <div className="auth-switch auth-note">
          <p>{t("acc.daai_note")}</p>
          <p className="faint small">{t("acc.daai_demo")}</p>
        </div>
      ) : (
        <p className="auth-switch">
          {t(signup ? "acc.have_account" : "acc.no_account")}{" "}
          <button type="button" className="link-btn" onClick={() => setMode(signup ? "signin" : "signup")}>
            {t(signup ? "acc.signin_title" : "acc.create_account")}
          </button>
        </p>
      )}
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

function PlaceCard({ account }) {
  const { t } = useI18n();
  const [f, setF] = useState({ country: account.country || "", city: account.city || "" });
  const save = async (e) => {
    e.preventDefault();
    try { setAccount((await api.post("/api/account/profile", f)).account); toast(t("acc.saved"), "success"); }
    catch (err) { toast(accError(err, t), "error"); }
  };
  return (
    <form className="card stack" onSubmit={save}>
      <h3>{t("acc.place")}</h3>
      <p className="small muted">{t("acc.place_lead")}</p>
      <PlaceFields f={f} setF={setF} prefix="acc" />
      <div className="row"><button type="submit" className="btn btn-primary"><Icon name="check" />{t("acc.save")}</button></div>
    </form>
  );
}

function AboutCard({ account }) {
  const { t, setLang } = useI18n();
  const saved = { lang: account.lang || "ar", gender: account.gender || "", age_band: account.age_band || "" };
  const [f, setF] = useState(saved);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async (e) => {
    e.preventDefault();
    try {
      const r = await api.post("/api/account/profile", f);
      setLang(r.account.lang);
      setAccount(r.account);
      toast(t("acc.saved"), "success");
    } catch (err) { toast(accError(err, t), "error"); }
  };
  return (
    <form className="card stack" onSubmit={save}>
      <h3>{t("acc.about")}</h3>
      <p className="small muted">{t("acc.about_lead")}</p>
      <AboutFields f={f} set={set} prefix="ab" />
      {f.age_band === "u18" && <p className="small muted">{t("acc.age_minor")}</p>}
      <div className="row">
        <button type="submit" className="btn btn-primary" disabled={JSON.stringify(f) === JSON.stringify(saved) || !f.gender || !f.age_band}>
          <Icon name="check" />{t("acc.save")}
        </button>
      </div>
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
  useEffect(() => { api.get("/api/conversations").then((r) => setCount(r.conversations.length)).catch(() => setCount(0)); }, []);
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
    try { sessionStorage.removeItem("sabeeli.chat"); } catch { /* ignore */ }   // the saved chat stays in the account
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
        <button type="button" className="btn btn-danger-soft" onClick={signout}><Icon name="logout" />{t("acc.signout")}</button>
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

export default function AccountPage({ query = {} }) {
  const { t, fmtDate } = useI18n();
  const { account, loaded } = useAccount();
  if (!loaded) return null;
  if (!account) {
    const role = ["user", "daai"].includes(query.as) ? query.as : undefined;   // #/account?as=daai opens on "da'i"
    return (
      <div className="auth-page"><SignInCard role={role} /></div>
    );
  }
  return (
    <>
      <div className="page-head account-head">
        <span className="account-avatar" aria-hidden="true">{account.username.charAt(0).toUpperCase()}</span>
        <div><h1>{t("acc.welcome", { u: account.username })}</h1><p>{t("acc.since", { d: fmtDate(account.created_at, { month: "long", year: "numeric" }) })}</p></div>
      </div>
      <div className="stack">
        {needsAbout(account) && (
          <section className="card stack complete-about">
            <h3><Icon name="users" />{t("acc.complete_title")}</h3>
            <CompleteAbout account={account} />
          </section>
        )}
        <NewMuslimPrompt manage />
        <Activity />
        <SavedChats />
        {!needsAbout(account) && <AboutCard account={account} />}
        <PlaceCard account={account} />
        <EmailCard account={account} />
        <Security />
      </div>
    </>
  );
}
