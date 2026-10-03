// Answers and source cards. Owner: Mushari (RAG).
// Public to other features through ./public.js: community shows assistant replies with <Answer compact/>,
// calls shows the sources cited on a referral card with <SourceCard/>.
import "./strings.js";
import "./rag.css";
import { useI18n } from "../../core/i18n.jsx";
import { Icon, Notice, openSheet } from "../../core/ui.jsx";

const MARKER = /\[\[(q:\d{1,3}:\d{1,3}|h:\d+|t:[a-z_]+|qa:\d+|b:\d+)\]\]/g;
const VERSE_MARKER = /\[\[(q:\d{1,3}:\d{1,3})\]\]/g;
const arDigits = (n) => new Intl.NumberFormat("ar-SA-u-nu-arab").format(n);
const KIND_LABEL = { quran: "verse", hadith: "hadith", term: "term", qa: "qa", bayyinat: "bayyinat" };

/** An encyclopedia answer: its own Arabic text, with every verse it quotes shown from the Mushaf. */
function QaAnswer({ text, verses }) {
  const out = [];
  text.split(VERSE_MARKER).forEach((part, i) => {
    if (i % 2 === 1) {
      const v = verses[part];
      if (v) {
        out.push(
          <p key={i} className="verse-text qa-verse" lang="ar" dir="rtl" title={`${v.sura_name_ar} ${v.sura}:${v.aya}`}>
            <span className="orn">﴿</span>{v.text_ar} <span className="aya-num">{arDigits(v.aya)}</span><span className="orn">﴾</span>
            <span className="qa-verse-ref">{`[${v.sura_name_ar}: ${arDigits(v.aya)}]`}</span>
          </p>,
        );
      }
      return;
    }
    part.split(/\n+/).forEach((line, j) => { if (line.trim()) out.push(<p key={`${i}-${j}`}>{line}</p>); });
  });
  return <div className="qa-answer" lang="ar" dir="rtl">{out}</div>;
}

function SourceLink({ url }) {
  const { t } = useI18n();
  if (!url) return null;
  return (
    <a className="icon-btn src-link" href={url} target="_blank" rel="noopener noreferrer" aria-label={t("src.open")} title={t("src.open")}>
      <Icon name="external" />
    </a>
  );
}

function Details({ summary, children }) {
  return <details className="src-details"><summary>{summary}</summary><div className="src-details-body">{children}</div></details>;
}

/** A verse, hadith, glossary or Q&A card rendered from reference data (never from model text). */
export function SourceCard({ card, num = null, compact = false }) {
  const { t, lang, fmtNum } = useI18n();
  const head = (kind, extra = null) => (
    <div className="src-head">
      {num != null && <span className="src-num">{fmtNum(num)}</span>}
      <span className="badge badge-mint">{t(`src.${kind}`)}</span>
      {extra}
      <span className="src-title">{card.title}</span>
      <SourceLink url={card.url} />
    </div>
  );
  if (card.kind === "quran") {
    return (
      <article className={`src-card verse-card ${compact ? "compact" : ""}`} data-id={card.id}>
        {head("verse")}
        <p className="verse-text" lang="ar" dir="rtl">
          <span className="orn">﴿</span>{card.text_ar} <span className="aya-num">{arDigits(card.aya)}</span><span className="orn">﴾</span>
        </p>
        {lang !== "ar" && card.translation_en && <p className="verse-translation" lang="en" dir="ltr">{card.translation_en}</p>}
        {!compact && <Details summary={t("src.tafsir")}><p lang="ar" dir="rtl">{card.tafsir_ar}</p></Details>}
        <div className="src-foot">{card.source}</div>
      </article>
    );
  }
  if (card.kind === "hadith") {
    return (
      <article className={`src-card hadith-card ${compact ? "compact" : ""}`} data-id={card.id}>
        {head("hadith", card.grade ? <span className="badge badge-purple">{card.grade}</span> : null)}
        <p className="hadith-text" lang="ar" dir="rtl">{card.text_ar}</p>
        {lang !== "ar" && (card.text_en ? <p className="hadith-en" lang="en" dir="ltr">{card.text_en}</p> : <p className="faint">{t("src.no_en")}</p>)}
        {card.attribution && <div className="faint">{card.attribution}</div>}
        {!compact && card.explanation && <Details summary={t("src.explanation")}><p>{card.explanation}</p></Details>}
        <div className="src-foot">{card.source}</div>
      </article>
    );
  }
  if (card.kind === "qa" || card.kind === "bayyinat") {
    const verses = card.verses || {};
    return (
      <article className={`src-card qa-card ${compact ? "compact" : ""}`} data-id={card.id}>
        {head(card.kind)}
        {!card.title.includes(card.question) && <p className="qa-question" lang="ar" dir="rtl">{card.question}</p>}
        {lang !== "ar" && <p className="faint">{t("src.ar_only")}</p>}
        {card.short_answer && (
          <div className="qa-short"><div className="faint small">{t("src.short_answer")}</div><QaAnswer text={card.short_answer} verses={verses} /></div>
        )}
        <Details summary={t(card.kind === "qa" ? "src.qa_answer" : "src.full_answer")}><QaAnswer text={card.answer} verses={verses} /></Details>
        <div className="src-foot">{card.source}</div>
      </article>
    );
  }
  return (
    <article className="src-card term-card" data-id={card.id}>
      {head("term")}
      <p className="term-line"><strong lang="ar">{card.term_ar}</strong>{"  ·  "}<span lang="en" dir="ltr">{card.term_en}</span></p>
      <p className="small" lang="ar" dir="rtl"><span className="muted">{t("src.rule")}: </span>{card.rule_ar}</p>
      <div className="src-foot">{card.source}</div>
    </article>
  );
}

