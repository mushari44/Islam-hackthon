"""What the running app shows for 30 synthetic questions: the sources and the related videos. Owner: Mushari.

A manual check, not a score: read each block and ask "is every source and video here about this question?".
Run it after changing a threshold in features/rag/pipeline.py (SHOW_*) or features/videos/related.py, and
compare with the previous run. The questions are invented; no real user data.

Usage:  python -m uvicorn backend.app.main:app --port 8765   (in another terminal, with the index built)
        python eval/display_audit.py [out.json] [--base http://localhost:8765]
"""
import json
import sys

import httpx

QUESTIONS = [
    # doubts / non-Muslim questions (ar)
    ("ar", "هل القرآن من تأليف محمد؟"),
    ("ar", "لماذا يتجه المسلمون إلى الكعبة في صلاتهم؟"),
    ("ar", "ليش المسلمين يطوفون حول حجر؟"),
    ("ar", "لماذا يسمح الإسلام بتعدد الزوجات؟"),
    ("ar", "ما الدليل على وجود الله؟"),
    ("ar", "لماذا خلق الله الشر؟"),
    ("ar", "هل يجبر الإسلام الناس على الدخول فيه؟"),
    ("ar", "لماذا توقفت النبوة؟"),
    # practice / basics (ar)
    ("ar", "ما أركان الإسلام؟"),
    ("ar", "كيف أصلي؟"),
    ("ar", "لماذا يصوم المسلمون شهرا كاملا؟"),
    ("ar", "ما معنى التوحيد؟"),
    ("ar", "من هو النبي محمد؟"),
    ("ar", "ما حكم الصلاة للحائض؟"),
    # personal / off-topic / edge (ar)
    ("ar", "عمري ١٤ سنة وأخاف أن أهلي لا يقبلون إسلامي"),
    ("ar", "هل يجوز لي أن أتزوج دون علم أهلي؟"),
    ("ar", "ما الطقس اليوم في الرياض؟"),
    ("ar", "من فاز بكأس العالم؟"),
    ("ar", "قل هو الله واحد الله الصمد"),
    # English
    ("en", "Did Muhammad write the Quran?"),
    ("en", "Why do Muslims face Mecca when they pray?"),
    ("en", "Is Islam against science?"),
    ("en", "Who is Jesus in Islam?"),
    ("en", "What are the five pillars of Islam?"),
    ("en", "How do I become a Muslim?"),
    ("en", "Why is pork forbidden?"),
    ("en", "Does Islam oppress women?"),
    ("en", "What is the best football team?"),
    ("en", "Can I keep my name if I convert?"),
    ("en", "What happens after death in Islam?"),
]

BASE = sys.argv[sys.argv.index("--base") + 1] if "--base" in sys.argv else "http://localhost:8765"
c = httpx.Client(base_url=BASE, timeout=120)
tok = c.post("/api/session").json()["token"]
out = []
for lang, q in QUESTIONS:
    d = c.post("/api/ask", data={"question": q, "lang": lang}, headers={"X-Seeker": tok}).json()
    rows = {r["id"]: r for r in d["trace"].get("retrieval", [])}
    shown = [(pid, d["cards"][pid]["title"][:70], rows.get(pid, {}).get("coverage"), rows.get(pid, {}).get("dense"))
             for pid in d["sources"] if pid in d["cards"]]
    vids = []
    if d["kind"] in ("answer", "sources", "abstain"):
        v = c.post("/api/videos/related", json={"lang": d["lang"], "q": q, "hints": []}).json()
        vids = [(x["title"][:60], x["match"]) for x in v["items"]]
    out.append({"q": q, "kind": d["kind"], "level": d["level"], "shown": shown, "videos": vids})
    print(f"\n### {q}  [{d['kind']}, {d['level']}]")
    for pid, title, cov, dense in shown:
        print(f"   {pid:10} cov={cov} dense={dense}  {title}")
    for title, m in vids:
        print(f"   VIDEO {title}  {m}")
target = next((a for a in sys.argv[1:] if a.endswith(".json")), "display_audit.json")
with open(target, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
