"""Conservative candidate detection and evidence-bound human decisions.

Lexical matches suggest review candidates; they do not prove semantic conflicts.
"""

import csv
import io
from collections import Counter, defaultdict
from datetime import datetime

from .common import PRIORITY, atomic_write, digest, normalize, read_jsonl, write_jsonl

RULE_VERSION = "1"
ACTIONS = {"select", "separate_senses", "allow_variants", "reject_link", "defer"}
REASONS = {
    "regional_policy": "專案避免用語出現在中華語文知識庫臺灣欄；需確認領域與適用義項。",
    "translation_choice": "同一英文詞的候選譯法不同；可能為不同概念、產品用語或可並用詞。",
    "sense_alignment": "技術用語與一般辭典同詞目；尚未建立適用義項關聯，請確認語境。",
    "regional_variants": "同分類及同一大陸詞對應不同臺灣詞組；需確認義項或別名關係。",
    "glossary_variants": "相同英文詞與定義對應不同臺灣譯法；需確認詞形或可並用關係。",
}


def terms(r, field):
    return {normalize(v) for v in r[field] if v}


def content_hash(r):
    # Global snapshot dates/versions don't invalidate an unchanged individual entry.
    return digest({k: v for k, v in r.items() if k not in ("source_version", "url", "data_url")})


def evidence(r):
    return {k: v for k, v in r.items() if k != "original"}


def detect_conflicts(records):
    by_tw, by_en = defaultdict(list), defaultdict(list)
    for r in records:
        if r["kind"] == "style":
            continue
        for term in terms(r, "tw"):
            by_tw[term].append(r)
        for term in terms(r, "en"):
            by_en[term].append(r)
    found = {}

    def add(kind, key, candidates, domain=""):
        candidates = sorted({r["id"]: r for r in candidates}.values(), key=lambda r: (PRIORITY[r["source"]], r["id"]))
        if len(candidates) < 2:
            return
        identity = digest([kind, key, domain])[:24]
        fingerprint = digest([RULE_VERSION, kind, key, domain,
                              [(r["id"], content_hash(r)) for r in candidates]])
        found[identity] = {"id": identity, "fingerprint": fingerprint, "rule_version": RULE_VERSION,
            "review_group": "supplementary" if kind == "glossary_variants" else "primary",
            "kind": kind, "term": key, "domain": domain, "reason": REASONS[kind],
            "classification": "candidate-needs-human-context", "status": "pending", "decision": None,
            "suggestion": "先查中華語文知識庫，再查《簡編本》，《重編本》補充義項；以符合語境的義項為準。",
            "candidates": [evidence(r) for r in candidates]}

    for r in records:
        if r["source"] != "project" or r["kind"] == "style":
            continue
        for forbidden in terms(r, "cn") - terms(r, "tw"):
            matches = [x for x in by_tw[forbidden] if x["source"] == "linguipedia"]
            if matches:
                add("regional_policy", forbidden + " / " + ", ".join(r["en"]), [r] + matches, r["domain"])
        for en in terms(r, "en"):
            matches = [x for x in by_en[en] if x["source"] == "microsoft"]
            if matches and any(not (terms(r, "tw") & terms(x, "tw")) for x in matches):
                add("translation_choice", en, [r] + matches, r["domain"])
        # Project general/Android vocabulary is used for software localization.
        # General dictionary headword matches need a deliberate technical sense link.
        if r["domain"] in ("一般用語", "Android / 行動裝置"):
            for tw in terms(r, "tw"):
                matches = [x for x in by_tw[tw] if x["source"] in ("moe-concised", "moe-revised")]
                if matches:
                    add("sense_alignment", tw + " / " + ", ".join(r["en"]), [r] + matches, "電腦資訊")

    lp_pairs, ms_concepts = defaultdict(list), defaultdict(list)
    for r in records:
        if r["source"] == "linguipedia" and r["relation"] == "同實異名":
            for cn in terms(r, "cn"):
                lp_pairs[(cn, r["domain"])].append(r)
        if r["source"] == "microsoft":
            definition = normalize(" ".join(d["text"] for d in r["definitions"]))
            if definition:
                for en in terms(r, "en"):
                    ms_concepts[(en, definition)].append(r)
    for (term, domain), group in lp_pairs.items():
        forms = {tuple(sorted(terms(r, "tw"))) for r in group}
        if len(forms) > 1 and not set.intersection(*(set(x) for x in forms)):
            add("regional_variants", term, group, domain)
    for (term, definition), group in ms_concepts.items():
        if len({tuple(sorted(terms(r, "tw"))) for r in group}) > 1:
            add("glossary_variants", term + " / " + digest(definition)[:8], group, "電腦資訊")
    return sorted(found.values(), key=lambda c: (list(REASONS).index(c["kind"]), c["term"], c["id"]))


