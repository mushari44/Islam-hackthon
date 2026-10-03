"""Fixes from the overnight audit (4 October): related videos when embedding fails, and search over
text normalised once per build. Owner: Mushari. No network."""
import time

from backend.app.features.videos import islamhouse, related


def _vid(id_, title, topic=None, description=""):
    it = islamhouse._item({"id": id_, "title": title, "description": description, "full_description": None,
                           "add_date": 0, "image": None, "prepared_by": [],
                           "attachments": [{"extension_type": "MP4", "url": f"https://d1.islamhouse.com/{id_}.mp4"}]}, "ar")
    it["topic"] = topic
    return it


def _index():
    idx = islamhouse.Index("ar")
    idx.items = [_vid(1, "صفة الصلاة", "الصلاة", "تطبيق عملي لصفة صلاة النبي"),
                 _vid(2, "بشائر في صيام شهر رمضان", "الصيام")]
    idx.built_at = time.time()
    return idx


class BrokenEncoder:
    def embed_documents(self, texts):
        raise RuntimeError("out of memory")


def test_a_failed_embedding_falls_back_to_words_instead_of_loading_forever():
    idx, enc = _index(), BrokenEncoder()
    related.pending(idx, enc)               # starts the embedding, which fails in its thread
    for _ in range(50):
        if related._stats(idx).failed:
            break
        time.sleep(0.02)
    assert related._stats(idx).failed
    assert related.pending(idx, enc) is False                   # no endless "loading" and re-embedding
    related.related(idx, "ما صفة الصلاة", encoder=enc)           # words only, no crash


def test_search_uses_text_normalised_once():
    idx = _index()
    assert [it["id"] for it in idx.search(idx.items, "الصلاه")] == [1]
    assert 1 in idx._search_text and [it["id"] for it in idx.search(idx.items, "رمضان")] == [2]
