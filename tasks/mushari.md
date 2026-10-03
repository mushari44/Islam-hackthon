# Mushari: task list

You own **RAG** (cited answers, photo reading, verse matching, evaluation) and **Community** (groups, the @سبيلي assistant in groups, meetups). For community you own the backend and the seeker-facing screens. Since 2 October, the da'i-facing screens (group moderation, meetup hosting) and all login are Eman's: keep the community API in `docs/API.md` stable for her, and agree on any change.

Your folders, and the only ones you edit without asking Eman:

- `backend/app/features/rag/`, `backend/app/features/community/`
- `frontend/src/features/rag/`, `frontend/src/features/community/`
- `tests/rag/`, `tests/community/`
- `eval/`, `scripts/` (corpus ingestion), `data/corpus/`

Shared (`backend/app/core/`, `frontend/src/core/`, `frontend/src/styles/`, `frontend/src/pages/`, `frontend/src/App.jsx`, `docs/API.md`) changes only after agreeing with Eman.

Work on a branch named `mushari/<topic>` and open a pull request into `main`.

**Every task:** pull before you start and push when you finish. The exact commands are in `CLAUDE.md`, section 2a.

Tick a box when the task is merged. Keep the order unless the team agrees otherwise.

## Before 4 October (setup, not judged)

- [ ] Put `ANTHROPIC_API_KEY` in `.env` (never commit it). Run the six sample questions on the Ask page, and check that the answers carry citations and that `/api/health` shows `"ai": true`.
- [ ] If the API rejects the `fallbacks` parameter, set `SABEELI_FALLBACKS=0` in `.env` and note it in `docs/STARTING_POINT.md`.
- [ ] Confirm the source usage terms with the reviewer: QuranEnc, HadeethEnc, and the glossary from the scholarly package. Record the answer in `THIRD_PARTY.md`.
- [ ] Ask the reviewer to confirm At-Tafsir Al-Muyassar. Page 9 lists QuranEnc with its tafsirs, while the tafsir rule on page 3 names early sources or dorar.net/tafseer. If the reviewer says no, switch the tafsir to Dorar.
- [ ] Ask the organisers for the scholarly appendix and the exact content-level wording, and update `LEVELS` in `features/rag/assistant.py` if it differs.

## Day 1: 4 October (content and answers)

- [ ] **Evaluation set** `eval/cases.csv`: 60 synthetic cases, 30 Arabic and 30 English, split like the deck:
  - 20 photo/quote matching (clear text, unclear text, a verse quoted with a mistake);
  - 20 explanation and follow-up;
  - 10 limits and disagreement (missing source, a request to fabricate a hadith, a disputed matter);
  - 10 personal fatwa.

  Include all 12 sample cases from the scholarly package (page 6). Each row lists: id, group, language, question, the photo file if any, the expected behaviour (answer / abstain / refer / quote_differs), the expected source ids, and the content level.

  *Built on 3 October in PR #8; tick it when that is merged.*
- [ ] **10 photo examples** in `eval/photos/`: synthetic photos of printed text, including verses with a deliberate mistake. Use no real people and no real chats. *Built in PR #8 (`eval/make_photos.py`).*
- [ ] **Eval runner** `eval/run_eval.py`: 3 runs per case (180 runs). Score each run:
  - behaviour correct;
  - every cited id exists and supports the claim (`trace.cited_share`, `trace.uncited`);
  - no Quran text typed by the model (`trace.scripture_guard`);
  - no ruling on level D.

  Targets: **90% composite success** and **10/10 safe behaviour on personal fatwa**. Write `eval/results/<date>.json` and a short `eval/REPORT.md`. Estimate the cost first and get the team's OK before a full run.

  *Built in PR #8. One run of 60 costs about 4 cents, and 180 runs about 13 cents. mushari asked for everything to be tested overnight on 3 October; the results are in `eval/REPORT.md`.*
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

## Videos (IslamHouse), added 3 October

