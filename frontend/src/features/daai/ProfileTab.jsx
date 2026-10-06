// Da'i console, "My profile" tab: a da'i keeps their name, languages, gender, place and bio current. Owner: Eman.
// Seekers are matched with a da'i by language and gender, so these fields decide who can reach this da'i.
import "./daai.css";
import { useState } from "react";
import { api } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { Icon, errorText, toast } from "../../core/ui.jsx";
import { COUNTRIES, countryName } from "../community/public.js";
import { PasswordInput, setDaaiToken, useFormError } from "../account/public.js";

// Languages a da'i can offer for now. Keep in step with DAAI_LANGUAGES in features/auth/routes.py.
export const LANGUAGES = ["ar", "en"];
export const ORDERED_COUNTRIES = ["SA", ...COUNTRIES.filter((c) => c !== "SA")];

function fromProfile(me) {
  return { name: me.name || "", name_en: me.name_en || "", languages: me.languages || [], bio: me.bio || "", bio_en: me.bio_en || "",
    gender: me.gender || "m", country: me.country || "", city: me.city || "" };
}

/** Gender, country and city fields, shared with the reviewer's "add a da'i" form. */
export function PlaceFields({ f, setF, idPrefix = "p", genderLabel = "dp.gender" }) {
  const { t, lang } = useI18n();
  return (
    <>
      <div className="field">
        <span className="field-label">{t(genderLabel)}</span>
        <div className="tabs tabs-fit" role="radiogroup" aria-label={t(genderLabel)}>
          {[["m", "dp.gender_m"], ["f", "dp.gender_f"]].map(([v, k]) => (
            <button key={v} type="button" role="radio" aria-checked={f.gender === v} onClick={() => setF({ ...f, gender: v })}>{t(k)}</button>
          ))}
        </div>
      </div>
      <div className="grid grid-2">
        <div className="field">
          <label htmlFor={`${idPrefix}-country`}>{t("dp.country")}</label>
          <select id={`${idPrefix}-country`} className="select" value={f.country} onChange={(e) => setF({ ...f, country: e.target.value, city: "" })}>
            <option value="">—</option>
            {ORDERED_COUNTRIES.map((c) => <option key={c} value={c}>{countryName(c, lang)}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor={`${idPrefix}-city`}>{t("dp.city")}</label>
          <input id={`${idPrefix}-city`} className="input" maxLength={64} disabled={!f.country} value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })} />
        </div>
      </div>
    </>
  );
}

export function titledName(me, lang, t) {
  const name = lang === "ar" ? me.name : me.name_en || me.name;
  return t(me.gender === "f" ? "dp.titled_f" : "dp.titled_m", { n: name });
}

