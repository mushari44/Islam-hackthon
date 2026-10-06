# Sabeeli: how the AI works (deck content)

The slides are built from this text: `docs/Sabeeli-AI-deck.pptx` and `docs/Sabeeli-AI-deck.pdf`. Every number here comes from the repo (`eval/REPORT.md`, `docs/RAG-PLAN.md`, `docs/DATA-PIPELINE.md`, `docs/SOURCES.md`).

## 1. Sabeeli (سَبِيلي)

Cited answers about Islam in your language, and a da'i when it matters. Open track, AI in the Service of Islamic Content Challenge 2026. Team: Mushari Alothman, Eman Saheli. Live: https://sabeeli-self.vercel.app

## 2. The problem

- A person curious about Islam, or a new Muslim, asks a chatbot and gets fluent text with no source, and sometimes a misquoted verse or a hadith that doesn't exist.
- They can't tell which sentence is reliable, and a personal question can get a personal "ruling" from a machine.
- Sabeeli's promise: every sentence shows its approved source, Quran and hadith text is never generated, and personal cases go to a person.

## 3. What the AI does

Four jobs, all through one model gateway (`core/claude.py`: Gemma 4 31B on OpenRouter by default, Claude as an option):

1. **Analyse** the question: language, content level A-D, personal case or not, any quoted verse, and 2-4 search phrases in Arabic and English.
2. **Read a photo** of a verse or a saying (transcription only; the check is done in code).
3. **Write the answer** from retrieved passages only, citing each sentence.
4. **Draft the referral card** for the da'i, which the seeker edits and approves before it is shared.

The same cited pipeline answers mentions of the Sabeeli assistant (@سبيلي) in community groups.

## 4. The pipeline

Question → analysis (model) → hybrid retrieval over 10,626 approved records → answer (model, numbered sources) → code checks (grounding, scripture guard, markers) → answer with a source card under every statement and a "How I found this" sheet.

When the model is unavailable, a sources-only mode shows the matching approved passages without a written answer.

## 5. The sources (scholarly package only)

| Source | Package page | Records |
|---|---|---|
| Mushaf text, At-Tafsir Al-Muyassar, Rowwad English (QuranEnc) | p. 9 | 6,236 verses |
| HadeethEnc | pp. 9-10 | 3,574 hadiths |
| icadb Q&A encyclopedias (non-Muslims, Muslims) | p. 10 | 543 answers |
| «بينات» (built locally, rights reserved) | p. 4 | 263 questions |
| Package glossary | p. 7 | 10 terms |
| IslamHouse videos (shown, never cited) | p. 9 | 107 languages |

Official APIs only, no scraping. Each record keeps the link to the original.

## 6. Retrieval

- **Natural units, never fixed chunks:** one verse, one hadith, one Q&A item, each with a stable id (`q:2:256`, `h:2962`).
- **Hybrid search:** multilingual E5-large (FAISS, local) + Arabic BM25 with Uthmani-aware normalisation, fused by weighted reciprocal rank (70% dense, 30% BM25).
- **Answer slot:** the closest approved Q&A answer (E5 ≥ 0.84) always gets a place.
- **Measured:** an expected source is among the 8 passages the model reads in 17/23 cases with BM25 alone, 22/23 with the hybrid, 23/23 with the answer slot.
- **Abstain:** below the similarity bar, the answer is "not found in the approved sources", never a weak match.

## 7. Grounded generation

- The model never types Quran or hadith text: it writes `[[q:S:A]]` / `[[h:ID]]` and the app shows the stored text.
- **Strict grounding:** every sentence must cite a retrieved passage or it is removed. Only short connectors pass (≤ 6 words, ≤ 3 at level D, no ruling words). An answer with no citation becomes the fixed "not found" message.
- **Scripture guard:** text in ﴿﴾ or quotation marks is matched to the Mushaf and replaced by the real verse; 7+ words that follow the Mushaf are replaced too; a quoted saying found in no retrieved passage removes its sentence.
- Citation faithfulness was checked: median E5 similarity 0.84 between 287 cited sentences and their passages; the 34 under 0.80 were read by hand and all were faithful paraphrases.

## 8. Quote and photo check

A typed or photographed verse is compared word by word with the Mushaf (deterministic, no model): exact, differs (each differing word shown), several possible verses, or not found. A saying printed as if it were a verse is caught as "not in the Quran".

## 9. Scholarly safety

- **Content levels:** A answer with source; B explain from approved material; C note that scholars differ; D personal case: general information, the fatwa notice and a da'i, never "allowed/required for you".
- **No personal fatwa** in any path, including sources-only mode (level D shows no raw texts at all).
- **Human in the loop:** a live call with a da'i who speaks the seeker's language; the referral card is shared only after the seeker approves it.
- **Privacy:** anonymous by default, questions deleted after 24 hours, model calls only to providers that don't store or train on prompts, synthetic data only in tests and evaluation.

## 10. Evaluation

60 synthetic cases (30 Arabic, 30 English), including the package's 12 sample cases: 20 quotes and photos, 20 explanations and follow-ups, 10 limits (missing sources, invented hadith, disputed matters), 10 personal fatwa. Each run must pass every check: behaviour, expected source, grounding, no generated scripture, no personal ruling.

| Run | Passed |
|---|---|
| Baseline | 88% (53/60) |
| After fixes | 95% (57/60) |
| Final, 3 runs per case | **100% (180/180)**, personal fatwa 30/30 safe |
| No model (fallback) | 73% (44/60) |

## 11. Speed and cost

- Median 2.8 s per answer, 3.7 s p90 (analysis 1.1 s, answer 1.6 s, all retrieval 76 ms).
- About $0.0007 per question with Gemma 4 31B; the whole evaluation cost about $0.22.
- 229 automated tests run with the model mocked.

## 12. Limits and next steps

- Ask the scholarly reviewer to confirm At-Tafsir Al-Muyassar (p. 3 names other tafsir sources) and sign off on the corpus.
- The free live server runs keyword search only and without «بينات», so it says "not found" more often than the evaluated setup.
- Short verses (under 7 words) typed by the model without quotation marks can slip past the guard.
- English answers rely on verses and hadiths; add English Q&A sources from the package (icadb translations, IslamHouse, Byenah).
- Stream answers, and measure benefit with real seekers and da'is.
