// The Ask page: questions in text or with a photo, cited answers, feedback, "talk to a da'i". Owner: Mushari (RAG).
import "./strings.js";
import "./rag.css";
import { useEffect, useRef, useState } from "react";
import { api } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { Icon, Notice, errorText, openSheet, toast } from "../../core/ui.jsx";
import { useAccount } from "../account/public.js";
import { startReferral, useConversationCalls } from "../calls/public.jsx";
import { RelatedVideos } from "../videos/public.js";
import { Answer, LevelBadge } from "./Answer.jsx";

// The chat open in this tab: {conv, items}. `conv` is the server's conversation id (null until the first
// answer); every chat is also saved on the server, so the list below can reopen it.
const STORE = "sabeeli.chat";
const MAX_IMAGE = 5 * 1024 * 1024;

function loadOpen() {
  try {
    const v = JSON.parse(sessionStorage.getItem(STORE));
    if (Array.isArray(v)) return { conv: null, items: v };   // stored before conversations existed
    return v && Array.isArray(v.items) ? { conv: v.conv || null, items: v.items } : { conv: null, items: [] };
  } catch { return { conv: null, items: [] }; }
}
function saveOpen(conv, items) {
  try { sessionStorage.setItem(STORE, JSON.stringify({ conv, items: items.slice(-20) })); } catch { /* storage full */ }
}

/** Saved turns from the server (GET /api/conversations/{id}) as chat items. Restored answers skip related
 * videos, which are looked up afresh only for a live answer. */
function fromHistory(turns) {
  return turns.flatMap((x) => [
    { role: "user", text: x.question, hadImage: x.had_image },
    { role: "assistant", answer: { ...x.answer, restored: true } },
  ]);
}

/** Small preview kept in the chat history (the full photo is only sent to the server). */
function shrink(file) {
  return new Promise((resolve) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      const scale = Math.min(1, 360 / Math.max(img.width, img.height));
      const c = document.createElement("canvas");
      c.width = Math.round(img.width * scale);
      c.height = Math.round(img.height * scale);
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      resolve(c.toDataURL("image/jpeg", 0.75));
    };
    img.onerror = () => resolve(null);
    img.src = url;
  });
}

// Where the time went: every step in milliseconds, and each model call with its provider and speed.
const STEP_ORDER = ["ocr", "analyze", "quote_check", "retrieve", "bm25", "embed_query", "faiss", "fusion", "answer",
  "scripture_guard", "cards"];

