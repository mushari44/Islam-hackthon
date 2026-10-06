// Video cards and the player sheet, shared by the videos page and the related videos under an answer.
// Owner: Mushari. Media is never re-hosted: MP4s stream from IslamHouse's CDN, YouTube items use their
// embed, and every card and player links back to the item's IslamHouse page.
import "./strings.js";
import "./videos.css";
import { useState } from "react";
import { useI18n } from "../../core/i18n.jsx";
import { Icon, Logo, openSheet } from "../../core/ui.jsx";

// Languages written right to left (IslamHouse codes); cards in these get dir="rtl".
export const RTL = new Set(["ar", "ur", "fa", "ps", "ug", "ku", "ckb", "dv", "he", "sd", "ks"]);

/** Presenters' names joined as the video's own language joins a list ("A, B and C", «أ وب وج»). */
function joinNames(names, lang) {
  try { return new Intl.ListFormat(lang, { type: "conjunction" }).format(names); } catch { /* old browser or odd code */ }
  return names.join(RTL.has(lang) ? "، " : ", ");
}

function SourceLine({ item }) {
  const { t } = useI18n();
  return (
    <a className="vid-source" href={item.page_url} target="_blank" rel="noopener noreferrer">
      <Icon name="external" size={14} />{t("vid.source")}
    </a>
  );
}

function Player({ item, dir }) {
  const { t, tn, lang, fmtNum } = useI18n();
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
        <ol className="vid-parts" aria-label={tn("vid.parts", item.parts.length)}>
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
        {item.authors.length > 0 && (
          <span className="muted small">{t("vid.by", { names: "" })}<span lang={item.lang} dir={dir}>{joinNames(item.authors, item.lang || lang)}</span></span>
        )}
        {item.description ? <p className="vid-desc" lang={item.lang} dir={dir}>{item.description}</p> : <p className="vid-desc faint">{t("vid.no_desc")}</p>}
        {/* One link back to the item's IslamHouse page; the credit beside it stays as plain text. */}
        <div className="row spread">
          <span className="vid-credit">{t("vid.source")}</span>
          <a className="btn btn-sm" href={item.page_url} target="_blank" rel="noopener noreferrer"><Icon name="external" />{t("vid.open_source")}</a>
        </div>
      </div>
    </div>
  );
}

export function openPlayer(item) {
  const dir = RTL.has(item.lang) ? "rtl" : "ltr";
  openSheet({ title: item.title, wide: true, render: () => <Player item={item} dir={dir} /> });
}

export function VideoCard({ item, compact = false }) {
  const dir = RTL.has(item.lang) ? "rtl" : "ltr";
  const { t, tn, lang } = useI18n();
  const youtube = item.parts.every((p) => p.kind === "youtube");
  const [thumbOk, setThumbOk] = useState(Boolean(item.thumbnail));   // many IslamHouse thumbnails are missing (404)
  return (
    <article className={`card vid-card ${compact ? "vid-card-compact" : ""}`}>
      <button type="button" className="vid-thumb" onClick={() => openPlayer(item)} aria-label={`${t("vid.watch")}: ${item.title}`}>
        {thumbOk
          ? <img src={item.thumbnail} alt="" loading="lazy" onError={() => setThumbOk(false)} />
          : <span className="vid-thumb-empty" aria-hidden="true"><Logo size={54} /></span>}
        <span className="vid-play"><Icon name="play" size={22} /></span>
        <span className="vid-tags">
          {item.parts.length > 1 && <span className="badge">{tn("vid.parts", item.parts.length)}</span>}
          {youtube && <span className="badge">{t("vid.youtube")}</span>}
        </span>
      </button>
      <div className="vid-body">
        {item.topic && <span className="badge badge-mint vid-topic" lang={item.lang} dir={dir}>{item.topic}</span>}
        <h3 lang={item.lang} dir={dir}><button type="button" className="vid-title" onClick={() => openPlayer(item)}>{item.title}</button></h3>
        {item.authors.length > 0 && <span className="faint" lang={item.lang} dir={dir}>{joinNames(item.authors, item.lang || lang)}</span>}
        {!compact && <SourceLine item={item} />}
      </div>
    </article>
  );
}
