# Instructions for AI coding agents working on Sabeeli

This file is identical to `AGENTS.md`. If you change one, change the other.

## 1. Who are you working for?

Two people build this project, and each has their own agent:

| Person | Owns | Task list |
|---|---|---|
| **Mushari** | RAG (cited answers, photo reading, verse matching, evaluation) and Community (groups, meetups) | `tasks/mushari.md` |
| **Eman** | Auth (seeker sessions, da'i login and accounts), the whole da'i-facing interface (console, calls, groups and meetups tabs), Calls (call requests, WebRTC room) and the referral card and its experiment | `tasks/eman.md` |

At the start of a session, find out which person you are working for: from the branch name (`mushari/...` or `eman/...`), or from what the developer said. If you can't tell, **ask before editing anything**. Then read that person's task list and work on the first unticked task, unless the developer asks for something else.

## 2. Where you may edit

| Area | Folders | Who edits |
|---|---|---|
| RAG | `backend/app/features/rag/`, `frontend/src/features/rag/`, `tests/rag/`, `eval/`, `scripts/`, `data/corpus/` | Mushari's agent |
| Community | `backend/app/features/community/`, `frontend/src/features/community/` (seeker screens), `tests/community/` | Mushari's agent |
| Calls | `backend/app/features/calls/`, `frontend/src/features/calls/`, `tests/calls/` | Eman's agent |
| Auth | `backend/app/features/auth/` (sessions, login, accounts, demo accounts), `tests/auth/` | Eman's agent |
| Da'i interface | `frontend/src/features/daai/` (login screen, console, calls / groups / meetups tabs) | Eman's agent |
| Shared core | `backend/app/core/`, `backend/app/main.py`, `frontend/src/core/`, `frontend/src/styles/`, `frontend/src/pages/`, `frontend/src/App.jsx`, `docs/API.md`, `requirements.txt`, `frontend/package.json` | Only after both people agree |

Rules:

- **Never edit the other person's folders.** If you need something from them, write it down under "Requests" in your own task list, and tell your developer.
- Features talk to each other only through their public modules:
  - backend: `features/rag/public.py` and `features/auth/public.py`;
  - frontend: `features/rag/public.js`, `features/community/public.js` and `features/calls/public.jsx`;
  - the shell entry points: `frontend/src/features/*/index.js`.

  The da'i screens (Eman) call the community API (Mushari) as documented in `docs/API.md`.

  Don't import a feature's internal files from another feature.
- A change to a shared API shape (a request or response used by the other person's code) needs both people's agreement, and `docs/API.md` must change in the same commit.
- Each feature keeps its own strings (`strings.js`, registered with `register()`), its own CSS file and its own tests. Don't put feature strings or styles in `core/`.
- Work on your owner's branch (`mushari/<topic>` or `eman/<topic>`). Never push to `main` directly, never force-push, and never rewrite shared history.

## 3. Content rules (these are the challenge's binding rules)

- Religious content comes **only** from the approved corpus in `data/corpus/` (Mushaf text, At-Tafsir Al-Muyassar and the Rowwad translation from QuranEnc, HadeethEnc, the package glossary). Never add religious text from model memory.
- **Quran and hadith text is never generated.** The model refers to passages with `[[q:SURA:AYA]]` / `[[h:ID]]` markers, and the app renders the reference text. Keep `_guard_scripture` and `_clean_markers` in `pipeline.py` working.
- **No personal fatwa.** Level D questions get general information and a referral. The `fatwa` notice must stay.
- Use **synthetic data only**: no real seekers' chats, names or photos in the repo, tests, evals or prompts. Demo accounts are marked "(demo)".
- Don't infer or store anything about a user's religion or other sensitive traits. Seekers stay anonymous.
- Every tool, model, dataset and service you add goes into `THIRD_PARTY.md` with its licence.

## 4. Running things

```bash
pip install -r requirements.txt
python -m uvicorn backend.app.main:app --port 8000      # API on :8000
cd frontend && npm install && npm run dev               # UI on :5173 (proxies /api and /ws to :8000)
```

Tests (no API key needed; they run in sources-only mode and mock Claude):

```bash
python -m pytest tests/rag tests/community     # Mushari
python -m pytest tests/calls tests/auth        # Eman
python -m pytest tests                         # everything, before any pull request
```

Before opening a pull request, run the whole test suite and `npm run build` in `frontend/`.

- **Don't run anything that spends API credits** (the full evaluation, bulk calls to Claude) without your developer's explicit OK.
- Never commit `.env`, API keys, the database, `data/raw/` or `HACKTHON/`.

## 5. Style

- Python: type hints, short functions, docstrings that say why. Use the `core/claude.py` helpers for every Claude call, and keep prompts in the feature that uses them.
- React: function components and hooks, and no new dependencies without both people's agreement.
  - Every visible string goes through `t("key")`, with Arabic and English entries.
  - Use logical CSS properties (`margin-inline-start`, ...) so RTL and LTR both work.
- Keep commits small, with a clear message saying what changed and why.
