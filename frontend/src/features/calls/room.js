// WebRTC audio room + in-call chat over the signalling WebSocket. Owner: Eman (calls).
// The da'i sends the offer once both people are in the room; the seeker answers.
import { api, wsUrl } from "../../core/api.js";

const AUDIO = { audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } };
const RETRY_MS = [1000, 2000, 4000, 8000, 10000];   // signalling reconnect backoff, capped at 10 s

/** Names the microphone problem, so the page can say how to fix it instead of a generic "no mic". */
export function micProblem(err) {
  const name = err && err.name;
  if (name === "NotAllowedError" || name === "SecurityError") return "mic-blocked";
  if (name === "NotFoundError" || name === "OverconstrainedError") return "mic-missing";
  if (name === "NotReadableError" || name === "AbortError") return "mic-busy";
  return "no-mic";
}

/** Asks for the microphone. Resolves to { stream } or { problem } (see micProblem). */
export async function requestMic() {
  try {
    if (!navigator.mediaDevices?.getUserMedia) return { problem: "no-mic" };
    return { stream: await navigator.mediaDevices.getUserMedia(AUDIO) };
  } catch (err) {
    return { problem: micProblem(err) };
  }
}

// onState(s): a connection state, "reconnecting", "other-tab", "refused", "peer-left", "peer-joined",
// "mic-ok" or a mic problem. onSocket(open) says whether text messages can be sent right now.
export async function createRoom({ callId, role, token, onState = () => {}, onChat = () => {}, onEnded = () => {}, onSocket = () => {} }) {
  let cfg = { iceServers: [{ urls: ["stun:stun.l.google.com:19302"] }], iceTransportPolicy: "all" };
  try { cfg = await api.pGet("/api/rtc-config"); } catch { /* use the default */ }

  const pc = new RTCPeerConnection({ iceServers: cfg.iceServers, iceTransportPolicy: cfg.iceTransportPolicy });
  let local = null;
  let muted = false;
  const first = await requestMic();
  if (first.stream) {
    local = first.stream;
    local.getTracks().forEach((track) => pc.addTrack(track, local));
  } else {
    onState(first.problem);
    pc.addTransceiver("audio", { direction: "recvonly" });
  }

  const remoteAudio = new Audio();
  remoteAudio.autoplay = true;
  pc.ontrack = (e) => { remoteAudio.srcObject = e.streams[0]; remoteAudio.play().catch(() => {}); };

  const pendingIce = [];
  let closed = false;
  let ws = null;
  let everJoined = false;   // a socket that never joined was refused; one that did may come back
  let attempt = 0;
  let retryTimer = null;
  /** True only when the message went out: a closed or still-opening socket drops it. */
  const send = (msg) => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(JSON.stringify(msg));
    return true;
  };

  pc.onicecandidate = (e) => { if (e.candidate) send({ type: "ice", candidate: e.candidate.toJSON() }); };
  pc.onconnectionstatechange = () => onState(pc.connectionState);
  const broken = () => pc.connectionState === "failed" || pc.connectionState === "disconnected";

  async function makeOffer(restart = false) {
    const offer = await pc.createOffer({ iceRestart: restart });
    await pc.setLocalDescription(offer);
    send({ type: "offer", sdp: pc.localDescription });
  }

  async function onMessage(ev) {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }
    try {
      switch (msg.type) {
        case "joined":
          everJoined = true;
          attempt = 0;
          onState(pc.connectionState === "connected" ? "connected" : "waiting-peer");
          if (msg.present.includes(role === "daai" ? "seeker" : "daai")) onState("peer-joined");
          if (role === "daai" && msg.present.includes("seeker")) await makeOffer(broken());
          break;
        case "peer-joined":
          onState("peer-joined");
          if (role === "daai") await makeOffer(broken());
          break;
        case "offer":
          await pc.setRemoteDescription(msg.sdp);
          await pc.setLocalDescription(await pc.createAnswer());
          send({ type: "answer", sdp: pc.localDescription });
          while (pendingIce.length) await pc.addIceCandidate(pendingIce.shift());
          break;
        case "answer":
          await pc.setRemoteDescription(msg.sdp);
          while (pendingIce.length) await pc.addIceCandidate(pendingIce.shift());
          break;
        case "ice":
          if (pc.remoteDescription) await pc.addIceCandidate(msg.candidate);
          else pendingIce.push(msg.candidate);
          break;
        case "chat":
          onChat(msg);
          break;
        case "peer-left":
          onState("peer-left");
          break;
        case "ended":
          onEnded(msg.by);
          cleanup();
          break;
        default:
      }
    } catch (err) {
      console.warn("signalling error", err);
    }
  }

  // The socket drops on a network blip or a phone switching networks: come back while the call is still on.
  function connect() {
    retryTimer = null;
    const sock = new WebSocket(wsUrl(`/ws/call/${callId}?role=${role}&token=${encodeURIComponent(token)}`));
    ws = sock;
    sock.addEventListener("open", () => onSocket(true));
    sock.addEventListener("message", onMessage);
    sock.addEventListener("close", (ev) => {
      if (sock !== ws) return;
      onSocket(false);
      if (closed) return;
      if (ev.code === 4001) { onState("other-tab"); cleanup(); return; }   // the same person opened it elsewhere
      if (ev.code === 4003 || !everJoined) { onState("refused"); return; }   // not (or no longer) this call
      onState("reconnecting");
      retryTimer = setTimeout(connect, RETRY_MS[Math.min(attempt, RETRY_MS.length - 1)]);
      attempt += 1;
    });
  }
  connect();

  /** Puts a new microphone track on the call: the existing audio sender if there is one, else a new one. */
  async function useMic(stream) {
    const track = stream.getAudioTracks()[0];
    track.enabled = !muted;
    const audio = pc.getTransceivers().filter((x) => x.receiver.track?.kind === "audio" && !x.stopped);
    const tr = audio.find((x) => x.mid !== null) || audio[0];
    let renegotiate = false;
    if (tr) {
      await tr.sender.replaceTrack(track);
      if (tr.direction !== "sendrecv") { tr.direction = "sendrecv"; renegotiate = true; }
    } else {
      pc.addTrack(track, stream);
      renegotiate = true;
    }
    if (local) local.getTracks().forEach((t) => t.stop());
    local = stream;
    // Either side may offer: the other answers. Only when a call is already set up and nothing is in flight.
    if (renegotiate && pc.remoteDescription && pc.signalingState === "stable") await makeOffer();
  }

  function cleanup() {
    if (closed) return;
    closed = true;
    clearTimeout(retryTimer);
    try { ws.close(); } catch { /* already closed */ }
    pc.close();
    if (local) local.getTracks().forEach((track) => track.stop());
    remoteAudio.srcObject = null;
  }

  return {
    get hasMic() { return Boolean(local); },
    mute(on) { muted = on; if (local) local.getAudioTracks().forEach((track) => { track.enabled = !on; }); },
    /** Asks for the microphone again (after the person fixed the problem). Reports through onState. */
    async retryMic() {
      const res = await requestMic();
      if (closed) { res.stream?.getTracks().forEach((t) => t.stop()); return; }
      if (!res.stream) { onState(res.problem); return; }
      try {
        await useMic(res.stream);
        onState("mic-ok");
      } catch (err) {
        console.warn("mic swap failed", err);
        onState("no-mic");
      }
    },
    sendChat(text) { return send({ type: "chat", text }); },
    end() { send({ type: "end" }); setTimeout(cleanup, 150); },
    close: cleanup,
  };
}
