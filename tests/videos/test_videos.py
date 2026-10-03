"""Videos feature (IslamHouse). Owner: Mushari. No network: the IslamHouse index is built from fixtures."""
import threading

import pytest

from backend.app.features.videos import islamhouse


def _raw(id_, title, attachments, description="", authors=(), added=0):
    return {"id": id_, "title": title, "description": description, "full_description": None, "add_date": added,
            "image": f"https://d1.islamhouse.com/{id_}.jpg", "attachments": attachments,
            "prepared_by": [{"title": a} for a in authors]}


MP4 = {"extension_type": "MP4", "url": "https://d1.islamhouse.com/a.mp4", "description": "part", "size": "9 MB"}
YT = {"extension_type": "YOUTUBE", "url": "https://www.youtube.com/embed/abc?rel=0", "description": None}
PDF = {"extension_type": "PDF", "url": "https://d1.islamhouse.com/a.pdf", "description": None}


def _index(lang="ar"):
    idx = islamhouse.Index(lang)
    items = [
        islamhouse._item(_raw(1, "صفة الصلاة", [MP4], "تطبيق عملي", ["الفريق العلمي"], added=30), lang),
        islamhouse._item(_raw(2, "أحكام الأضحية", [MP4, MP4], "شروط الصلاة غير مذكورة هنا", added=20), lang),
        islamhouse._item(_raw(3, "La prière du voyageur", [YT], added=10), lang),
    ]
    items[0]["topic_id"], items[0]["topic"] = 100, "الصلاة"
    idx.items = items
    idx.members = {100: {1}, 200: {2, 3}}
    idx.topics = [{"id": 100, "title": "فقه", "count": 1}, {"id": 200, "title": "العقيدة", "count": 2}]
    idx.built_at = 1.0
    return idx


def test_item_keeps_only_playable_media_and_prefers_files():
    assert islamhouse._item(_raw(9, "كتاب", [PDF]), "ar") is None          # "videos" that are really PDFs
    both = islamhouse._item(_raw(8, "درس", [YT, MP4]), "ar")
    assert [p["kind"] for p in both["parts"]] == ["mp4"]                     # same talk twice: keep the IslamHouse file
    only_yt = islamhouse._item(_raw(7, "درس", [YT]), "ar")
    assert only_yt["parts"][0]["url"].startswith("https://www.youtube-nocookie.com/embed/")
    assert only_yt["page_url"] == "https://islamhouse.com/ar/videos/7/"


def test_descriptions_are_plain_text():
    it = islamhouse._item(_raw(6, "<b>عنوان</b>", [MP4], "سطر<br>آخر &amp; <a href='x'>رابط</a>"), "ar")
    assert it["title"] == "عنوان"
    assert it["description"] == "سطر\nآخر & رابط"


def test_search_ignores_hamza_taa_marbuta_article_and_accents():
    idx = _index()
    for q in ["صلاة", "الصلاه", "صلاه"]:
        assert [x["id"] for x in idx.query(None, 1, 10, q)["items"]] == [1, 2]   # title match ranks first
    assert [x["id"] for x in idx.query(None, 1, 10, "PRIERE")["items"]] == [3]
    assert [x["id"] for x in idx.query(None, 1, 10, "الفريق")["items"]] == [1]   # author names are searched
    assert idx.query(None, 1, 10, "zzqq")["total"] == 0


def test_topic_filter_combines_with_search_and_pages():
    idx = _index()
    assert [x["id"] for x in idx.query(200, 1, 10)["items"]] == [2, 3]
    assert [x["id"] for x in idx.query(200, 1, 10, "صلاة")["items"]] == [2]
    page2 = idx.query(None, 2, 2)
    assert (page2["page"], page2["pages"], page2["total"], [x["id"] for x in page2["items"]]) == (2, 2, 3, [3])


def test_route_reports_loading_then_ready(client, monkeypatch):
    monkeypatch.setattr(islamhouse, "get_index", lambda lang: (None, "loading"))
    r = client.get("/api/videos?lang=fr")
    assert r.status_code == 200 and r.json()["state"] == "loading" and r.json()["items"] == []

    idx = _index("ar")
    monkeypatch.setattr(islamhouse, "get_index", lambda lang: (idx, "ready"))
    d = client.get("/api/videos", params={"lang": "ar", "topic": 200}).json()
    assert d["state"] == "ready" and d["total"] == 2
    assert d["source"]["name"] == "IslamHouse" and d["topics"][0]["title"] == "فقه"
    # search words travel in a POST body, never in the URL (access logs)
    d = client.post("/api/videos/search", json={"lang": "ar", "q": "الصلاة", "topic": 100}).json()
    assert d["total"] == 1 and d["items"][0]["id"] == 1


