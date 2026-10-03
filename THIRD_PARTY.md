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
| icadb.com (Islamic Content Service Association): «موسوعة الأسئلة والأجوبة لغير المسلمين» (202) and «موسوعة الأسئلة والأجوبة للمسلمين» (341) | Approved answers to doubts and new-Muslim questions, in Arabic (`data/corpus/qa.jsonl`). Cards link to the same items on islamenc.com | Public export API, no key, approved versions only; `scripts/ingest_icadb.py` | Listed in the package (page 10). Same association and terms as QuranEnc and HadeethEnc |
| «بينات: أسئلة وأجوبة عن الإسلام» (مركز أصول, جمعية الدعوة والإرشاد وتوعية الجاليات بالربوة, 1445 AH) | 263 questions with short and detailed answers, the package's named source for doubts and recurring questions (page 4) | PDF from the package's link dawa.center/file/7937, extracted by `scripts/ingest_bayyinat.py` | Rights reserved by the publisher. Provided by the package for this use, but **not redistributed**: the PDF and the extracted text are git-ignored and each copy builds them locally. Ask the reviewer before committing the text |
| IslamHouse (islamhouse.com, Islamic Content Service Association): videos | The «مرئيات» section: titles, descriptions, presenters, topics, thumbnails and video files in 107 languages | Official API v3 (`api3.islamhouse.com/v3`) with the public key published in its Postman documentation (documenter.getpostman.com/view/7929737/TzkyMfPc); read live by `backend/app/features/videos/islamhouse.py` and cached in memory for 6 hours. Nothing is stored in the repo | Listed in the package (page 9: «... وصوتيات ومرئيات مصنّفة موضوعياً», with this developer interface). No explicit embedding or redistribution licence was found; the site footer says it protects intellectual property under the Saudi copyright law. So media is **never re-hosted**: MP4s stream from IslamHouse's CDN, each item links back to its IslamHouse page, and text is shown as published. Ask the reviewer to confirm |

## Models and services

| Service | Used for | Notes |
|---|---|---|
| OpenRouter (openrouter.ai), model `google/gemma-4-31b-it` (Gemma 4 31B, Google) — the default | Question analysis, photo transcription, cited answers, referral card drafts | Needs `OPENROUTER_API_KEY`. Requests go only to OpenRouter providers that don't store or train on prompts (`provider.data_collection = "deny"`; `SABEELI_OPENROUTER_PRIVATE`). Gemma is under the Gemma Terms of Use; OpenRouter under its own terms. Without a key the app runs in sources-only mode. Only synthetic data is sent in tests and evaluation |
| Anthropic Claude API (`claude-opus-5-5`) — the alternative | The same jobs, when `SABEELI_LLM_PROVIDER=anthropic` | Needs `ANTHROPIC_API_KEY`. Uses Claude's search-result citations; with Gemma the model cites numbered sources instead |
| Google public STUN server (`stun.l.google.com:19302`) | WebRTC connectivity for calls | Configurable with `STUN_URLS`. Add the TURN provider here when it is chosen |
| YouTube embeds (`youtube-nocookie.com`, privacy-enhanced mode) | Playing IslamHouse videos that IslamHouse publishes only as a YouTube embed | Today every such item also has an MP4 on IslamHouse, which is preferred, so the embed is a fallback only |
| Google Fonts: Readex Pro, Amiri Quran | Interface and verse typography | SIL Open Font License |
| `intfloat/multilingual-e5-large` (Microsoft, via Hugging Face) | Optional semantic search: embeds every corpus passage and each search query, locally | MIT. Runs on the machine (no data leaves it); downloaded once, about 2.2 GB. Off unless `scripts/build_embeddings.py` has been run |

## Software

| Package | Licence |
|---|---|
| FastAPI, Starlette, Pydantic, Uvicorn, HTTPX | MIT / BSD |
| SQLAlchemy | MIT |
| anthropic (Python SDK) | MIT |
| python-dotenv, python-multipart, websockets | BSD / Apache-2.0 |
| pytest | MIT |
| LangChain (`langchain`, `langchain-core`, `langchain-community`, `langchain-text-splitters`): retrievers, rank fusion, FAISS wrapper, text splitter. Optional (`requirements-embeddings.txt`) | MIT |
| sentence-transformers, transformers | Apache-2.0 |
| PyTorch | BSD-3-Clause |
| FAISS (`faiss-cpu`) | MIT |
| PyMuPDF (`pip install pymupdf`), used only by `scripts/ingest_bayyinat.py` to read the Bayyinat PDF; not needed to run the app | AGPL-3.0 (or commercial). Not part of the app or its requirements |
| Pillow, used only by `eval/make_photos.py` to blur, shrink and tilt two of the synthetic evaluation photos; not needed to run the app | MIT-CMU (HPND) |
| Google Chrome or Microsoft Edge in headless mode, used only by `eval/make_photos.py` to render the printed text of the synthetic evaluation photos (the photos are committed in `eval/photos/`) | The browser's own terms; nothing of it is redistributed |
| React, React DOM | MIT |
| Vite, @vitejs/plugin-react | MIT |
