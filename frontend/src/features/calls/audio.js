// Audio quality helpers for the call room. Owner: Eman (calls).
// Everything here degrades gracefully: a browser that lacks a feature simply keeps its default.

/** Speech-tuned capture: the browser's echo/noise/gain processing, mono at 48 kHz (what Opus encodes natively). */
export function micConstraints(deviceId = "") {
  const audio = {
    echoCancellation: { ideal: true },
    noiseSuppression: { ideal: true },
    autoGainControl: { ideal: true },
    channelCount: { ideal: 1 },
    sampleRate: { ideal: 48000 },
    sampleSize: { ideal: 16 },
  };
  if (deviceId) audio.deviceId = { exact: deviceId };
  return { audio, video: false };
}

/**
 * Opens a microphone. Falls back step by step so an old or picky browser still gets a mic:
 * chosen device -> default device with tuned constraints -> plain `audio: true`.
 * Throws only when no microphone can be opened at all (denied, none plugged in, insecure page).
 */
export async function openMic(deviceId = "") {
  const md = navigator.mediaDevices;
  if (!md?.getUserMedia) throw Object.assign(new Error("getUserMedia unavailable"), { name: "NotSupportedError" });
  const attempts = [micConstraints(deviceId)];
  if (deviceId) attempts.push(micConstraints(""));
  attempts.push({ audio: true, video: false });
  let lastErr;
  for (const c of attempts) {
    try {
      const stream = await md.getUserMedia(c);
      const track = stream.getAudioTracks()[0];
      if ("contentHint" in track) track.contentHint = "speech";
      return track;
    } catch (err) {
      lastErr = err;
      // Permission refused: retrying with other constraints won't help.
      if (err?.name === "NotAllowedError" || err?.name === "SecurityError") break;
    }
  }
  throw lastErr;
}

export async function listDevices() {
  try {
    const all = await navigator.mediaDevices.enumerateDevices();
    return {
      inputs: all.filter((d) => d.kind === "audioinput" && d.deviceId),
      outputs: all.filter((d) => d.kind === "audiooutput" && d.deviceId),
    };
  } catch {
    return { inputs: [], outputs: [] };
  }
}

export const canPickSpeaker = typeof HTMLMediaElement !== "undefined" && "setSinkId" in HTMLMediaElement.prototype;

/**
 * Prefer RED (redundant Opus, survives packet loss on mobile networks) then Opus.
 * Must run before createOffer/createAnswer. Browsers without RED or setCodecPreferences keep their order.
 */
export function preferVoiceCodecs(pc) {
  try {
    const caps = RTCRtpReceiver.getCapabilities?.("audio");
    if (!caps) return;
    const rank = (c) => {
      const m = c.mimeType.toLowerCase();
      if (m === "audio/red") return 0;
      if (m === "audio/opus") return 1;
      return 2;
    };
    const codecs = [...caps.codecs].sort((a, b) => rank(a) - rank(b));
    pc.getTransceivers().forEach((tx) => {
      const kind = tx.receiver?.track?.kind || tx.sender?.track?.kind;
      if (kind === "audio" && tx.setCodecPreferences) tx.setCodecPreferences(codecs);
    });
  } catch { /* keep the browser's default order */ }
}

const OPUS_PARAMS = {
  useinbandfec: "1",          // forward error correction: hides lost packets
  usedtx: "0",                // no discontinuous transmission: avoids clipped word starts
  stereo: "0",
  "sprop-stereo": "0",
  maxaveragebitrate: "40000", // clear wideband speech with headroom; Opus' default is lower
  maxplaybackrate: "48000",
};

/** Rewrites the Opus fmtp line of an SDP so both sides send FEC-protected, full-band mono speech. */
export function tuneOpus(sdp) {
  if (!sdp) return sdp;
  const pts = [...sdp.matchAll(/^a=rtpmap:(\d+) opus\/48000/gim)].map((m) => m[1]);
  let out = sdp;
  for (const pt of pts) {
    const re = new RegExp(`^a=fmtp:${pt} (.*)$`, "m");
    const m = out.match(re);
    const params = {};
    if (m) m[1].split(";").forEach((kv) => { const [k, v] = kv.trim().split("="); if (k) params[k] = v ?? ""; });
    Object.assign(params, OPUS_PARAMS);
    const line = `a=fmtp:${pt} ${Object.entries(params).map(([k, v]) => (v === "" ? k : `${k}=${v}`)).join(";")}`;
    if (m) out = out.replace(re, line);
    else out = out.replace(new RegExp(`^(a=rtpmap:${pt} opus/48000.*)$`, "im"), `$1\r\n${line}`);
  }
  return out;
}

