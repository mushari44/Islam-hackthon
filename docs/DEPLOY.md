# Deploying Sabeeli: website on Vercel, API on Render

Vercel hosts the React website. It can't run the backend: Vercel functions have no lasting disk for
SQLite, no long-lived WebSockets for call chat, and a size limit far below the retrieval stack. So the
FastAPI backend runs on Render as one Docker service (`render.yaml`), and the Vercel site calls it.

```
browser ──> https://<project>.vercel.app      (static build of frontend/, vercel.json)
        └─> https://<service>.onrender.com/api (FastAPI, REST + /ws call chat)
```

## 1. Backend on Render

1. render.com > New > Blueprint > connect GitHub > pick `mushari44/Islam-hackthon`, branch `main`.
2. Fill the values it asks for:
   - `OPENROUTER_API_KEY`: the OpenRouter key (without it the API runs sources-only).
   - `CORS_ORIGINS`: the Vercel address from step 2, e.g. `https://sabeeli.vercel.app` (no trailing
     slash). You can leave it empty now and add it after step 2 (Environment > Save, it redeploys).
   - TURN and SMTP values are optional.
3. `DEMO_PASSWORD` is generated at random. Read it in the service's Environment tab to sign in to the
   demo da'i accounts; never use the README default on a public link.
4. Wait for "Live", then open `https://<service>.onrender.com/api/health`: `"ai": true` means the model is on.

The free plan sleeps after 15 minutes without traffic and takes about a minute to wake. For judging,
use a paid instance or a free uptime pinger hitting `/api/health` every 10 minutes. The SQLite
database lives on the container's disk and resets to fresh demo data on each deploy or restart.

## 2. Website on Vercel

1. vercel.com > Add New > Project > import `mushari44/Islam-hackthon`. Keep Root Directory as the repo
   root: `vercel.json` sets the build (`frontend/`) and output (`frontend/dist`).
2. Environment Variables: `VITE_API_URL` = `https://<service>.onrender.com` (no trailing slash).
   It is read at build time, so redeploy after changing it.
3. Deploy, then put the `*.vercel.app` address in Render's `CORS_ORIGINS` (step 1.2).

Preview deployments get other addresses. To let them call the API too, set on Render
`CORS_ORIGIN_REGEX=https://<project>-.*\.vercel\.app`.

## Check it

- The home page loads and shows live counts (they come from the API).
- Ask a question: an answer with sources means the API, CORS and the model all work.
- Da'i console (`#/daai`) login with `reviewer` and the generated password.
- A call between two browsers: the call chat uses `wss://<service>.onrender.com/ws/...`.

Without `VITE_API_URL` the build calls its own origin, which is what local runs and the single
Render service (FastAPI serving `frontend/dist`) expect.
