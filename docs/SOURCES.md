# Islamic sources and how Sabeeli verifies them

This is the judges' document for the challenge requirement "documentation of the Islamic sources and how they are verified". Page numbers refer to the challenge's scholarly package (الحزمة العلمية). Licences and terms are in [`THIRD_PARTY.md`](../THIRD_PARTY.md); the extraction scripts are described in [`DATA-PIPELINE.md`](DATA-PIPELINE.md); the answer pipeline in [`RAG-PLAN.md`](RAG-PLAN.md); the test results in [`../eval/REPORT.md`](../eval/REPORT.md).

## 1. The rule

Sabeeli answers **only** from sources named in the scholarly package. Nothing comes from the model's memory:

1. Every sentence of an answer must cite an approved passage, or it is removed before the user sees it.
2. Quran and hadith text is **never generated**. The model writes a reference (`[[q:2:255]]`, `[[h:3062]]`) and the app shows the text from the stored source.
3. Personal rulings (fatwa) are never given, in any track (package pp. 2, 4, 5). Personal questions get general information, the fatwa notice and an offer to talk to a da'i.
4. When the sources don't answer, Sabeeli says so ("not found in the approved sources") and offers a da'i, rather than filling the gap.

## 2. The sources

### Cited in answers (10,626 records in the corpus)

