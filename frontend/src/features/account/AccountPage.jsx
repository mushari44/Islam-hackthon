// Account page: the sign-in card (seekers and da'is), sign up, and "my account". Owner: Eman.
// Accounts are optional: a username, a password, the seeker's sex and age band, and an optional email and place
// (see features/auth on the backend).
import "./strings.js";
import "./account.css";
import { useEffect, useRef, useState } from "react";
import { api } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { navigate, useHashPath } from "../../core/router.jsx";
import { Icon, Spinner, errorText, toast } from "../../core/ui.jsx";
import { COUNTRIES, NewMuslimPrompt, countryName } from "../community/public.js";
import { AboutFields, CompleteAbout, PasswordInput, RecoveryCode, USERNAME_PROPS, accError, needsAbout, useFormError } from "./fields.jsx";
import { setAccount, setDaaiToken, signOutSeeker, useAccount } from "./store.js";

/** A labelled input; type="password" gets the show/hide button. */
function Field({ id, label, hint, type, ...props }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {type === "password" ? <PasswordInput id={id} {...props} /> : <input id={id} className="input" type={type} {...props} />}
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

// The card used to open on the role this device signed in with last time, so on a shared device the next seeker
// could land on the da'i sign-in. It now opens as "user" unless the page asks for "da'i"; drop the old setting.
try { localStorage.removeItem("sabeeli.signin_as"); } catch { /* private mode */ }

const DAAI_ERRORS = { 401: "acc.err.daai_bad", 403: "acc.err.daai_disabled", 429: "acc.err.daai_too_many" };

/**
 * The one sign-in card for seekers and da'is: a switch at the top says who is signing in, and the same username and
 * password go to the matching sign-in. Only seekers can sign up here; da'i accounts are added by the reviewer.
 * role ("user" | "daai") preselects the switch (the da'i console and #/account?as=daai pass "daai"), else "user".
 * onDaaiSignIn(me) runs after a da'i signs in; without it the card opens the da'i console.
 * next: where a seeker goes after signing in (the page that sent them here), else their account.
 */
export function SignInCard({ role: preset, onDaaiSignIn, next }) {
  const { t, lang, setLang } = useI18n();
  const { account } = useAccount();
  const { path } = useHashPath();
  const [role, setRole] = useState(() => preset || "user");
  const [mode, setMode] = useState("signin");          // signin | signup | forgot (seekers only)
  // The interface language by default; sex and age band are left for the seeker to pick (no default, no "prefer not to say").
  const [f, setF] = useState({ username: "", password: "", email: "", lang, country: "", city: "", age_band: "", gender: "" });
  const [busy, setBusy] = useState(false);
  const [errorBox, setError, clearOnEdit] = useFormError();
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const daai = role === "daai" || Boolean(account);     // a seeker who is already signed in only needs the da'i sign-in
  const signup = !daai && mode === "signup";
  const switchMode = (m) => { setMode(m); setError(""); };
  const pick = (r) => { setRole(r); switchMode("signin"); };
  const done = (acc) => {
    if (acc.lang) setLang(acc.lang);                   // the account's language follows the seeker to this device
    setAccount(acc);
    toast(t("acc.welcome", { u: acc.username }), "success");
    if (next) navigate(next); else if (!path.startsWith("/account")) navigate("/account");
  };
  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (daai) {
        const r = await api.post("/api/daai/login", { username: f.username, password: f.password }, { as: "none" });
        setDaaiToken(r.token);
        if (onDaaiSignIn) onDaaiSignIn(r.me); else navigate("/daai");
        return;
      }
      const r = signup
        ? await api.post("/api/account/signup", {
          username: f.username, password: f.password, email: f.email, lang: f.lang,
          country: f.country, city: f.city, age_band: f.age_band, gender: f.gender,
        })
        : await api.post("/api/account/signin", { username: f.username, password: f.password });
      done(r.account);
    } catch (err) {
      setError(daai ? (DAAI_ERRORS[err.status] ? t(DAAI_ERRORS[err.status]) : errorText(err, t)) : accError(err, t));
    } finally {
      setBusy(false);
    }
  };
  if (!daai && mode === "forgot") {
    return <ForgotPassword login={f.username} onDone={done} onBack={() => switchMode("signin")} />;
  }
  // A plain login card: title, who is signing in, the fields, one full-width button, a "forgot password?" link
  // (seekers only) and a link to sign up.
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
            <button key={r} type="button" role="radio" aria-checked={role === r} onClick={() => pick(r)}>{t(k)}</button>
          ))}
        </div>
      )}
      {!signup && <p className="auth-lead muted">{t(daai ? "acc.daai_lead" : "acc.signin_lead")}</p>}
      {!signup && <SampleAccounts daai={daai} onPick={(u) => { setF({ ...f, username: u, password: SAMPLE_PASSWORD }); setError(""); }}
        onSignup={() => switchMode("signup")} />}
      <form className="stack" onSubmit={submit} onChange={clearOnEdit}>
        <Field id="acc-user" label={t("acc.username")} hint={signup ? t("acc.username_hint") : null} {...USERNAME_PROPS}
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
        {errorBox}
        <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
          {busy ? t(signup ? "acc.signing_up" : "acc.signing_in") : t(signup ? "acc.do_signup" : "acc.do_signin")}
        </button>
        {!daai && !signup && (
          <button type="button" className="link-btn auth-forgot" onClick={() => switchMode("forgot")}>{t("acc.forgot")}</button>
        )}
      </form>
      {daai ? (
        <div className="auth-switch auth-note">
          <p>{t("acc.daai_note")}</p>
        </div>
      ) : (
        <p className="auth-switch">
          {t(signup ? "acc.have_account" : "acc.no_account")}{" "}
          <button type="button" className="link-btn" onClick={() => switchMode(signup ? "signin" : "signup")}>
            {t(signup ? "acc.signin_title" : "acc.create_account")}
          </button>
        </p>
      )}
    </section>
  );
}

