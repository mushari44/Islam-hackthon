// Home page. Shared.
import { useEffect, useState } from "react";
import { api } from "../core/api.js";
import { register, useI18n } from "../core/i18n.jsx";
import { Icon } from "../core/ui.jsx";

register({
  ar: {
    "home.lead": "اكتب ما يثير تساؤلك", "home.journey": "ابدأ من هنا",
    
    "home.verse_ref": "سورة يوسف، الآية ١٠٨", "home.f1_t": "اسأل", "home.f1_d": "اسأل ما يثير فضولك لمعرفته",
    "home.f2_t": "تحدّث مباشرة", "home.f2_d": "مكالمة للرد على استفسارك",
    "home.f3_t": "المجتمع المسلم", "home.f3_d": "مجموعات ولقاءات",
  },
  en: {
    "home.lead": "Write what makes you wonder", "home.journey": "Start here",
    
    "home.verse_ref": "Surah Yusuf, verse 108", "home.f1_t": "Ask", "home.f1_d": "Ask what you're curious to know",
    "home.f2_t": "Talk directly", "home.f2_d": "A call to answer your question",
    "home.f3_t": "Muslim community", "home.f3_d": "Groups and meetups",
  },
});

// The three ways in, drawn as stops along one path (سبيل): ask, talk to a da'i, join others.
const STOPS = [["#/ask", "camera", "f1"], ["#/talk", "talk", "f2"], ["#/community", "community", "f3"]];

function Journey() {
  const { t } = useI18n();
  return (
    <nav className="journey" aria-label={t("home.journey")}>
      {STOPS.map(([href, icon, k]) => (
        <a className="stop" href={href} key={k}>
          <span className="stop-node"><Icon name={icon} size={22} /></span>
          <span className="stop-text"><strong>{t(`home.${k}_t`)}</strong><span>{t(`home.${k}_d`)}</span></span>
          <Icon name="arrow" size={18} className="stop-go" />
        </a>
      ))}
    </nav>
  );
}

export default function Home() {
  const { t, lang } = useI18n();
  const [verse, setVerse] = useState(null);
  useEffect(() => { api.pGet(`/api/sources/q:12:108?lang=${lang}`).then(setVerse).catch(() => {}); }, [lang]);
  return (
    <>
      <section className="hero pattern home-hero">
        <div className="hero-text">
          <h1 className="hero-title">{t("app.name")}</h1>
          <p className="hero-tag">{t("app.tag")}</p>
          <p className="hero-lead">{t("home.lead")}</p>
          <Journey />
        </div>
        <div className="hero-side">
          <div className="hero-verse">
            {verse ? (
              <figure className="src-card verse-card compact home-verse">
                <p className="verse-text" lang="ar" dir="rtl"><span className="orn">﴿</span>{verse.text_ar}<span className="orn">﴾</span></p>
                <figcaption>{t("home.verse_ref")}</figcaption>
              </figure>
            ) : <div className="skeleton" style={{ height: 160 }} />}
          </div>
        </div>
      </section>
    </>
  );
}