| Source | Package page | What we use | Records | How we got it |
|---|---|---|---|---|
| The Mushaf (King Fahd Complex text), via QuranEnc | p. 9 (QuranEnc: "the Quran, its tafsirs and translations of its meanings") | Uthmani text of every verse | 6,236 verses | QuranEnc public API, `scripts/ingest_quran.py` |
| At-Tafsir Al-Muyassar, via QuranEnc (`arabic_moyassar`) | p. 9 | Arabic explanation of each verse | 6,236 | same API and script |
| Rowwad Translation Center English translation, via QuranEnc (`english_rwwad`) | p. 9 | English meaning of each verse | 6,236 | same API and script |
| HadeethEnc (Encyclopedia of Translated Prophetic Hadiths) | pp. 9-10 (the association's platforms) | Hadith text, grade, attribution, explanation and lessons | 3,574 (2,328 also in English) | HadeethEnc public API, `scripts/ingest_hadith.py` |
| icadb: «موسوعة الأسئلة والأجوبة لغير المسلمين» and «موسوعة الأسئلة والأجوبة للمسلمين» | p. 10 | Approved answers to doubts and new-Muslim questions | 543 (Arabic) | icadb public export API, approved versions only, `scripts/ingest_icadb.py` |
| «بينات: أسئلة وأجوبة عن الإسلام» (مركز أصول) | p. 4 (named for doubts and recurring questions) | Short and detailed answers | 263 | The package's link (dawa.center/file/7937), `scripts/ingest_bayyinat.py`. Rights reserved by the publisher, so it is **not** in the public repo: each copy builds it locally |
| The package's sample glossary | p. 7 | 10 core terms, their approved English forms and usage rules | 10 | Typed from the package |

### Shown, never cited

| Source | Package page | Use |
|---|---|---|
| IslamHouse videos | p. 9 | The «مرئيات» library (107 languages). Streamed from IslamHouse's own servers, titles and descriptions shown exactly as published, every card links back. Never summarised by a model and never used as evidence in an answer |
| mp3quran.net | p. 12 | Surah names only |

Sources named in the package but **not** ingested yet (Byenah, Dorar, Shamela, the Kuwaiti Fiqh Encyclopedia, Siwar, the King Fahd Complex files, more QuranEnc and HadeethEnc languages) are listed in the team's source inventory; adding any of them requires checking it against the package first, with its page number.

## 3. How each source is checked when it enters the corpus

- **Official APIs only, no scraping.** Every record keeps its id and the URL of the same item on the publisher's site, so a judge can open the original from any citation card.
- **Text is stored as published.** Search uses a normalised copy (no diacritics, unified alef, etc.); the user always sees the original text (`core/textnorm.py`).
- **Counts are checked after each run:** 6,236 verses with no empty tafsir or translation (the script fails otherwise), 3,574 unique hadith ids, 543 unique icadb cards, 263 Bayyinat questions. These were re-counted against each source's own API on 4 October.
- **Verses inside Q&A answers come from the Mushaf, not from the copy.** icadb and Bayyinat answers quote verses; each quote is matched against the Mushaf using the reference the source gives and replaced by a verse marker (1,002 in icadb, 847 in Bayyinat). Every icadb replacement was checked against the sura name the source wrote: 669 agree, and the 3 that don't are errors in the source's own reference. A quote that can't be placed with certainty is left as the source wrote it, never guessed.
- **Small, deliberate edits are recorded:** Rowwad footnote marks `[n]` are removed from the running text (the footnotes are kept in their own field); hadith fields are only trimmed.

## 4. How every answer is checked before it is shown

These run in code on every question (`backend/app/features/rag/pipeline.py`); none depends on the model behaving well.

| Check | What it does |
|---|---|
| Content level A-D | The analysis step classifies the question. Level D (personal case) gets general information, the fixed fatwa notice and a da'i referral, never "this is allowed/required for you" |
| Retrieval threshold | Hybrid search (multilingual E5 + Arabic BM25). If no passage is close enough, the answer is "not found in the sources" |
| Strict grounding | Each sentence must carry a citation to a retrieved, approved passage, or it is dropped. Only short connectors (at most 6 words, 3 at level D, no ruling words) pass without one. An answer left with no citation becomes the fixed "not found" message |
| Scripture guard | Text in ﴿﴾, {} or quotation marks is matched against the Mushaf and replaced by the stored verse. Seven or more consecutive words that follow the Mushaf are replaced the same way. A quoted saying found in no retrieved passage (a hadith from memory) removes its whole sentence |
| Marker check | Verse and hadith references the model writes are kept only if that passage was retrieved; the app renders the text from the corpus |
| Quote check | A verse typed or photographed by the user is compared word by word with the Mushaf, and every differing word is shown |
| Transparency | Every answer has a "How I found this" sheet: the passages found, their scores, how many sentences the checks removed, and timings |

## 5. Evidence that it works

- **Evaluation set** (`eval/cases.csv`): 60 synthetic cases, 30 Arabic and 30 English, including all 12 sample cases from package p. 6: quoted and photographed verses (with deliberate mistakes), explanations and follow-ups, missing sources and invented hadiths, and 10 personal-fatwa questions.
- **Result, 3 runs per case** (Gemma 4 31B, E5 + BM25, full corpus): **180/180 runs passed** every check (behaviour, expected source, grounding, no generated scripture, no personal ruling), personal fatwa **30/30 safe**, median 2.8 s per answer. Without the model (sources-only fallback): 44/60.
- **Automated tests:** 229 backend tests (`python -m pytest tests`), including the grounding, scripture-guard and quote-matching rules, with the model mocked.

## 6. Known limits (disclosed)

- **At-Tafsir Al-Muyassar** comes from QuranEnc, which p. 9 lists for "the Quran, its tafsirs and translations". The tafsir rule on p. 3 names early sources or dorar.net/tafseer and does not name Al-Muyassar. We ask the scholarly reviewer to confirm it, or we switch to a p. 3 source.
- **Scholarly reviewer:** the reviewer has not signed off on the corpus yet.
- **The live demo differs from the evaluated setup:** the public server (Render, free plan) runs keyword search only (no E5, which needs a 2.2 GB model) and has no Bayyinat (rights reserved, not redistributed). It answers fewer questions and says "not found" more often; it does not loosen any check.
- **Short scripture typed by the model:** the guard catches verses of 7 words or more and any quoted text. A shorter verse or hadith typed without quotation marks can slip past it; in the evaluation this never reached the screen, and it is on the task list.
- **English:** the Q&A sources are Arabic only, so English questions rely more on verses and hadiths with their English translations.
