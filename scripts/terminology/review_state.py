"""Attach scoped answers and assistant notes without changing source fingerprints."""

from collections import Counter

from .followup import index_policies


def integrate_review_state(conflicts, policies=(), notes=None):
    index = index_policies(policies, conflicts)
    annotated = {p["id"]: p for entries in index.values() for p in entries}
    active = [p for p in annotated.values() if p["active"]]
    stale = [p for p in annotated.values() if not p["active"]]
    held = sorted(sid for sid, entries in index.items() if any(p["use_status"] == "on-hold" for p in entries))
    context = sorted(sid for sid, entries in index.items() if sid not in held and any(p["active"] for p in entries))
    policy_groups = {}
    for policy in policies:
        item = {**policy, "active": annotated.get(policy["id"], {}).get("active", False)}
        policy_groups.setdefault(policy["conflict_id"], []).append(item)
    cases = {}
    if notes:
        if (notes.get("kind"), notes.get("version"), notes.get("authority")) != (
                "localization-tw-assistant-sense-review", 1, "assistant-assessment-not-human-approval"):
            raise ValueError("Unsupported assistant review notes")
        cases = {c["conflict_id"]: c for c in notes["cases"]}
        if len(cases) != len(notes["cases"]):
            raise ValueError("Duplicate assistant review notes")
    current_notes, references = [], []
    for conflict in conflicts:
        conflict["source_policies"] = policy_groups.get(conflict["id"], [])
        for candidate in conflict["candidates"]:
            candidate["source_review"] = index.get(candidate["id"], [])
        note = cases.get(conflict["id"])
        if note:
            valid = (note["fingerprint"] == conflict["fingerprint"] and
                     note["candidate_ids"] == [c["id"] for c in conflict["candidates"]])
            conflict["assistant_review"] = {**note, "active": valid, "human_approved": False}
            if valid:
                current_notes.append(conflict["id"])
                if not note["requires_more_evidence"]:
                    references.append(conflict["id"])
        else:
            conflict.pop("assistant_review", None)
    return {
        "scoped_source_review": {
            "recorded_answers": len(policies), "active_answers": len(active), "stale_answers": len(stale),
            "active_choices": dict(Counter(p["choice"] for p in active)),
            "held_source_count": len(held), "held_source_ids": held,
            "context_source_count": len(context), "context_source_ids": context,
            "whole_conflicts_resolved": 0,
            "note": "Answers apply only to their specified sources; verification remains pending.",
        },
        "assistant_sense_review": {
            "recorded_cases": len(cases), "current_cases": len(current_notes),
            "stale_or_missing_cases": len(cases) - len(current_notes),
            "reference_only_cases": len(references), "reference_conflict_ids": references,
            "human_approved": False,
        },
    }