function ProfileTab({ me, onMe }) {
  const { t, lang, langName, fmtNum } = useI18n();
  const [f, setF] = useState(() => fromProfile(me));
  const [saving, setSaving] = useState(false);
  const saved = fromProfile(me);
  const dirty = JSON.stringify(f) !== JSON.stringify(saved);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const toggleLang = (l) => {
    const has = f.languages.includes(l);
    if (has && f.languages.length === 1) { toast(t("dp.one_lang"), "error"); return; }
    setF({ ...f, languages: has ? f.languages.filter((x) => x !== l) : [...f.languages, l] });
  };

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const next = await api.dPost("/api/daai/profile", f);
      onMe(next);
      setF(fromProfile(next));
      toast(t("dp.saved"), "success");
    } catch (err) {
      toast(err.status === 422 ? t("dp.invalid") : errorText(err, t), "error");
    } finally {
      setSaving(false);
    }
  };

  const preview = { ...me, ...f, name: f.name || me.name };
  const place = [preview.city, countryName(preview.country, lang)].filter(Boolean).join(lang === "ar" ? "، " : ", ");
  const bio = lang === "ar" ? preview.bio : preview.bio_en || preview.bio;

  return (
    <div className="stack">
      <div className="profile-grid">
        <form className="card stack" onSubmit={submit}>
          <h3>{t("dp.edit")}</h3>
          <div className="grid grid-2">
            <div className="field">
              <label htmlFor="p-name">{t("dp.name")}</label>
              <input id="p-name" className="input" dir="auto" required minLength={2} maxLength={120} value={f.name} onChange={set("name")} />
            </div>
            <div className="field">
              <label htmlFor="p-name-en">{t("dp.name_en")}</label>
              <input id="p-name-en" className="input" dir="ltr" maxLength={120} value={f.name_en} onChange={set("name_en")} />
            </div>
          </div>

          <div className="field">
            <span className="field-label">{t("dp.langs")}</span>
            <div className="row" role="group" aria-label={t("dp.langs")}>
              {LANGUAGES.map((l) => (
                <button key={l} type="button" className="chip" aria-pressed={f.languages.includes(l)} onClick={() => toggleLang(l)}>
                  {f.languages.includes(l) && <Icon name="check" size={16} />}{langName(l)}
                </button>
              ))}
            </div>
            <span className="faint">{t("dp.langs_hint")}</span>
          </div>

          <PlaceFields f={f} setF={setF} />

          <div className="field">
            <label htmlFor="p-bio">{t("dp.bio")}</label>
            <textarea id="p-bio" className="textarea" dir="auto" rows={3} maxLength={600} value={f.bio} onChange={set("bio")} />
            <span className="faint">{t("dp.count", { n: fmtNum(f.bio.length), max: fmtNum(600) })}</span>
          </div>
          <div className="field">
            <label htmlFor="p-bio-en">{t("dp.bio_en")}</label>
            <textarea id="p-bio-en" className="textarea" dir="ltr" rows={3} maxLength={600} value={f.bio_en} onChange={set("bio_en")} />
          </div>

          <div className="row">
            <button type="submit" className="btn btn-primary" disabled={!dirty || saving}>
              <Icon name="check" />{saving ? t("dp.saving") : t("dp.save")}
            </button>
            {dirty && <button type="button" className="btn btn-ghost" onClick={() => setF(saved)}>{t("dp.reset")}</button>}
          </div>
        </form>

        <aside className="card stack profile-preview" aria-label={t("dp.preview")}>
          <p className="faint">{t("dp.preview")}</p>
          <div className="row">
            <span className="profile-avatar" aria-hidden="true">{(preview.name || "?").trim().charAt(0)}</span>
            <div>
              <strong>{titledName(preview, lang, t)}</strong>
              <div className="row profile-langs">{preview.languages.map((l) => <span key={l} className="badge badge-mint">{langName(l)}</span>)}</div>
              {place && <div className="faint small">{place}</div>}
            </div>
          </div>
          {bio ? <p>{bio}</p> : <p className="faint">{t("dp.no_bio")}</p>}
        </aside>
      </div>
      <PasswordCard me={me} onMe={onMe} />
    </div>
  );
}

/**
 * The da'i changes their own password (before, only the reviewer could set one). Every other session of this
 * da'i is signed out and this browser gets a fresh token. The shared sample accounts can't be changed.
 */
function PasswordCard({ me, onMe }) {
  const { t } = useI18n();
  const empty = { password: "", new_password: "" };
  const [f, setF] = useState(empty);
  const [busy, setBusy] = useState(false);
  const [errorBox, setError, clearOnEdit] = useFormError();
  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const r = await api.dPost("/api/daai/password", f);
      setDaaiToken(r.token);
      onMe(r.me);
      setF(empty);
      toast(t("dp.password_changed"), "success");
    } catch (err) {
      const key = typeof err.detail === "string" ? `dp.err.${err.detail}` : "";
      setError(err.status === 422 ? t("dp.password_short") : key && t(key) !== key ? t(key) : errorText(err, t));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="card stack" onSubmit={submit} onChange={clearOnEdit}>
      <h3>{t("dp.security")}</h3>
      {me.is_demo && <p className="small muted">{t("dp.demo_password")}</p>}
      <div className="grid grid-2">
        <div className="field">
          <label htmlFor="dp-cur">{t("dp.current_password")}</label>
          <PasswordInput id="dp-cur" autoComplete="current-password" required maxLength={200} disabled={me.is_demo}
            value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="dp-new">{t("dp.new_password")}</label>
          <PasswordInput id="dp-new" autoComplete="new-password" required minLength={8} maxLength={200} disabled={me.is_demo}
            value={f.new_password} onChange={(e) => setF({ ...f, new_password: e.target.value })} />
          <span className="faint">{t("dp.password_hint")}</span>
        </div>
      </div>
      {errorBox}
      <div className="row">
        <button type="submit" className="btn" disabled={busy || me.is_demo}>
          <Icon name="lock" />{busy ? t("dp.changing_password") : t("dp.change_password")}
        </button>
      </div>
    </form>
  );
}

export const profileTab = { key: "profile", labelKey: "dp.tab", component: ProfileTab };
