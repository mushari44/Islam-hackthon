// The live call: audio (WebRTC) + text chat + mute/end. Used by the seeker and by the da'i. Owner: Eman (calls).
import "./strings.js";
import "./calls.css";
import { useEffect, useRef, useState } from "react";
import { api } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { Icon, Notice } from "../../core/ui.jsx";
import { createRoom } from "./room.js";

export function useClock(running = true) {
  const [sec, setSec] = useState(0);
  useEffect(() => {
    if (!running) return undefined;
    const start = Date.now();
    const id = setInterval(() => setSec(Math.floor((Date.now() - start) / 1000)), 1000);
    return () => clearInterval(id);
  }, [running]);
  return sec;
}

export function Clock({ sec }) {
  const { fmtNum } = useI18n();
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return <span className="timer" dir="ltr">{fmtNum(m)}:{s < 10 ? fmtNum(0) : ""}{fmtNum(s)}</span>;
}

/**
 * props: callId, role ("seeker" | "daai"), token, title, onEnded(), historyPath (seeker only)
 */
export default function CallPanel({ callId, role, token, title, onEnded, historyPath }) {
  const { t } = useI18n();
  const [state, setState] = useState("connecting");
  const [problem, setProblem] = useState(null);   // "no-mic" | "failed"
  const [messages, setMessages] = useState([]);
  const [muted, setMuted] = useState(false);
  const [draft, setDraft] = useState("");
  const room = useRef(null);
  const logRef = useRef(null);
  const sec = useClock(true);
  const endedRef = useRef(onEnded);
  endedRef.current = onEnded;

  useEffect(() => {
    let cancelled = false;
    if (historyPath) api.get(historyPath).then((h) => !cancelled && setMessages(h)).catch(() => {});
    createRoom({
      callId, role, token,
      onState: (s) => {
        if (s === "no-mic" || s === "failed") setProblem(s);
        else setState(s);
        if (s === "connected") setProblem((p) => (p === "failed" ? null : p));
      },
      onChat: (m) => setMessages((list) => (list.some((x) => x.id === m.id) ? list : [...list, m])),
      onEnded: () => endedRef.current?.(),
    }).then((r) => { if (cancelled) r.close(); else room.current = r; });
    return () => { cancelled = true; room.current?.close(); room.current = null; };
  }, [callId, role, token, historyPath]);

  useEffect(() => { logRef.current?.lastElementChild?.scrollIntoView({ block: "end" }); }, [messages]);

  const stateLabel = {
    connected: t("talk.connected"), "peer-left": t("talk.peer_left"), refused: t("talk.refused"),
  }[state] || t("talk.connecting");

  const send = (e) => {
    e.preventDefault();
    const v = draft.trim();
    if (v && room.current) { room.current.sendChat(v); setDraft(""); }
  };
  const toggleMute = () => { const next = !muted; setMuted(next); room.current?.mute(next); };
  const end = () => {
    room.current?.end();
    // the socket may not be open yet (mic prompt): end the call on the server too
    if (role === "seeker") api.post(`/api/calls/${callId}/cancel`, {}).catch(() => {});
    onEnded?.();
  };

  return (
    <div className="call-layout">
      <div className="card call-stage">
        <div className="call-avatar"><Icon name="talk" size={38} /></div>
        <h3>{title}</h3>
        <div className="row" style={{ justifyContent: "center" }}>
          <span className="call-state">{stateLabel}</span><span className="faint">·</span><Clock sec={sec} />
        </div>
        {problem === "no-mic" && <Notice kind="warn" icon="micOff">{t("talk.no_mic")}</Notice>}
        {problem === "failed" && <Notice kind="warn" icon="alert">{t("talk.failed")}</Notice>}
        <div className="row call-controls">
          <button type="button" className="btn call-btn" onClick={toggleMute}>
            <Icon name={muted ? "micOff" : "mic"} />{muted ? t("talk.unmute") : t("talk.mute")}
          </button>
          <button type="button" className="btn btn-danger call-btn" onClick={end}><Icon name="phoneOff" />{t("talk.end")}</button>
        </div>
      </div>
      <div className="card call-chat">
        <h3>{t("talk.chat")}</h3>
        <div className="call-chat-log" aria-live="polite" ref={logRef}>
          {messages.map((m) => (
            <div key={m.id} className={`chat-line ${m.sender === role ? "mine" : "theirs"}`}>
              <span className="faint">{m.sender === role ? t("talk.you") : m.sender === "daai" ? t("talk.daai") : t("talk.seeker")}</span>
              <p dir="auto">{m.text}</p>
            </div>
          ))}
        </div>
        <form className="row" onSubmit={send}>
          <input className="input" style={{ flex: 1 }} value={draft} maxLength={1000} placeholder={t("talk.chat_ph")}
            aria-label={t("talk.chat")} onChange={(e) => setDraft(e.target.value)} />
          <button type="submit" className="btn btn-primary" aria-label={t("common.send")}><Icon name="send" /></button>
        </form>
      </div>
    </div>
  );
}
