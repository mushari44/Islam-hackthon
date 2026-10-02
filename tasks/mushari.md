# Mushari: task list

You own **RAG** (cited answers, photo reading, verse matching, evaluation) and **Community** (groups, the @سبيلي assistant in groups, meetups). For community you own the backend and the seeker-facing screens. Since 2 October, the da'i-facing screens (group moderation, meetup hosting) and all login are Eman's: keep the community API in `docs/API.md` stable for her, and agree on any change.

Your folders, and the only ones you edit without asking Eman:

- `backend/app/features/rag/`, `backend/app/features/community/`
- `frontend/src/features/rag/`, `frontend/src/features/community/`
- `tests/rag/`, `tests/community/`
- `eval/`, `scripts/` (corpus ingestion), `data/corpus/`

Shared (`backend/app/core/`, `frontend/src/core/`, `frontend/src/styles/`, `frontend/src/pages/`, `frontend/src/App.jsx`, `docs/API.md`) changes only after agreeing with Eman.

Work on a branch named `mushari/<topic>` and open a pull request into `main`.

Tick a box when the task is merged. Keep the order unless the team agrees otherwise.

## Before 4 October (setup, not judged)

- [ ] Put `ANTHROPIC_API_KEY` in `.env` (never commit it). Run the six sample questions on the Ask page, and check that the answers carry citations and that `/api/health` shows `"ai": true`.
- [ ] If the API rejects the `fallbacks` parameter, set `SABEELI_FALLBACKS=0` in `.env` and note it in `docs/STARTING_POINT.md`.
- [ ] Confirm the source usage terms with the reviewer: QuranEnc, HadeethEnc, and the glossary from the scholarly package. Record the answer in `THIRD_PARTY.md`.
- [ ] Ask the organisers for the scholarly appendix and the exact content-level wording, and update `LEVELS` in `features/rag/assistant.py` if it differs.

## Day 1: 4 October (content and answers)

- [ ] **Evaluation set** `eval/cases.csv`: 60 synthetic cases, 30 Arabic and 30 English, split like the deck:
  - 20 photo/quote matching (clear text, unclear text, a verse quoted with a mistake);
  - 20 explanation and follow-up;
  - 10 limits and disagreement (missing source, a request to fabricate a hadith, a disputed matter);
  - 10 personal fatwa.

  Include all 12 sample cases from the scholarly package (page 6). Each row lists: id, group, language, question, the photo file if any, the expected behaviour (answer / abstain / refer / quote_differs), the expected source ids, and the content level.
- [ ] **10 photo examples** in `eval/photos/`: synthetic photos of printed text, including verses with a deliberate mistake. Use no real people and no real chats.
- [ ] **Eval runner** `eval/run_eval.py`: 3 runs per case (180 runs). Score each run:
  - behaviour correct;
  - every cited id exists and supports the claim (`trace.cited_share`, `trace.uncited`);
  - no Quran text typed by the model (`trace.scripture_guard`);
  - no ruling on level D.

  Targets: **90% composite success** and **10/10 safe behaviour on personal fatwa**. Write `eval/results/<date>.json` and a short `eval/REPORT.md`. Estimate the cost first and get the team's OK before a full run.
- [ ] Tune retrieval on the failures:
  - analysis prompt queries (`ANALYZE_SYSTEM`);
  - BM25 weights (`corpus.py`);
  - `top_k`;
  - the low-coverage note threshold in `pipeline.py`.

  Re-run, and keep a log of each change and its score in `eval/REPORT.md`.

## Day 2: 5 October (community)

- [ ] Group assistant:
  - limit @mentions per member (for example, 5 per 10 minutes);
  - show the leader the questions flagged «بانتظار توضيح الداعية» first.
- [ ] Moderation:
  - review the abuse list with the reviewer;
  - add a "report message" button for members (API plus the seeker screen). The leader's view of reports is in Eman's da'i console: agree on the API with her.
- [ ] Meetups:
  - a city filter;
  - show "the group this meetup belongs to" on the card;
  - a reminder text on the booking confirmation.
- [ ] Tests for each change in `tests/community/`.

## Known gaps found in review (2 October)

- [ ] Community responses ignore the interface language. Join, RSVP, create group/meetup and the da'i's group and meetup lists always return the leader or host name in Arabic: pass `ui` through to `_group_view` and `_meetup_view`.
- [ ] Without an API key, sources-only answers come from raw-keyword BM25 and can be weak (e.g. «ما أركان الإسلام» misses «بني الإسلام على خمس»). Decide whether sources-only mode should show fewer and stronger passages, or a curated list of starter topics.

## Day 3: 6 October (test and publish)

- [ ] Final evaluation run (180 runs). Put the numbers in `eval/REPORT.md` and in the deck slide «خطة اختبار الموثوقية».
- [ ] Add a short `docs/SOURCES.md` section: how each source is used and how a reviewer can verify an answer (`كيف وصلتُ للإجابة؟`).
- [ ] With Eman: deploy, record the demo video (2 minutes or less), make the repo public, submit before **23:59 on 6 October (Riyadh time)**.

## Ideas if time allows

- [ ] Add «بينات: أسئلة وأجوبة عن الإسلام» (dawa.center) once its usage terms are confirmed: ingest it into `data/corpus/` with its own passage kind.
- [ ] Add Jamhara dictionary terms to `data/corpus/glossary.json`.
- [ ] Dense embeddings next to BM25 (only if allowed and documented in `THIRD_PARTY.md`).
