// The live call: audio (WebRTC) + text chat + mute/end. Used by the seeker and by the da'i. Owner: Eman (calls).
import "./strings.js";
import "./calls.css";
import { useEffect, useRef, useState } from "react";
import { api } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { Icon, Notice } from "../../core/ui.jsx";
import { canPickSpeaker } from "./audio.js";
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
  const [soundBlocked, setSoundBlocked] = useState(false);
  const [quality, setQuality] = useState("good");
  const [devices, setDevices] = useState({ inputs: [], outputs: [], mic: "" });
  const [speakerId, setSpeakerId] = useState("");
  const levelRef = useRef(null);
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
        else if (s === "mic-ok") setProblem((p) => (p === "no-mic" ? null : p));
        else setState(s);
        if (s === "connected") setProblem((p) => (p === "failed" ? null : p));
      },
      onAudio: ({ blocked }) => setSoundBlocked(blocked),
      onDevices: setDevices,
      onQuality: setQuality,
      onChat: (m) => setMessages((list) => (list.some((x) => x.id === m.id) ? list : [...list, m])),
      onEnded: () => endedRef.current?.(),
    }).then((r) => { if (cancelled) r.close(); else room.current = r; });
    return () => { cancelled = true; room.current?.close(); room.current = null; };
  }, [callId, role, token, historyPath]);

  // Microphone level bar, drawn straight to the DOM so it doesn't re-render the panel 60 times a second.
  useEffect(() => {
    let id;
    const tick = () => {
      const lv = room.current?.level() || 0;
      if (levelRef.current) levelRef.current.style.transform = `scaleX(${lv.toFixed(3)})`;
      id = requestAnimationFrame(tick);
    };
    id = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(id);
  }, []);

  useEffect(() => { logRef.current?.lastElementChild?.scrollIntoView({ block: "end" }); }, [messages]);

  const stateLabel = {
    connected: t("talk.connected"), "peer-left": t("talk.peer_left"), refused: t("talk.refused"),
  }[state] || t("talk.connecting");

  const send = (e) => {
    e.preventDefault();
    const v = draft.trim();
    if (v && room.current) { room.current.sendChat(v); setDraft(""); }
  };
  const toggleMute = () => { const next = !muted; setMuted(next); room.current?.unlock(); room.current?.mute(next); };
  const pickMic = (id) => { room.current?.unlock(); room.current?.setMic(id); };
  const pickSpeaker = (id) => { setSpeakerId(id); room.current?.setSpeaker(id); };
  const deviceName = (d, i, kind) => d.label || `${t(kind)} ${i + 1}`;
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
        {soundBlocked && (
          <button type="button" className="btn btn-primary call-sound" onClick={() => room.current?.unlock()}>
            <Icon name="talk" />{t("talk.sound_off")}
          </button>
        )}
        {problem === "no-mic" && (
          <Notice kind="warn" icon="micOff">
            {t("talk.no_mic")}{" "}
            <button type="button" className="btn btn-sm" onClick={() => room.current?.retryMic()}>{t("talk.retry_mic")}</button>
          </Notice>
        )}
        {problem === "failed" && <Notice kind="warn" icon="alert">{t("talk.failed")}</Notice>}
        {!problem && quality === "poor" && state === "connected" && <Notice kind="warn" icon="alert">{t("talk.poor")}</Notice>}
        {problem !== "no-mic" && (
          <div className="mic-level" role="img" aria-label={t("talk.mic_level")}><span ref={levelRef} /></div>
        )}
        <div className="row call-controls">
          <button type="button" className="btn call-btn" onClick={toggleMute}>
            <Icon name={muted ? "micOff" : "mic"} />{muted ? t("talk.unmute") : t("talk.mute")}
          </button>
          <button type="button" className="btn btn-danger call-btn" onClick={end}><Icon name="phoneOff" />{t("talk.end")}</button>
        </div>
        {(devices.inputs.length > 1 || (canPickSpeaker && devices.outputs.length > 1)) && (
          <div className="call-devices">
            {devices.inputs.length > 1 && (
              <label className="field">
                <span className="small muted">{t("talk.mic_label")}</span>
                <select className="input" value={devices.inputs.some((d) => d.deviceId === devices.mic) ? devices.mic : ""}
                  onChange={(e) => pickMic(e.target.value)}>
                  {!devices.inputs.some((d) => d.deviceId === "default") && <option value="">{t("talk.default_device")}</option>}
                  {devices.inputs.map((d, i) => <option key={d.deviceId} value={d.deviceId}>{deviceName(d, i, "talk.mic_label")}</option>)}
                </select>
              </label>
            )}
            {canPickSpeaker && devices.outputs.length > 1 && (
              <label className="field">
                <span className="small muted">{t("talk.speaker_label")}</span>
                <select className="input" value={speakerId} onChange={(e) => pickSpeaker(e.target.value)}>
                  {!devices.outputs.some((d) => d.deviceId === "default") && <option value="">{t("talk.default_device")}</option>}
                  {devices.outputs.map((d, i) => (
                    <option key={d.deviceId} value={d.deviceId === "default" ? "" : d.deviceId}>{deviceName(d, i, "talk.speaker_label")}</option>
                  ))}
                </select>
              </label>
            )}
          </div>
        )}
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
