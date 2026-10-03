// Da'i console, "My profile" tab: a da'i keeps their name, languages and bio current. Owner: Eman.
// Seekers are matched with a da'i by language, so the languages here decide who can reach this da'i.
import "./daai.css";
import { useState } from "react";
import { api } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { Icon, errorText, toast } from "../../core/ui.jsx";

// Languages a da'i can offer for now. Keep in step with DAAI_LANGUAGES in features/auth/routes.py.
const LANGUAGES = ["ar", "en"];

function fromProfile(me) {
  return { name: me.name || "", name_en: me.name_en || "", languages: me.languages || [], bio: me.bio || "", bio_en: me.bio_en || "" };
}

export function titledName(me, lang, t) {
  const name = lang === "ar" ? me.name : me.name_en || me.name;
  return t(me.gender === "f" ? "dp.titled_f" : "dp.titled_m", { n: name });
}

function ProfileTab({ me, onMe }) {
  const { t, lang, langName } = useI18n();
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

  const preview = { ...me, name: f.name || me.name, name_en: f.name_en, languages: f.languages, bio: f.bio, bio_en: f.bio_en };
  const bio = lang === "ar" ? preview.bio : preview.bio_en || preview.bio;

  return (
    <div className="profile-grid">
      <form className="card stack" onSubmit={submit}>
        <h3>{t("dp.edit")}</h3>
        <div className="grid grid-2">
          <div className="field">
            <label htmlFor="p-name">{t("dp.name")}</label>
            <input id="p-name" className="input" required minLength={2} maxLength={120} value={f.name} onChange={set("name")} />
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

        <div className="field">
          <label htmlFor="p-bio">{t("dp.bio")}</label>
          <textarea id="p-bio" className="textarea" rows={3} maxLength={600} value={f.bio} onChange={set("bio")} />
          <span className="faint">{t("dp.count", { n: f.bio.length })}</span>
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
          </div>
        </div>
        {bio ? <p>{bio}</p> : <p className="faint">{t("dp.no_bio")}</p>}
      </aside>
    </div>
  );
}

export const profileTab = { key: "profile", labelKey: "dp.tab", component: ProfileTab };
