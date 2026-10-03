# Third-party components, data and services (licence log)

The challenge terms require every tool, model and service to be disclosed. Add a row whenever you add something.

## Data (religious content)

| Source | Used for | Access | Terms |
|---|---|---|---|
| QuranEnc (Islamic Content Service Association): `arabic_moyassar` | Mushaf text (King Fahd Complex edition) and At-Tafsir Al-Muyassar | Public API, fetched by `scripts/ingest_quran.py` | Free for individuals and organisations, per the association's statement in the challenge's scholarly package. Confirm with the reviewer |
| QuranEnc: `english_rwwad` | English translation of the meanings (Rowwad Translation Center) | Public API | Same as above |
| HadeethEnc (Islamic Content Service Association) | Hadith text, grade, attribution, explanation, lessons (Arabic and English) | Public API, `scripts/ingest_hadith.py` | Same as above |
| Challenge scholarly package, sample glossary | 10 core terms and their usage rules (`data/corpus/glossary.json`) | Transcribed from the package (page 7) | Provided by the organisers for participants |
| mp3quran.net API | Surah names | Public API | Public, no key |

## Models and services

| Service | Used for | Notes |
|---|---|---|
| Anthropic Claude API (`claude-opus-5-5`) | Question analysis, photo transcription, cited answers, referral card drafts | Needs `ANTHROPIC_API_KEY`. Without a key the app runs in sources-only mode. Only synthetic data is sent in tests and evaluation |
| Google public STUN server (`stun.l.google.com:19302`) | WebRTC connectivity for calls | Configurable with `STUN_URLS`. Add the TURN provider here when it is chosen |
| Google Fonts: Readex Pro, Amiri Quran | Interface and verse typography | SIL Open Font License |
| TURN relay (e.g. Metered Open Relay, free tier) | Relays call audio when two networks block a direct connection | Optional, set with `TURN_URL`, `TURN_USERNAME`, `TURN_CREDENTIAL`. Audio is relayed, never recorded |
| SMTP email (any provider, e.g. Gmail with an app password) | Emails a seeker's 6-digit password reset code | Optional, set with `SMTP_*`. Python standard library `smtplib`, no extra package |
| Render (free web service) | Hosting the demo from the `Dockerfile` / `render.yaml` | Optional; any Docker host works |

## Software

| Package | Licence |
|---|---|
| FastAPI, Starlette, Pydantic, Uvicorn, HTTPX | MIT / BSD |
| SQLAlchemy | MIT |
| anthropic (Python SDK) | MIT |
| python-dotenv, python-multipart, websockets | BSD / Apache-2.0 |
| pytest | MIT |
| React, React DOM | MIT |
| Vite, @vitejs/plugin-react | MIT |
