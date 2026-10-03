# Source data pipeline: extract, normalise, process (owner: Mushari)

## 1. Extract

| Source | Script | API | Output |
|---|---|---|---|
| Quran text + At-Tafsir Al-Muyassar | `scripts/ingest_quran.py` | `quranenc.com/api/v1/translation/sura/arabic_moyassar/{1..114}` | `data/corpus/quran.jsonl` |
| English translation (Rowwad) | same script | `.../english_rwwad/{sura}` (footnote markers `[n]` stripped) | merged into the same verse rows |
| Surah names | same script | `www.mp3quran.net/api/v3/suwar?language=ar\|eng` | merged |
| Hadith | `scripts/ingest_hadith.py` | `hadeethenc.com/api/v1/categories/list`, `hadeeths/list` (every category, paged), `hadeeths/one` (ar and en) | `data/corpus/hadith.jsonl`, `hadith_categories.json`; raw responses cached in `data/raw/hadith/` (git-ignored) |
| Glossary | written by hand | page 7 of the scholarly package | `data/corpus/glossary.json` |

Not fetched yet: icadb.com and islamenc.com (no data was pulled from them) and «بينات» (a PDF on dawa.center). Add each with its own script once its usage terms are confirmed, and record it in `THIRD_PARTY.md`.

To re-run (takes a few minutes; the hadith script reuses its cache):

```bash
python scripts/ingest_quran.py
python scripts/ingest_hadith.py --workers 6
```

The BM25 index (`data/cache/bm25.pkl`) rebuilds by itself when a corpus file changes.

Videos (`backend/app/features/videos/`) are not part of this pipeline: they are read live from the IslamHouse API v3, cached in memory for 6 hours, and never ingested into `data/corpus/`. They are not retrieval units and are never cited in answers.

## 2. Normalise (`backend/app/core/textnorm.py`)

**Rule: store and display the original text; normalise only copies used for search and matching.** Citations and cards always show the original.

- `normalize_ar`:
  - removes harakat and Quranic marks (every combining mark) and tatweel;
  - maps ٱ أ إ آ → ا, ى → ي, ة → ه, ؤ → و, ئ → ي, and Persian ی ک;
  - drops ء;
  - converts the Uthmani spellings: وٰ → ا (صلوٰة → صلاة), mid-word ىٰ → ا (أدرىٰك → أدراك), and the dagger alef → ا.
- `skeleton`: the normalised text with no alef and no spaces. It is used only to match quoted verses, so that Uthmani and everyday spelling agree.
- `tokens`: Arabic and English stop-word removal plus a light stemmer (Arabic prefixes and suffixes, English plurals and -ing / -ed), used for BM25.

## 3. Process into retrieval units (`backend/app/features/rag/corpus.py`)

Each record becomes one `Passage` with a stable id and keeps all its metadata:

- **Verse `q:S:A`:** surah and ayah, surah names, the original Uthmani text, the tafsir, the translation and the source URLs.
- **Hadith `h:ID`:** Arabic and English text, grade, attribution, explanation, lessons, reference, categories and URLs.
- **Term `t:key`:** the Arabic and English term, aliases and the usage rule.

For each passage:

- `search_text()` decides what gets indexed. The tafsir and explanations carry most of the everyday vocabulary people search with; hadith titles are counted twice.
- `context_blocks()` is what Claude sees, as citable blocks: for a verse, the reference text, then the tafsir, then the translation.
- `card()` is what the user sees.

The content level (A-D) is decided per question by the analysis step, not stored per passage.

**Duplicates:**
- hadith ids are collected as a set across all categories (3,574 unique), and one record is written per id;
- verses are unique by surah:ayah;
- the BM25 cache is keyed by file size and modification time.

**Checks after a re-run:**
- 6,236 verses with no empty tafsir or translation (the Quran script exits with an error otherwise);
- the hadith count is printed;
- run `python -m pytest tests/rag` to confirm verse matching still works.
