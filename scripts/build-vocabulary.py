#!/usr/bin/env python3
"""Acquire complete sources, compare evidence, and create a human review queue."""

import argparse
import json
import os
import tempfile
from collections import Counter
from pathlib import Path

from terminology.common import (ROOT, PRIORITY, atomic_write, cache_dir, digest, legacy_records,
    normalize, now, project_records, read_json, read_jsonl, write_json, write_jsonl)
from terminology.network import (CONCISED_NOTICE, CONCISED_URL, CONCISED_VERSION,
    download, fetch_linguipedia, fetch_microsoft)
from terminology.sources import concised_records, linguipedia_records, microsoft_records
from terminology.revised import fetch_revised, load_revised
from terminology.review import RULE_VERSION, apply_decisions, content_hash, detect_conflicts, evidence
from terminology.reports import generate
from terminology.review_state import integrate_review_state
from terminology.termic import query


def build(args):
    cache = Path(args.cache).expanduser().resolve()
    raw = cache / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    if not args.offline:
        fetch_linguipedia(raw, refresh=args.refresh)
        fetch_microsoft(raw, refresh=args.refresh)
        # Validate an archive in staging before replacing a previous working copy.
        with tempfile.TemporaryDirectory(dir=cache) as scratch:
            target = raw / f"concised-{CONCISED_VERSION}.zip"
            if not target.exists() or args.refresh:
                candidate = download(CONCISED_URL, Path(scratch) / "concised.zip")
                concised_records(candidate)
                atomic_write(target, candidate.read_bytes())
        download(CONCISED_NOTICE, raw / "concised-usage.pdf")
        fetch_revised(raw, refresh=args.refresh)
    required = ["linguipedia.json", "microsoft-manifest.json", "microsoft-traditional.tbx",
                f"concised-{CONCISED_VERSION}.zip", "concised-usage.pdf"]
    missing = [p for p in required if not (raw / p).is_file()]
    if missing:
        raise ValueError("Missing source artifacts; run without --offline: " + ", ".join(missing))
    if not (raw / "concised-usage.pdf").read_bytes().startswith(b"%PDF"):
        # Drop the bad cache entry; download() would otherwise reuse it forever.
        (raw / "concised-usage.pdf").unlink()
        raise ValueError("MOE usage instructions are not a valid PDF download; removed the cached file, rerun to download it again")
    if (raw / "linguipedia-checkpoint.json").exists():
        raise ValueError("Linguipedia refresh is incomplete; resume it before publishing a full run")

    print("Importing complete sources…", flush=True)
    lp, lp_info = linguipedia_records(read_json(raw / "linguipedia.json"))
    moe, moe_info = concised_records(raw / f"concised-{CONCISED_VERSION}.zip")
    revised, revised_info = load_revised(raw)
    ms, ms_info, regions = microsoft_records(raw / "microsoft-traditional.tbx", read_json(raw / "microsoft-manifest.json"))
    project, legacy = project_records(), legacy_records()
    records = lp + moe + revised + ms + project + legacy
    if len({r["id"] for r in records}) != len(records):
        raise ValueError("Duplicate normalized record IDs")
    info = {"linguipedia": lp_info, "moe-concised": moe_info, "moe-revised": revised_info, "microsoft": ms_info,
            "project": {"imported": len(project), "sha256": digest(project)},
            "legacy-reference": {"imported": len(legacy), "sha256": digest(legacy),
                                  "note": "Preserved existing reference, not relabeled as verified live data"}}

    supplements = {"scope": "bounded-query-not-full-TM", "queries": []}
    supplement_path = raw / "termic-supplements.json"
    if args.online:
        for term in args.query or ["server", "process", "interface", "database"]:
            print(f"Supplementary Termic query: {term}", flush=True)
            try:
                observation = query(term, mode="exact", limit=5)
                observation["retrieved_at"] = now()
            except Exception as e:
                observation = {"query": term, "status": "unavailable", "error": str(e), "records": [], "retrieved_at": now()}
            supplements["queries"].append(observation)
        write_json(supplement_path, supplements)
    elif supplement_path.exists():
        supplements = read_json(supplement_path)

    print(f"Comparing {len(records):,} records…", flush=True)
    conflicts = detect_conflicts(records)
    for c in conflicts:
        candidate_en = {normalize(t) for r in c["candidates"] for t in r["en"]}
        extra = {r["id"]: r for q in supplements["queries"] if normalize(q["query"]) in candidate_en for r in q["records"]}
        if extra:
            c["candidates"].extend(evidence(r) for r in extra.values())
            c["candidates"].sort(key=lambda r: (PRIORITY[r["source"]], r["id"]))
            c["fingerprint"] = digest([c["fingerprint"], sorted((r["id"], content_hash(r)) for r in extra.values())])
    decisions = read_jsonl(args.decisions)
    review_stats = apply_decisions(conflicts, decisions)
    source_policies = read_jsonl(args.source_policies)
    notes_path = Path(args.sense_review)
    sense_notes = read_json(notes_path) if notes_path.exists() else None
    supplemental_review = integrate_review_state(conflicts, source_policies, sense_notes)
    lp_terms = {normalize(t) for r in lp for t in r["tw"]}
    moe_terms = {normalize(t) for r in moe for t in r["tw"]}
    revised_terms = {normalize(t) for r in revised for t in r["tw"]}
    legacy_terms = {normalize(t) for r in legacy for t in r["tw"]}
    implementation_files = list((ROOT / "scripts/terminology").glob("*")) + list((ROOT / "scripts").glob("*.py"))
    implementation = digest([(str(p.relative_to(ROOT)), digest(p.read_bytes())) for p in sorted(implementation_files) if p.is_file()])
    run_id = digest([[(k, v["sha256"]) for k, v in info.items()], RULE_VERSION, implementation,
                     decisions, source_policies, sense_notes,
                     [(q["query"], q["status"], q.get("raw")) for q in supplements["queries"]]])[:20]
    unresolved = {r["id"] for c in conflicts if c["status"] != "resolved" for r in c["candidates"]}
    summary = {"schema_version": 1, "run_id": run_id, "generated_at": now(), "sources": info,
        "machine_processing": "complete", "semantic_validation": "human-review-required",
        "source_order": ["linguipedia", "moe-concised", "moe-revised", "microsoft"],
        "record_count": len(records), "conflict_candidates": len(conflicts),
        "conflicts_by_kind": dict(Counter(c["kind"] for c in conflicts)), "human_review": review_stats,
        **supplemental_review,
        "review_groups": dict(Counter(c["review_group"] for c in conflicts)),
        "unresolved_record_count": len(unresolved), "rule_version": RULE_VERSION,
        "coverage": {"linguipedia_unique_tw_terms": len(lp_terms), "linguipedia_terms_with_concised_headword": len(lp_terms & moe_terms),
                     "linguipedia_terms_with_revised_headword": len(lp_terms & revised_terms),
                     "revised_headwords_absent_from_concised": len(revised_terms - moe_terms),
                     "unmatched_linguipedia_terms": len(lp_terms - moe_terms),
                     "legacy_terms_absent_from_live_linguipedia": sorted(legacy_terms - lp_terms),
                     "note": "Headword overlap is not an assertion of matching senses; missing entries are not conflicts."},
        "supplementary_queries": [{k: v for k, v in q.items() if k not in ("raw", "records")} for q in supplements["queries"]],
        "review_decisions_path": str(Path(args.decisions).resolve()),
        "source_policies_path": str(Path(args.source_policies).resolve()),
        "sense_review_notes_path": str(notes_path.resolve()),
        "distribution": "local research artifacts; source notices retained; no external publication performed"}
    runs = cache / "runs"
    runs.mkdir(exist_ok=True)
    destination = runs / run_id
    if not destination.exists():
        with tempfile.TemporaryDirectory(prefix=".build-", dir=runs) as staging:
            stage = Path(staging)
            write_jsonl(stage / "records.jsonl", records)
            generate(stage, records, conflicts, summary)
            write_json(stage / "microsoft-region-audit.json", regions)
            write_json(stage / "termic-supplements.json", supplements)
            write_jsonl(stage / "source-review-policies.jsonl", source_policies)
            write_json(stage / "sense-review-notes.json", sense_notes)
            write_jsonl(stage / "candidate-vocabulary.jsonl", (
                {"record_id": r["id"], "en": r["en"], "tw": r["tw"], "domain": r["domain"],
                 "status": "pending-review" if r["id"] in unresolved else "draft-evidence-not-human-verified"}
                for r in records if r["source"] in ("project", "linguipedia")))
            os.replace(stage, destination)
    report_dir = Path(args.reports).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    for p in sorted(destination.iterdir()):
        if p.name != "records.jsonl" and p.name != "full-run-summary.json":
            atomic_write(report_dir / p.name, p.read_bytes())
    atomic_write(report_dir / "full-run-summary.json", (destination / "full-run-summary.json").read_bytes())
    write_json(cache / "current.json", {"run_id": run_id, "directory": str(destination), "reports": str(report_dir)})
    print(json.dumps({"run_id": run_id, "records": len(records), "conflict_candidates": len(conflicts),
                      "scoped_source_review": supplemental_review["scoped_source_review"],
                      "assistant_sense_review": {k: v for k, v in supplemental_review["assistant_sense_review"].items()
                                                if k != "reference_conflict_ids"},
                      "human_review": review_stats, "review_page": str(report_dir / "review.html")}, ensure_ascii=False, indent=2))
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache", default=str(cache_dir()), help="Raw sources and normalized index directory")
    p.add_argument("--reports", default=str(ROOT / "reports"))
    p.add_argument("--decisions", default=str(ROOT / "data/review-decisions.jsonl"))
    p.add_argument("--source-policies", default=str(ROOT / "data/source-review-policies.jsonl"))
    p.add_argument("--sense-review", default=str(ROOT / "data/sense-review-notes.json"))
    p.add_argument("--offline", action="store_true", help="Use existing complete source snapshots")
    p.add_argument("--refresh", action="store_true", help="Acquire new complete source snapshots")
    p.add_argument("--online", action="store_true", help="Run bounded supplemental Termic queries")
    p.add_argument("--query", action="append", help="Supplementary exact English query; repeatable")
    args = p.parse_args()
    if args.offline and (args.refresh or args.online):
        p.error("--offline cannot be combined with --refresh or --online")
    if args.query and not args.online:
        p.error("--query requires --online")
    try:
        build(args)
    except (ValueError, OSError, RuntimeError, json.JSONDecodeError) as e:
        p.exit(1, f"Build failed: {e}\n")


if __name__ == "__main__":
    main()
