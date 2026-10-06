# سَبِيلي · Sabeeli

**معرفة تُنير، وصحبة تُعين.** سَبِيلي تطبيق ويب يتيح لمن يثير الإسلام فضوله، وللمسلم الجديد، أن يسأل بلغته (نصاً أو بصورة) ويحصل على شرح من مصادر معتمدة يظهر مصدره مع كل عبارة، وأن يتصل مباشرة بداعية متاح بلغته، ويتابع تعلّمه في مجموعات يقودها دعاة ولقاءات حضورية، ويشاهد مقاطع مرئية من موقع دار الإسلام بلغته.

> مشروع في تحدي الذكاء الاصطناعي في خدمة المحتوى الإسلامي 2026 (المسار المفتوح). الفريق: Mushari Alothman و Eman Saheli.

**Live:** https://sabeeli-self.vercel.app (website) · https://sabeeli.onrender.com/api/health (API; the free server sleeps when idle, so the first request can take about a minute)

*Sabeeli is a web app for people curious about Islam and for new Muslims. They ask in their own language, by text or with a photo, and get an explanation grounded in approved sources that are shown with every statement. They can call an available da'i who speaks their language, keep learning in da'i-led groups and in-person meetups, and watch IslamHouse videos in their own language.*

## What's inside

| | Feature | Owner |
|---|---|---|
| اسأل | Cited answers from the approved package only. Quran and hadith text is shown from the reference, never generated. Content levels A-D; no personal fatwa. A photo or quoted verse is checked against the Mushaf, word by word | Mushari |
| مرئيات | A video library from IslamHouse (listed in the scholarly package) in 107 languages, chosen separately from the interface language: topics, search (Arabic-aware: hamza, taa marbuta and diacritics don't block a match) and a player that streams straight from IslamHouse with a link back to the source. No re-hosting, no generated text | Mushari |
| المجتمع | Da'i-led groups with the @سبيلي assistant, moderation, nicknames only; meetups at public venues with RSVP codes and calendar files | Mushari |
| تحدّث | Direct voice call (WebRTC) with an available da'i in the seeker's language, in-call text chat, and a referral card the seeker edits and approves before it is shared | Eman |
| لوحة الداعية | Da'i sign-in, the calls queue, the call room with the shared card, and the screens to lead groups and host meetups | Eman |

## Run it

Requirements: Python 3.11 and Node 18 or newer.

```bash
pip install -r requirements.txt
cp .env.example .env            # add OPENROUTER_API_KEY (Gemma 4 31B) for AI answers; without it the app runs in sources-only mode
cd frontend && npm install && npm run build && cd ..
python -m uvicorn backend.app.main:app --port 8000
```

Open http://localhost:8000. For frontend development, run `npm run dev` in `frontend/` and open http://localhost:5173; API calls are proxied to port 8000.

**Semantic search (optional):** `pip install -r requirements-embeddings.txt`, then `python scripts/build_embeddings.py` (downloads multilingual E5-large, about 2.2 GB; a few minutes on a GPU). The app picks the index up on its next start and fuses it with BM25; without it, search is BM25 alone.

**Demo accounts** (synthetic, created on first start): da'i console at `#/daai`, users `khalid`, `maryam`, `yusuf` and `reviewer` (reviewer can run the referral experiment). The password is the value of `DEMO_PASSWORD` in `.env` (`sabeeli-demo` by default). Change it before deploying.

**Deploying:** the website goes on Vercel and the API on Render; see [docs/DEPLOY.md](docs/DEPLOY.md).

To try a call locally, open the app in two browsers: in one, sign in as a da'i and switch on "Available"; in the other, go to **تحدّث**.

The corpus is already in `data/corpus/`, except «بينات»: its publisher reserves the rights, so each copy builds it from the package's link with `pip install pymupdf` and `python scripts/ingest_bayyinat.py` (the app works without it). To refresh the rest from the official APIs, run `python scripts/ingest_quran.py`, `python scripts/ingest_hadith.py` and `python scripts/ingest_icadb.py`.

## Tests

```bash
python -m pytest tests             # 204 tests; no API key needed (sources-only mode + mocked OpenRouter and Claude APIs)
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
- **Privacy:** seekers can use everything without an account; an anonymous visitor's questions are deleted after 24 hours, and only a seeker who signs up keeps saved chats. Group members use nicknames, the referral card is shared only with consent, calls are not recorded, and every user can delete their data from **الخصوصية**. Videos and thumbnails load straight from IslamHouse's servers, search words are sent in a POST body, and Sabeeli stores no searches and no viewing history.
