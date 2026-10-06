// The seeker's optional account, shared across screens. Owner: Eman.
import { useEffect, useState } from "react";
import { api, daaiAuth } from "../../core/api.js";

let state = { account: null, loaded: false };
const listeners = new Set();
let loading = null;

// Other tabs of this browser learn about a sign-in, sign-out or account change through this key (and through the
// seeker token key, which changes when a session ends), so a tab left open never keeps showing a signed-out account.
const SEEKER_KEY = "sabeeli.seeker";     // keep in step with core/api.js
const DAAI_KEY = "sabeeli.daai";         // keep in step with core/api.js
const PING_KEY = "sabeeli.account_ping";

function apply(account) {
  state = { account, loaded: true };
  listeners.forEach((fn) => fn(state));
}

/** Show this account (null: signed out) here and tell this browser's other tabs to reload theirs. */
export function setAccount(account) {
  apply(account);
  try { localStorage.setItem(PING_KEY, String(Date.now())); } catch { /* private mode */ }
}

export function loadAccount() {
  // apply, not setAccount: a reload caused by another tab must not ping the tabs back.
  loading ||= api.get("/api/account")
    .then((d) => apply(d.account))
    .catch(() => apply(null))
    .finally(() => { loading = null; });
  return loading;
}

/** Sign the seeker out on this device. Their saved chats stay in the account; only this tab's open chat is dropped. */
export async function signOutSeeker() {
  await api.post("/api/account/signout", {}).catch(() => {});
  try { sessionStorage.removeItem("sabeeli.chat"); } catch { /* ignore */ }
  setAccount(null);
}

/** const { account, loaded } = useAccount(); account is null when signed out. */
export function useAccount() {
  const [s, set] = useState(state);
  useEffect(() => {
    listeners.add(set);
    if (!state.loaded) loadAccount();
    return () => listeners.delete(set);
  }, []);
  return s;
}

// Whether a da'i is signed in on this browser. The token itself lives in core/api.js; this only tells the top bar
// and the da'i console when it changes, so the bar can show "Da'i console" instead of "Sign in".
let daai = Boolean(daaiAuth.token);
const daaiListeners = new Set();

function applyDaai(on) {
  daai = on;
  daaiListeners.forEach((fn) => fn(daai));
}

/** Keep (token) or drop (null) the da'i's sign-in, and tell every screen that shows it. */
export function setDaaiToken(token) {
  if (token) daaiAuth.set(token); else daaiAuth.clear();
  applyDaai(Boolean(token));
}

/** True while a da'i is signed in on this browser. */
export function useDaaiSignedIn() {
  const [on, set] = useState(daai);
  useEffect(() => {
    daaiListeners.add(set);
    set(Boolean(daaiAuth.token));
    return () => daaiListeners.delete(set);
  }, []);
  return on;
}

// The storage event fires only in the other tabs, never in the one that wrote, so there is no echo.
if (typeof window !== "undefined") {
  window.addEventListener("storage", (e) => {
    if (e.key === null || e.key === SEEKER_KEY || e.key === PING_KEY) { if (state.loaded) loadAccount(); }
    if (e.key === null || e.key === DAAI_KEY) applyDaai(Boolean(daaiAuth.token));
  });
}
