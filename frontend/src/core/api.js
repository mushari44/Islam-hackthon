// HTTP client. Shared core.
// Seekers get an anonymous session token (localStorage); da'is a signed token (sessionStorage).

// Where the API lives. Empty (the default) = same origin, as when FastAPI serves the build or Vite proxies it.
// A frontend hosted on its own (Vercel) sets VITE_API_URL at build time, e.g. https://sabeeli.onrender.com
const API_BASE = (import.meta.env.VITE_API_URL || "").replace(/\/+$/, "");
/** Full URL for an API path ("/api/..."), for fetch calls and plain links such as .ics downloads. */
export function apiUrl(path) { return API_BASE + path; }

const SEEKER_KEY = "sabeeli.seeker";
const DAAI_KEY = "sabeeli.daai";

function store(kind) { return kind === "daai" ? sessionStorage : localStorage; }
function read(kind, key) { try { return store(kind).getItem(key); } catch { return null; } }
function write(kind, key, val) {
  try { val == null ? store(kind).removeItem(key) : store(kind).setItem(key, val); } catch { /* private mode */ }
}

export class ApiError extends Error {
  constructor(status, detail) { super(typeof detail === "string" ? detail : "error"); this.status = status; this.detail = detail; }
}

let sessionPromise = null;
export async function seekerToken() {
  let tok = read("seeker", SEEKER_KEY);
  if (tok) return tok;
  sessionPromise ||= fetch(apiUrl("/api/session"), { method: "POST" })
    .then((r) => { if (!r.ok) throw new ApiError(r.status, "session"); return r.json(); })
    .then((d) => {
      write("seeker", SEEKER_KEY, d.token);
      sessionPromise = null;
      return d.token;
    })
    .catch((e) => {
      sessionPromise = null; // let the next call try again
      throw e instanceof ApiError ? e : new ApiError(0, "offline");
    });
  return sessionPromise;
}
export function forgetSeeker() { write("seeker", SEEKER_KEY, null); }

export const daaiAuth = {
  get token() { return read("daai", DAAI_KEY); },
  set(token) { write("daai", DAAI_KEY, token); },
  clear() { write("daai", DAAI_KEY, null); },
};

async function request(method, path, { body, form, as = "seeker", retry = true } = {}) {
  const headers = {};
  if (as === "seeker") headers["X-Seeker"] = await seekerToken();
  if (as === "daai" && daaiAuth.token) headers.Authorization = `Bearer ${daaiAuth.token}`;
  let payload;
  if (form) payload = form;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  let res;
  try {
    res = await fetch(apiUrl(path), { method, headers, body: payload });
  } catch {
    throw new ApiError(0, "offline");
  }
  if (res.status === 401 && as === "seeker" && retry) {
    forgetSeeker();
    return request(method, path, { body, form, as, retry: false });
  }
  const type = res.headers.get("content-type") || "";
  const data = type.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) throw new ApiError(res.status, data && data.detail ? data.detail : data);
  return data;
}

export const api = {
  get: (path, opts) => request("GET", path, opts),
  post: (path, body, opts = {}) => request("POST", path, { ...opts, body }),
  form: (path, form, opts = {}) => request("POST", path, { ...opts, form }),
  del: (path, opts) => request("DELETE", path, opts),
  // da'i-authenticated shortcuts
  dGet: (path) => request("GET", path, { as: "daai" }),
  dPost: (path, body) => request("POST", path, { as: "daai", body }),
  // public (no auth)
  pGet: (path) => request("GET", path, { as: "none" }),
};

export function wsUrl(path) {
  if (API_BASE) return API_BASE.replace(/^http/, "ws") + path;
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}${path}`;
}
