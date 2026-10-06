# سَبِيلي · Sabeeli

**معرفة تُنير، وصحبة تُعين.** سَبِيلي تطبيق ويب يتيح لمن يثير الإسلام فضوله، وللمسلم الجديد، أن يسأل بلغته (نصاً أو بصورة) ويحصل على شرح من مصادر معتمدة يظهر مصدره مع كل عبارة، وأن يتصل مباشرة بداعية متاح بلغته، ويتابع تعلّمه في مجموعات يقودها دعاة ولقاءات حضورية، ويشاهد مقاطع مرئية من موقع دار الإسلام بلغته.

> مشروع في تحدي الذكاء الاصطناعي في خدمة المحتوى الإسلامي 2026 (المسار المفتوح). الفريق: Mushari Alothman و Eman Saheli.

**Live:** https://sabeeli-self.vercel.app (website) · https://sabeeli.onrender.com/api/health (API; the free server sleeps when idle, so the first request can take about a minute)

*Sabeeli is a web app for people curious about Islam and for new Muslims. They ask in their own language, by text or with a photo, and get an explanation grounded in approved sources that are shown with every statement. They can call an available da'i who speaks their language, keep learning in da'i-led groups and in-person meetups, and watch IslamHouse videos in their own language.*

## How to sign in (judges)

