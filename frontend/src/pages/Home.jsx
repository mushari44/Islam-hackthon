// Home page. Shared.
// Everything below the name is live: the ask box goes straight to an answer, and the three ways in,
// the coming meetups, the groups, the videos and the source counts all come from the app's own APIs.
// Each block keeps its height while it loads, so nothing jumps when the data arrives.
import { useEffect, useState } from "react";
import { api } from "../core/api.js";
import { register, useI18n } from "../core/i18n.jsx";
import { navigate } from "../core/router.jsx";
import { Icon } from "../core/ui.jsx";
import { useAccount } from "../features/account/public.js";
import { useWhen } from "../features/community/public.js";
import { VideoCard } from "../features/videos/public.js";

register({
  ar: {
    "home.tag": "معرفة تُنير، وصحبة تُعين",
    "home.ask_label": "سؤالك", "home.ask_ph": "مثلاً: ما معنى التوحيد؟", "home.ask_go": "اسأل",
    "home.try": "جرّب:",
    "home.ex1": "ما أركان الإسلام؟", "home.ex2": "كيف أتوضأ؟", "home.ex3": "من هو النبي محمد ﷺ؟",
    "home.journey": "ابدأ من هنا", "home.verse_ref": "سورة يوسف، الآية ١٠٨",
    "home.f1_t": "اسأل", "home.f1_d": "اكتب سؤالك أو صوّر نصاً",
    "home.f2_t": "تحدّث مباشرة", "home.f2_d": "مكالمة مع داعية",
    "home.f3_t": "المجتمع المسلم", "home.f3_d": "مجموعات ولقاءات",
    "home.live_sources": "{n} نص موثّق", "home.live_daais": "{n} داعية متاح الآن", "home.live_daais_none": "اترك طلباً ويتصل بك داعية",
    "home.live_meetups": "{n} لقاء قادم", "home.live_groups": "{n} مجموعة",
    "home.soon_t": "لقاءات قادمة", "home.soon_all": "كل اللقاءات", "home.soon_empty": "لا لقاءات قادمة الآن. تصفّح المجموعات وانضم إلى إحداها.",
    "home.online": "عن بُعد", "home.in_person": "حضوري", "home.live_now": "يحدث الآن",
    "home.groups_t": "مجموعات تتعلم معاً", "home.groups_all": "كل المجموعات", "home.groups_empty": "لا مجموعات بعد.",
    "home.members": "{n} عضو",
    "home.videos_t": "مرئيات من دار الإسلام", "home.videos_all": "كل المرئيات",
    "home.trust_t": "كل إجابة من مصادر معتمدة", "home.trust_d": "لا يظهر للمستخدم إلا ما له مصدر، ونصوص القرآن والحديث تُعرض كما هي في المصدر.",
    "home.stat_q": "آية بتفسيرها", "home.stat_h": "حديث مشروح", "home.stat_qa": "سؤال وجواب", "home.trust_more": "تعرّف على المصادر",
  },
  en: {
    "home.tag": "Knowledge that enlightens, company that supports",
    "home.ask_label": "Your question", "home.ask_ph": "e.g. What does tawhid mean?", "home.ask_go": "Ask",
    "home.try": "Try:",
    "home.ex1": "What are the pillars of Islam?", "home.ex2": "How do I make wudu?", "home.ex3": "Who is Prophet Muhammad ﷺ?",
    "home.journey": "Start here", "home.verse_ref": "Surah Yusuf, verse 108",
    "home.f1_t": "Ask", "home.f1_d": "Type a question or snap a text",
    "home.f2_t": "Talk directly", "home.f2_d": "A call with a da'i",
    "home.f3_t": "Muslim community", "home.f3_d": "Groups and meetups",
    "home.live_sources": "{n} verified texts", "home.live_daais": "{n} da'is available now", "home.live_daais_none": "Leave a request and a da'i calls you",
    "home.live_meetups": "{n} upcoming meetups", "home.live_groups": "{n} groups",
    "home.soon_t": "Coming up", "home.soon_all": "All meetups", "home.soon_empty": "No meetups coming up right now. Browse the groups and join one.",
    "home.online": "Online", "home.in_person": "In person", "home.live_now": "Happening now",
    "home.groups_t": "Groups learning together", "home.groups_all": "All groups", "home.groups_empty": "No groups yet.",
    "home.members": "{n} members",
    "home.videos_t": "Videos from IslamHouse", "home.videos_all": "All videos",
    "home.trust_t": "Every answer comes from approved sources", "home.trust_d": "Only sourced text reaches you, and Quran and hadith text is shown exactly as in the source.",
    "home.stat_q": "verses with tafsir", "home.stat_h": "explained hadiths", "home.stat_qa": "questions and answers", "home.trust_more": "About the sources",
  },
});

