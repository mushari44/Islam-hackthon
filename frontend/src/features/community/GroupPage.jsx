// A group's conversation, with the @سبيلي assistant. Owner: Mushari (community).
import "./strings.js";
import "./community.css";
import { useEffect, useRef, useState } from "react";
import { api } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { navigate } from "../../core/router.jsx";
import { Icon, errorText, toast, usePolling } from "../../core/ui.jsx";
import { Answer } from "../rag/public.js";
import { NewMuslimPrompt } from "./NewMuslim.jsx";
import { Rules, openJoin } from "./shared.jsx";

const BOT_RX = /@\s?(سبيلي|سَبِيلي|sabeeli)/i;

/** One message bubble; `tools` lets the da'i console add moderation buttons. */
export function GroupMessage({ m, mine = false, tools = null }) {
  const { t, fmtAgo } = useI18n();
  if (m.author_type === "system") {   // e.g. the welcome when a member shares that they embraced Islam
    return (
      <div className="g-msg system">
        <p dir="auto">{m.text}</p>
        {tools}
      </div>
    );
  }
  const cls = m.author_type === "bot" ? "bot" : m.author_type === "daai" ? "leader" : mine ? "mine" : "member";
  let body;
  if (m.deleted) body = <p className="faint">{t("gr.deleted")}</p>;
  else if (m.author_type === "bot" && m.payload && m.payload.segments) body = <Answer answer={m.payload} compact />;
  else body = <p dir="auto">{m.text}</p>;
  return (
    <div className={`g-msg ${cls}`}>
      <div className="g-who">
        <strong>{mine ? t("gr.you") : m.author}</strong>
        {m.author_type === "daai" && <span className="badge badge-mint">{t("gr.leader")}</span>}
        {m.author_type === "bot" && <span className="badge badge-purple">{t("gr.bot")}</span>}
        {m.new_muslim && <span className="badge badge-mint">{t("gnm.badge")}</span>}
        <span className="faint">{fmtAgo(m.at)}</span>
      </div>
      {body}
      {m.needs_leader && !m.deleted && <span className="badge badge-warn">{t("gr.needs_leader")}</span>}
      {tools}
    </div>
  );
}

