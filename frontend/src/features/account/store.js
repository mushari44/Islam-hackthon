// The seeker's optional account, shared across screens. Owner: Eman.
import { useEffect, useState } from "react";
import { api } from "../../core/api.js";

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
