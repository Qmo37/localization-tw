"""Publish source evidence and an offline human review page."""

import json
from pathlib import Path

from .common import atomic_write, write_json, write_jsonl
from .review import sample_unflagged, write_csv


def generate(directory, records, conflicts, summary):
    directory = Path(directory)
    write_json(directory / "full-run-summary.json", summary)
    write_jsonl(directory / "conflict-evidence.jsonl", conflicts)
    write_csv(directory / "conflicts.csv", conflicts)
    write_csv(directory / "conflicts-primary.csv", [c for c in conflicts if c["review_group"] == "primary"])
    write_jsonl(directory / "unflagged-sample.jsonl", sample_unflagged(records, conflicts))
    payload = json.dumps({"run_id": summary["run_id"], "generated_at": summary["generated_at"],
                          "scoped_source_review": summary.get("scoped_source_review", {}),
                          "assistant_sense_review": summary.get("assistant_sense_review", {}),
                          "record_count": len(records), "conflicts": conflicts}, ensure_ascii=False)
    # Source text cannot close the JSON script tag or inject HTML/JavaScript.
    payload = payload.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    template = Path(__file__).with_name("review-template.html").read_text(encoding="utf-8")
    atomic_write(directory / "review.html", template.replace("__PAYLOAD__", payload))
