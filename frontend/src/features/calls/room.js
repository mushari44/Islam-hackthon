// WebRTC audio room + in-call chat over the signalling WebSocket. Owner: Eman (calls).
// The da'i sends the offer once both people are in the room; the seeker answers.
import { api, wsUrl } from "../../core/api.js";

export async function createRoom({ callId, role, token, onState = () => {}, onChat = () => {}, onEnded = () => {} }) {
  let cfg = { iceServers: [{ urls: ["stun:stun.l.google.com:19302"] }], iceTransportPolicy: "all" };
  try { cfg = await api.pGet("/api/rtc-config"); } catch { /* use the default */ }

  const pc = new RTCPeerConnection({ iceServers: cfg.iceServers, iceTransportPolicy: cfg.iceTransportPolicy });
  let local = null;
  try {
    local = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    local.getTracks().forEach((track) => pc.addTrack(track, local));
  } catch {
    onState("no-mic");
    pc.addTransceiver("audio", { direction: "recvonly" });
  }

  const remoteAudio = new Audio();
  remoteAudio.autoplay = true;
  pc.ontrack = (e) => { remoteAudio.srcObject = e.streams[0]; remoteAudio.play().catch(() => {}); };

  const pendingIce = [];
  let closed = false;
  const ws = new WebSocket(wsUrl(`/ws/call/${callId}?role=${role}&token=${encodeURIComponent(token)}`));
  const send = (msg) => { if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg)); };

  pc.onicecandidate = (e) => { if (e.candidate) send({ type: "ice", candidate: e.candidate.toJSON() }); };
  pc.onconnectionstatechange = () => onState(pc.connectionState);

  async function makeOffer(restart = false) {
    const offer = await pc.createOffer({ iceRestart: restart });
    await pc.setLocalDescription(offer);
    send({ type: "offer", sdp: pc.localDescription });
  }

  ws.onmessage = async (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }
    try {
      switch (msg.type) {
        case "joined":
          onState("waiting-peer");
          if (role === "daai" && msg.present.includes("seeker")) await makeOffer();
          break;
        case "peer-joined":
          if (role === "daai") await makeOffer(pc.connectionState === "failed" || pc.connectionState === "disconnected");
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
  };
  let joined = false;
  ws.addEventListener("message", (ev) => { if (!joined && ev.data.includes('"joined"')) joined = true; });
  ws.onclose = (ev) => { if (!closed && (ev.code === 4003 || !joined)) onState("refused"); };

  function cleanup() {
    if (closed) return;
    closed = true;
    try { ws.close(); } catch { /* already closed */ }
    pc.close();
    if (local) local.getTracks().forEach((track) => track.stop());
    remoteAudio.srcObject = null;
  }

  return {
    hasMic: Boolean(local),
    mute(on) { if (local) local.getAudioTracks().forEach((track) => { track.enabled = !on; }); },
    sendChat(text) { send({ type: "chat", text }); },
    end() { send({ type: "end" }); setTimeout(cleanup, 150); },
    close: cleanup,
  };
}