| | Live site (https://sabeeli-self.vercel.app) | Local run (your machine) |
|---|---|---|
| **Seeker (user)** | There are no preset user accounts: **create your own** in a few seconds. No account is needed to ask, watch videos or browse groups and events; to call or book a da'i, join a group, post in it or book a seat at an event, create one: «تسجيل الدخول» → «مستخدم» → «أنشئ حساباً», any username (3-24 letters or digits), a password of 8+ characters, sex and age range | The same |
| **Da'i** | «تسجيل الدخول» → «داعية» (or `/#/daai`). Users `reviewer` (admin), `khalid`, `maryam`, `yusuf`. Password **`123`** for all four. The sign-in card lists them too: tap a name to fill it in | Same users. Password **`123`** for all four (the `DEMO_PASSWORD` line in `.env`) |

The sample da'is are synthetic and created automatically on the first start. Details: [Run it yourself](#run-it-yourself).

## What's inside

| | Feature | Owner |
|---|---|---|
| اسأل | Cited answers from the approved package only. Quran and hadith text is shown from the reference, never generated. Content levels A-D; no personal fatwa. A photo or quoted verse is checked against the Mushaf, word by word | Mushari |
| مرئيات | A video library from IslamHouse (listed in the scholarly package) in 107 languages, chosen separately from the interface language: topics, search (Arabic-aware: hamza, taa marbuta and diacritics don't block a match) and a player that streams straight from IslamHouse with a link back to the source. No re-hosting, no generated text | Mushari |
| المجتمع | Da'i-led groups with the @سبيلي assistant, moderation, nicknames only; meetups at public venues with RSVP codes and calendar files | Mushari |
| تحدّث | Direct voice call (WebRTC) with an available da'i in the seeker's language, in-call text chat, and a referral card the seeker edits and approves before it is shared | Eman |
| لوحة الداعية | Da'i sign-in, the calls queue, the call room with the shared card, and the screens to lead groups and host meetups | Eman |

## Run it yourself

The fastest way to try Sabeeli is the live link above. To run the code on your own machine, pick one:

| | Search for answers | Needs |
|---|---|---|
| Docker, default or full mode | **BM25** (keyword search), like the live site | Docker only |
| Docker, GPU mode | **Hybrid**: BM25 + the E5 embedding model, like the team's copy | An **NVIDIA GPU with 8 GB of VRAM or more** that Docker can use |
| Python and Node (option 2) | BM25, or **hybrid** after the E5 steps | For hybrid: an **NVIDIA GPU with 8 GB of VRAM or more** (about 3 hours without one) |

Everything else (AI answers with a key, videos, community, calls, da'i console) is the same in every mode.

**Option 1: Docker (one command).** Needs Docker Desktop, or Docker with Compose 2.24 or newer.

```bash
git clone https://github.com/mushari44/Islam-hackthon.git
cd Islam-hackthon
docker compose up --build
```

Open http://localhost:8000. The first build takes a few minutes; later starts take seconds. Port 8000 busy? Run `SABEELI_PORT=8080 docker compose up` (PowerShell: `$env:SABEELI_PORT=8080; docker compose up`) and open port 8080. Stop with Ctrl+C, or `docker compose down`.

**Full mode, with «بينات»:** `docker compose --profile full up --build sabeeli-full`. It also builds «بينات» from the scholarly package's own link on your machine (its rights are reserved, so the repo can't ship it). This adds a few minutes to the first build.

**GPU mode, with hybrid search:** `docker compose --profile gpu up --build sabeeli-gpu`. It adds «بينات» and the hybrid search (BM25 + the E5 embedding model). It needs an NVIDIA GPU with **8 GB of VRAM or more** that Docker can use: on Windows, Docker Desktop with WSL2 and a recent NVIDIA driver; on Linux, the NVIDIA Container Toolkit; it doesn't work on a Mac. The image is large (the CUDA build of PyTorch, about 2.5 GB). On the first start the container downloads the E5 model (about 2.2 GB) and builds the index in a few minutes, then opens the site; later starts reuse both. If Docker can't see a GPU, it says so in the log and runs with BM25.

We recommend the default command, or full mode, for judging. Add an OpenRouter key (below) for AI answers in any mode; it is the one thing the repo can't ship.

**Option 2: without Docker (Python and Node).** Install [Python 3.11 or newer](https://www.python.org/downloads/) (on Windows, tick "Add python.exe to PATH") and [Node.js 18 or newer](https://nodejs.org/), then run these lines one at a time in a terminal.

Windows (PowerShell or Command Prompt):

```bat
git clone https://github.com/mushari44/Islam-hackthon.git
cd Islam-hackthon
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cd frontend
npm install
npm run build
cd ..
python -m uvicorn backend.app.main:app --port 8000
```

macOS / Linux:

```bash
git clone https://github.com/mushari44/Islam-hackthon.git
cd Islam-hackthon
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
python -m uvicorn backend.app.main:app --port 8000
```

If PowerShell refuses the `activate` line, run `Set-ExecutionPolicy -Scope Process Bypass` first, or use Command Prompt.

Open http://localhost:8000 and keep the terminal open while you use the app (Ctrl+C stops it). The first start takes about 15 seconds while the search index loads. To start it again later: open a terminal in the folder, activate the environment (the `activate` line above), then run the last line. Without Git, download the code as a ZIP from GitHub (green "Code" button) and start from the `cd` line. For frontend development, run `npm run dev` in `frontend/` and open http://localhost:5173; API calls are proxied to port 8000.

**Full mode without Docker**, with the environment active. «بينات» takes a few minutes:

```bash
pip install pymupdf
python scripts/ingest_bayyinat.py
```

**Hybrid search (BM25 + E5 embedding model), like the team's copy.** It uses the free `intfloat/multilingual-e5-large` model from Hugging Face (about 2.2 GB, downloaded on first use, no key needed) to embed about 15,000 passages into a search index.

> **GPU requirement**
> - You need an **NVIDIA GPU with 8 GB of VRAM or more**, a recent NVIDIA driver, and the CUDA build of PyTorch, installed **before** the lines below from https://pytorch.org/get-started/locally/. The index then builds in a few minutes, and the GPU is picked up by itself (or set `SABEELI_EMBED_DEVICE=cuda` in `.env`).
> - Without such a GPU (CPU only, Apple Silicon or AMD), the same steps still work but take **about 3 hours**. Until the index exists the app uses BM25, so you can skip this part.

```bash
pip install -r requirements-embeddings.txt
python scripts/build_embeddings.py
```

Then start the app again as above.

**What works with no setup:** the repo includes a ready [`.env`](.env) settings file, and the app runs with it as is. Questions get answers built only from the approved sources, with every passage cited (sources-only mode), search uses BM25, and all sample accounts, groups and events are created on the first start. Sign in as a da'i with user `reviewer` and password `123` (header «تسجيل الدخول», then «داعية», or go to `#/daai`).

**AI answers and photo reading** need an OpenRouter key (https://openrouter.ai/keys). The key is the only setting you need to fill in:

1. Open [`.env`](.env) in the project folder.
2. Paste the key after `OPENROUTER_API_KEY=` (section 1 at the top, no quotes).
3. Start the app again with the same command. http://localhost:8000/api/health then shows `"ai": true`.

Every other line in `.env` is explained there and can stay as it is. You might change `DEMO_PASSWORD` (the sample da'is' password), `SECRET_KEY` (keeps da'is signed in across restarts) or `SABEELI_PORT` (Docker's port). If you fork the repo, run `git update-index --skip-worktree .env` after adding a key so it is never committed.

**Not in the default run:** «بينات» (its publisher reserves the rights, so it is built on your machine, not shipped) and E5 semantic search. Full mode, GPU mode or the «بينات» steps above add «بينات»; the hybrid search needs GPU mode or option 2's E5 steps. Password-reset emails need an SMTP server (the `SMTP_` lines in `.env`); trying the app doesn't need them.

**Accounts to sign in with.** These sample accounts are created on the first start, like the sample groups and events. They are synthetic, and the site shows them without a "demo" tag. All four are da'i accounts and share one password:

| Username | Password | Who | What to try |
|---|---|---|---|
| `reviewer` | `123` | Reviewer (admin), Arabic and English | Everything a da'i can do, plus the «حسابات الدعاة» tab (add, disable or reset da'is) and the referral comparison |
| `khalid` | `123` | Khalid, Arabic and English | Taking calls, leading groups, hosting events, setting a schedule for bookings |
| `maryam` | `123` | Maryam (da'iyah), Arabic and English | The same, as a da'iyah |
| `yusuf` | `123` | Yusuf, English only | The same, for an English-speaking seeker |

To sign in as a da'i: «تسجيل الدخول» in the header, then «داعية» (or go straight to http://localhost:8000/#/daai). The sign-in card lists the four accounts; tap one to fill in its name and password. The password is the `DEMO_PASSWORD` line in `.env`; change it there before putting the app online.

**Seeker (user) side:** no account is needed to ask questions, watch videos or browse groups and events. Calling or booking a da'i, joining a group, posting in it and booking a seat at an event need a seeker account (it also keeps your chats), which takes a few seconds: «تسجيل الدخول», then «مستخدم», then «أنشئ حساباً». Choose any username (3 to 24 letters or digits) and a password of at least 8 characters, and pick sex and age range.

**Deploying:** the website goes on Vercel and the API on Render; see [docs/DEPLOY.md](docs/DEPLOY.md).

**To try a call** on one computer, use two browsers, or a normal and a private window. In one, sign in as `khalid` and switch on «متاح لاستقبال المكالمات» (Available for calls). In the other, create a seeker account and go to **تحدّث**. Allow the microphone when the browser asks.

The corpus is already in `data/corpus/`, except «بينات»: its publisher reserves the rights, so each copy builds it from the package's link with `pip install pymupdf` and `python scripts/ingest_bayyinat.py` (the app works without it). To refresh the rest from the official APIs, run `python scripts/ingest_quran.py`, `python scripts/ingest_hadith.py` and `python scripts/ingest_icadb.py`.

## Tests

```bash
python -m pytest tests             # no API key needed (sources-only mode + mocked OpenRouter and Claude APIs)
                                   # 230 pass with requirements.txt (the E5 tests are skipped); 236 with requirements-embeddings.txt too
```

## How the code is organised

```
backend/app/
  core/               shared: config, database, model transport (OpenRouter/Gemma or Claude), Arabic normalisation
  features/auth/      Eman: seeker sessions, da'i login and accounts, demo accounts
  features/rag/       Mushari: corpus, retrieval, verse matching, answer pipeline, prompts
  features/community/ Mushari: groups, moderation, meetups
  features/videos/    Mushari: IslamHouse video library (live API, cached index, search)
  features/calls/     Eman: call queue, WebRTC signalling, referral card and experiment
frontend/src/
  core/ styles/ pages/ App.jsx   shared shell, design system, i18n (Arabic/English, RTL)
  features/rag/ features/community/      Mushari: Ask page, groups and meetups (seeker side)
  features/videos/                       Mushari: the videos page (مرئيات)
  features/calls/ features/daai/          Eman: Talk page; the whole da'i console and its login
tests/{auth,rag,community,calls}/   tests per owner
tests/videos/         Mushari: videos (IslamHouse responses mocked, no network)
data/corpus/          the approved corpus (JSONL)
scripts/              corpus ingestion
```

Each person works only in their own folders. Shared code changes only by agreement. The rules for people and AI agents are in **`CLAUDE.md`** (same as `AGENTS.md`), the task lists are in **`tasks/mushari.md`** and **`tasks/eman.md`**, and the API contract between frontend and backend is in **`docs/API.md`**.

## Challenge documents

- **[`docs/SOURCES.md`](docs/SOURCES.md):** the Islamic sources (with their page in the scholarly package) and how every source and every answer is verified.
- **[`docs/AI-DECK.md`](docs/AI-DECK.md):** the content of the deck that explains the AI; the slides are in `docs/Sabeeli-AI-deck.pptx` and `.pdf`.
- **[`eval/REPORT.md`](eval/REPORT.md):** the 60-case evaluation (3 runs each) and its results.
- **[`STARTING_POINT.md`](STARTING_POINT.md):** what existed before 4 October 06:00 UTC (the challenge judges only work done from 4 to 6 October).
- **[`THIRD_PARTY.md`](THIRD_PARTY.md):** licence record: sources, models, services and software with their licences.
- **[`LICENSE`](LICENSE):** the team's code is under the MIT licence; the religious content keeps its publishers' terms.
- **[`docs/RAG-PLAN.md`](docs/RAG-PLAN.md):** how the RAG system uses the approved sources, and how it is evaluated.
- **Privacy:** seekers can ask and browse without an account (calling or booking a da'i, joining a group, posting and booking an event seat need a free username-and-password account, with no phone number or real name), an anonymous visitor's questions are deleted after 24 hours (a signed-in seeker keeps saved chats), the referral card is shared only with consent, calls are not recorded, and every user can delete their data from **الخصوصية**. Videos and thumbnails load straight from IslamHouse's servers, search words are sent in a POST body, and Sabeeli stores no searches and no viewing history.
