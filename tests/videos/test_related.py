"""Related videos under an answer. Owner: Mushari. No network and no real model: a small fixture index
and a fake encoder whose vectors are set by hand."""
import numpy as np

from backend.app.features.videos import islamhouse, related


def _vid(id_, title, topic=None, description="", added=0):
    it = islamhouse._item({"id": id_, "title": title, "description": description, "full_description": None,
                           "add_date": added, "image": None, "prepared_by": [],
                           "attachments": [{"extension_type": "MP4", "url": f"https://d1.islamhouse.com/{id_}.mp4"}]}, "ar")
    it["topic"] = topic
    return it


def _index():
    idx = islamhouse.Index("ar")
    idx.items = [
        _vid(1, "بشائر في صيام شهر رمضان", "حكم الصيام وفضله"),
        _vid(2, "صفة الصلاة", "الصلاة", "تطبيق عملي لصفة صلاة النبي"),
        _vid(3, "سلسلة ما لا يسع أطفال المسلمين جهله", "شؤون الطفل"),
        _vid(4, "فضل يوم عاشوراء", "الصيام"),
        _vid(5, "لماذا ندرس التوحيد؟", "التوحيد وأقسامه"),
        _vid(6, "صفة الصلاة", "الصلاة", "الجزء الثاني"),     # same title again (a series)
    ]
    # filler, so word rarity looks like a real list: hundreds of videos, where words such as
    # "المسلمين" and "يوم" are common
    idx.items += [_vid(100 + i, f"درس اليوم للمسلمين {i}" if i % 3 else f"محاضرة مسجلة {i}", "متفرقات") for i in range(300)]
    idx.built_at = 1.0
    return idx


class FakeEncoder:
    """Vectors chosen by hand: video i points along axis i; the question points where the test says."""

    def __init__(self, query_vec):
        self.query_vec = np.asarray(query_vec, dtype="float32")

    def embed_documents(self, texts):
        return np.eye(len(texts), 8, dtype="float32").tolist()

    def embed_query(self, text):
        return self.query_vec.tolist()


def test_words_alone_need_a_strong_match():
    idx = _index()
    hits = related.related(idx, "كيف أصلي؟", ["صفة الصلاة", "كيفية الصلاة"])
    assert [h["id"] for h in hits] == [2]                 # the series repeat of "صفة الصلاة" is suggested once
    # common words ("المسلمون", "اليوم") anchor nothing on their own
    assert related.related(idx, "لماذا يصوم المسلمون شهرا كاملا؟") == []
    assert related.related(idx, "ما الطقس اليوم في الرياض؟") == []


def test_meaning_decides_and_borderline_needs_words():
    idx = _index()
    st = related._stats(idx)
    st.vectors = np.eye(len(idx.items), 8, dtype="float32")    # video i (i < 8) points along axis i
    q = np.zeros(8, dtype="float32")
    q[0], q[3] = 0.90, 0.83        # video 1 (Ramadan) clearly close; video 4 (Ashura) borderline with no shared word
    hits = related.related(idx, "لماذا يصوم المسلمون شهرا كاملا؟", encoder=FakeEncoder(q))
    assert [h["id"] for h in hits] == [1]
    assert hits[0]["match"]["meaning"] == 0.9
    q = np.zeros(8, dtype="float32")
    q[4] = 0.83                    # borderline meaning, and the words agree ("التوحيد"): suggested
    assert [h["id"] for h in related.related(idx, "ما معنى التوحيد؟", encoder=FakeEncoder(q))] == [5]
    q[4] = 0.5                     # far in meaning: words alone don't override the encoder
    assert related.related(idx, "ما معنى التوحيد؟", encoder=FakeEncoder(q)) == []


def test_nothing_is_suggested_while_the_videos_are_being_embedded(monkeypatch):
    idx = _index()
    started = []
    monkeypatch.setattr(related, "_embed_in_background", lambda st, enc: started.append(enc))
    enc = FakeEncoder(np.zeros(8))
    assert related.pending(idx, enc) is True and started == [enc]
    assert related.related(idx, "صفة الصلاة", encoder=enc) == []     # no word-only guesses meanwhile
    assert related.pending(idx, None) is False                        # without the encoder: words only


def test_route(client, monkeypatch):
    monkeypatch.setattr(islamhouse, "get_index", lambda lang: (None, "loading"))
    d = client.post("/api/videos/related", json={"lang": "ar", "q": "كيف أصلي؟"}).json()
    assert d["state"] == "loading" and d["items"] == []
    idx = _index()
    monkeypatch.setattr(islamhouse, "get_index", lambda lang: (idx, "ready"))
    d = client.post("/api/videos/related", json={"lang": "ar", "q": "كيف أصلي؟", "hints": ["صفة الصلاة"]}).json()
    assert d["state"] == "ready" and [x["id"] for x in d["items"]] == [2]
    assert d["items"][0]["page_url"].startswith("https://islamhouse.com/ar/videos/")
    assert client.post("/api/videos/related", json={"lang": "ar", "q": "x", "hints": ["y" * 201]}).status_code == 422
