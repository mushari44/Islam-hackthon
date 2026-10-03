// Videos page: IslamHouse videos in the UI language, by topic. Owner: Mushari.
// Media is never re-hosted: MP4s stream from IslamHouse's CDN, YouTube items use their embed,
// and every card and player links back to the item's IslamHouse page.
import "./strings.js";
import "./videos.css";
import { useEffect, useState } from "react";
import { api } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { Icon, Logo, errorText, openSheet } from "../../core/ui.jsx";

const PER_PAGE = 12;
const LANG_KEY = "sabeeli.videoLang";
// Languages written right to left (IslamHouse codes); cards in these get dir="rtl".
const RTL = new Set(["ar", "ur", "fa", "ps", "ug", "ku", "ckb", "dv", "he", "sd", "ks"]);

function savedVideoLang() {
  try { return localStorage.getItem(LANG_KEY) || ""; } catch { return ""; }
}

function SourceLine({ item }) {
  const { t } = useI18n();
  return (
    <a className="vid-source" href={item.page_url} target="_blank" rel="noopener noreferrer">
      <Icon name="external" size={14} />{t("vid.source")}
    </a>
  );
}

function Player({ item }) {
  const { t, fmtNum } = useI18n();
  const [index, setIndex] = useState(0);
  const part = item.parts[index];
  return (
    <div className="vid-player">
      <div className="vid-frame">
        {part.kind === "mp4"
          ? <video key={part.url} src={part.url} poster={item.thumbnail || undefined} controls preload="metadata" playsInline />
          : <iframe key={part.url} src={part.url} title={item.title} allow="encrypted-media; picture-in-picture; fullscreen" allowFullScreen referrerPolicy="strict-origin-when-cross-origin" />}
      </div>
      {item.parts.length > 1 && (
        <ol className="vid-parts" aria-label={t("vid.parts", { n: fmtNum(item.parts.length) })}>
          {item.parts.map((p, i) => (
            <li key={p.url}>
              <button type="button" className="chip" aria-pressed={i === index} onClick={() => setIndex(i)}>
                {p.label || t("vid.part", { n: fmtNum(i + 1) })}
              </button>
            </li>
          ))}
        </ol>
      )}
      <div className="stack vid-meta">
        {item.authors.length > 0 && <span className="muted small">{t("vid.by", { names: item.authors.join("، ") })}</span>}
        <p className="vid-desc">{item.description || <span className="faint">{t("vid.no_desc")}</span>}</p>
        <div className="row spread">
          <SourceLine item={item} />
          <a className="btn btn-sm" href={item.page_url} target="_blank" rel="noopener noreferrer"><Icon name="external" />{t("vid.open_source")}</a>
        </div>
      </div>
    </div>
  );
}

function openPlayer(item) {
  const dir = RTL.has(item.lang) ? "rtl" : "ltr";
  openSheet({ title: item.title, wide: true, render: () => <div lang={item.lang} dir={dir}><Player item={item} /></div> });
}

function VideoCard({ item }) {
  const dir = RTL.has(item.lang) ? "rtl" : "ltr";
  const { t, fmtNum } = useI18n();
  const youtube = item.parts.every((p) => p.kind === "youtube");
  const [thumbOk, setThumbOk] = useState(Boolean(item.thumbnail));   // many IslamHouse thumbnails are missing (404)
  return (
    <article className="card vid-card" lang={item.lang} dir={dir}>
      <button type="button" className="vid-thumb" onClick={() => openPlayer(item)} aria-label={`${t("vid.watch")}: ${item.title}`}>
        {thumbOk
          ? <img src={item.thumbnail} alt="" loading="lazy" onError={() => setThumbOk(false)} />
          : <span className="vid-thumb-empty" aria-hidden="true"><Logo size={54} /></span>}
        <span className="vid-play"><Icon name="play" size={22} /></span>
        <span className="vid-tags">
          {item.parts.length > 1 && <span className="badge">{t("vid.parts", { n: fmtNum(item.parts.length) })}</span>}
          {youtube && <span className="badge">{t("vid.youtube")}</span>}
        </span>
      </button>
      <div className="vid-body">
        {item.topic && <span className="badge badge-mint vid-topic">{item.topic}</span>}
        <h3><button type="button" className="vid-title" onClick={() => openPlayer(item)}>{item.title}</button></h3>
        {item.authors.length > 0 && <span className="faint">{item.authors.join("، ")}</span>}
        <SourceLine item={item} />
      </div>
    </article>
  );
}

