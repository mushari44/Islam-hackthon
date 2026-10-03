# Third-party components, data and services (licence log)

The challenge terms require every tool, model and service to be disclosed. Add a row whenever you add something.

## Data (religious content)

| Source | Used for | Access | Terms |
|---|---|---|---|
| QuranEnc (Islamic Content Service Association): `arabic_moyassar` | Mushaf text (King Fahd Complex edition) and At-Tafsir Al-Muyassar | Public API, fetched by `scripts/ingest_quran.py` | Free for individuals and organisations, per the association's statement in the challenge's scholarly package. Al-Muyassar is covered by the package: page 9 lists QuranEnc as "the Quran, its tafsirs and translations of its meanings". The tafsir rule on page 3 names early sources or dorar.net/tafseer, so ask the reviewer to confirm |
| QuranEnc: `english_rwwad` | English translation of the meanings (Rowwad Translation Center) | Public API | Same as above |
| HadeethEnc (Islamic Content Service Association) | Hadith text, grade, attribution, explanation, lessons (Arabic and English) | Public API, `scripts/ingest_hadith.py` | Same as above |
| Challenge scholarly package, sample glossary | 10 core terms and their usage rules (`data/corpus/glossary.json`) | Transcribed from the package (page 7) | Provided by the organisers for participants |
| mp3quran.net API | Surah names | Public API | Public, no key |
| IslamHouse (islamhouse.com, Islamic Content Service Association): videos | The «مرئيات» section: titles, descriptions, presenters, topics, thumbnails and video files in 107 languages | Official API v3 (`api3.islamhouse.com/v3`) with the public key published in its Postman documentation (documenter.getpostman.com/view/7929737/TzkyMfPc); read live by `backend/app/features/videos/islamhouse.py` and cached in memory for 6 hours. Nothing is stored in the repo | Listed in the package (page 9: «... وصوتيات ومرئيات مصنّفة موضوعياً», with this developer interface). No explicit embedding or redistribution licence was found; the site footer says it protects intellectual property under the Saudi copyright law. So media is **never re-hosted**: MP4s stream from IslamHouse's CDN, each item links back to its IslamHouse page, and text is shown as published. Ask the reviewer to confirm |

## Models and services

| Service | Used for | Notes |
|---|---|---|
| Anthropic Claude API (`claude-opus-5-5`) | Question analysis, photo transcription, cited answers, referral card drafts | Needs `ANTHROPIC_API_KEY`. Without a key the app runs in sources-only mode. Only synthetic data is sent in tests and evaluation |
| Google public STUN server (`stun.l.google.com:19302`) | WebRTC connectivity for calls | Configurable with `STUN_URLS`. Add the TURN provider here when it is chosen |
| YouTube embeds (`youtube-nocookie.com`, privacy-enhanced mode) | Playing IslamHouse videos that IslamHouse publishes only as a YouTube embed | Today every such item also has an MP4 on IslamHouse, which is preferred, so the embed is a fallback only |
| Google Fonts: Readex Pro, Amiri Quran | Interface and verse typography | SIL Open Font License |

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
