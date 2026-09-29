"""Literal evidence retrieval with explicit source order and review state."""

import re

from .common import PRIORITY, normalize, plain
from .followup import index_policies


def search(records, query, *, mode="substring", domain="", limit=20, conflicts=(),
           source_policies=(), include_held=False):
    if not query.strip():
        raise ValueError("Query must not be empty")
    if not 1 <= limit <= 1000:
        raise ValueError("Limit must be between 1 and 1000")
    if mode not in ("exact", "substring", "fuzzy", "regex"):
        raise ValueError("Unknown search mode")
    pattern = re.compile(query, re.I) if mode == "regex" else None
    key = normalize(query)
    policies = index_policies(source_policies, conflicts)
    held = {sid for sid, entries in policies.items() if any(p["use_status"] == "on-hold" for p in entries)}
    # A held source cannot serve as a hidden bridge to linked dictionary entries.
    if not include_held:
        records = [r for r in records if r["id"] not in held]
    anchors = {}
    if mode in ("exact", "substring", "fuzzy"):
        for r in records:
            if key in terms_for(r, "en") and (not domain or r["domain"] in (domain, "一般用語", "")):
                for tw in terms_for(r, "tw"):
                    anchors.setdefault(tw, []).append(r["id"])
    by_record = {}
    for c in conflicts:
        for r in c["candidates"]:
            by_record.setdefault(r["id"], []).append({"conflict_id": c["id"], "status": c["status"],
                "reason": c["reason"], "decision": c.get("decision")})
    matches = []
    for r in records:
        if domain and r["domain"] not in (domain, "一般用語", ""):
            continue
        fields = r["en"] + r["tw"] + r["cn"]
        normalized = [normalize(v) for v in fields]
        linked_via = sorted({identity for tw in terms_for(r, "tw") for identity in anchors.get(tw, []) if identity != r["id"]})
        def definitions():
            return (normalize(plain(d.get("display", d["text"]))) for d in r["definitions"])
        if pattern:
            score = 2 if any(pattern.search(v) for v in fields) else 1 if any(pattern.search(v) for v in definitions()) else 0
        elif key in normalized:
            score = 3
        elif linked_via:
            score = 2
        elif mode != "exact" and any(key in v for v in normalized):
            score = 2
        elif mode != "exact" and any(key in v for v in definitions()):
            score = 1
        else:
            score = 0
        if score:
            item = {k: v for k, v in r.items() if k != "original"}
            item.update(match_type={3: "exact-term", 2: "term", 1: "definition"}[score],
                        review=by_record.get(r["id"], []), context_assessment="requires-reader-context")
            if r["id"] in policies:
                item["source_review"] = policies[r["id"]]
                item["source_use_status"] = "on-hold" if r["id"] in held else (
                    "context-or-verification-required" if any(p["active"] for p in policies[r["id"]])
                    else "stale-policy-not-applied")
            if linked_via and key not in normalized:
                item.update(match_type="linked-headword-not-verified-sense", linked_via=linked_via)
            # Contextual human choices are shown, never converted into global replacements.
            item["preference_status"] = "unresolved" if any(c["status"] != "resolved" for c in item["review"]) else "evidence-only"
            if any(c.get("decision") and c["decision"]["action"] == "select" and r["id"] in c["decision"]["selected_ids"] for c in item["review"]):
                item["preference_status"] = "human-choice-see-scope" if item["preference_status"] != "unresolved" else "unresolved"
            matches.append((score, PRIORITY[r["source"]], r["id"], item))
    # Term matches precede incidental definition mentions; source priority applies
    # within that relevance tier, without claiming an automatic sense decision.
    matches.sort(key=lambda x: (-int(x[0] > 1), x[1], -x[0], x[2]))
    return [x[3] for x in matches[:limit]], len(matches)


def terms_for(record, field):
    return {normalize(t) for t in record[field]}