// The synthetic sample da'is (auth/seed.py) and their shared password, shown on the sign-in card so judges and visitors
// can try the da'i side (mushari, 6 October 2026). Seekers have no sample accounts: they create their own.
const SAMPLE_DAAIS = [["reviewer", "acc.sample_reviewer"], ["khalid"], ["maryam"], ["yusuf"]];
const SAMPLE_PASSWORD = "123";

function SampleAccounts({ daai, onPick, onSignup }) {
  const { t } = useI18n();
  if (!daai) {
    return (
      <div className="auth-sample">
        <p>{t("acc.sample_user")}{" "}
          <button type="button" className="link-btn" onClick={onSignup}>{t("acc.create_account")}</button></p>
      </div>
    );
  }
  return (
    <div className="auth-sample">
      <p><strong>{t("acc.sample_title")}</strong> {t("acc.sample_daai", { p: SAMPLE_PASSWORD })}</p>
      <div className="auth-sample-list">
        {SAMPLE_DAAIS.map(([u, k]) => (
          <button key={u} type="button" className="chip" dir="ltr" onClick={() => onPick(u)}>
            {u}{k ? ` (${t(k)})` : ""}
          </button>
        ))}
      </div>
    </div>
  );
}

/**
 * "Forgot password?" from the sign-in card. The seeker gives their username (or email): when email is set up and the
 * account has one, a 6-digit code is emailed; otherwise, or by choice, a recovery code made under Security resets it.
 * We keep nothing else that proves who owns an account, so without either the password can't be reset.
 * There is still no screen after sign-up (removed on 3 Oct); a recovery code is made from the account page instead.
 */
