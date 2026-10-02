// Home page. Shared.
import { useEffect, useState } from "react";
import { api } from "../core/api.js";
import { register, useI18n } from "../core/i18n.jsx";
import { Icon } from "../core/ui.jsx";
import { SourceCard } from "../features/rag/public.js";

register({
  ar: {
    "home.badge": "تحدي الذكاء الاصطناعي في خدمة المحتوى الإسلامي",
    "home.lead": "رحلة لفهم الإسلام بمعرفة موثّقة، وحوار مع داعية، وصحبة داعمة. اسأل عمّا يثير فضولك بلغتك، بصورة أو بدونها، وانتقل إلى إنسان متى شئت.",
    "home.ask": "اسأل الآن", "home.talk": "تحدّث مع داعية", "home.name_why": "سبب الاسم",
    "home.f1_t": "اسأل بصورة أو بدونها", "home.f1_d": "اكتب سؤالك أو صوّر نصاً رأيته، فتأتيك الإجابة بلغتك مع مصدرها، ويُطابَق النص القرآني بالمصحف.",
    "home.f2_t": "تحدّث مباشرة", "home.f2_d": "اتصال صوتي بداعية متاح بلغتك، مع ملخص لسؤالك تراجعه وتوافق عليه قبل مشاركته.",
    "home.f3_t": "مجتمع ولقاءات", "home.f3_d": "مجموعات يقودها دعاة ومعها المساعد عند استدعائه، ولقاءات حضورية في أماكن عامة.",
    "home.how": "كيف يعمل سَبِيلي؟",
    "home.s1": "تسأل بلغتك", "home.s1d": "نصاً أو صورة، دون حساب ولا تسجيل.",
    "home.s2": "نبحث في المصادر المعتمدة فقط", "home.s2d": "المصحف والتفسير الميسر وموسوعة الأحاديث وموسوعات الأسئلة والأجوبة وقاموس المصطلحات.",
    "home.s3": "تأتيك الإجابة مع مصدرها", "home.s3d": "أو نقول بوضوح إننا لم نجد، ولا نصدر فتوى في حالتك الشخصية.",
    "home.s4": "تنتقل إلى داعية", "home.s4d": "بملخص تراجعه وتعدّله، فلا تعيد شرح سؤالك من البداية.",
    "home.corpus": "في الحزمة المعتمدة الآن", "home.verses": "آية", "home.hadiths": "حديث بدرجته وشرحه", "home.terms": "مصطلح معتمد", "home.qa": "سؤال وجواب معتمد",
    "home.levels": "نعرف حدودنا",
    "home.lvA": "معلومات أصلية مستقرة: إجابة مباشرة موثقة بالمصدر.",
    "home.lvB": "شرح وتعريف: من المادة المعتمدة مع إظهار المرجع.",
    "home.lvC": "مسائل خلافية: بيان وجود الخلاف أو الإحالة للمختص.",
    "home.lvD": "حالة شخصية أو فتوى: معلومة عامة فقط وإحالة إلى جهة مؤهلة.",
  },
  en: {
    "home.badge": "AI Challenge Serving Islamic Content",
    "home.lead": "A journey to understand Islam through verified knowledge, conversation with a guide, and supportive company. Ask what you're curious about, in your language, with or without a photo, and move to a person whenever you like.",
    "home.ask": "Ask now", "home.talk": "Talk to a da'i", "home.name_why": "Why the name",
    "home.f1_t": "Ask, with or without a photo", "home.f1_d": "Type a question or photograph a text you saw. The answer comes in your language with its source, and Quran text is checked against the Mushaf.",
    "home.f2_t": "Talk directly", "home.f2_d": "A voice call with an available da'i in your language, with a summary of your question you review and approve first.",
    "home.f3_t": "Community and meetups", "home.f3_d": "Groups led by da'is, with the assistant on call, and in-person meetups at public venues.",
    "home.how": "How Sabeeli works",
    "home.s1": "You ask in your language", "home.s1d": "Text or a photo, no account needed.",
    "home.s2": "We search approved sources only", "home.s2d": "The Mushaf, At-Tafsir Al-Muyassar, the hadith encyclopedia, the Q&A encyclopedias and the glossary.",
    "home.s3": "The answer comes with its source", "home.s3d": "Or we say plainly we didn't find it. No fatwa on personal situations.",
    "home.s4": "You move to a da'i", "home.s4d": "With a summary you review and edit, so you don't start over.",
    "home.corpus": "In the approved package now", "home.verses": "verses", "home.hadiths": "hadiths with grade and explanation", "home.terms": "approved terms", "home.qa": "approved questions and answers",
    "home.levels": "We know our limits",
    "home.lvA": "Settled core information: a direct answer with its source.",
    "home.lvB": "Explanation: from approved material, reference shown.",
    "home.lvC": "Disputed matters: we note the disagreement or refer to a specialist.",
    "home.lvD": "Personal case or fatwa: general information only, and referral to a qualified scholar.",
  },
});