- [x] «مرئيات» section: live IslamHouse API v3, 107 video languages chosen separately from the interface language, topics, Arabic-aware search, a player that streams from IslamHouse with a link back. `features/videos/`, `tests/videos/`.
- [ ] Ask the reviewer to confirm that showing IslamHouse videos this way is allowed (no explicit embedding licence was found; see `THIRD_PARTY.md`). Record the answer there.
- [ ] Topic names that IslamHouse hasn't translated fall back to English; consider hiding topics with very few videos.
- [ ] Consider a "related videos" block under an answer on the Ask page, matched by topic. Show only IslamHouse's own titles; never generate text about a video.
- [ ] Many IslamHouse thumbnails return 404; tell IslamHouse if a contact is available.

- [x] Related videos under each answer (`/api/videos/related`, `features/videos/related.py`): E5 meaning plus title/topic words over the IslamHouse list in the answer's language. Thresholds (0.85 / 0.815) were set by hand on 12 questions; check them with the evaluation set.
- [x] A visible list of the sources each answer used, under the answer (replaces the collapsed panel).
- [x] Only related text and videos are shown: precision-first bars in `pipeline.py` (SHOW_*) and `videos/related.py`, checked with `eval/display_audit.py` on 30 questions. Also fixed: «؟» and «،» stuck to the word before them in search tokens (`core/textnorm.py`, shared), and questions were sometimes checked as misquoted verses.
- [ ] Recall without the model is now low for English and for some Arabic questions (they say "not found"). With the API key, Claude's Arabic/English search phrases should bring most back: re-run `eval/display_audit.py` then.

- [x] RAG review (3 October): fixed uncited text slipping past grounding (marker-carrying sentences, short claims, long intro lines), verses typed without brackets or in {}, unverified hadith quotes, unchecked `clarify` text, odd model JSON crashing a request, one failed call dropping structured output for good, personal questions missed without the model, removed text sent to the browser, and splitter edge cases. Tests in `tests/rag/test_review_fixes.py`.
- [ ] Gemma's `[n]` citations are self-declared: in the evaluation, sample cited sentences and judge whether the cited passage supports them; if not reliable, add a check (E5 similarity between the sentence and the passage). *Checked in PR #8: the 34 weakest of 287 cited sentences were all faithful, so no runtime check is needed (`eval/REPORT.md`).*

## Ideas if time allows

- [x] Add «بينات: أسئلة وأجوبة عن الإسلام» (dawa.center): `scripts/ingest_bayyinat.py`, passage kind `bayyinat` (built locally, git-ignored).
- [x] Add icadb's two Q&A encyclopedias (`qa.jsonl`, 543 items).
- [ ] Ask the reviewer whether the extracted Bayyinat text may be committed to the public repo (rights reserved). Until then it stays git-ignored.
- [ ] English: icadb's Q&A cards have no translations. icadb's books (e.g. «الإسلام دين الفطرة والعقل والسعادة», «رسالة موجزة إلى ملحد», «من خلق الكون؟») do, in many languages: a candidate source for English answers.
- [ ] Add Jamhara dictionary terms to `data/corpus/glossary.json`.
- [x] Dense embeddings next to BM25: multilingual E5-large + LangChain (`features/rag/embeddings.py`), documented in `THIRD_PARTY.md`.
- [ ] Use the evaluation set to compare BM25 alone (`SABEELI_EMBEDDINGS=0`) with the hybrid, and tune the fusion weights and the abstain threshold on the result. *Done in PR #8:*
  - *Hits: BM25 alone 17/23, hybrid 22/23, and 23/23 with the new answer slot.*
  - *80/20 ranks the expected passage slightly better than 70/30; the split is the team's call.*
  - *The `SHOW_*` bars stay as they are.*
- [x] Glossary matching took «سنة» (year) for the term «السنة»: the bare alias is removed (the term still matches «السنة»).
- [x] Level D without the model showed raw hadiths next to a personal question: now only the notice and the referral.
- [x] The same hadith under two HadeethEnc ids was shown twice: deduplicated by text at retrieval.
- [x] The model saw only the first 4,000 characters of a long Q&A/Bayyinat answer: it now gets the opening plus the lines matching the question.
- [ ] Rebuild the vector index after the glossary change (`python scripts/build_embeddings.py`); not urgent, terms are 10 of 10,626 passages.
