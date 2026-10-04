// WebRTC audio room + in-call chat over the signalling WebSocket. Owner: Eman (calls).
// The da'i sends the offer once both people are in the room; the seeker answers.
// Audio quality (capture, Opus/RED, autoplay, device changes, network) lives in audio.js.
import { api, wsUrl } from "../../core/api.js";
import {
  createLevelMeter, createSpeaker, keepAwake, listDevices, openMic, preferVoiceCodecs, prioritiseAudio, tuneOpus, watchQuality,
} from "./audio.js";

export async function createRoom({
  callId, role, token,
  onState = () => {}, onChat = () => {}, onEnded = () => {},
  onAudio = () => {},      // ({ blocked }) the browser refused to autoplay the other person's voice
  onDevices = () => {},    // ({ inputs, outputs, mic }) available microphones and speakers
  onQuality = () => {},    // ("good" | "poor") network quality of the incoming audio
}) {
  let cfg = { iceServers: [{ urls: ["stun:stun.l.google.com:19302"] }], iceTransportPolicy: "all" };
  try { cfg = await api.pGet("/api/rtc-config"); } catch { /* use the default */ }

  const pc = new RTCPeerConnection({ iceServers: cfg.iceServers, iceTransportPolicy: cfg.iceTransportPolicy, bundlePolicy: "max-bundle" });
  const localStream = new MediaStream();
  let track = null;        // the live microphone track, or null
  let chosenMic = "";      // deviceId the person picked; "" follows the system default
  let muted = false;
  let closed = false;
  const meter = createLevelMeter();
  const speaker = createSpeaker((blocked) => onAudio({ blocked }));
  const releaseWake = keepAwake();
  const stopQuality = watchQuality(pc, onQuality);
  // Safari and Chrome start Web Audio only after a tap: resume the level meter on the first one.
  const wake = () => meter?.resume();
  ["pointerdown", "keydown", "touchend"].forEach((ev) => document.addEventListener(ev, wake, true));

  const audioTx = () => pc.getTransceivers().find((tx) => tx.receiver?.track?.kind === "audio" && !tx.stopped);

  async function useTrack(next) {
    const old = track;
    track = next;
    if (track) {
      track.enabled = !muted;
      track.onended = () => { if (!closed && track === next) recoverMic(); };
      localStream.getTracks().forEach((tr) => localStream.removeTrack(tr));
      localStream.addTrack(track);
    }
    const tx = audioTx();
    if (tx) {
      await tx.sender.replaceTrack(track);
      prioritiseAudio(tx.sender);
    }
    if (old && old !== track) old.stop();
    meter?.setTrack(track);
  }

  async function publishDevices() {
    const { inputs, outputs } = await listDevices();
    onDevices({ inputs, outputs, mic: track?.getSettings?.().deviceId || chosenMic });
    return inputs;
  }

  async function acquire(deviceId = chosenMic) {
    try {
      await useTrack(await openMic(deviceId));
      onState("mic-ok");
      publishDevices();
      return true;
    } catch {
      onState("no-mic");
      return false;
    }
  }

  // A headset was unplugged, a Bluetooth device dropped, or the OS took the mic: reopen one.
  let recovering = false;
  async function recoverMic() {
    if (recovering || closed) return;
    recovering = true;
    try {
      const inputs = await publishDevices();
      const keep = chosenMic && inputs.some((d) => d.deviceId === chosenMic) ? chosenMic : "";
      if (!keep) chosenMic = "";
      await acquire(keep);
    } finally { recovering = false; }
  }

  async function onDeviceChange() {
    if (closed) return;
    const inputs = await publishDevices();
    const s = track?.getSettings?.() || {};
    const gone = !track || track.readyState === "ended" || (s.deviceId && !inputs.some((d) => d.deviceId === s.deviceId));
    if (gone) { recoverMic(); return; }
    // Following the system default: a newly plugged headset becomes the default in Chrome/Edge, so move to it.
    if (!chosenMic) {
      const def = inputs.find((d) => d.deviceId === "default");
      if (def?.groupId && s.groupId && def.groupId !== s.groupId) acquire("");
    }
  }
  navigator.mediaDevices?.addEventListener?.("devicechange", onDeviceChange);

  await acquire("");
  // The da'i offers: create the audio line now so the mic (or a later one) can be swapped in without renegotiating.
  if (role === "daai") {
    const tx = pc.addTransceiver("audio", { direction: "sendrecv", streams: [localStream] });
    if (track) await tx.sender.replaceTrack(track);
    prioritiseAudio(tx.sender);
  }

  pc.ontrack = (e) => { speaker.attach(e.streams[0] || new MediaStream([e.track])); };

  const pendingIce = [];
  const ws = new WebSocket(wsUrl(`/ws/call/${callId}?role=${role}&token=${encodeURIComponent(token)}`));
  const send = (msg) => { if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg)); };

  pc.onicecandidate = (e) => { if (e.candidate) send({ type: "ice", candidate: e.candidate.toJSON() }); };

  async function makeOffer(restart = false) {
    if (closed) return;
    preferVoiceCodecs(pc);
    const offer = await pc.createOffer({ iceRestart: restart });
    await pc.setLocalDescription({ type: "offer", sdp: tuneOpus(offer.sdp) });
    send({ type: "offer", sdp: pc.localDescription });
  }

  // Network changed (Wi-Fi to mobile data, a short drop): restart ICE instead of losing the call.
  // The da'i restarts directly; the seeker asks the da'i to with "ready".
  let dropTimer = null;
  const askRestart = () => { if (role === "daai") makeOffer(true).catch(() => {}); else send({ type: "ready", restart: true }); };
  pc.onconnectionstatechange = () => {
    const st = pc.connectionState;
    onState(st);
    clearTimeout(dropTimer);
    if (st === "failed") askRestart();
    if (st === "disconnected") dropTimer = setTimeout(() => { if (pc.connectionState === "disconnected") askRestart(); }, 4000);
    if (st === "connected") speaker.play();
  };

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
        case "ready":
          if (role === "daai" && msg.restart) await makeOffer(true);
          break;
        case "offer": {
          await pc.setRemoteDescription(msg.sdp);
          // The seeker answers on the da'i's audio line (sendrecv), so a mic found later still goes out.
          const tx = audioTx();
          if (tx) {
            tx.direction = "sendrecv";
            await tx.sender.replaceTrack(track);
            try { tx.sender.setStreams?.(localStream); } catch { /* optional */ }
            prioritiseAudio(tx.sender);
          }
          preferVoiceCodecs(pc);
          const answer = await pc.createAnswer();
          await pc.setLocalDescription({ type: "answer", sdp: tuneOpus(answer.sdp) });
          send({ type: "answer", sdp: pc.localDescription });
          while (pendingIce.length) await pc.addIceCandidate(pendingIce.shift());
          break;
        }
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
    clearTimeout(dropTimer);
    navigator.mediaDevices?.removeEventListener?.("devicechange", onDeviceChange);
    ["pointerdown", "keydown", "touchend"].forEach((ev) => document.removeEventListener(ev, wake, true));
    try { ws.close(); } catch { /* already closed */ }
    pc.close();
    if (track) track.stop();
    stopQuality();
    releaseWake();
    meter?.close();
    speaker.destroy();
  }

  return {
    get hasMic() { return Boolean(track); },
    mute(on) { muted = on; if (track) track.enabled = !on; },
    /** Switch microphone ("" = system default). */
    async setMic(deviceId) { chosenMic = deviceId || ""; return acquire(chosenMic); },
    /** Try the microphone again after a refusal (e.g. the person allowed it in the browser settings). */
    retryMic() { return acquire(chosenMic); },
    setSpeaker(deviceId) { return speaker.setSink(deviceId); },
    /** Call from a click: starts blocked sound and the level meter on iOS/Safari. */
    unlock() { speaker.play(); meter?.resume(); },
    level() { return muted ? 0 : meter?.level() || 0; },
    sendChat(text) { send({ type: "chat", text }); },
    end() { send({ type: "end" }); setTimeout(cleanup, 150); },
    close: cleanup,
  };
}