function Feature({ href, icon, title, desc }) {
  const { t } = useI18n();
  return (
    <a className="card card-link feature" href={href}>
      <div className="feature-icon"><Icon name={icon} size={26} /></div>
      <h3>{t(title)}</h3>
      <p className="muted small">{t(desc)}</p>
    </a>
  );
}

export default function Home() {
  const { t, lang, fmtNum } = useI18n();
  const [verse, setVerse] = useState(null);
  const [stats, setStats] = useState(null);
  useEffect(() => { api.pGet(`/api/sources/q:12:108?lang=${lang}`).then(setVerse).catch(() => {}); }, [lang]);
  useEffect(() => { api.pGet("/api/corpus").then(setStats).catch(() => {}); }, []);
  return (
    <>
      <section className="hero pattern">
        <div className="hero-text">
          <span className="badge badge-purple">{t("home.badge")}</span>
          <h1 className="hero-title">{t("app.name")}</h1>
          <p className="hero-tag">{t("app.tag")}</p>
          <p className="hero-lead">{t("home.lead")}</p>
          <div className="row">
            <a className="btn btn-primary btn-lg" href="#/ask"><Icon name="ask" />{t("home.ask")}</a>
            <a className="btn btn-accent btn-lg" href="#/talk"><Icon name="talk" />{t("home.talk")}</a>
          </div>
        </div>
        <div className="hero-side">
          <p className="faint">{t("home.name_why")}</p>
          <div className="hero-verse">{verse ? <SourceCard card={verse} compact /> : <div className="skeleton" style={{ height: 160 }} />}</div>
        </div>
      </section>
      <section className="section grid grid-3">
        <Feature href="#/ask" icon="camera" title="home.f1_t" desc="home.f1_d" />
        <Feature href="#/talk" icon="talk" title="home.f2_t" desc="home.f2_d" />
        <Feature href="#/community" icon="community" title="home.f3_t" desc="home.f3_d" />
      </section>
      <section className="section">
        <h2>{t("home.how")}</h2>
        <ol className="steps">
          {["s1", "s2", "s3", "s4"].map((k, i) => (
            <li className="step" key={k}>
              <span className="step-num">{fmtNum(i + 1)}</span>
              <div><strong>{t(`home.${k}`)}</strong><p className="muted small">{t(`home.${k}d`)}</p></div>
            </li>
          ))}
        </ol>
      </section>
      <section className="section grid grid-2">
        <div className="card stack">
          <h3>{t("home.corpus")}</h3>
          <div className="stats">
            {stats && [[stats.quran_verses, "home.verses"], [stats.hadiths, "home.hadiths"], [(stats.qa || 0) + (stats.bayyinat || 0), "home.qa"]].map(([n, k]) => (
              <div className="stat" key={k}><span className="stat-num">{fmtNum(n)}</span><span className="stat-label">{t(k)}</span></div>
            ))}
          </div>
        </div>
        <div className="card stack">
          <h3>{t("home.levels")}</h3>
          <ul className="levels">
            {["A", "B", "C", "D"].map((l) => <li key={l}><span className="level-tag">{l}</span><span className="small">{t(`home.lv${l}`)}</span></li>)}
          </ul>
        </div>
      </section>
    </>
  );
}
