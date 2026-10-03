// Da'i console, "Da'i accounts" tab (reviewer only): add da'is, edit their place, disable them, reset passwords. Owner: Eman.
// Before this tab, da'i accounts came only from features/auth/seed.py.
import "./daai.css";
import { useEffect, useState } from "react";
import { api } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { Icon, errorText, toast } from "../../core/ui.jsx";
import { countryName } from "../community/public.js";
import { LANGUAGES, PlaceFields } from "./ProfileTab.jsx";

const EMPTY = { username: "", password: "", name: "", name_en: "", languages: ["ar"], gender: "m", country: "", city: "" };

function adminError(err, t) {
  if (err && err.status === 422) return t("da.invalid");
  const key = err && typeof err.detail === "string" ? `da.err.${err.detail}` : "";
  return key && t(key) !== key ? t(key) : errorText(err, t);
}

function AddForm({ onAdded }) {
  const { t, langName } = useI18n();
  const [f, setF] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const toggleLang = (l) => {
    const next = f.languages.includes(l) ? f.languages.filter((x) => x !== l) : [...f.languages, l];
    if (next.length) setF({ ...f, languages: next });
  };
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const made = await api.dPost("/api/daai/admin/daais", f);
      onAdded(made);
      setF(EMPTY);
      toast(t("da.added", { u: made.username }), "success");
    } catch (err) {
      toast(adminError(err, t), "error");
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="card stack" onSubmit={submit}>
      <h3>{t("da.add")}</h3>
      <div className="grid grid-2">
        <div className="field">
          <label htmlFor="na-user">{t("dai.user")}</label>
          <input id="na-user" className="input" dir="ltr" autoComplete="off" required minLength={3} maxLength={32} value={f.username} onChange={set("username")} />
          <span className="faint">{t("da.user_hint")}</span>
        </div>
        <div className="field">
          <label htmlFor="na-pass">{t("da.first_password")}</label>
          <input id="na-pass" className="input" type="password" autoComplete="new-password" required minLength={8} value={f.password} onChange={set("password")} />
          <span className="faint">{t("da.pass_hint")}</span>
        </div>
        <div className="field">
          <label htmlFor="na-name">{t("dp.name")}</label>
          <input id="na-name" className="input" required minLength={2} maxLength={120} value={f.name} onChange={set("name")} />
        </div>
        <div className="field">
          <label htmlFor="na-name-en">{t("dp.name_en")}</label>
          <input id="na-name-en" className="input" dir="ltr" maxLength={120} value={f.name_en} onChange={set("name_en")} />
        </div>
      </div>
      <div className="field">
        <span className="field-label">{t("da.langs")}</span>
        <div className="row" role="group" aria-label={t("da.langs")}>
          {LANGUAGES.map((l) => (
            <button key={l} type="button" className="chip" aria-pressed={f.languages.includes(l)} onClick={() => toggleLang(l)}>
              {f.languages.includes(l) && <Icon name="check" size={16} />}{langName(l)}
            </button>
          ))}
        </div>
      </div>
      <PlaceFields f={f} setF={setF} idPrefix="na" genderLabel="da.gender" />
      <div className="row"><button type="submit" className="btn btn-primary" disabled={busy}><Icon name="check" />{t("da.do_add")}</button></div>
    </form>
  );
}

function Row({ d, me, onChange }) {
  const { t, lang, langName } = useI18n();
  const [pw, setPw] = useState(null);
  const save = async (body, msg) => {
    try { onChange(await api.dPost(`/api/daai/admin/daais/${d.id}`, body)); toast(t(msg), "success"); return true; }
    catch (err) { toast(adminError(err, t), "error"); return false; }
  };
  const reset = async (e) => {
    e.preventDefault();
    if (await save({ password: pw }, "da.reset_done")) setPw(null);
  };
  const place = [d.city, countryName(d.country, lang)].filter(Boolean).join(lang === "ar" ? "، " : ", ");
  return (
    <li className="admin-row">
      <div className="stack admin-who">
        <strong>{lang === "ar" ? d.name : d.name_en || d.name}</strong>
        <span className="faint small" dir="ltr">@{d.username}</span>
        <div className="row profile-langs">
          {d.role === "admin" && <span className="badge badge-purple">{t("da.reviewer")}</span>}
          {!d.active && <span className="badge badge-warn">{t("da.disabled")}</span>}
          {(d.languages || []).map((l) => <span key={l} className="badge">{langName(l)}</span>)}
          {place && <span className="faint small">{place}</span>}
        </div>
      </div>
      <div className="row">
        {d.id !== me.id && (
          <button type="button" className="btn btn-sm" onClick={() => save({ active: !d.active }, d.active ? "da.disabled_done" : "da.enabled_done")}>
            <Icon name={d.active ? "x" : "check"} />{t(d.active ? "da.disable" : "da.enable")}
          </button>
        )}
        {pw === null && <button type="button" className="btn btn-sm btn-ghost" onClick={() => setPw("")}><Icon name="lock" />{t("da.reset")}</button>}
      </div>
      {pw !== null && (
        <form className="row admin-reset" onSubmit={reset}>
          <input className="input" type="password" autoComplete="new-password" aria-label={t("da.new_password")} placeholder={t("da.new_password")}
            required minLength={8} value={pw} onChange={(e) => setPw(e.target.value)} />
          <button type="submit" className="btn btn-sm btn-primary"><Icon name="check" />{t("dp.save")}</button>
          <button type="button" className="btn btn-sm btn-ghost" onClick={() => setPw(null)}>{t("common.cancel")}</button>
        </form>
      )}
    </li>
  );
}

function AdminTab({ me }) {
  const { t } = useI18n();
  const [list, setList] = useState(null);
  useEffect(() => { api.dGet("/api/daai/admin/daais").then(setList).catch((err) => { toast(errorText(err, t), "error"); setList([]); }); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const replace = (d) => setList((xs) => xs.map((x) => (x.id === d.id ? d : x)));
  return (
    <div className="stack">
      <AddForm onAdded={(d) => setList((xs) => [...(xs || []), d])} />
      <section className="card stack">
        <h3>{t("da.list")}</h3>
        <p className="small muted">{t("da.list_lead")}</p>
        {list && <ul className="admin-list">{list.map((d) => <Row key={d.id} d={d} me={me} onChange={replace} />)}</ul>}
      </section>
    </div>
  );
}

export const adminTab = { key: "accounts", labelKey: "da.tab", component: AdminTab, adminOnly: true };