def test_outage_is_reported_once_and_not_retried_in_a_loop(client, monkeypatch):
    calls = []

    def broken_build(self):
        calls.append(self.lang)
        raise islamhouse.httpx.ConnectError("IslamHouse down")

    monkeypatch.setattr(islamhouse.Index, "build", broken_build)
    islamhouse._errors.pop("zz", None)
    islamhouse._build("zz")                         # what the background thread runs
    assert calls == ["zz"]
    assert islamhouse.get_index("zz") == (None, "unavailable")
    assert calls == ["zz"]                          # no new attempt within RETRY_AFTER
    d = client.get("/api/videos?lang=zz").json()
    assert d["state"] == "unavailable" and d["items"] == []
    islamhouse._errors.pop("zz", None)


def test_only_known_languages_are_indexed_once_the_list_is_loaded(monkeypatch):
    monkeypatch.setitem(islamhouse._languages, "list", [{"code": "ur", "name": "اردو", "count": 1545}])
    assert islamhouse.is_language("ur") and islamhouse.is_language("en")
    assert not islamhouse.is_language("zz")         # falls back to Arabic: no build for made-up codes
    monkeypatch.setitem(islamhouse._languages, "list", [])
    assert islamhouse.is_language("zz")             # list not loaded yet: tried, under the build cap
    assert not islamhouse.is_language("../x")


def test_at_most_max_builds_run_at_once(monkeypatch):
    gate = threading.Event()
    monkeypatch.setattr(islamhouse.Index, "build", lambda self: gate.wait(5))
    monkeypatch.setattr(islamhouse, "_indexes", {})
    monkeypatch.setattr(islamhouse, "_errors", {})
    monkeypatch.setattr(islamhouse, "_building", {f"busy{i}": None for i in range(islamhouse.MAX_BUILDS)})
    assert islamhouse.get_index("ur") == (None, "loading")
    assert "ur" not in islamhouse._building         # no free slot: waits, the client keeps polling
    del islamhouse._building["busy0"]
    assert islamhouse.get_index("ur") == (None, "loading")
    started = islamhouse._building["ur"]            # a slot freed up: the build starts
    gate.set()
    started.join(5)
    assert "ur" in islamhouse._indexes and "ur" not in islamhouse._building


def test_languages_outage_is_not_retried_for_every_visitor(monkeypatch):
    calls = []

    def down():
        calls.append(1)
        raise islamhouse.httpx.ConnectError("IslamHouse down")

    monkeypatch.setattr(islamhouse, "_fetch_languages", down)
    monkeypatch.setattr(islamhouse, "_languages", {"at": 0.0, "list": [], "failed": 0.0})
    for _ in range(3):
        with pytest.raises(Exception):
            islamhouse.languages()
    assert len(calls) == 1                          # one attempt per RETRY_AFTER, not one per request
    islamhouse._languages.update(list=[{"code": "en", "name": "English", "count": 1615}], failed=0.0)
    assert islamhouse.languages()[0]["code"] == "en"    # a failed refresh keeps serving the last good list
    assert len(calls) == 2


def test_index_without_a_topic_tree_still_lists_videos(monkeypatch):
    page = {"links": {"pages_number": 1}, "data": [_raw(1, "صفة الصلاة", [MP4])]}

    def fake_get(client, path):
        if path.startswith("main/videos/"):
            return page
        raise islamhouse.httpx.ConnectError("tree down")

    monkeypatch.setattr(islamhouse, "_get", fake_get)
    idx = islamhouse.Index("ar")
    idx.build()
    assert [x["id"] for x in idx.items] == [1] and idx.topics == [] and idx.members == {}


def test_languages_list_from_islamhouse_counts(monkeypatch):
    home = {"data": [{"language_code": "en", "title": "English"}, {"language_code": "ur", "title": "اردو"},
                     {"language_code": "af", "title": "Afrikaans"}]}
    counts = {"en": 1615, "ur": 1545, "af": 0}

    def fake_get(client, path):
        if path == "main/home/json":
            return home
        code = path.split("/")[2]
        return [{"block_name": "books", "items_count": 9}, {"block_name": "videos", "items_count": counts[code]}]

    monkeypatch.setattr(islamhouse, "_get", fake_get)
    monkeypatch.setitem(islamhouse._languages, "at", 0.0)
    out = islamhouse.languages()
    assert out == [{"code": "en", "name": "English", "count": 1615}, {"code": "ur", "name": "اردو", "count": 1545}]
    islamhouse._languages.update(at=0.0, list=[])


def test_languages_route(client, monkeypatch):
    monkeypatch.setattr(islamhouse, "languages", lambda: [{"code": "en", "name": "English", "count": 1615}])
    assert client.get("/api/videos/languages").json()[0]["code"] == "en"

    def down():
        raise RuntimeError("offline")
    monkeypatch.setattr(islamhouse, "languages", down)
    assert client.get("/api/videos/languages").status_code == 503
