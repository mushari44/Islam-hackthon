# Starting version (before the challenge days)

The challenge evaluates **only the work done from 4 to 6 October 2026**. Prior work is allowed if the starting version is documented before 4 October, with its components and rights, together with a statement of what is added during the challenge. This file is that record.

- **Starting version:** git tag `starting-version` (commit made on 2 October 2026).
- **Team:** Mushari Alothman, Eman Saheli. The team owns all code in this repository. Third-party components and data are listed in `THIRD_PARTY.md`.

## What exists in the starting version

| Component | State on 2 October | Owner |
|---|---|---|
| Corpus ingestion (`scripts/`, `data/corpus/`) | 6,236 verses (Mushaf text, At-Tafsir Al-Muyassar, Rowwad translation, from QuranEnc), 3,574 hadiths from HadeethEnc, and 10 glossary terms from the scholarly package | Mushari |
| Retrieval (`features/rag/corpus.py`) | BM25 over Arabic and English, with Arabic normalisation | Mushari |
| Verse matching (`features/rag/quran_match.py`) | Deterministic Uthmani-aware matching and word-level misquote detection | Mushari |
| Answer pipeline (`features/rag/pipeline.py`, `assistant.py`) | Content levels A-D, Claude prompts with citations, scripture guard, and a sources-only fallback. Tested against a mocked API only: no real model run yet | Mushari |
| Community (`features/community/`) | Groups with moderation and the @سبيلي assistant; meetups with RSVP and calendar files | Mushari |
| Videos (`features/videos/`, `tests/videos/`), built 2 and 3 October, before the challenge days | IslamHouse video library from its official API: 107 languages, topics, Arabic-aware search, a player that streams from IslamHouse with a link back; 12 tests with IslamHouse mocked | Mushari |
| Calls (`features/calls/`) | Call queue, WebRTC audio with signalling and in-call chat, da'i calls tab, referral card (model / template / none arms) and experiment counters. Tested between two local browsers | Eman |
| Auth and da'i console (`backend/app/features/auth/`, `frontend/src/features/daai/`) | Anonymous seeker sessions, da'i login and demo accounts, the da'i console with calls / groups / meetups tabs | Eman |
| Shared core and React shell (`backend/app/core/`, `frontend/src/core/`, `styles/`, `pages/`) | Config, database, Claude transport, Arabic normalisation, Arabic/English RTL interface, design system | shared |
| Tests (`tests/`) | 37 backend tests; no evaluation set yet | per owner |

## What the challenge days add

The plan is in `tasks/mushari.md` and `tasks/eman.md`. In short:

- the 60-case evaluation set (3 runs each), its runner and results;
- the first real model runs and tuning;
- the 10 photo test cases;
- calls tested across two networks with TURN;
- da'i notifications;
- the referral experiment and its results;
- community moderation features;
- deployment, the public repository, the demo video and the final deck.

`git log starting-version..main` lists every change made during the challenge.
