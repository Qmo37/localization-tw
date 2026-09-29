#!/usr/bin/env python3
"""Import the answers downloaded from glossary-regional-review.html as scoped source policies."""

import argparse
import json
import shutil
from pathlib import Path

from terminology.common import ROOT, digest, now, read_json, read_jsonl, write_json, write_jsonl
from terminology.triage import regional_policies, regional_questions


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("file", type=Path)
    p.add_argument("--triage", type=Path, default=ROOT / "reports/glossary-triage.json")
    p.add_argument("--evidence", type=Path, default=ROOT / "reports/conflict-evidence.jsonl")
    p.add_argument("--policies", type=Path, default=ROOT / "data/source-review-policies.jsonl")
    p.add_argument("--received", type=Path, default=ROOT / "reports/received-human-review")
    args = p.parse_args()
    try:
        raw = args.file.read_bytes()
        answers = json.loads(raw)
        conflicts = read_jsonl(args.evidence)
        triage = read_json(args.triage)
        provenance = {"file_name": args.file.name, "file_sha256": digest(raw), "received_at": now()}
        policies = regional_policies(answers, regional_questions(triage["entries"], conflicts), conflicts, provenance)
        if not policies:
            raise ValueError("The file contains no completed answers")
        # Everything is validated before any file changes.
        ids = {x["id"] for x in policies}
        write_jsonl(args.policies, [x for x in read_jsonl(args.policies) if x["id"] not in ids] + policies)
        args.received.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.file, args.received / f"glossary-regional-{provenance['file_sha256'][:16]}.json")
        write_json(args.received / f"glossary-regional-{provenance['file_sha256'][:16]}-policies.json",
                   {"provenance": provenance, "policies": policies})
        held = sorted({s for x in policies for s in x["held_source_ids"]})
        print(f"Imported {len(answers['answers'])} answers as {len(policies)} scoped policies; {len(held)} sources on hold.")
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as e:
        p.exit(2, f"Glossary review import failed: {e}\n")


if __name__ == "__main__":
    main()