function ForgotPassword({ login, onDone, onBack }) {
  const { t } = useI18n();
  const [step, setStep] = useState("ask");          // ask | email | recovery | code (the new recovery code, shown once)
  const [emailOff, setEmailOff] = useState(false);   // the server said email isn't set up
  const [f, setF] = useState({ login: login || "", code: "", new_password: "" });
  const [fresh, setFresh] = useState("");
  const [busy, setBusy] = useState(false);
  const [errorBox, setError, clearOnEdit] = useFormError();
  // A recovery-code reset signs this browser in at once, but the page only switches to the account on "Continue",
  // so the new code stays on screen until the seeker has kept it (or leaves the page).
  const pending = useRef(null);
  useEffect(() => () => { if (pending.current) setAccount(pending.current); }, []);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const go = (s) => {
    setStep(s);
    setError("");
    // A recovery code goes with the username: an email typed in the first step can't be used there.
    setF((x) => ({ ...x, code: "", new_password: "", login: s === "recovery" && x.login.includes("@") ? "" : x.login }));
  };
  const run = (fn) => async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try { await fn(); } catch (err) { setError(accError(err, t)); } finally { setBusy(false); }
  };
  const ask = run(async () => {
    const r = await api.post("/api/account/forgot", { login: f.login }, { as: "none" });
    setEmailOff(r.via !== "email");
    go(r.via === "email" ? "email" : "recovery");
  });
  const byEmail = run(async () => {
    onDone((await api.post("/api/account/reset", { login: f.login, code: f.code, new_password: f.new_password })).account);
  });
  const byCode = run(async () => {
    const r = await api.post("/api/account/recover", { username: f.login, recovery_code: f.code, new_password: f.new_password });
    pending.current = r.account;
    setFresh(r.recovery_code);
    setStep("code");
  });
  const finish = () => { const acc = pending.current; pending.current = null; onDone(acc); };
  const newPassword = (
    <Field id="fp-new" type="password" label={t("acc.new_password")} hint={t("acc.password_hint")} autoComplete="new-password"
      required minLength={8} maxLength={200} value={f.new_password} onChange={set("new_password")} />
  );
  const submitBtn = (label) => (
    <button type="submit" className="btn btn-primary btn-block" disabled={busy}>{busy ? t("acc.working") : t(label)}</button>
  );
  return (
    <section className="card auth-card" aria-labelledby="fp-title">
      <div className="auth-head">
        <span className="auth-icon" aria-hidden="true"><Icon name="lock" size={22} /></span>
        <h1 id="fp-title">{t("acc.fp_title")}</h1>
      </div>
      {step === "ask" && (
        <form className="stack" onSubmit={ask} onChange={clearOnEdit}>
          <p className="small muted">{t("acc.fp_lead")}</p>
          <Field id="fp-login" label={t("acc.fp_login")} {...USERNAME_PROPS} autoComplete="username" required maxLength={254}
            value={f.login} onChange={set("login")} />
          {errorBox}
          {submitBtn("acc.fp_continue")}
          <button type="button" className="link-btn auth-forgot" onClick={() => go("recovery")}>{t("acc.fp_have_code")}</button>
        </form>
      )}
      {step === "email" && (
        <form className="stack" onSubmit={byEmail} onChange={clearOnEdit}>
          <p className="small muted">{t("acc.fp_email_sent")}</p>
          <Field id="fp-code" label={t("acc.fp_email_code")} dir="ltr" inputMode="numeric" autoComplete="one-time-code" required
            maxLength={12} value={f.code} onChange={set("code")} />
          {newPassword}
          {errorBox}
          {submitBtn("acc.fp_reset")}
          <button type="button" className="link-btn auth-forgot" onClick={() => go("recovery")}>{t("acc.fp_use_code")}</button>
        </form>
      )}
      {step === "recovery" && (
        <form className="stack" onSubmit={byCode} onChange={clearOnEdit}>
          {emailOff && <p className="small muted">{t("acc.fp_email_off")}</p>}
          <p className="small muted">{t("acc.fp_code_lead")}</p>
          <Field id="fp-user" label={t("acc.username")} {...USERNAME_PROPS} autoComplete="username" required maxLength={24}
            value={f.login} onChange={set("login")} />
          <Field id="fp-code" label={t("acc.fp_recovery_code")} dir="ltr" autoCapitalize="characters" autoCorrect="off" spellCheck={false}
            autoComplete="off" required maxLength={32} value={f.code} onChange={set("code")} />
          {newPassword}
          {errorBox}
          {submitBtn("acc.fp_reset")}
          <p className="small muted">{t("acc.fp_none")}</p>
        </form>
      )}
      {step === "code" && (
        <div className="stack">
          <p>{t("acc.fp_done")}</p>
          <RecoveryCode code={fresh} />
          <button type="button" className="btn btn-primary btn-block" onClick={finish}>{t("acc.fp_continue")}</button>
        </div>
      )}
      {step !== "code" && (
        <p className="auth-switch"><button type="button" className="link-btn" onClick={onBack}>{t("acc.fp_back")}</button></p>
      )}
    </section>
  );
}

