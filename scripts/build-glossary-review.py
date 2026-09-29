#!/usr/bin/env python3
"""Build the short questionnaire for glossary variants that triage left for a person."""

import argparse
import json
from pathlib import Path

from terminology.common import ROOT, atomic_write, read_json, read_jsonl
from terminology.triage import regional_questions


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--triage", type=Path, default=ROOT / "reports/glossary-triage.json")
    p.add_argument("--evidence", type=Path, default=ROOT / "reports/conflict-evidence.jsonl")
    p.add_argument("--output", type=Path, default=ROOT / "reports/glossary-regional-review.html")
    args = p.parse_args()
    triage = read_json(args.triage)
    if not any(e["needs_human"] for e in triage["entries"]):
        p.exit(0, "No glossary variants are waiting for a person; no questionnaire built.\n")
    questions = regional_questions(triage["entries"], read_jsonl(args.evidence))
    payload = json.dumps({"run_id": triage["summary"]["run_id"], "questions": questions},
                         ensure_ascii=False).replace("<", "\\u003c")
    template = (ROOT / "scripts/terminology/glossary-review-template.html").read_text(encoding="utf-8")
    atomic_write(args.output, template.replace("__PAYLOAD__", payload))
    print(f"{len(questions)} questions -> {args.output}")


if __name__ == "__main__":
    main()