export default function GroupPage({ params }) {
  const { t, tn, lang, langName } = useI18n();
  const gid = Number(params.id);
  const [group, setGroup] = useState(null);
  const [error, setError] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loaded, setLoaded] = useState(false);       // the first poll answered, so an empty feed is really empty
  const [waitingBot, setWaitingBot] = useState(false);
  const [text, setText] = useState("");
  const [posting, setPosting] = useState(false);
  const [leaving, setLeaving] = useState(null);       // null, "ask" (the "leave this group?" step) or "busy"
  const lastId = useRef(0);
  const polls = useRef(0);
  const endRef = useRef(null);
  const inputRef = useRef(null);

  // A new group starts from an empty feed (the router can reuse this page for another id).
  useEffect(() => {
    lastId.current = 0; polls.current = 0;
    setMessages([]); setLoaded(false); setWaitingBot(false); setError(null); setLeaving(null);
  }, [gid]);

  const load = () => api.get(`/api/groups/${gid}?ui=${lang}`).then(setGroup).catch(setError);
  useEffect(() => { load(); }, [gid, lang]); // eslint-disable-line react-hooks/exhaustive-deps

  // New messages every poll; every 5th poll the newest page again, so messages the leader
  // deleted or answered since we fetched them update for everyone.
  const poll = async () => {
    const refresh = lastId.current > 0 && ++polls.current % 5 === 0;
    const msgs = await api.get(`/api/groups/${gid}/messages?after=${refresh ? 0 : lastId.current}`);
    setLoaded(true);
    if (!msgs.length) return;
    lastId.current = Math.max(lastId.current, ...msgs.map((m) => m.id));
    if (msgs.some((m) => m.author_type === "bot")) setWaitingBot(false);
    setMessages((list) => {
      const fresh = new Map(msgs.map((m) => [m.id, m]));
      const known = new Set(list.map((m) => m.id));
      return [...list.map((m) => fresh.get(m.id) || m), ...msgs.filter((m) => !known.has(m.id))];
    });
  };
  usePolling(poll, 3000, [gid], Boolean(group && group.membership));
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages.length, waitingBot]);
  // The box grows with the message, as on the Ask page.
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [text]);

  // Enter pressed twice before the first post returns must not send the message twice.
  const sending = useRef(false);
  const botTimer = useRef(null);
  useEffect(() => () => clearTimeout(botTimer.current), []);

  const post = async (e) => {
    e?.preventDefault();
    const v = text.trim();
    if (!v || sending.current) return;
    sending.current = true;
    setPosting(true);
    try {
      const res = await api.post(`/api/groups/${gid}/messages`, { text: v, lang });
      setText("");
      if (res.redacted) toast(t("gr.redacted"));
      if (BOT_RX.test(v) && v.replace(BOT_RX, "").trim()) {
        setWaitingBot(true);
        clearTimeout(botTimer.current);   // an earlier question's timer must not hide this one's indicator
        botTimer.current = setTimeout(() => setWaitingBot(false), 60000);
      }
      await poll();
    } catch (err) {
      const key = { abuse: "gr.err.abuse", too_fast: "gr.err.too_fast", too_long: "gr.err.too_long", muted: "gr.muted" }[err.detail];
      toast(key ? t(key) : errorText(err, t), "error");
      if (err.detail === "muted" || err.detail === "abuse") load();   // show the paused composer straight away
    } finally {
      sending.current = false;
      setPosting(false);
      inputRef.current?.focus();   // the Send button was just disabled, so focus would otherwise be lost
    }
  };

  const askBot = () => {
    if (!BOT_RX.test(text)) setText(`${lang === "ar" ? "@سبيلي" : "@sabeeli"} ${text}`);
    inputRef.current?.focus();
  };

  const leave = async () => {
    setLeaving("busy");
    try {
      await api.post(`/api/groups/${gid}/leave`, {});
      toast(t("gr.left"), "success");
      navigate("/community");
    } catch (err) {
      toast(errorText(err, t), "error");
      setLeaving("ask");
    }
  };

  if (error) {
    // A missing group can only go back; a network or server error can also be tried again.
    const transient = !error.status || error.status >= 500;
    return (
      <div className="empty">
        <p>{error.status === 404 ? t("gr.not_found") : errorText(error, t)}</p>
        <div className="row com-empty-actions">
          <a className="btn btn-sm" href="#/community"><Icon name="arrow" className="icon-back" />{t("gr.back")}</a>
          {transient && <button type="button" className="btn btn-ghost btn-sm" onClick={() => { setError(null); load(); }}>{t("common.retry")}</button>}
        </div>
      </div>
    );
  }
  if (!group) return <div className="skeleton" style={{ height: 160 }} />;
  const member = group.membership;

  return (
    <>
      <a className="btn btn-ghost btn-sm" href="#/community"><Icon name="arrow" className="icon-back" />{t("gr.back")}</a>
      <div className="page-head">
        <div className="row"><span className="badge">{langName(group.lang)}</span></div>
        <h1>{group.title}</h1>
        <p>{group.description}</p>
      </div>
      {member && <NewMuslimPrompt onChange={() => { lastId.current = 0; poll(); }} />}
      <div className="group-layout">
        <section className="group-main">
          {!member ? (
            <div className="empty">
              <Icon name="lock" size={46} />
              <p>{t("gr.not_member")}</p>
              <button type="button" className="btn btn-accent" onClick={() => openJoin(group, t, load)}>{t("com.join")}</button>
            </div>
          ) : (
            <>
              <div className="group-feed" aria-live="polite">
                {loaded && !messages.length && !waitingBot && (
                  <div className="empty group-empty"><Icon name="chat" size={46} /><p>{t("gr.empty")}</p></div>
                )}
                {messages.map((m) => <GroupMessage key={m.id} m={m} mine={m.member_id === member.id && m.author_type === "seeker"} />)}
                {waitingBot && <div className="g-msg bot pending"><div className="row"><div className="spinner" /><span className="muted">{t("gr.bot_thinking")}</span></div></div>}
                <div ref={endRef} />
              </div>
              <form className="composer" onSubmit={post}>
                <div className="composer-row">
                  <button type="button" className="btn btn-ghost btn-sm" disabled={member.muted} onClick={askBot}>
                    <Icon name="sparkle" />{t("gr.ask_bot")}
                  </button>
                  <textarea ref={inputRef} className="composer-input" rows={1} maxLength={1000} value={text} disabled={member.muted}
                    placeholder={member.muted ? t("gr.muted") : t("gr.ph")} aria-label={t("gr.ph")}
                    onChange={(e) => setText(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); post(); } }} />
                  <button type="submit" className="btn btn-primary composer-send" aria-label={t("common.send")} aria-busy={posting}
                    disabled={member.muted || posting}>
                    {posting ? <span className="spinner" aria-hidden="true" /> : <Icon name="send" className="icon-send" />}
                  </button>
                </div>
              </form>
            </>
          )}
        </section>
        <aside className="group-side">
          <div className="card stack">
            {group.leader && <div className="row"><Icon name="users" /><span>{group.leader.name} · {tn("com.members", group.members)}</span></div>}
            <h3>{t("gr.rules")}</h3>
            <Rules />
            {member && (leaving ? (
              <div className="leave-ask">
                <span className="small">{t("gr.leave_q")}</span>
                <div className="row">
                  <button type="button" className="btn btn-danger btn-sm" disabled={leaving === "busy"} aria-busy={leaving === "busy"} onClick={leave}>
                    {t("gr.leave_yes")}
                  </button>
                  <button type="button" className="btn btn-ghost btn-sm" autoFocus disabled={leaving === "busy"} onClick={() => setLeaving(null)}>
                    {t("gr.leave_stay")}
                  </button>
                </div>
              </div>
            ) : (
              <button type="button" className="btn btn-danger-soft btn-sm" onClick={() => setLeaving("ask")}>
                <Icon name="logout" />{t("gr.leave")}
              </button>
            ))}
          </div>
        </aside>
      </div>
    </>
  );
}
