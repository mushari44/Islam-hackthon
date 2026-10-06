# Starting version (before the challenge days)

The challenge evaluates **only the work done from 4 October 09:00 to 6 October 23:59, Riyadh time** (4 October 06:00 UTC to 6 October 20:59 UTC). Earlier work is allowed if it is disclosed as the starting version, with its components and rights. This file is that record.

- **Team:** Mushari Alothman, Eman Saheli. The team owns all code in this repository (MIT, see `LICENSE`). Third-party components and data are listed in `THIRD_PARTY.md`.
- **Starting version = everything committed before 4 October 06:00 UTC.** The last such commit is `3e0f7b9` (3 October, 23:13 UTC).
- The git tag `starting-version` (`5282f8e`, 2 October) marks the first snapshot only. The team kept building on 2 and 3 October, before the challenge days; that work is **also part of the starting version** and is listed below. This file was first written on 2 October and corrected on 6 October so that it covers the whole period.

To see each part yourself:

```bash
git log --until=2026-10-04T06:00:00Z     # the starting version
git log --since=2026-10-04T06:00:00Z     # work done during the challenge days
```

Every commit is dated, so the line between the two is in the history itself. Pull request #12 is a special case: it was merged on 4 October 07:20 UTC, but all its commits are from 3 October, so it belongs to the starting version.

## What existed before 4 October 06:00 UTC

| Component | State at `3e0f7b9` | Owner |
|---|---|---|
| Corpus (`scripts/`, `data/corpus/`) | 6,236 verses with At-Tafsir Al-Muyassar and the Rowwad translation (QuranEnc), 3,574 hadiths (HadeethEnc), 543 icadb Q&A answers, 10 glossary terms, the «بينات» extractor (263 questions, built locally) | Mushari |
| Retrieval (`features/rag/`) | Arabic BM25 plus optional multilingual E5 semantic search, fused 70/30; thresholds for showing or abstaining | Mushari |
| Answer pipeline | Content levels A-D, strict grounding (uncited sentences dropped), scripture guard, Quran/hadith shown from the corpus only, sources-only fallback, "How I found this" trace. Gemma 4 31B on OpenRouter as the default model, Claude as an option | Mushari |
| Quote and photo check | Word-by-word verse matching against the Mushaf, photo reading by the model | Mushari |
| Evaluation (`eval/`) | 60 cases (30 Arabic, 30 English, incl. the package's 12 sample cases), 10 synthetic photos, the runner and `eval/REPORT.md`: 180/180 runs passed on 3 October | Mushari |
| Community (`features/community/`) | Groups with moderation and the @سبيلي assistant; online and in-person meetups with booking, sex and age filters, My activities | Mushari |
| Videos (`features/videos/`) | IslamHouse video library from its official API (107 languages), Arabic-aware search, streamed from IslamHouse with a link back | Mushari |
| Calls (`features/calls/`) | Call queue, WebRTC audio with in-call chat, referral card and its experiment, choosing a named da'i, sharing an Ask chat with the da'i | Eman (sharing built by Mushari's agent with Eman as reviewer) |
| Auth, accounts and the da'i console | Seeker accounts (optional) and anonymous sessions, saved Ask chats, da'i login, reviewer-managed da'is, the da'i console (calls, groups, meetups, history) | Eman (accounts built by Mushari's agent with Eman as reviewer) |
| Shared shell | Arabic/English RTL interface, design system, Dockerfile and `render.yaml` | shared |
| Audit fixes (`3e0f7b9`) | Database deadlock under load, grounding gaps, booking race, admin token secret | shared |
| Tests | 176 backend tests | per owner |

## What the challenge days added (from 4 October 06:00 UTC)

| Date (UTC) | Work |
|---|---|
| 4 Oct | Accounts: sex and age band are chosen by the seeker (`0f17068`) |
| 4 Oct | New home page with live content, fitting every screen from 320 px to wide desktops (`da1ac46`, `5114479`, `4ab4c9a`) |
| 4 Oct | Deployment: website on Vercel, API on Render, the live link (`4c38ba2`, `278890c`) |
| 4 Oct | "New Muslim": a da'i can record that a seeker embraced Islam in a call; the seeker alone decides whether their groups hear it, and an unanswered record is deleted after 7 days (`c478af3`, `49df046`) |
| 5 Oct | Site-wide pass on common website conventions: one sign-in card for users and da'is, header and footer, confirmations before destructive actions, loading and retry states, closable messages, Arabic plurals, phone layout (pull request #18) |
| 6 Oct | Second site-wide review: fixes across Ask, videos (no off-topic suggestions), community, calls, sign-in and the da'i console (pull requests #21, #25, #26) |
| 6 Oct | Submission documents: `LICENSE`, `docs/SOURCES.md` (sources and how they are verified), `docs/AI-DECK.md` and the AI deck, this corrected record, README with the live link |
| 6 Oct | Booking a call from a da'i's weekly schedule: «اتصل الآن» or «احجز موعدًا» (pull requests #23, #24) |
| 6 Oct | Home page count of people who embraced Islam through Sabeeli, as an anonymous number (#19); «ملفي الشخصي» tab (#22); community tab «لقاءات ودروس المجتمع المسلم» (#29) |
| 6 Oct | Joining a group, posting in it and booking an event seat need an account (#27) |
| 6 Oct | Run it yourself: `docker compose up --build`, a ready `.env` with every key empty, full mode with «بينات», sample da'i password `123` (#28, #30, #31); the sign-in card lists the sample da'i accounts (#32); an experimental Docker GPU mode for the hybrid search (#33) |

The `git log --since` command above is the complete, authoritative list.
