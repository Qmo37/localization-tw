#!/usr/bin/env python3
"""Sort the supplementary glossary-variant candidates into "needs a person" and "reference only"."""

import argparse
import csv
import io
import json

from terminology.common import ROOT, atomic_write, cache_dir, read_json, read_jsonl, write_json
from terminology.triage import triage


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence", default=ROOT / "reports/conflict-evidence.jsonl")
    p.add_argument("--policies", default=ROOT / "data/source-review-policies.jsonl")
    p.add_argument("--output-dir", default=ROOT / "reports")
    args = p.parse_args()
    run = read_json(cache_dir() / "current.json")
    project, linguipedia = [], []
    with open(run["directory"] + "/records.jsonl", encoding="utf-8") as f:
        for line in f:
            # Record ids are "<source>:<identity>"; only these two sources are parsed.
            if line.startswith('{"id": "project:'):
                project.append(json.loads(line))
            elif line.startswith('{"id": "linguipedia:'):
                linguipedia.append(json.loads(line))
    if not project or not linguipedia:
        p.exit(2, "Triage failed: no project or Linguipedia records found; the index format may have changed.\n")
    entries, summary = triage(read_jsonl(args.evidence), project, linguipedia, read_jsonl(args.policies))
    summary["run_id"] = run["run_id"]
    write_json(f"{args.output_dir}/glossary-triage.json", {"summary": summary, "entries": entries})
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["conflict_id", "term", "class", "needs_human", "forms", "detail"])
    for e in entries:
        detail = {k: v for k, v in e.items() if k in ("regional_forms", "project_terms", "supported_forms")}
        writer.writerow([e["conflict_id"], e["term"], e["class"], e["needs_human"],
                         " | ".join(e["forms"]), json.dumps(detail, ensure_ascii=False)])
    atomic_write(f"{args.output_dir}/glossary-triage.csv", "﻿" + buf.getvalue())
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
