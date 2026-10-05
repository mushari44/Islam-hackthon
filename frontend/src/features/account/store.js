// The seeker's optional account, shared across screens. Owner: Eman.
import { useEffect, useState } from "react";
import { api, daaiAuth } from "../../core/api.js";

let state = { account: null, loaded: false };
const listeners = new Set();
let loading = null;

export function setAccount(account) {
  state = { account, loaded: true };
  listeners.forEach((fn) => fn(state));
}

export function loadAccount() {
  loading ||= api.get("/api/account")
    .then((d) => setAccount(d.account))
    .catch(() => setAccount(null))
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

// Whether a da'i is signed in on this tab. The token itself lives in core/api.js; this only tells the top bar
// and the da'i console when it changes, so the bar can show "Da'i console" instead of "Sign in".
let daai = Boolean(daaiAuth.token);
const daaiListeners = new Set();

/** Keep (token) or drop (null) the da'i's sign-in, and tell every screen that shows it. */
export function setDaaiToken(token) {
  if (token) daaiAuth.set(token); else daaiAuth.clear();
  daai = Boolean(token);
  daaiListeners.forEach((fn) => fn(daai));
}

/** True while a da'i is signed in on this tab. */
export function useDaaiSignedIn() {
  const [on, set] = useState(daai);
  useEffect(() => {
    daaiListeners.add(set);
    set(Boolean(daaiAuth.token));
    return () => daaiListeners.delete(set);
  }, []);
  return on;
}
