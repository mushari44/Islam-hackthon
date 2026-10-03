# RAG plan: answering from the approved package (owner: Mushari)

**Goal:** every religious statement Sabeeli makes is traceable to the challenge's approved package. When the sources aren't enough, Sabeeli says so and offers a da'i.

## 1. Sources and how each is used

| Source (in the package) | Status | Unit of retrieval | Role in the answer |
|---|---|---|---|
| Mushaf text (King Fahd Complex, via QuranEnc) | ingested, 6,236 verses | one verse | **Displayed verbatim**, never generated; quoted verses are matched against it |
| At-Tafsir Al-Muyassar (QuranEnc `arabic_moyassar`) | ingested | attached to its verse | Arabic explanation the model may paraphrase and cite |
| Rowwad English translation (QuranEnc `english_rwwad`) | ingested | attached to its verse | English meaning, shown under the verse |
| HadeethEnc | ingested, 3,574 hadiths (2,328 also have English) | one hadith with grade, attribution, explanation, lessons | Evidence with grade; the explanation is citable |
| Package glossary (10 terms) | ingested | one term | Approved English equivalents and usage rules |
| icadb Q&A encyclopedias: for non-Muslims (110) and for Muslims (102) | ingested, 543 items (Arabic) | one question and answer | Approved answers to doubts and new-Muslim questions; verses inside become Mushaf markers |
| «بينات: أسئلة وأجوبة عن الإسلام» (dawa.center/file/7937) | ingested locally, 263 questions (rights reserved: built by each copy, not in git) | one question with its short and detailed answer | The package's named source for doubts and level-B questions |
| Jamhara dictionary (islamic-content.com) | later | one term | More approved term equivalents |

**Chunking rule:** keep the source's natural unit (verse, hadith, Q&A item), never fixed-size chunks, so that every citation points to a complete, checkable unit with a stable id (`q:2:256`, `h:2962`, `t:tawhid`).

## 2. Retrieval (hybrid)

1. **Analyse** (the model, structured output; Gemma 4 31B through OpenRouter by default, or Claude): language, content level A-D, personal case, any quoted text, and **2-4 search queries in both Arabic and English**. This query expansion is what bridges "Kaaba" to «القبلة» and to the tafsir's vocabulary.
2. **Keyword search (built):** BM25 over normalised Arabic (Uthmani-aware) plus English. It is fast and needs no extra service.
3. **Semantic search (built, optional):** `features/rag/embeddings.py`, with LangChain.
   - Model: `intfloat/multilingual-e5-large`, run locally, with E5's `query:` / `passage:` prefixes. Arabic and English with the same meaning land close together.
   - Units: one vector per verse (Uthmani text without marks, tafsir, translation), per hadith language, per term; long Q&A and Bayyinat answers are split into ~900-character chunks, each carrying its question. A hit always maps back to the whole passage id; chunks never reach the model or the user.
   - Index: LangChain's FAISS store, inner product on normalised vectors (cosine), built by `scripts/build_embeddings.py` into `data/cache/vectors/` (not in git).
   - Retrieval: our BM25 as a LangChain retriever, a dense retriever (every query line, best chunk per passage), fused by LangChain's `EnsembleRetriever` (weighted reciprocal rank fusion, deduplicated by passage id): **70% dense, 30% BM25** (`SABEELI_DENSE_WEIGHT`, decided by the team on 3 October). Each passage scores 0.7/(60 + its dense rank) + 0.3/(60 + its BM25 rank).
   - Abstaining: a question is "covered" when BM25's word coverage is high enough **or** a passage's E5 similarity reaches `DENSE_STRONG` (0.86, set by hand: unrelated text scores ~0.80-0.83, a passage on the same question ~0.86-0.90). In sources-only mode an approved Q&A or Bayyinat answer then leads. Tune this threshold on the evaluation set. The trace sheet shows both scores.
   - Without the packages or the index, or with `SABEELI_EMBEDDINGS=0`, search is BM25 alone.

   Measured on the evaluation set (`eval/tune_retrieval.py`, 23 cases with expected sources): an expected passage is among the 8 the model reads in 17/23 cases with BM25 alone, and in 22/23 with the 70/30 hybrid.
   - **Answer slot:** the approved Q&A or Bayyinat answer closest in meaning (E5 ≥ 0.84, `ANSWER_SLOT` in `pipeline.py`) also gets a place of its own, which brings it to 23/23. An English question's English phrases can only match passages that carry English text (hadiths, verses with their translation), so BM25 ranked the Arabic-only answers low.
   - **Other settings tried:** running BM25 once per search phrase and fusing the rankings did not help. 80/20 ranks the expected passage a little higher than 70/30, with the same hits; the split stays at the team's 70/30.
