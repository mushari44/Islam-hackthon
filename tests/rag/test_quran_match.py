"""Verse matching and misquote detection. Owner: Mushari."""
import pytest

from backend.app.core.textnorm import skeleton
from backend.app.features.rag.quran_match import get_matcher


@pytest.fixture(scope="module")
def matcher():
    return get_matcher()


@pytest.mark.parametrize("text,ids", [
    ("قل هو الله احد الله الصمد", ["q:112:1", "q:112:2"]),
    ("لا إكراه في الدين قد تبين الرشد من الغي", ["q:2:256"]),
    ("يا أيها الذين آمنوا كتب عليكم الصيام كما كتب على الذين من قبلكم لعلكم تتقون", ["q:2:183"]),
    ("الحمد لله رب العالمين الرحمن الرحيم مالك يوم الدين", ["q:1:2", "q:1:3", "q:1:4"]),
    ("وأقيموا الصلاة وآتوا الزكاة واركعوا مع الراكعين", ["q:2:43"]),
    ("قال تعالى: إنا أنزلناه في ليلة القدر وما أدراك ما ليلة القدر صدق الله العظيم", ["q:97:1", "q:97:2"]),
])
def test_exact_quotes(matcher, text, ids):
    best = matcher.match(text)[0]
    assert best.ids == ids
    assert best.exact, best.differences


@pytest.mark.parametrize("text,ids,quoted,reference_has", [
    ("قل هو الله واحد الله الصمد", ["q:112:1", "q:112:2"], "واحد", "أحد"),
    ("قال هو الله أحد", ["q:112:1"], "قال", "قل"),
    ("لا اكراه في الدين قد تبين الحق من الباطل", ["q:2:256"], "الحق", "الرشد"),
])
def test_changed_words(matcher, text, ids, quoted, reference_has):
    best = matcher.match(text)[0]
    assert best.ids == ids
    assert not best.exact
    # compare letter skeletons: Uthmani reference text carries marks the typed word doesn't
    assert any(d["type"] == "changed" and d["quoted"] == quoted and skeleton(reference_has) in skeleton(d["reference"])
               for d in best.differences)


def test_missing_middle(matcher):
    best = matcher.match("يا أيها الذين آمنوا كتب عليكم الصيام لعلكم تتقون")[0]
    assert best.ids == ["q:2:183"]
    assert [d["type"] for d in best.differences] == ["missing"]


def test_short_phrase_is_ambiguous(matcher):
    results = matcher.match("إن الله غفور رحيم")
    assert len(results) > 1 and results[0].ambiguous


def test_non_quran_text(matcher):
    assert matcher.match("هذا نص عربي عادي لا علاقة له بالقرآن الكريم ابدا ولا بغيره") == []
