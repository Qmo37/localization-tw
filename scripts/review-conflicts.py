#!/usr/bin/env python3
"""Import decisions exported by a human from review.html or conflicts.csv."""

import argparse
import csv
import json
from pathlib import Path

from terminology.common import ROOT, read_jsonl
from terminology.review import import_decisions


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("file", type=Path)
    p.add_argument("--evidence", type=Path, default=ROOT / "reports/conflict-evidence.jsonl")
    p.add_argument("--decisions", type=Path, default=ROOT / "data/review-decisions.jsonl")
    args = p.parse_args()
    try:
        if args.file.suffix.lower() == ".csv":
            with args.file.open(encoding="utf-8-sig", newline="") as f:
                fields = ("conflict_id", "fingerprint", "action", "scope", "rationale", "reviewed_by", "reviewed_at")
                rows = [{**{k: r.get(k, "") for k in fields},
                         "selected_ids": [s.strip() for s in r.get("selected_ids", "").split(";") if s.strip()]}
                        for r in csv.DictReader(f) if r.get("action")]
        else:
            rows = json.loads(args.file.read_text(encoding="utf-8"))
        if isinstance(rows, dict) and rows.get("kind") == "localization-tw-review-draft":
            raise ValueError("This is an unfinished draft backup. Restore it in review.html, complete the required fields, and export completed decisions before importing.")
        if not isinstance(rows, list) or not rows or any(not isinstance(r, dict) for r in rows):
            raise ValueError("Expected a nonempty list of human decisions")
        import_decisions(rows, read_jsonl(args.evidence), args.decisions)
        print(f"Imported {len(rows)} human decisions into {args.decisions}.")
        print("Rebuild with python3 scripts/build-vocabulary.py --offline to apply them.")
    except (ValueError, OSError) as e:
        p.exit(2, f"Review import failed: {e}\n")


if __name__ == "__main__":
    main()