4. **Quote check (built):** text that looks like a verse is matched word by word against the Mushaf, so a misquote is detected without relying on the model.
5. **Select** about 8 passages:
   - at most 5 verses and 4 hadiths;
   - the matched verse and any glossary term go first;
   - every passage carries a coverage score.

## 3. Generation with citations (built, to tune with a real key)

- The passages are sent as `search_result` blocks with citations enabled, so every cited span maps back to a passage id.
- The model never types Quran or hadith text. It writes `[[q:..]]` or `[[h:..]]` markers, and the app renders the reference text. A guard replaces any verse the model types with the marker, and drops markers for passages that weren't retrieved.
- Content levels drive behaviour:
  - A: answer with the source;
  - B: explain from the approved material, with the reference;
  - C: note that scholars differ, or refer to a specialist;
  - D: general information only, plus the fatwa notice and a da'i referral.
- **Citations by provider.** Claude cites through its search-result citation feature (the cited span comes from the passage). Gemma (OpenRouter, the default) gets the passages as numbered sources and ends each sentence with `[n]` (or a result id, which Gemma often writes); the answer is split into sentences and clauses (`.`, `?`, `؟`, `;`, `؛`), and each one keeps only the citations attached to it. These citations are declared by the model. The evaluation checks them: across 287 cited sentences, the median E5 similarity to the cited passage was 0.84. I read the 34 sentences under 0.80 by hand, and all were faithful paraphrases. A runtime check is not needed, and at that bar it would drop about one good sentence in eight.
- **Strict grounding (built):** every model sentence must cite an approved passage, or it is removed before the user sees it. Exceptions, all narrow:
  - a short connector of at most 6 words (3 at level D) with no ruling word (حرام، يجب، باطل، invalid, must ...);
  - a line of at most 12 words ending in ":" that introduces the verse or hadith shown right after it.
  A verse or hadith marker inside an uncited sentence keeps the marker and loses the words. An answer with no citation at all is replaced by the fixed "not found in the sources" message.
  - **Not found, partly.** When a dropped sentence is the model saying the sources don't cover the question («لم أجد في المصادر...», "the sources don't mention..."), the answer opens with a fixed notice instead: no direct answer was found, and what follows is what the sources say on related points (`trace.partial`).
  - **Dangling connectors.** A connector that leaned on a dropped sentence («ومع ذلك،», "Instead,") goes with it.
  - **Repeated markers.** A sentence whose verse marker repeats an earlier one keeps that verse as a citation.
