# Source data pipeline: extract, normalise, process (owner: Mushari)

## 1. Extract

| Source | Script | API | Output |
|---|---|---|---|
| Quran text + At-Tafsir Al-Muyassar | `scripts/ingest_quran.py` | `quranenc.com/api/v1/translation/sura/arabic_moyassar/{1..114}` | `data/corpus/quran.jsonl` |
| English translation (Rowwad) | same script | `.../english_rwwad/{sura}` (footnote markers `[n]` stripped) | merged into the same verse rows |
| Surah names | same script | `www.mp3quran.net/api/v3/suwar?language=ar\|eng` | merged |
| Hadith | `scripts/ingest_hadith.py` | `hadeethenc.com/api/v1/categories/list`, `hadeeths/list` (every category, paged), `hadeeths/one` (ar and en) | `data/corpus/hadith.jsonl`, `hadith_categories.json`; raw responses cached in `data/raw/hadith/` (git-ignored) |
| Glossary | written by hand | page 7 of the scholarly package | `data/corpus/glossary.json` |
| Q&A encyclopedias (icadb) | `scripts/ingest_icadb.py` | `icadb.com/api/encyclopedias/{110,102}/cards/latest/` (public export, approved versions only) | `data/corpus/qa.jsonl` (543 items); raw responses in `data/raw/icadb/` |
| «بينات» | `scripts/ingest_bayyinat.py` (needs `pip install pymupdf`) | the PDF linked from `dawa.center/file/7937` | `data/corpus/bayyinat.jsonl` (263 questions), **git-ignored**: the book's rights are reserved, so each copy builds it |

**Verses inside the Q&A sources** never reach the user as copied text:
- icadb answers quote verses as text between ﴿ ﴾. Each one is matched against the Mushaf, piece by piece, using the aya numbers the source writes, and replaced by `[[q:S:A]]` markers (1,002 of them). A phrase that occurs in several verses and has no number (18 cases) is left as the source wrote it. Every replacement was checked against the sura name the source gives after the verse: 669 agree, and the 3 that don't are errors in the source's own reference.
- Bayyinat sets verses in the King Fahd Complex page fonts, which carry no text. Each verse is followed by its reference (`[يس: 40]`), which becomes the markers (847). A verse with no reference next to it (63) becomes ﴿…﴾ rather than a guess.
- Bayyinat's text layer is rebuilt line by line from glyph positions, which repairs the reversed lam-alef and «الله» ligatures, spaces drawn on top of letters, and punctuation the layout moved. Questions are split on the book's own labels (السؤال، عبارات مشابهة، مضمون السؤال، مختصر الإجابة، الجواب التفصيلي) and titled from its table of contents.

Not fetched: islamenc.com's other encyclopedias and books (icadb also serves books with translations, a candidate for English content), Jamhara, Dorar, Shamela.

To re-run (takes a few minutes; the hadith script reuses its cache):

```bash
python scripts/ingest_quran.py
python scripts/ingest_hadith.py --workers 6
python scripts/ingest_icadb.py          # --refresh to download again
python scripts/ingest_bayyinat.py       # downloads the PDF once into data/raw/bayyinat/
```

The BM25 index (`data/cache/bm25.pkl`) rebuilds by itself when a corpus file changes.

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
- **Q&A `qa:ID`:** one icadb card: question, answer (with verse markers), categories, encyclopedia, islamenc.com link.
- **Bayyinat `b:N`:** one question of the book: title, section, question, similar wordings, gist, short answer, detailed answer (with verse markers) and page.

A Q&A or Bayyinat item is never cut into chunks; the model sees the question and the first 4,000 characters of the answer, line by line so each line is citable, and the card shows all of it. The verses inside a retrieved answer may be shown as markers too.

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

## 4. Embed (optional semantic search, `features/rag/embeddings.py`)

`python scripts/build_embeddings.py` embeds every passage with `intfloat/multilingual-e5-large` (prefix `passage: `, normalised vectors) and saves a LangChain FAISS index to `data/cache/vectors/<model>/` with a `stamp.json` (model, corpus file sizes, chunk count, time). Re-run it after any change in `data/corpus/`; the app warns if the index was built from a different corpus.

What is embedded:
- a verse: its text without marks, the tafsir and the English translation;
- a hadith: the Arabic title, text and explanation, plus the same in English when translated;
- a term: both forms, aliases and the usage rule;
- a Q&A item: ~900-character chunks of the answer, each starting with the question (verse markers removed);
- a Bayyinat question: the question with its similar wordings, the gist with the short answer, then chunks of the detailed answer.