export function LevelBadge({ level }) {
  const { t } = useI18n();
  const cls = level === "D" ? "badge-warn" : level === "C" ? "badge-purple" : "badge-mint";
  return <span className={`badge ${cls}`}>{level} · {t(`level.${level}`)}</span>;
}

function QuoteCheck({ qc }) {
  const { t } = useI18n();
  if (!qc) return null;
  const kind = qc.status === "exact" ? "mint" : qc.status === "differs" || qc.status === "not_found" ? "warn" : "";
  const diffs = qc.status === "differs" && qc.matches[0] ? qc.matches[0].differences : [];
  return (
    <Notice kind={kind} icon={qc.status === "exact" ? "check" : "quote"}>
      <strong>{t(`qc.title_${qc.status}`)}</strong>
      {diffs.length > 0 && (
        <ul className="qc-diffs">
          {diffs.slice(0, 6).map((d, i) => (
            <li key={i}>
              <span className="badge">{t(`qc.${d.type}`)}</span>{" "}
              {d.quoted && <span><span className="faint">{t("qc.quoted")}: </span><span className="qc-q" lang="ar">{d.quoted}</span></span>}
              {d.quoted && d.reference && "  ←  "}
              {d.reference && <span><span className="faint">{t("qc.reference")}: </span><span className="qc-r" lang="ar">{d.reference}</span></span>}
            </li>
          ))}
        </ul>
      )}
    </Notice>
  );
}

/**
 * Renders a pipeline answer: text with citation numbers, inline reference cards for [[markers]],
 * the quote check, notices and the numbered source list. `compact` is used inside group chats.
 */
export function Answer({ answer, compact = false }) {
  const { t, fmtNum } = useI18n();
  const cards = answer.cards || {};
  const numbers = new Map();
  const num = (id) => { if (!numbers.has(id)) numbers.set(id, numbers.size + 1); return numbers.get(id); };
  const openSource = (id) => openSheet({ title: cards[id].title, render: () => <SourceCard card={cards[id]} num={num(id)} /> });

  // Build blocks: paragraphs (runs of text + citation buttons) and cards.
  const blocks = [];
  let para = [];
  const flush = () => { if (para.length) blocks.push({ type: "p", items: para }); para = []; };
  (answer.segments || []).forEach((seg, si) => {
    const shown = new Set([...seg.text.matchAll(MARKER)].map((m) => m[1]));
    seg.text.split(MARKER).forEach((part, i) => {
      if (i % 2 === 1) {
        flush();
        if (cards[part]) blocks.push({ type: "card", id: part, n: num(part) });
        return;
      }
      part.split(/\n{2,}/).forEach((line, j) => {
        if (j > 0) flush();
        const clean = line.replace(/\n+/g, " ");
        if (clean.trim()) para.push({ type: "text", text: clean, key: `${si}-${i}-${j}` });
      });
    });
    for (const id of seg.cites || []) {
      if (cards[id] && !shown.has(id)) para.push({ type: "cite", id, n: num(id), key: `${si}-c-${id}` });
    }
  });
  flush();

  return (
    <div className="answer">
      <QuoteCheck qc={answer.quote_check} />
      {answer.ocr && answer.ocr.text && (
        <Details summary={t("ocr.read")}>
          {answer.ocr.description && <p className="faint">{t("ocr.shows")}: {answer.ocr.description}</p>}
          <p className="ocr-text" dir="auto">{answer.ocr.text}</p>
        </Details>
      )}
      <div className="answer-body" dir="auto">
        {blocks.map((b, i) => (b.type === "card"
          ? <SourceCard key={`card-${i}`} card={cards[b.id]} num={b.n} compact={compact} />
          : (
            <p key={`p-${i}`}>
              {b.items.map((it) => (it.type === "text" ? <span key={it.key}>{it.text}</span> : (
                <button key={it.key} type="button" className="cite" title={cards[it.id].title}
                  aria-label={t("ans.cite", { n: fmtNum(it.n) })} onClick={() => openSource(it.id)}>{fmtNum(it.n)}</button>
              )))}
            </p>
          )))}
      </div>
      {(answer.notices || []).map((n, i) => {
        const warn = n.type === "fatwa" || n.type === "ocr";
        return <Notice key={i} kind={warn ? "warn" : ""} icon={warn ? "alert" : "info"}>{n.text}</Notice>;
      })}
      {!compact && numbers.size > 0 && (
        <section className="sources-used" aria-label={t("ans.used", { n: fmtNum(numbers.size) })}>
          <h4><Icon name="book" />{t("ans.used", { n: fmtNum(numbers.size) })}</h4>
          <ol className="src-mini">
            {[...numbers].filter(([id]) => cards[id]).map(([id, n]) => (
              <li key={id}>
                <span className="src-num">{fmtNum(n)}</span>
                <span className="badge badge-mint">{t(`src.${KIND_LABEL[cards[id].kind] || "term"}`)}</span>
                <span className="src-mini-text">
                  <button type="button" className="src-mini-title" onClick={() => openSource(id)}>{cards[id].title}</button>
                  <span className="faint small">{cards[id].source}</span>
                </span>
                <SourceLink url={cards[id].url} />
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}
