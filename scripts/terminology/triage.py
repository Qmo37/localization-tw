"""Machine triage of `glossary_variants` candidates.

The result is an assistant assessment, never a human approval. Groups are only
sorted into "needs a person" and "reference only"; no preferred form is chosen.
"""

import re
import unicodedata
from collections import Counter

CJK = re.compile(r"[㐀-鿿]")
LATIN = re.compile(r"[A-Za-z0-9.+#/()（） ]+")
SPELLING = (("記錄", "紀錄"), ("臺", "台"), ("裏", "裡"), ("着", "著"))
# Forms that read as mainland/Hong Kong usage in a Taiwan glossary column.
# Value: the Taiwan form the project vocabulary uses.
REGIONAL = {"網絡": "網路", "軟件": "軟體", "硬件": "硬體", "視頻": "影片", "客戶端": "用戶端",
            "調用": "呼叫", "控件": "控制項", "交互": "互動", "服務器": "伺服器", "信息": "資訊",
            "內存": "記憶體", "字節": "位元組", "數據": "資料"}
TAIWAN_VALID = ("行動數據",)

CLASSES = {
    "regional-usage-check": (True, "形式含大陸或港式用語，同組沒有對應的臺灣形式，需確認能否作為臺灣用語。"),
    "regional-form-with-taiwan-counterpart": (False, "形式含大陸或港式用語，但同組已有逐字對應的臺灣形式；不建議採用前者。"),
    "project-term-uncovered": (True, "與專案詞條共用英文詞，但專案譯法不在這些形式中，且沒有同詞的主要複核題。"),
    "covered-by-primary-review": (False, "同一英文詞已有主要複核題（譯法差異），不另外詢問。"),
    "spelling-or-decoration-only": (False, "只有異體字、空白、標點或附註差異。"),
    "abbreviation-or-product-name": (False, "含縮寫、產品名或未翻譯的英文形式，屬並列寫法。"),
    "scope-extension": (False, "較短形式包含在較長形式內，為同一詞的不同範圍寫法。"),
    "dictionary-supported": (False, "其中一種形式與中華語文知識庫的臺灣欄一致，僅供參考。"),
    "alternative-terms": (False, "不同用詞並列於術語庫；未推斷偏好，保留作備選。"),
}


def fold(text):
    text = unicodedata.normalize("NFKC", text).lower()
    for a, b in SPELLING:
        text = text.replace(a, b)
    return re.sub(r"[\s\-_·]+", "", text)


def regional_hits(forms):
    """Map each regional form to the Taiwan form the group would need to offer."""
    folded = {fold(f) for f in forms}
    hits = {}
    for form in forms:
        clean = form
        for ok in TAIWAN_VALID:
            clean = clean.replace(ok, "")
        for term, taiwan in REGIONAL.items():
            if term in clean:
                hits[form] = {"term": term, "taiwan": taiwan,
                              "counterpart_present": fold(form.replace(term, taiwan)) in folded}
    return hits


def form_shape(forms):
    folded = {fold(f) for f in forms}
    if len(folded) == 1:
        return "spelling-or-decoration-only"
    chinese = [f for f in forms if CJK.search(f)]
    if len(chinese) <= 1:
        return "abbreviation-or-product-name"
    cores = {fold(LATIN.sub("", f)) for f in chinese}
    if len(cores) == 1:
        return "spelling-or-decoration-only"
    cores = sorted((c for c in cores if c), key=len)
    if all(cores[0] in c for c in cores[1:]):
        return "scope-extension"
    return "alternative-terms"


def classify(conflict, project, linguipedia_tw, primary_terms):
    candidates = conflict["candidates"]
    forms = sorted({t for c in candidates for t in c["tw"]})
    english = {fold(e) for c in candidates for e in c["en"]}
    hits = regional_hits(forms)
    if hits:
        name = "regional-form-with-taiwan-counterpart" if all(
            h["counterpart_present"] for h in hits.values()) else "regional-usage-check"
        return name, {"regional_forms": hits}
    for entry in project:
        if english & entry["en"]:
            if any(fold(t) in fold(f) for t in entry["tw"] for f in forms):
                continue
            if english & primary_terms:
                return "covered-by-primary-review", {"project_terms": sorted(entry["tw"])}
            return "project-term-uncovered", {"project_terms": sorted(entry["tw"])}
    shape = form_shape(forms)
    if shape == "alternative-terms":
        supported = sorted(f for f in forms if fold(f) in linguipedia_tw)
        if supported:
            return "dictionary-supported", {"supported_forms": supported}
    return shape, {}