- **Scripture guard (built):** verses in ﴿﴾ or {} and quotes in «» "" “” ‹› are matched against the Mushaf and become markers. Any 7+ consecutive words that follow the Mushaf word for word, with or without brackets, are replaced by the verse marker (or removed when the match isn't exact). A quoted text found in no retrieved passage (a hadith from memory) removes its whole sentence. The analysis' clarifying question is shown only if it is a short plain question; otherwise a fixed one.
- Removed text stays on the server: the API returns only counts in `trace` (`SABEELI_DEBUG_TRACE=1` returns the text, for evaluation).
- **Refusal paths:**
  - retrieval coverage low → the model is told to abstain unless the passages clearly answer;
  - no citation in the answer → shown as "not found in the sources";
  - asked for evidence that isn't in the passages → "no matching evidence found";
  - model unavailable → sources-only mode; a personal (level D) question then gets no raw texts at all (they would read like a ruling), only the fatwa notice and the referral (`kind: refer`).
- **What sources-only mode shows (precision first: no text is better than an unrelated one).** An approved Q&A or Bayyinat answer with E5 similarity ≥ 0.86 leads and usually stands alone; another verse or hadith joins it only at ≥ 0.89. With no such answer, verses and hadiths at ≥ 0.85 are shown (at most 3), if they also share 40% of the question's words or reach 0.87 (meaning alone showed a hadith on the Last Hour's battles for «what does jihad mean?»). Otherwise the answer is "not found". A glossary card appears only when the question asks what the term means («ما معنى التوحيد؟»), not whenever it names one. Without E5 (BM25 only), a passage must contain 65% of the question's words. A question («لماذا خلق الله الشر؟») is never checked as a misquoted verse; only text that isn't a question is. These bars were set by reading what 30 questions showed (`eval/display_audit.py`); re-run it after changing them.
- **Speed, measured per step.** Every answer carries `trace.timings` (steps in ms, and each model call with its provider, tokens and tokens per second), shown in the "How I found this" sheet, and the server logs one `sabeeli.timing` line per question. `eval/speed_report.py` runs the 30 audit questions and prints median, 90th percentile and worst per step. On 2026-10-03 (Gemma 4 31B on OpenRouter, E5 on the GPU): 2.8 s median per answer, 3.7 s p90. The answer call is 1.6 s (59%) and the analysis call 1.1 s (40%). All of retrieval is 76 ms (E5 query 26 ms, FAISS 27 ms, BM25 6 ms), and related videos take 39 ms. The slow outliers are answers that OpenRouter sent to a slower host (DeepInfra, 52 tok/s against ModelRun's 157).

## 4. Evaluation (decides every change)

- **Cases:** 60 synthetic cases in `eval/cases.csv`, 30 Arabic and 30 English:
  - 20 photo/quote matching;
  - 20 explanation and follow-up;
  - 10 limits and disagreement;
  - 10 personal fatwa.

  Include the package's 12 sample cases.
- **Runs:** 3 per case (180).
- **Automatic checks per run:**
  - correct behaviour (answer / abstain / refer / quote_differs);
  - expected source ids retrieved and cited;
  - cited share of the text ≥ 0.8;
  - no scripture guard needed;
  - no ruling on level D.
- **Human review:** check the failures with the reviewer.
- **Built (3 October):** `eval/run_eval.py` runs the set and scores each run on behaviour, sources, grounding, scripture, no ruling at level D and the case patterns. It runs in-process with `--runs N`, with `--sources-only` (no model, free) and with `--rescore`. Results go to `eval/results/`, and the numbers and change log to `eval/REPORT.md`.
- **Targets:** 90% composite success, and 10/10 safe behaviour on personal fatwa.
- **Change log:** record each change (prompt, BM25 weights, embeddings on or off) with its score in `eval/REPORT.md`.

## 5. Order of work

1. Add the API key and run the 6 sample questions.
2. ~~Write the 60 cases~~ done (`eval/cases.csv`, `eval/photos/`).
3. ~~Build the eval runner and get a baseline score~~ done: 88%, then 95% after the first fixes (`eval/REPORT.md`).
4. ~~Ingest «بينات»~~ done (built locally); the icadb Q&A encyclopedias are in too.
5. ~~Add embeddings with fusion~~ built; keep them on only if the evaluation score improves.
6. Tune the prompts and thresholds on the failures.
7. Run the final evaluation, then update the deck and README.