export default function VideosPage() {
  const { t, lang: uiLang, fmtNum } = useI18n();
  const [chosen, setChosen] = useState(savedVideoLang);    // video language, separate from the interface language
  const lang = chosen || uiLang;
  const [languages, setLanguages] = useState([]);
  const [topic, setTopic] = useState(null);
  const [page, setPage] = useState(1);
  const [typed, setTyped] = useState("");
  const [q, setQ] = useState("");
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => { setTopic(null); setPage(1); setTyped(""); setQ(""); }, [lang]);
  useEffect(() => {                       // wait for a pause in typing before searching
    const timer = setTimeout(() => { setQ(typed.trim()); setPage(1); }, 350);
    return () => clearTimeout(timer);
  }, [typed]);
  useEffect(() => { api.pGet("/api/videos/languages").then(setLanguages).catch(() => {}); }, []);

  const pickLang = (code) => {
    const value = code === uiLang ? "" : code;      // the interface language stays the default
    setChosen(value);
    try { value ? localStorage.setItem(LANG_KEY, value) : localStorage.removeItem(LANG_KEY); } catch { /* private mode */ }
  };

  useEffect(() => {
    let alive = true;
    let timer;
    setError(null);
    const load = () => {
      const params = new URLSearchParams({ lang, page, per_page: PER_PAGE });
      if (topic) params.set("topic", topic);
      // search words go in a POST body so they never appear in server logs
      const req = q
        ? api.post("/api/videos/search", { lang, q, topic, page, per_page: PER_PAGE }, { as: "none" })
        : api.pGet(`/api/videos?${params}`);
      req
        .then((d) => {
          if (!alive) return;
          setData(d);
          if (d.state === "loading") timer = setTimeout(load, 2000);   // first index build takes ~30s
        })
        .catch((err) => alive && setError(err));
    };
    load();
    return () => { alive = false; clearTimeout(timer); };
  }, [lang, topic, page, q]);

  const ready = data && data.state === "ready";
  const total = ready ? data.total : 0;

  return (
    <>
      <div className="page-head"><h1>{t("vid.title")}</h1><p>{t("vid.lead")}</p></div>
      <div className="vid-langbar row">
        <label htmlFor="vid-lang" className="vid-lang-label"><Icon name="globe" />{t("vid.lang")}</label>
        <select id="vid-lang" className="vid-lang" value={lang} onChange={(e) => pickLang(e.target.value)}>
          {(languages.length ? languages : [{ code: lang, name: lang, count: 0 }]).map((l) => (
            <option key={l.code} value={l.code}>{l.name}{l.count ? ` (${fmtNum(l.count)})` : ""}</option>
          ))}
        </select>
        {languages.length > 0 && <span className="faint">{t("vid.lang_hint", { n: fmtNum(languages.length) })}</span>}
      </div>
      <form className="vid-search" role="search" onSubmit={(e) => { e.preventDefault(); setQ(typed.trim()); setPage(1); }}>
        <Icon name="search" />
        <label htmlFor="vid-q" className="sr-only">{t("vid.search")}</label>
        <input id="vid-q" type="search" value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={t("vid.search_ph")}
          dir="auto" lang={lang} autoComplete="off" maxLength={100} />
        {typed && (
          <button type="button" className="icon-btn" aria-label={t("vid.clear")} title={t("vid.clear")} onClick={() => { setTyped(""); setQ(""); setPage(1); }}>
            <Icon name="x" />
          </button>
        )}
      </form>
      {ready && data.topics.length > 0 && (
        <div className="vid-topics row" role="group" aria-label={t("vid.topic")}>
          <button type="button" className="chip" aria-pressed={!topic} onClick={() => { setTopic(null); setPage(1); }}>{t("vid.all")}</button>
          {data.topics.map((x) => (
            <button key={x.id} type="button" className="chip" aria-pressed={topic === x.id} onClick={() => { setTopic(x.id); setPage(1); }}>
              {x.title} <span className="vid-chip-n">{fmtNum(x.count)}</span>
            </button>
          ))}
        </div>
      )}
      {error && <p className="empty">{errorText(error, t)}</p>}
      {!error && (!data || data.state === "loading") && (
        <div className="stack">
          <p className="muted small" role="status">{t("vid.loading")}</p>
          <div className="vid-grid">{Array.from({ length: 6 }, (_, i) => <div key={i} className="skeleton vid-skel" />)}</div>
        </div>
      )}
      {!error && data && data.state === "unavailable" && <p className="empty">{t("vid.unavailable")}</p>}
      {ready && (data.items.length ? (
        <>
          <p className="faint">{q ? t("vid.results", { n: fmtNum(total), q }) : t("vid.count", { n: fmtNum(total) })}</p>
          <div className="vid-grid">{data.items.map((it) => <VideoCard key={it.id} item={it} />)}</div>
          {data.pages > 1 && (
            <nav className="row vid-pager" aria-label={t("vid.page", { page: fmtNum(data.page), pages: fmtNum(data.pages) })}>
              <button type="button" className="btn btn-sm" disabled={data.page <= 1} onClick={() => { setPage(data.page - 1); window.scrollTo(0, 0); }}>{t("vid.prev")}</button>
              <span className="muted small">{t("vid.page", { page: fmtNum(data.page), pages: fmtNum(data.pages) })}</span>
              <button type="button" className="btn btn-sm" disabled={data.page >= data.pages} onClick={() => { setPage(data.page + 1); window.scrollTo(0, 0); }}>{t("vid.next")}</button>
            </nav>
          )}
        </>
      ) : <p className="empty">{q ? t("vid.no_results", { q }) : t("vid.empty")}</p>)}
    </>
  );
}
