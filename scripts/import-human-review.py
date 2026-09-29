#!/usr/bin/env python3
"""Receive the focused HTML questionnaire without inventing whole-group approvals."""

import argparse
import json
from pathlib import Path

from terminology.common import ROOT, read_jsonl
from terminology.followup import import_answers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--questionnaire", type=Path, default=ROOT / "reports/review-human-only.html")
    parser.add_argument("--evidence", type=Path, default=ROOT / "reports/conflict-evidence.jsonl")
    parser.add_argument("--policies", type=Path, default=ROOT / "data/source-review-policies.jsonl")
    parser.add_argument("--reports", type=Path, default=ROOT / "reports")
    args = parser.parse_args()
    try:
        receipt = import_answers(args.file, args.questionnaire, read_jsonl(args.evidence), args.policies, args.reports)
        print(json.dumps({k: receipt[k] for k in ("answered_count", "unanswered_question_ids", "choices", "held_source_ids")}, ensure_ascii=False, indent=2))
        print(f"Receipt: {args.reports / 'review-human-only-received.html'}")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"Answer import failed: {error}\n")


if __name__ == "__main__":
    main()