// Every form below disables its button while it saves, so a double click can't send it twice.
function EmailCard({ account }) {
  const { t } = useI18n();
  const [email, setEmail] = useState(account.email || "");
  const [busy, setBusy] = useState(false);
  const [errorBox, setError, clearOnEdit] = useFormError();
  const save = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try { setAccount((await api.post("/api/account/profile", { email })).account); toast(t("acc.saved"), "success"); }
    catch (err) { setError(accError(err, t)); }
    finally { setBusy(false); }
  };
  return (
    <form className="card stack" onSubmit={save} onChange={clearOnEdit}>
      <h3>{t("acc.email_title")}</h3>
      <p className="small muted">{t("acc.email_hint")}</p>
      <div className="row email-row">
        <input id="acc-email-edit" className="input" type="email" dir="ltr" aria-label={t("acc.email_title")} autoComplete="email"
          maxLength={254} value={email} onChange={(e) => setEmail(e.target.value)} />
        <button type="submit" className="btn btn-primary" disabled={busy || email === (account.email || "")}><Icon name="check" />{t("acc.save")}</button>
      </div>
      {errorBox}
    </form>
  );
}

function PlaceCard({ account }) {
  const { t } = useI18n();
  const [f, setF] = useState({ country: account.country || "", city: account.city || "" });
  const [busy, setBusy] = useState(false);
  const [errorBox, setError, clearOnEdit] = useFormError();
  const unchanged = f.country === (account.country || "") && f.city === (account.city || "");
  const save = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try { setAccount((await api.post("/api/account/profile", f)).account); toast(t("acc.saved"), "success"); }
    catch (err) { setError(accError(err, t)); }
    finally { setBusy(false); }
  };
  return (
    <form className="card stack" onSubmit={save} onChange={clearOnEdit}>
      <h3>{t("acc.place")}</h3>
      <p className="small muted">{t("acc.place_lead")}</p>
      <PlaceFields f={f} setF={setF} prefix="acc" />
      {errorBox}
      <div className="row"><button type="submit" className="btn btn-primary" disabled={busy || unchanged}><Icon name="check" />{t("acc.save")}</button></div>
    </form>
  );
}

