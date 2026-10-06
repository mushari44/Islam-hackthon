# Instructions for AI coding agents working on Sabeeli

This file is identical to `AGENTS.md`. If you change one, change the other.

## 1. Who are you working for?

Two people build this project, and each has their own agent:

| Person | Owns | Task list |
|---|---|---|
| **Mushari** | RAG (cited answers, photo reading, verse matching, evaluation) Community (groups, meetups) and Videos (the IslamHouse video library) | `tasks/mushari.md` |
| **Eman** | Auth (seeker sessions, da'i login and accounts), the whole da'i-facing interface (console, calls, groups and meetups tabs), Calls (call requests, WebRTC room) and the referral card and its experiment | `tasks/eman.md` |

At the start of a session, find out which person you are working for: from the branch name (`mushari/...` or `eman/...`), or from what the developer said. If you can't tell, **ask before editing anything**. Then read that person's task list and work on the first unticked task, unless the developer asks for something else.

## 2. Where you may edit

| Area | Folders | Who edits |
|---|---|---|
| RAG | `backend/app/features/rag/`, `frontend/src/features/rag/`, `tests/rag/`, `eval/`, `scripts/`, `data/corpus/` | Mushari's agent |
| Community | `backend/app/features/community/`, `frontend/src/features/community/` (seeker screens), `tests/community/` | Mushari's agent |
| Videos | `backend/app/features/videos/`, `frontend/src/features/videos/`, `tests/videos/` | Mushari's agent |
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
- **Mushari is the team lead: his approval counts for both people.** When he approves a shared change or a pull request, Eman's agreement is not needed as well (decided 3 October 2026). Still tell Eman when her folders or the shared API change.
- Each feature keeps its own strings (`strings.js`, registered with `register()`), its own CSS file and its own tests. Don't put feature strings or styles in `core/`.
- Work on your owner's branch (`mushari/<topic>` or `eman/<topic>`). Never push to `main` directly, never force-push, and never rewrite shared history.

## 2a. Git: pull before you start, push when you finish

Do this **every time**, so the two agents never work on stale code. Replace `<owner>` with `mushari` or `eman`, and `<topic>` with a short name for the task.

**Before changing anything:**

```bash
git status                      # must be clean; if not, commit or ask your developer first
git checkout main
git pull origin main            # get the other person's merged work
git checkout -B <owner>/<topic> # your branch for this task (existing branch: git checkout <owner>/<topic> && git merge main)
```

**When the task is done:**

```bash
python -m pytest tests          # all tests must pass
cd frontend && npm run build && cd ..
git add -A
git commit -m "<what changed and why>"
git pull origin main            # merge anything new before pushing
git push -u origin <owner>/<topic>
```

Then open a pull request into `main` on GitHub (`https://github.com/mushari44/Islam-hackthon`). After the other person or your developer merges it, start the next task again from "Before changing anything".

**Rules:**
- Never force-push, never push to `main` directly, never rewrite history.
- If a pull brings a conflict in the other person's folders, stop and tell your developer. Don't resolve it by editing their files.
- Commit only your own folders. Shared files (`core/`, `docs/API.md`, ...) go in a pull request that both people approve.

## 3. Content rules (these are the challenge's binding rules)

- Religious content comes **only** from the approved corpus in `data/corpus/` (Mushaf text, At-Tafsir Al-Muyassar and the Rowwad translation from QuranEnc, HadeethEnc, the package glossary, the two Q&A encyclopedias from icadb, and «بينات», which each copy builds locally with `scripts/ingest_bayyinat.py`). Never add religious text from model memory.
- **Only cited text reaches the user.** With `SABEELI_STRICT_GROUNDING=1` (the default), `pipeline.py` drops every model sentence that cites no approved passage (connectors of at most `SABEELI_MAX_UNCITED_WORDS` words are kept). An answer with no citations becomes the fixed "not found in the sources" message. Don't weaken this.
- **Quran and hadith text is never generated.** The model refers to passages with `[[q:SURA:AYA]]` / `[[h:ID]]` markers, and the app renders the reference text. Keep `_guard_scripture` and `_clean_markers` in `pipeline.py` working.
- **Videos come only from IslamHouse** (listed on page 9 of the scholarly package). They play from IslamHouse's own URLs (their CDN, or a privacy-mode YouTube embed when that is all they publish), every card links back to the item's IslamHouse page, and titles and descriptions are shown exactly as published. Never re-host the media, never generate or summarise video text with a model, and never cite a video in an answer (answers cite the approved corpus only).
- **No personal fatwa.** Level D questions get general information and a referral. The `fatwa` notice must stay.
- Use **synthetic data only**: no real seekers' chats, names or photos in the repo, tests, evals or prompts. The sample da'is, groups and events are synthetic. Since 6 October 2026 (Mushari's decision) the site shows them without a "(demo)" tag, and the README says they are samples. Never give them a real person's name.
- Don't infer or store anything about a user's religion or other sensitive traits. Seekers stay anonymous. One exception, approved by Mushari for the "new Muslim" feature: when a da'i confirms in a call that a seeker embraced Islam, a pending record is kept until the seeker answers (at most 7 days). It is shown or announced only if they agree, and deleted if they decline, never answer or later hide it. Without their yes, only an anonymous count is kept.
- Every tool, model, dataset and service you add goes into `THIRD_PARTY.md` with its licence.

## 4. Running things

```bash
pip install -r requirements.txt
python -m uvicorn backend.app.main:app --port 8000      # API on :8000
cd frontend && npm install && npm run dev               # UI on :5173 (proxies /api and /ws to :8000)
```

Tests (no API key needed; they run in sources-only mode and mock the model API):

```bash
python -m pytest tests/rag tests/community tests/videos   # Mushari
python -m pytest tests/calls tests/auth        # Eman
python -m pytest tests                         # everything, before any pull request
```

Before opening a pull request, run the whole test suite and `npm run build` in `frontend/`.

- **Don't run anything that spends API credits** (the full evaluation, bulk calls to the model) without your developer's explicit OK.
- Never commit `.env`, API keys, the database, `data/raw/` or `HACKTHON/`.

## 5. Style

- Python: type hints, short functions, docstrings that say why. Use `core/claude.py`'s `get_claude()` (Gemma through OpenRouter by default, or Claude) for every model call, and keep prompts in the feature that uses them.
- React: function components and hooks, and no new dependencies without both people's agreement.
  - Every visible string goes through `t("key")`, with Arabic and English entries.
  - Use logical CSS properties (`margin-inline-start`, ...) so RTL and LTR both work.
- Keep commits small, with a clear message saying what changed and why.
