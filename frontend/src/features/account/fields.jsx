// The seeker's sex and age band (and language): picked at sign-up, edited under "About me", and asked once of an
// older account that has none. There is no "prefer not to say". Owner: Eman.
import "./strings.js";
import { useState } from "react";
import { api } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { Icon, errorText, toast } from "../../core/ui.jsx";
import { setAccount } from "./store.js";

// Keep in step with AGE_BANDS, GENDERS and DAAI_LANGUAGES in backend/app/features/auth/routes.py.
export const AGE_BANDS = ["u18", "18_24", "25_34", "35_44", "45_54", "55p"];
const LANGS = ["ar", "en"];

/** True when an account still has no sex or age band (made before they were required). */
export const needsAbout = (account) => Boolean(account) && (!account.gender || !account.age_band);

/** Language, sex and age band. Sex and age band must be picked: until then the form can't be sent. */
export function AboutFields({ f, set, prefix, withLang = true }) {
  const { t, langName } = useI18n();
  return (
    <div className="grid grid-2">
      {withLang && (
        <div className="field">
          <label htmlFor={`${prefix}-lang`}>{t("acc.lang")}</label>
          <select id={`${prefix}-lang`} className="select" value={f.lang} onChange={set("lang")}>
            {LANGS.map((l) => <option key={l} value={l}>{langName(l)}</option>)}
          </select>
        </div>
      )}
      <div className="field">
        <label htmlFor={`${prefix}-gender`}>{t("acc.gender")}</label>
        <select id={`${prefix}-gender`} className="select" required value={f.gender} onChange={set("gender")}>
          <option value="" disabled>{t("acc.choose")}</option>
          <option value="m">{t("acc.gender_m")}</option>
          <option value="f">{t("acc.gender_f")}</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-age`}>{t("acc.age")}</label>
        <select id={`${prefix}-age`} className="select" required value={f.age_band} onChange={set("age_band")}>
          <option value="" disabled>{t("acc.choose")}</option>
          {AGE_BANDS.map((b) => <option key={b} value={b}>{t(`acc.age.${b}`)}</option>)}
        </select>
      </div>
    </div>
  );
}

/** Asks an account made before sex and age band were required to pick them. */
export function CompleteAbout({ account, close }) {
  const { t } = useI18n();
  const [f, setF] = useState({ gender: account.gender || "", age_band: account.age_band || "" });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      setAccount((await api.post("/api/account/profile", f)).account);
      toast(t("acc.saved"), "success");
      close?.();
    } catch (err) {
      toast(errorText(err, t), "error");
      setBusy(false);
    }
  };
  return (
    <form className="stack" onSubmit={save}>
      <p className="small muted">{t("acc.complete_lead")}</p>
      <AboutFields f={f} set={set} prefix="ca" withLang={false} />
      {f.age_band === "u18" && <p className="small muted">{t("acc.age_minor")}</p>}
      <div className="row">
        <button type="submit" className="btn btn-primary" disabled={busy || !f.gender || !f.age_band}><Icon name="check" />{t("acc.save")}</button>
      </div>
    </form>
  );
}