/** Ask the network stack to treat call audio as high priority (DSCP on supporting browsers). */
export async function prioritiseAudio(sender) {
  try {
    const p = sender.getParameters();
    if (!p.encodings?.length) return;
    p.encodings.forEach((e) => { e.priority = "high"; e.networkPriority = "high"; });
    await sender.setParameters(p);
  } catch { /* not supported here */ }
}

/**
 * The remote voice. An <audio> element in the page (iOS needs playsinline), with a "blocked" signal
 * when autoplay is refused, which happens on iOS/Safari and some Android browsers after a long wait
 * in the queue: the page then shows a button, and any tap anywhere starts the sound.
 */
export function createSpeaker(onBlocked = () => {}) {
  const el = document.createElement("audio");
  el.autoplay = true;
  el.setAttribute("playsinline", "");
  el.style.display = "none";
  document.body.appendChild(el);
  let blocked = false;
  const setBlocked = (v) => { if (v !== blocked) { blocked = v; onBlocked(v); } };

  async function play() {
    if (!el.srcObject) return;
    try {
      await el.play();
      setBlocked(false);
    } catch (err) {
      if (err?.name === "NotAllowedError") setBlocked(true);
    }
  }
  const onGesture = () => { if (blocked) play(); };
  ["pointerdown", "keydown", "touchend"].forEach((ev) => document.addEventListener(ev, onGesture, true));

  return {
    attach(stream) {
      if (el.srcObject !== stream) el.srcObject = stream;
      play();
    },
    play,
    async setSink(id) {
      if (!canPickSpeaker) return false;
      try { await el.setSinkId(id || ""); return true; } catch { return false; }
    },
    destroy() {
      ["pointerdown", "keydown", "touchend"].forEach((ev) => document.removeEventListener(ev, onGesture, true));
      el.pause();
      el.srcObject = null;
      el.remove();
    },
  };
}

/** A 0..1 loudness reading of the local mic, for the level bar. Returns null where Web Audio is missing. */
export function createLevelMeter() {
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) return null;
  let ctx = null;
  let source = null;
  let analyser = null;
  let data = null;
  return {
    setTrack(track) {
      try {
        if (!ctx) ctx = new Ctx();
        source?.disconnect();
        source = null;
        if (!track) return;
        analyser = analyser || Object.assign(ctx.createAnalyser(), { fftSize: 512, smoothingTimeConstant: 0.6 });
        data = data || new Uint8Array(analyser.fftSize);
        source = ctx.createMediaStreamSource(new MediaStream([track]));
        source.connect(analyser);
        ctx.resume?.().catch(() => {});
      } catch { source = null; }
    },
    resume() { ctx?.resume?.().catch(() => {}); },
    level() {
      if (!source || !analyser || ctx?.state !== "running") return 0;
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i += 1) { const v = (data[i] - 128) / 128; sum += v * v; }
      return Math.min(1, Math.sqrt(sum / data.length) * 4);
    },
    close() { try { source?.disconnect(); ctx?.close(); } catch { /* closed */ } },
  };
}

/** Keeps the phone screen on during a call so the OS doesn't suspend the mic. */
export function keepAwake() {
  let lock = null;
  let stopped = false;
  const take = async () => {
    if (stopped || document.visibilityState !== "visible" || !navigator.wakeLock) return;
    try { lock = await navigator.wakeLock.request("screen"); } catch { lock = null; }
  };
  const onVis = () => { if (document.visibilityState === "visible") take(); };
  document.addEventListener("visibilitychange", onVis);
  take();
  return () => {
    stopped = true;
    document.removeEventListener("visibilitychange", onVis);
    lock?.release?.().catch(() => {});
  };
}

/**
 * Watches inbound audio stats every 3 s and reports "good" or "poor"
 * (more than 5% packets lost, or round trip over 400 ms).
 */
export function watchQuality(pc, onQuality) {
  let last = null;
  let current = "";
  const id = setInterval(async () => {
    if (pc.connectionState !== "connected") return;
    try {
      const stats = await pc.getStats();
      let lost = 0; let received = 0; let rtt = 0;
      stats.forEach((s) => {
        if (s.type === "inbound-rtp" && (s.kind === "audio" || s.mediaType === "audio")) {
          lost += s.packetsLost || 0; received += s.packetsReceived || 0;
        }
        if (s.type === "candidate-pair" && s.nominated && s.state === "succeeded" && s.currentRoundTripTime) rtt = s.currentRoundTripTime;
      });
      if (last) {
        const dLost = lost - last.lost;
        const dRecv = received - last.received;
        const lossRate = dRecv + dLost > 0 ? dLost / (dRecv + dLost) : 0;
        const q = lossRate > 0.05 || rtt > 0.4 ? "poor" : "good";
        if (q !== current) { current = q; onQuality(q); }
      }
      last = { lost, received };
    } catch { /* stats unavailable */ }
  }, 3000);
  return () => clearInterval(id);
}