function AboutCard({ account }) {
  const { t, setLang } = useI18n();
  const saved = { lang: account.lang || "ar", gender: account.gender || "", age_band: account.age_band || "" };
  const [f, setF] = useState(saved);
  const [busy, setBusy] = useState(false);
  const [errorBox, setError, clearOnEdit] = useFormError();
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const r = await api.post("/api/account/profile", f);
      setLang(r.account.lang);
      setAccount(r.account);
      toast(t("acc.saved"), "success");
    } catch (err) { setError(accError(err, t)); }
    finally { setBusy(false); }
  };
  return (
    <form className="card stack" onSubmit={save} onChange={clearOnEdit}>
      <h3>{t("acc.about")}</h3>
      <p className="small muted">{t("acc.about_lead")}</p>
      <AboutFields f={f} set={set} prefix="ab" />
      {f.age_band === "u18" && <p className="small muted">{t("acc.age_minor")}</p>}
      {errorBox}
      <div className="row">
        <button type="submit" className="btn btn-primary" disabled={busy || JSON.stringify(f) === JSON.stringify(saved) || !f.gender || !f.age_band}>
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
                <li key={m.id}><Icon name="calendar" size={16} /><a href="#/community?tab=mine">{m.title}</a>
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
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.get("/api/conversations").then((r) => setCount(r.conversations.length)).catch(() => setCount(0)); }, []);
  const clear = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await api.del("/api/ask/history");
      try { sessionStorage.removeItem("sabeeli.chat"); } catch { /* ignore */ }
      setCount(0); setSure(false); toast(t("acc.chats_deleted"), "success");
    } catch (err) { toast(accError(err, t), "error"); }
    finally { setBusy(false); }
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
              <button type="button" className="btn btn-sm btn-danger" disabled={busy} onClick={clear}>
                <Icon name="trash" />{busy ? t("acc.deleting") : t("acc.chats_confirm")}
              </button>
              <button type="button" className="btn btn-sm btn-ghost" disabled={busy} onClick={() => setSure(false)}>{t("common.cancel")}</button>
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
  const [rc, setRc] = useState(null);      // the password typed to make a recovery code (null: form closed)
  const [code, setCode] = useState("");    // the new recovery code, shown once
  const [del, setDel] = useState(null);
  const [busy, setBusy] = useState("");   // "password" | "code" | "signout" | "delete" while that request runs
  const [pwError, setPwError, clearPwError] = useFormError();
  const [rcError, setRcError, clearRcError] = useFormError();
  const [delError, setDelError, clearDelError] = useFormError();
  const change = async (e) => {
    e.preventDefault();
    setPwError("");
    setBusy("password");
    try { await api.post("/api/account/password", pw); setPw({ password: "", new_password: "" }); toast(t("acc.password_changed"), "success"); }
    catch (err) { setPwError(accError(err, t)); }
    finally { setBusy(""); }
  };
  // A new code replaces the stored one, so a code written down earlier stops working.
  const makeCode = async (e) => {
    e.preventDefault();
    setRcError("");
    setBusy("code");
    try { setCode((await api.post("/api/account/recovery-code", { password: rc })).recovery_code); setRc(null); }
    catch (err) { setRcError(accError(err, t)); }
    finally { setBusy(""); }
  };
  const signout = async () => {
    if (busy) return;
    setBusy("signout");
    await signOutSeeker();
    toast(t("acc.signed_out"));
  };
  const remove = async (e) => {
    e.preventDefault();
    setDelError("");
    setBusy("delete");
    try { await api.post("/api/account/delete", { password: del }); setAccount(null); toast(t("acc.deleted")); }
    catch (err) { setDelError(accError(err, t)); setBusy(""); }
  };
  return (
    <section className="card stack">
      <h3>{t("acc.security")}</h3>
      <form className="grid grid-2" onSubmit={change} onChange={clearPwError}>
        <Field id="acc-cur" type="password" label={t("acc.current_password")} autoComplete="current-password" required
          value={pw.password} onChange={(e) => setPw({ ...pw, password: e.target.value })} />
        <Field id="acc-new" type="password" label={t("acc.new_password")} hint={t("acc.password_hint")} autoComplete="new-password"
          required minLength={8} value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} />
        {pwError}
        <div className="row">
          <button type="submit" className="btn" disabled={busy === "password"}>
            <Icon name="lock" />{busy === "password" ? t("acc.changing_password") : t("acc.change_password")}
          </button>
        </div>
      </form>
      <div className="stack account-recovery">
        <strong>{t("acc.rc_title")}</strong>
        <p className="small muted">{t("acc.rc_lead")}</p>
        {code && <RecoveryCode code={code} />}
        {!code && rc === null && (
          <div className="row"><button type="button" className="btn" onClick={() => setRc("")}><Icon name="shield" />{t("acc.rc_create")}</button></div>
        )}
        {rc !== null && (
          <form className="stack" onSubmit={makeCode} onChange={clearRcError}>
            <Field id="acc-rc" type="password" label={t("acc.current_password")} autoComplete="current-password" required
              value={rc} onChange={(e) => setRc(e.target.value)} />
            {rcError}
            <div className="row">
              <button type="submit" className="btn btn-primary" disabled={busy === "code"}>
                <Icon name="shield" />{busy === "code" ? t("acc.working") : t("acc.rc_create")}
              </button>
              <button type="button" className="btn btn-ghost" onClick={() => setRc(null)}>{t("common.cancel")}</button>
            </div>
          </form>
        )}
      </div>
      <div className="row spread account-actions">
        <button type="button" className="btn btn-danger-soft" disabled={busy === "signout"} onClick={signout}>
          <Icon name="logout" />{busy === "signout" ? t("acc.signing_out") : t("acc.signout")}
        </button>
        {del === null && <button type="button" className="btn btn-ghost danger-text" onClick={() => setDel("")}><Icon name="trash" />{t("acc.delete")}</button>}
      </div>
      {del !== null && (
        <form className="stack danger-zone" onSubmit={remove} onChange={clearDelError}>
          <p className="small">{t("acc.delete_lead")}</p>
          <Field id="acc-del" type="password" label={t("acc.delete_confirm")} autoComplete="current-password" required
            value={del} onChange={(e) => setDel(e.target.value)} />
          {delError}
          <div className="row">
            <button type="submit" className="btn btn-danger" disabled={busy === "delete"}>
              <Icon name="trash" />{busy === "delete" ? t("acc.deleting") : t("acc.do_delete")}
            </button>
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
  // While the account loads: the page's heading (for screen readers) and a spinner, rather than a blank page.
  if (!loaded) return <div className="section" aria-busy="true"><h1 className="sr-only">{t("acc.mine")}</h1><Spinner /></div>;
  if (!account) {
    const role = ["user", "daai"].includes(query.as) ? query.as : undefined;   // #/account?as=daai opens on "da'i"
    // #/account?next=/ask brings the seeker back to that page once signed in (only paths inside this site).
    const next = /^\/(?![/\\])/.test(query.next || "") ? query.next : undefined;
    return (
      <div className="auth-page"><SignInCard role={role} next={next} /></div>
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