def validate_decision(d, conflict):
    if d.get("fingerprint") != conflict["fingerprint"]:
        raise ValueError(f"{conflict['id']}: evidence changed; review the current candidates")
    if d.get("action") not in ACTIONS:
        raise ValueError(f"{conflict['id']}: unsupported review action")
    for field in ("reviewed_by", "reviewed_at", "rationale", "scope"):
        if not isinstance(d.get(field), str) or not d[field].strip():
            raise ValueError(f"{conflict['id']}: human review requires {field}")
    try:
        stamp = datetime.fromisoformat(d["reviewed_at"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("timezone missing")
    except ValueError as e:
        raise ValueError(f"{conflict['id']}: invalid reviewed_at (timezone required)") from e
    selected = d.get("selected_ids", [])
    if not isinstance(selected, list) or any(not isinstance(x, str) for x in selected):
        raise ValueError("selected_ids must be a list of candidate IDs")
    allowed = {r["id"] for r in conflict["candidates"]}
    if not set(selected).issubset(allowed) or (d["action"] == "select" and not selected):
        raise ValueError(f"{conflict['id']}: select existing candidate IDs")


def apply_decisions(conflicts, decisions):
    latest = {d["conflict_id"]: d for d in decisions}
    stats = Counter()
    for c in conflicts:
        d = latest.get(c["id"])
        if d and d.get("fingerprint") == c["fingerprint"]:
            validate_decision(d, c)
            c["status"] = "deferred" if d["action"] == "defer" else "resolved"
            c["decision"] = d
        elif d:
            c["status"] = "pending"
            c["previous_decision"] = d
            stats["reopened"] += 1
        stats[c["status"]] += 1
    return dict(stats)


def import_decisions(incoming, conflicts, output):
    lookup = {c["id"]: c for c in conflicts}
    if len({d.get("conflict_id") for d in incoming}) != len(incoming):
        raise ValueError("Duplicate decisions in import")
    for d in incoming:
        if d.get("conflict_id") not in lookup:
            raise ValueError(f"Unknown conflict: {d.get('conflict_id')}")
        validate_decision(d, lookup[d["conflict_id"]])
    existing = read_jsonl(output)
    keys = {d["conflict_id"] for d in incoming}
    # Validate the entire import before changing any decisions.
    write_jsonl(output, [d for d in existing if d["conflict_id"] not in keys] + incoming)


def write_csv(path, conflicts):
    out = io.StringIO(newline="")
    columns = ["conflict_id", "fingerprint", "review_group", "kind", "term", "domain", "reason", "candidates", "status",
               "scoped_answers", "held_source_ids", "assistant_review_status", "assistant_review_guidance",
               "action", "selected_ids", "scope", "rationale", "reviewed_by", "reviewed_at"]
    writer = csv.DictWriter(out, fieldnames=columns)
    writer.writeheader()
    for c in conflicts:
        row = {k: c.get(k, "") for k in columns}
        row.update(conflict_id=c["id"], candidates="\n".join(
            f"{r['id']} | {r['source']} | EN: {' / '.join(r['en'])} | TW: {' / '.join(r['tw'])} | {r['url']}" for r in c["candidates"]))
        row["scoped_answers"] = "\n".join(
            f"{'active' if p['active'] else 'stale'} | {p['choice']} | {p['decision_text']}"
            for p in c.get("source_policies", []))
        row["held_source_ids"] = ";".join(r["id"] for r in c["candidates"]
            if any(p["use_status"] == "on-hold" for p in r.get("source_review", [])))
        note = c.get("assistant_review")
        if note:
            row["assistant_review_status"] = ("stale" if not note["active"] else
                "reference-not-human-approved" if not note["requires_more_evidence"] else "context-question-recorded")
            row["assistant_review_guidance"] = note["relationship_guidance"]
        if c.get("decision"):
            row.update({k: c["decision"].get(k, "") for k in columns if k in c["decision"]})
            row["selected_ids"] = ";".join(c["decision"].get("selected_ids", []))
        writer.writerow({k: "'" + str(v) if str(v).startswith(("=", "+", "-", "@")) else v for k, v in row.items()})
    atomic_write(path, "\ufeff" + out.getvalue())


def sample_unflagged(records, conflicts, per_group=5):
    flagged = {r["id"] for c in conflicts for r in c["candidates"]}
    groups = defaultdict(list)
    for r in records:
        if r["id"] not in flagged:
            groups[(r["source"], r["domain"])].append(r)
    result = []
    for key, group in sorted(groups.items()):
        for r in sorted(group, key=lambda x: digest(x["id"]))[:per_group]:
            result.append({"sample_status": "not-human-reviewed", "record": evidence(r)})
    return result