const AUDIENCE_FROM_GENDER = { f: "women", m: "men" };

/** Loads `path` once per change of `key`. Returns undefined while loading, null on failure, else the data. */
function useLive(path, key = path) {
  const [data, setData] = useState(undefined);
  useEffect(() => {
    let alive = true;
    setData(undefined);
    api.pGet(path).then((d) => { if (alive) setData(d); }).catch(() => { if (alive) setData(null); });
    return () => { alive = false; };
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  return data;
}

function AskBox() {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const go = (text) => { const s = text.trim(); if (s) navigate(`/ask?q=${encodeURIComponent(s)}`); };
  return (
    <div className="home-ask">
      <form className="home-ask-box" onSubmit={(e) => { e.preventDefault(); go(q); }}>
        <label className="sr-only" htmlFor="home-q">{t("home.ask_label")}</label>
        <Icon name="search" size={20} className="home-ask-icon" />
        <input id="home-q" className="home-ask-input" value={q} onChange={(e) => setQ(e.target.value)}
          placeholder={t("home.ask_ph")} maxLength={1000} autoComplete="off" enterKeyHint="send" />
        <button type="submit" className="btn btn-primary home-ask-go" disabled={!q.trim()}>
          <span>{t("home.ask_go")}</span><Icon name="arrow" size={18} className="icon-go" />
        </button>
      </form>
      <div className="home-try">
        <span>{t("home.try")}</span>
        {["ex1", "ex2", "ex3"].map((k) => (
          <button type="button" className="chip" key={k} onClick={() => go(t(`home.${k}`))}>{t(`home.${k}`)}</button>
        ))}
      </div>
    </div>
  );
}

/** One short live line under a stop; keeps its height while loading. */
function LiveLine({ text, on = false }) {
  if (text === undefined) return <span className="stop-live"><span className="skeleton stop-live-skel" /></span>;
  if (!text) return <span className="stop-live" />;
  return <span className={`stop-live fade-in ${on ? "is-on" : ""}`}>{on && <span className="live-dot" aria-hidden="true" />}{text}</span>;
}

// The three ways in, drawn as stops along one path (سبيل): ask, talk to a da'i, join others.
function Journey({ corpus, avail, meetups, groups }) {
  const { t, lang, fmtNum } = useI18n();
  const sources = corpus && (corpus.quran_verses || 0) + (corpus.hadiths || 0) + (corpus.qa || 0) + (corpus.bayyinat || 0) + (corpus.terms || 0);
  const daais = avail && (avail.languages?.[lang]?.total || 0);
  const lines = {
    f1: corpus === undefined ? undefined : sources ? t("home.live_sources", { n: fmtNum(sources) }) : "",
    f2: avail === undefined ? undefined : avail === null ? "" : daais ? t("home.live_daais", { n: fmtNum(daais) }) : t("home.live_daais_none"),
    f3: meetups === undefined || groups === undefined ? undefined
      : meetups?.length ? t("home.live_meetups", { n: fmtNum(meetups.length) })
        : groups?.length ? t("home.live_groups", { n: fmtNum(groups.length) }) : "",
  };
  const stops = [["#/ask", "camera", "f1"], ["#/talk", "talk", "f2"], ["#/community", "community", "f3"]];
  return (
    <nav className="journey" aria-label={t("home.journey")}>
      {stops.map(([href, icon, k]) => (
        <a className="stop" href={href} key={k}>
          <span className="stop-node"><Icon name={icon} size={22} /></span>
          <span className="stop-text">
            <strong>{t(`home.${k}_t`)}</strong>
            <span>{t(`home.${k}_d`)}</span>
            <LiveLine text={lines[k]} on={k === "f2" && Boolean(daais)} />
          </span>
        </a>
      ))}
    </nav>
  );
}

function SectionHead({ title, href, more }) {
  return (
    <div className="home-sec-head">
      <h2>{title}</h2>
      <a className="home-more" href={href}>{more}<Icon name="arrow" size={16} className="icon-go" /></a>
    </div>
  );
}

function MeetupRow({ m }) {
  const { t } = useI18n();
  const w = useWhen(m);
  const where = m.format === "online" ? t("home.online") : [m.city, m.venue].filter(Boolean).join(" · ") || t("home.in_person");
  return (
    <a className="home-row fade-in" href="#/community?tab=meetups">
      <span className="home-date" aria-hidden="true"><strong>{w.day}</strong><span>{w.month}</span></span>
      <span className="home-row-text">
        <strong dir="auto">{m.title}</strong>
        <span className="home-row-meta">
          {w.live ? <span className="badge badge-mint"><span className="live-dot" aria-hidden="true" />{t("home.live_now")}</span> : <span>{w.date} · {w.time}</span>}
        </span>
        <span className="home-row-meta"><Icon name={m.format === "online" ? "globe" : "pin"} size={14} />{where}</span>
      </span>
    </a>
  );
}

function GroupRow({ g }) {
  const { t, fmtNum, langName } = useI18n();
  return (
    <a className="home-row fade-in" href={`#/groups/${g.id}`}>
      <span className="home-row-icon" aria-hidden="true"><Icon name="community" size={20} /></span>
      <span className="home-row-text">
        <strong dir="auto">{g.title}</strong>
        <span className="home-row-meta">
          {[langName ? langName(g.lang) : g.lang, g.city, g.members ? t("home.members", { n: fmtNum(g.members) }) : ""].filter(Boolean).join(" · ")}
        </span>
      </span>
    </a>
  );
}

function RowsSkeleton() {
  return [0, 1, 2].map((i) => <div className="home-row home-row-skel" key={i}><span className="skeleton" /><span className="skeleton" /></div>);
}

// Items in the page's language come first; the order within each language stays as the API gave it.
const ownLangFirst = (rows, lang) => [...rows].sort((a, b) => (a.lang !== lang) - (b.lang !== lang));

function Community({ meetups, groups }) {
  const { t, lang } = useI18n();
  return (
    <section className="home-split" aria-label={t("home.f3_t")}>
      <div className="home-panel">
        <SectionHead title={t("home.soon_t")} href="#/community?tab=meetups" more={t("home.soon_all")} />
        <div className="home-rows">
          {meetups === undefined ? <RowsSkeleton />
            : meetups?.length ? ownLangFirst(meetups, lang).slice(0, 3).map((m) => <MeetupRow m={m} key={m.id} />)
              : <p className="home-empty">{t("home.soon_empty")}</p>}
        </div>
      </div>
      <div className="home-panel">
        <SectionHead title={t("home.groups_t")} href="#/community" more={t("home.groups_all")} />
        <div className="home-rows">
          {groups === undefined ? <RowsSkeleton />
            : groups?.length ? ownLangFirst([...groups].sort((a, b) => (b.members || 0) - (a.members || 0)), lang).slice(0, 3).map((g) => <GroupRow g={g} key={g.id} />)
              : <p className="home-empty">{t("home.groups_empty")}</p>}
        </div>
      </div>
    </section>
  );
}

// IslamHouse videos, shown exactly as published. The list is built in the background after start-up,
// so a "loading" reply is asked again a few times. The section sits last and only appears once there are
// videos to show, so its arrival never pushes anything else down.
function Videos() {
  const { t, lang } = useI18n();
  const [items, setItems] = useState(undefined);
  useEffect(() => {
    let alive = true;
    let timer;
    const load = (tries) => api.pGet(`/api/videos?lang=${lang}&per_page=4`).then((r) => {
      if (!alive) return;
      if (r.state === "loading" && tries > 0) timer = setTimeout(() => load(tries - 1), 5000);
      else setItems(r.items || []);
    }).catch(() => { if (alive) setItems([]); });
    load(3);
    return () => { alive = false; clearTimeout(timer); };
  }, [lang]);
  if (!items || !items.length) return null;
  return (
    <section className="home-videos" aria-label={t("home.videos_t")}>
      <SectionHead title={t("home.videos_t")} href="#/videos" more={t("home.videos_all")} />
      <div className="home-vid-grid">
        {items.map((v) => <div className="fade-in" key={v.id}><VideoCard item={v} compact /></div>)}
      </div>
    </section>
  );
}

function Trust({ corpus }) {
  const { t, fmtNum } = useI18n();
  const stats = [["quran_verses", "stat_q"], ["hadiths", "stat_h"], ["qa", "stat_qa"]];
  return (
    <section className="home-trust">
      <div className="home-trust-text">
        <span className="home-trust-icon" aria-hidden="true"><Icon name="shield" size={22} /></span>
        <div>
          <h2>{t("home.trust_t")}</h2>
          <p>{t("home.trust_d")}</p>
          <a className="home-more" href="#/sources">{t("home.trust_more")}<Icon name="arrow" size={16} className="icon-go" /></a>
        </div>
      </div>
      <div className="home-stats">
        {stats.map(([key, label]) => (
          <div className="home-stat" key={key}>
            {corpus === undefined ? <span className="skeleton home-stat-skel" />
              : <strong className="fade-in">{corpus ? fmtNum((corpus[key] || 0) + (key === "qa" ? corpus.bayyinat || 0 : 0)) : "—"}</strong>}
            <span>{t(`home.${label}`)}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

export default function Home() {
  const { t, lang } = useI18n();
  const { account } = useAccount();
  const audience = AUDIENCE_FROM_GENDER[account?.gender] || "";
  const verse = useLive(`/api/sources/q:12:108?lang=${lang}`);
  const corpus = useLive("/api/corpus");
  const avail = useLive("/api/availability");
  const meetups = useLive(`/api/meetups?ui=${lang}&audience=${audience}`);
  const groups = useLive(`/api/groups?ui=${lang}&audience=${audience}`);
  return (
    <div className="home">
      <section className="home-hero">
        <div className="hero-text">
          <h1 className="hero-title">{t("app.name")}</h1>
          <p className="hero-tag">{t("home.tag")}</p>
          <AskBox />
        </div>
        <div className="hero-side">
          {verse ? (
            <figure className="src-card verse-card compact home-verse fade-in">
              <p className="verse-text" lang="ar" dir="rtl"><span className="orn">﴿</span>{verse.text_ar}<span className="orn">﴾</span></p>
              <figcaption>{t("home.verse_ref")}</figcaption>
            </figure>
          ) : verse === undefined ? <div className="skeleton home-verse-skel" /> : null}
        </div>
      </section>
      <Journey corpus={corpus} avail={avail} meetups={meetups} groups={groups} />
      <Community meetups={meetups} groups={groups} />
      <Trust corpus={corpus} />
      <Videos />
    </div>
  );
}