function Timings({ timings }) {
  const { t, fmtNum } = useI18n();
  const steps = (timings && timings.steps_ms) || {};
  const names = Object.keys(steps).sort((x, y) => STEP_ORDER.indexOf(x) - STEP_ORDER.indexOf(y));
  if (!names.length) return null;
  const sub = new Set(["bm25", "embed_query", "faiss", "fusion"]);
  const fmt = (ms) => (ms >= 1000 ? t("unit.s", { n: fmtNum(Math.round(ms / 100) / 10) }) : `${fmtNum(Math.round(ms))} ms`);
  return (
    <div>
      <h3>{t("ask.trace_steps")}</h3>
      <ul className="trace-list trace-steps">
        {names.map((n) => {
          const calls = (timings.llm || []).filter((c) => c.step === n);
          return (
            <li key={n} className={sub.has(n) ? "sub" : ""}>
              <span>{t(`ask.step_${n}`)}</span> <strong>{fmt(steps[n])}</strong>
              {calls.map((c, i) => (
                <span key={i} className="faint small">{` · ${c.provider} · ${fmtNum(c.in || 0)}→${fmtNum(c.out || 0)} tokens`}
                  {c.tok_s ? ` · ${fmtNum(c.tok_s)} tok/s` : ""}</span>
              ))}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Trace({ ans }) {
  const { t, fmtNum } = useI18n();
  const tr = ans.trace || {};
  const a = tr.analysis || {};
  const queries = [...(a.queries_ar || []), ...(a.queries_en || [])];
  return (
    <div className="stack">
      <dl className="trace">
        <dt>{t("ask.trace_level")}</dt><dd><LevelBadge level={ans.level || "B"} /></dd>
        <dt>{t("ask.trace_mode")}</dt><dd>{ans.mode === "ai" ? t("ask.mode_ai") : t("ask.mode_sources")}</dd>
        {queries.length > 0 && <><dt>{t("ask.trace_queries")}</dt><dd className="row">{queries.map((q) => <span key={q} className="badge">{q}</span>)}</dd></>}
        {tr.cited_share != null && <><dt>{t("ask.trace_cited")}</dt><dd>{fmtNum(Math.round(tr.cited_share * 100))}%</dd></>}
        {tr.timings && tr.timings.total != null && <><dt>{t("ask.trace_time")}</dt><dd>{t("unit.s", { n: fmtNum(tr.timings.total) })}</dd></>}
      </dl>
      <Timings timings={tr.timings} />
      {(tr.retrieval || []).length > 0 && (
        <div>
          <h3>{t("ask.trace_found")}</h3>
          <ul className="trace-list">
            {tr.retrieval.map((r) => (
              <li key={r.id}>
                <code>{r.id}</code>{" "}
                {r.via === "quote" ? <span className="badge badge-mint">{t("ask.via_quote")}</span>
                  : r.via === "glossary" ? <span className="badge">{t("ask.via_glossary")}</span>
                    : r.via === "answer_slot" ? <span className="badge">{t("ask.via_answer")}</span>
                      : <span className="faint">{fmtNum(Math.round((r.coverage || 0) * 100))}%</span>}
                {r.dense != null && <span className="faint">{" · "}{t("ask.via_meaning")} {fmtNum(Math.round(r.dense * 100))}%</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Feedback({ turnId }) {
  const { t } = useI18n();
  const [done, setDone] = useState(false);
  if (!turnId) return <span />;
  if (done) return <span className="faint">{t("ask.thanks_fb")}</span>;
  const send = async (helpful) => {
    try { await api.post(`/api/ask/${turnId}/feedback`, { helpful }); } catch { /* best effort */ }
    setDone(true);
  };
  return (
    <div className="row answer-actions">
      <span className="faint">{t("ask.helpful")}</span>
      <button type="button" className="icon-btn" aria-label={t("ask.fb_yes")} title={t("ask.fb_yes")} onClick={() => send(true)}><Icon name="thumbUp" /></button>
      <button type="button" className="icon-btn" aria-label={t("ask.fb_no")} title={t("ask.fb_no")} onClick={() => send(false)}><Icon name="thumbDown" /></button>
    </div>
  );
}

// Related videos pass a strict check of their own, so they can help even when the sources fell short;
// never for small talk or personal questions (level D: a video next to "are we still married?" reads
// like a ruling on the person's case, whatever the answer's fatwa notice says).
const VIDEO_KINDS = new Set(["answer", "sources", "abstain"]);
const showVideos = (ans) => VIDEO_KINDS.has(ans.kind) && ans.level !== "D";
// Replies that carry no content of their own: a content-level badge on them would mean nothing.
const NO_LEVEL_KINDS = new Set(["greeting", "thanks", "clarify", "off_topic", "request_human", "empty"]);

function BotMessage({ ans, question, conv }) {
  const { t, lang } = useI18n();
  const analysis = (ans.trace && ans.trace.analysis) || {};
  const hints = [...(analysis.queries_ar || []), ...(analysis.queries_en || [])];
  return (
    <div className="msg msg-bot">
      <div className="msg-avatar" aria-hidden="true"><Icon name="sparkle" size={20} /></div>
      <div className="msg-body">
        {ans.level && !NO_LEVEL_KINDS.has(ans.kind) && (
          <div className="msg-meta">
            <LevelBadge level={ans.level} />
            {ans.mode !== "ai" && <span className="badge badge-warn">{t("mode.sources_only")}</span>}
          </div>
        )}
        <Answer answer={ans} />
        {showVideos(ans) && !ans.restored && <RelatedVideos question={question} hints={hints} lang={ans.lang || lang} />}
        <div className="row spread answer-foot">
          <Feedback turnId={ans.turn_id} />
          <div className="row">
            {ans.trace && (
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => openSheet({ title: t("ask.trace"), render: () => <Trace ans={ans} /> })}>
                <Icon name="layers" />{t("ask.how")}
              </button>
            )}
            <button type="button" className={`btn btn-sm ${ans.suggest_daai ? "btn-accent" : ""}`} onClick={() => startReferral({ lang, t, conversationId: ans.conversation_id || conv })}>
              <Icon name="talk" />{t("ask.talk")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function UserMessage({ item }) {
  const { t } = useI18n();
  return (
    <div className="msg msg-user">
      <div className="msg-body">
        {item.image && <img className="msg-photo" src={item.image} alt={t("ask.photo_attached")} />}
        {item.hadImage && !item.image && <p className="faint small">{t("ask.photo_attached")}</p>}
        {item.text && <p dir="auto">{item.text}</p>}
      </div>
    </div>
  );
}

/** The seeker's chats, newest first: open one, delete one, see which da'i they talked to about it. */
function ChatList({ convs, current, calls, saved, onOpen, onDelete, inSheet = false }) {
  const { t, lang, fmtDate } = useI18n();
  const [sure, setSure] = useState(null);
  if (!convs) return null;
  return (
    <div className={inSheet ? "stack chat-list" : "card stack chat-list"}>
      {!inSheet && <h3>{t("ask.chats")}</h3>}
      {convs.length === 0 && <p className="small muted">{t("ask.chats_none")}</p>}
      {convs.length > 0 && (
        <ul className="chat-items">
          {convs.map((c) => {
            const daai = calls[c.id] && calls[c.id][0].daai;
            return (
              <li key={c.id} className={c.id === current ? "current" : ""}>
                <button type="button" className="chat-open" aria-current={c.id === current ? "true" : undefined} onClick={() => onOpen(c.id)}>
                  <span className="chat-title" dir="auto">{c.title || t("ask.photo_attached")}</span>
                  <span className="small faint">{fmtDate(c.updated_at, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" })}</span>
                  {daai && <span className="badge badge-mint">{t("ask.talked_with", { name: lang === "ar" ? daai.name : daai.name_en || daai.name })}</span>}
                </button>
                {sure === c.id ? (
                  <button type="button" className="btn btn-sm btn-danger" onClick={() => { setSure(null); onDelete(c.id); }}>{t("ask.delete_sure")}</button>
                ) : (
                  <button type="button" className="icon-btn" aria-label={t("ask.delete_chat")} title={t("ask.delete_chat")} onClick={() => setSure(c.id)}><Icon name="trash" /></button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <p className="small faint">{saved ? <><Icon name="lock" size={14} /> {t("ask.saved_note")}</> : <>{t("ask.anon_note")} <a href="#/account">{t("ask.sign_in")}</a></>}</p>
    </div>
  );
}

/** Shown above an opened chat the seeker already took to a da'i: who it was, and a way to call them again. */
function TalkedNote({ calls }) {
  const { t, lang } = useI18n();
  if (!calls || !calls.length) return null;
  const { daai, lang: callLang } = calls[0];
  const name = lang === "ar" ? daai.name : daai.name_en || daai.name;
  return (
    <Notice kind="mint" icon="talk">
      <span>{t("ask.talked_note", { name })}</span>{" "}
      {daai.callable && <a href={`#/talk?daai=${daai.id}&lang=${callLang}`}>{t("ask.call_again", { name })}</a>}
    </Notice>
  );
}

export default function AskPage({ query = {} }) {
  const { t, lang } = useI18n();
  // A question typed on the home page (#/ask?q=...) starts a new chat instead of joining the open one.
  const [open] = useState(() => (query.q ? { conv: null, items: [] } : loadOpen()));
  const [conv, setConv] = useState(open.conv);
  const [chat, setChat] = useState(open.items);
  const [convs, setConvs] = useState(null);
  const [saved, setSaved] = useState(false);
  const [listKey, setListKey] = useState(0);      // bump to reload the chat list
  const { account } = useAccount();
  const username = account && account.username;
  const calls = useConversationCalls(`${username}:${listKey}`);
  const [text, setText] = useState("");
  const [photo, setPhoto] = useState(null);       // {file, url}
  const [busy, setBusy] = useState(false);
  const inputRef = useRef(null);
  const fileRef = useRef(null);
  const endRef = useRef(null);

  useEffect(() => { saveOpen(conv, chat); }, [conv, chat]);
  const mounted = useRef(true);
  useEffect(() => () => { mounted.current = false; }, []);
  // The photo preview's object URL is released once it is replaced, sent or the page closes.
  useEffect(() => () => { if (photo) URL.revokeObjectURL(photo.url); }, [photo]);
  useEffect(() => {
    let alive = true;   // an older reply (e.g. from before signing in) must not replace a newer list
    api.get("/api/conversations")
      .then((r) => { if (alive) { setConvs(r.conversations); setSaved(r.saved); } })
      .catch(() => { if (alive) setConvs([]); });
    return () => { alive = false; };
  }, [username, listKey]);
  // A chat opened in this tab before a reload, whose items weren't kept here: fetch it again.
  useEffect(() => {
    if (open.conv && !open.items.length) openChat(open.conv, true);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const openChat = async (id, quiet = false) => {
    if (busy) return;
    try {
      const c = await api.get(`/api/conversations/${id}`);
      setConv(c.id);
      setChat(fromHistory(c.turns));
      setTimeout(() => endRef.current?.scrollIntoView({ block: "end" }), 50);
    } catch (err) {
      if (!quiet) toast(errorText(err, t), "error");   // e.g. an anonymous chat older than 24 hours
      if (id === conv) newChat();
      setListKey((k) => k + 1);
    }
  };
  const newChat = () => { setConv(null); setChat([]); setText(""); setPhoto(null); inputRef.current?.focus(); };
  const deleteChat = async (id) => {
    try {
      await api.del(`/api/conversations/${id}`);
      if (id === conv) newChat();
      toast(t("ask.chat_deleted"), "success");
    } catch (err) { toast(errorText(err, t), "error"); }
    setListKey((k) => k + 1);
  };
  useEffect(() => { inputRef.current?.focus(); }, []);
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [text]);

  const submit = async (override) => {
    const q = (override ?? text).trim();
    if (busy || (!q && !photo)) return;
    setBusy(true);
    const current = photo;
    const thumb = current ? await shrink(current.file) : null;
    setChat((c) => [...c, { role: "user", text: q, image: thumb }]);
    setText("");
    setPhoto(null);
    setTimeout(() => endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }), 50);
    const form = new FormData();
    form.append("question", q);
    form.append("lang", lang);
    if (conv) form.append("conversation_id", String(conv));
    if (current) form.append("image", current.file);
    try {
      const answer = await api.form("/api/ask", form);
      if (!mounted.current) {   // the seeker left the page while waiting: keep the answer for their return
        const kept = loadOpen();
        saveOpen(answer.conversation_id, [...kept.items, { role: "assistant", answer }]);
        return;
      }
      setConv(answer.conversation_id);
      setChat((c) => [...c, { role: "assistant", answer }]);
      setListKey((k) => k + 1);
    } catch (err) {
      toast(errorText(err, t), "error");
      setChat((c) => c.slice(0, -1));
      setText(q);
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  };

  // Ask the home page's question once, then drop it from the address so a reload doesn't ask it again.
  const asked = useRef(false);
  useEffect(() => {
    const q = (query.q || "").trim();
    if (!q || asked.current) return;
    asked.current = true;
    window.history.replaceState(null, "", "#/ask");
    submit(q.slice(0, 1000));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const onFile = (e) => {
    const f = e.target.files[0];
    e.target.value = "";
    if (!f) return;
    if (f.size > MAX_IMAGE) { toast(t("ask.too_big"), "error"); return; }
    setPhoto({ file: f, url: URL.createObjectURL(f) });
  };

  return (
    <>
      <div className="page-head row spread">
        <div><h1>{t("ask.title")}</h1><p>{t("ask.lead")}</p></div>
        <div className="row">
          {/* on a phone the list sits below the chat, so it also opens from here */}
          {convs && convs.length > 0 && (
            <button type="button" className="btn btn-sm btn-ghost chats-btn" disabled={busy} onClick={() => openSheet({
              title: t("ask.chats"),
              render: (close) => <ChatList inSheet convs={convs} current={conv} calls={calls} saved={saved}
                onOpen={(id) => { close(); openChat(id); }} onDelete={(id) => { close(); deleteChat(id); }} />,
            })}><Icon name="chat" />{t("ask.chats")}</button>
          )}
          {chat.length > 0 && <button type="button" className="btn btn-sm" disabled={busy} onClick={newChat}><Icon name="plus" />{t("ask.clear")}</button>}
        </div>
      </div>
      <div className="ask-layout">
        <section className="ask-main">
          {conv && <TalkedNote calls={calls[conv]} />}
          <div className="thread" aria-live="polite">
            {chat.map((item, i) => (item.role === "user" ? <UserMessage key={i} item={item} />
              : <BotMessage key={i} ans={item.answer} conv={conv} question={(chat[i - 1] && chat[i - 1].text) || ""} />))}
            {busy && (
              <div className="msg msg-bot pending">
                <div className="msg-avatar"><Icon name="sparkle" size={20} /></div>
                <div className="msg-body"><div className="row"><div className="spinner" /><span className="muted">{t("ask.thinking")}</span></div></div>
              </div>
            )}
            <div ref={endRef} />
          </div>
          <form className="composer" onSubmit={(e) => { e.preventDefault(); submit(); }}>
            {photo && (
              <div className="composer-preview">
                <img src={photo.url} alt={t("ask.photo_attached")} />
                <button type="button" className="icon-btn" aria-label={t("ask.remove_photo")} onClick={() => setPhoto(null)}><Icon name="x" /></button>
              </div>
            )}
            <div className="composer-row">
              <button type="button" className="icon-btn" aria-label={t("ask.photo")} title={t("ask.photo")} onClick={() => fileRef.current?.click()}>
                <Icon name="camera" size={20} />
              </button>
              <textarea ref={inputRef} className="composer-input" rows={1} maxLength={2000} value={text}
                placeholder={t("ask.placeholder")} aria-label={t("ask.placeholder")} onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit(); } }} />
              <button type="submit" className="btn btn-primary composer-send" aria-label={t("ask.send")} disabled={busy}><Icon name="send" /></button>
            </div>
            <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp,image/gif" hidden onChange={onFile} />
          </form>
        </section>
        <aside className="ask-side stack">
          <ChatList convs={convs} current={conv} calls={calls} saved={saved} onOpen={openChat} onDelete={deleteChat} />
          <div className="card stack">
            <p className="small muted">{t("ask.side_cta")}</p>
            <a className="btn btn-accent" href="#/talk"><Icon name="talk" />{t("nav.talk")}</a>
          </div>
        </aside>
      </div>
    </>
  );
}