def triage(conflicts, project_records, linguipedia_records, policies=()):
    project = [{"en": {fold(e) for e in r["en"]}, "tw": r["tw"]} for r in project_records]
    linguipedia_tw = {fold(t) for r in linguipedia_records for t in r["tw"]}
    primary_terms = {fold(c["term"]) for c in conflicts if c["kind"] == "translation_choice"}
    # A "defer" answer means the person could not decide, so the group stays in the queue.
    answered = {(p["conflict_id"], p["fingerprint"]): p["choice"] for p in policies if p["choice"] != "defer"}
    entries, counts = [], Counter()
    for c in conflicts:
        if c["kind"] != "glossary_variants":
            continue
        name, detail = classify(c, project, linguipedia_tw, primary_terms)
        needs_human, note = CLASSES[name]
        choice = answered.get((c["id"], c["fingerprint"]))
        if needs_human and choice:
            needs_human, detail = False, {**detail, "answered_choice": choice}
        counts[name] += 1
        entries.append({"conflict_id": c["id"], "fingerprint": c["fingerprint"], "term": c["term"],
                        "class": name, "needs_human": needs_human, "note": note,
                        "forms": sorted({t for x in c["candidates"] for t in x["tw"]}), **detail})
    return entries, {"total": len(entries), "by_class": dict(counts.most_common()),
                     "needs_human": sum(e["needs_human"] for e in entries),
                     "answered": sum("answered_choice" in e for e in entries),
                     "authority": "assistant-assessment-not-human-approval"}


def regional_questions(entries, conflicts):
    """One question per shared definition among the entries that still need a person."""
    by_id = {c["id"]: c for c in conflicts}
    groups = {}
    for e in entries:
        if e["needs_human"]:
            groups.setdefault(e["term"].rsplit(" / ", 1)[-1], []).append(e)
    questions = []
    for key, members in sorted(groups.items()):
        candidates = [x for m in members for x in by_id[m["conflict_id"]]["candidates"]]
        english = sorted({e for c in candidates for e in c["en"]}, key=lambda t: (-len(t), t))
        definition = next((d["text"] for c in candidates for d in c["definitions"] if d.get("text")), "")
        flagged = sorted({f for m in members for f, h in m.get("regional_forms", {}).items() if not h["counterpart_present"]})
        questions.append({"id": key, "title": " / ".join(english[:2]), "english": english,
                          "forms": sorted({f for m in members for f in m["forms"]}), "flagged_forms": flagged,
                          "definition": definition[:400], "conflict_ids": [m["conflict_id"] for m in members],
                          "fingerprints": {m["conflict_id"]: m["fingerprint"] for m in members}})
    return questions


REGIONAL_KIND = "localization-tw-glossary-regional-review"
REGIONAL_CHOICES = {
    "block": ("hold-mapping", "不採用標示的大陸或港式形式，只暫停指定來源；同組其他形式保留。"),
    "keep-as-vendor-wording": ("retain-context", "保留為微軟產品用字，僅供參考；不推薦給臺灣在地化使用。"),
    "defer": ("defer", "待查，暫不決定；不暫停任何來源。")}
REGIONAL_SCOPE = "只適用於該組列出的微軟術語庫來源；不推定整個英文詞或中文詞是否禁用。"


def regional_policies(answers, questions, conflicts, provenance):
    """Turn portable answers into scoped source policies bound to the current evidence."""
    from datetime import datetime

    from .common import digest
    from .followup import POLICY_KIND
    if not isinstance(answers, dict) or answers.get("kind") != REGIONAL_KIND or answers.get("version") != 1:
        raise ValueError("Not a glossary regional review answer file")
    if answers.get("authority") != "human-answers" or not isinstance(answers.get("reviewer"), str):
        raise ValueError("Answer file has no human authority or reviewer field")
    by_id, lookup = {q["id"]: q for q in questions}, {c["id"]: c for c in conflicts}
    if not isinstance(answers.get("answers"), list) or len({a.get("question_id") for a in answers["answers"]}) != len(answers["answers"]):
        raise ValueError("Answers must be a list with one answer per question")
    policies = []
    for a in answers["answers"]:
        question = by_id.get(a.get("question_id"))
        if question is None:
            raise ValueError(f"{a.get('question_id')}: question is not in the current evidence")
        if a.get("choice") not in REGIONAL_CHOICES or not isinstance(a.get("note", ""), str):
            raise ValueError(f"{question['id']}: invalid answer")
        if datetime.fromisoformat(str(a.get("answered_at")).replace("Z", "+00:00")).tzinfo is None:
            raise ValueError(f"{question['id']}: answer timestamp needs a timezone")
        if a.get("fingerprints") != question["fingerprints"]:
            raise ValueError(f"{question['id']}: source evidence changed; do not apply an old answer")
        choice, text = REGIONAL_CHOICES[a["choice"]]
        for conflict_id in question["conflict_ids"]:
            flagged = [c["id"] for c in lookup[conflict_id]["candidates"]
                       if set(c["tw"]) & set(question["flagged_forms"])]
            policies.append({
                "kind": POLICY_KIND, "version": 1, "id": digest(["glossary-regional", question["id"], conflict_id]),
                "question_id": question["id"], "title": question["title"], "conflict_id": conflict_id,
                "fingerprint": question["fingerprints"][conflict_id], "focus_ids": flagged,
                "held_source_ids": flagged if choice == "hold-mapping" else [],
                "choice": choice, "decision_text": text, "scope": REGIONAL_SCOPE, "note": a.get("note", "").strip(),
                "reviewed_by": answers["reviewer"], "reviewed_at": a["answered_at"],
                "source_verification": "not-applicable" if choice == "hold-mapping" else "still-required",
                "resolves_whole_conflict": False, "provenance": provenance})
    return policies
