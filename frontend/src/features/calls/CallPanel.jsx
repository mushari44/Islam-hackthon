// The live call: audio (WebRTC) + text chat + mute/end. Used by the seeker and by the da'i. Owner: Eman (calls).
import "./strings.js";
import "./calls.css";
import { useEffect, useRef, useState } from "react";
import { api } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { Icon, Notice, toast } from "../../core/ui.jsx";
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

/** Asks the browser to confirm ("Leave site?") before the page is closed or reloaded while `active`. */
export function useLeaveWarning(active) {
  useEffect(() => {
    if (!active) return undefined;
    const warn = (e) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [active]);
}

export const MIC_PROBLEMS = { "mic-blocked": "talk.mic_blocked", "mic-missing": "talk.mic_missing", "mic-busy": "talk.mic_busy", "no-mic": "talk.no_mic" };
const PEER_GONE_MS = 2 * 60 * 1000;   // after this long without the other person, offer the seeker to end the call

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
  const [problem, setProblem] = useState(null);   // "failed" (audio couldn't connect)
  const [micProblem, setMicProblem] = useState(null);   // a key of MIC_PROBLEMS, or null when the mic works
  const [peerAway, setPeerAway] = useState(false);   // the other person dropped and hasn't come back yet
  const [peerGone, setPeerGone] = useState(false);   // ...for more than PEER_GONE_MS
  const [retrying, setRetrying] = useState(false);
  const [messages, setMessages] = useState([]);
  const [muted, setMuted] = useState(false);
  const [draft, setDraft] = useState("");
  const [canSend, setCanSend] = useState(false);   // the signalling socket is open
  const [confirmEnd, setConfirmEnd] = useState(false);
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
        if (cancelled) return;
        if (MIC_PROBLEMS[s]) setMicProblem(s);
        else if (s === "mic-ok") setMicProblem(null);
        else if (s === "failed") setProblem(s);
        else if (s === "peer-joined") setPeerAway(false);
        else setState(s);
        if (s === "peer-left") setPeerAway(true);
        if (s === "connected") { setProblem(null); setPeerAway(false); }
      },
      onChat: (m) => setMessages((list) => (list.some((x) => x.id === m.id) ? list : [...list, m])),
      onEnded: () => endedRef.current?.(),
      onSocket: (open) => { if (!cancelled) setCanSend(open); },
    }).then((r) => { if (cancelled) r.close(); else room.current = r; });
    return () => { cancelled = true; room.current?.close(); room.current = null; };
  }, [callId, role, token, historyPath]);

  // The da'i's end button asks for a second tap; the question goes away by itself after a few seconds.
  useEffect(() => {
    if (!confirmEnd) return undefined;
    const id = setTimeout(() => setConfirmEnd(false), 3000);
    return () => clearTimeout(id);
  }, [confirmEnd]);

  useEffect(() => {
    setPeerGone(false);
    if (!peerAway) return undefined;
    const id = setTimeout(() => setPeerGone(true), PEER_GONE_MS);
    return () => clearTimeout(id);
  }, [peerAway]);

  // The seeker is warned before closing the page mid-call; the da'i's console has its own End button flow.
  useLeaveWarning(role === "seeker" && state !== "refused" && state !== "other-tab");

  useEffect(() => { logRef.current?.lastElementChild?.scrollIntoView({ block: "end" }); }, [messages]);

  const stateLabel = {
    connected: t("talk.connected"), "peer-left": t("talk.peer_left"), refused: t("talk.refused"),
    reconnecting: t("talk.reconnecting"), "other-tab": t("talk.other_tab"),
  }[state] || t("talk.connecting");

  const send = (e) => {
    e.preventDefault();
    const v = draft.trim();
    if (!v) return;
    // Clear the box only once the message is really on its way, so nothing typed is lost.
    if (room.current?.sendChat(v)) setDraft("");
    else toast(t("talk.not_sent"), "error");
  };
  const retryMic = async () => {
    setRetrying(true);
    try { await room.current?.retryMic(); } finally { setRetrying(false); }
  };
  const toggleMute = () => { const next = !muted; setMuted(next); room.current?.mute(next); };
  const end = () => {
    room.current?.end();
    // the socket may not be open yet (mic prompt): end the call on the server too
    if (role === "seeker") api.post(`/api/calls/${callId}/cancel`, {}).catch(() => {});
    onEnded?.();
  };
  // One tap for the seeker, always: they must be able to leave at any moment. The da'i confirms with a second tap.
  const onEndClick = () => {
    if (role === "daai" && !confirmEnd) setConfirmEnd(true);
    else end();
  };

  return (
    <div className="call-layout">
      <div className="card call-stage">
        <div className="call-avatar"><Icon name="talk" size={38} /></div>
        <h3>{title}</h3>
        <div className="row" style={{ justifyContent: "center" }}>
          <span className="call-state" role="status">{stateLabel}</span><span className="faint">·</span><Clock sec={sec} />
        </div>
        <div role="status" className="stack call-notices">
          {micProblem && (
            <Notice kind="warn" icon="micOff">
              <div className="stack">
                <span>{t(MIC_PROBLEMS[micProblem])}</span>
                <div className="row"><button type="button" className="btn btn-sm" disabled={retrying} onClick={retryMic}><Icon name="mic" />{t("talk.mic_retry")}</button></div>
              </div>
            </Notice>
          )}
          {problem === "failed" && <Notice kind="warn" icon="alert">{t("talk.failed")}</Notice>}
          {role === "seeker" && peerGone && (
            <Notice kind="warn" icon="alert">
              <div className="stack">
                <span>{t("talk.peer_gone")}</span>
                <div className="row"><button type="button" className="btn btn-danger btn-sm" onClick={end}><Icon name="phoneOff" />{t("talk.end")}</button></div>
              </div>
            </Notice>
          )}
        </div>
        <div className="row call-controls">
          <button type="button" className="btn call-btn" onClick={toggleMute} disabled={Boolean(micProblem)} aria-pressed={muted}>
            <Icon name={muted ? "micOff" : "mic"} />{muted ? t("talk.unmute") : t("talk.mute")}
          </button>
          <button type="button" className="btn btn-danger call-btn" onClick={onEndClick}>
            <Icon name="phoneOff" /><span aria-live="polite">{confirmEnd ? t("talk.end_again") : t("talk.end")}</span>
          </button>
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
          <button type="submit" className="btn btn-primary" aria-label={t("common.send")} disabled={!canSend}><Icon name="send" className="icon-send" /></button>
        </form>
      </div>
    </div>
  );
}
