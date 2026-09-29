"""Build reports must preserve scoped answers without changing sense evidence."""
# ruff: noqa: E402

import copy
import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from terminology.common import digest, read_json, read_jsonl, record, write_json, write_jsonl
from terminology.followup import POLICY_KIND
from terminology.review import detect_conflicts
from terminology.review_state import integrate_review_state
from terminology.searching import search


class IntegratedReview(unittest.TestCase):
    def setUp(self):
        self.project = [record("project", "code", en=["code"], tw=["程式碼"], domain="一般用語"),
                        record("project", "audio", en=["audio"], tw=["音訊"], domain="一般用語")]
        self.ms = [record("microsoft", "code", en=["code"], tw=["撰寫"], domain="電腦資訊",
                          definitions=[{"text": "A system of symbols."}]),
                   record("microsoft", "audio", en=["audio"], tw=["音訊檔案"], domain="電腦資訊")]
        self.records = self.project + self.ms
        self.conflicts = detect_conflicts(self.records)
        code = next(c for c in self.conflicts if c["term"] == "code")
        self.policy = {"kind": POLICY_KIND, "version": 1, "id": "synthetic-human-answer", "choice": "hold-mapping",
                       "conflict_id": code["id"], "fingerprint": code["fingerprint"],
                       "focus_ids": ["microsoft:code"], "held_source_ids": ["microsoft:code"],
                       "decision_text": "Fixture: suspend this particular mapping.", "scope": "Fixture symbol definition."}
        self.notes = {"kind": "localization-tw-assistant-sense-review", "version": 1,
                      "authority": "assistant-assessment-not-human-approval", "cases": [
                          {"conflict_id": c["id"], "fingerprint": c["fingerprint"],
                           "candidate_ids": [r["id"] for r in c["candidates"]], "requires_more_evidence": c["term"] == "code",
                           "assessment": "Fixture", "full_reading_assessment": "Separate by context.",
                           "relationship_guidance": "Multiple forms may coexist."} for c in self.conflicts]}

    def test_annotations_preserve_pending_status_fingerprints_and_raw_sources(self):
        before = copy.deepcopy(self.records)
        identities = [(c["id"], c["fingerprint"]) for c in self.conflicts]
        summary = integrate_review_state(self.conflicts, [self.policy], self.notes)
        self.assertEqual(summary["scoped_source_review"]["active_answers"], 1)
        self.assertEqual(summary["scoped_source_review"]["held_source_ids"], ["microsoft:code"])
        self.assertEqual(summary["assistant_sense_review"]["reference_only_cases"], 1)
        self.assertEqual(self.records, before)
        self.assertEqual([(c["id"], c["fingerprint"]) for c in self.conflicts], identities)
        self.assertTrue(all(c["status"] == "pending" and not c["assistant_review"]["human_approved"] for c in self.conflicts))

    def test_changed_evidence_reopens_notes_and_source_answers(self):
        self.ms[0]["definitions"][0]["text"] = "A changed concept."
        conflicts = detect_conflicts(self.records)
        summary = integrate_review_state(conflicts, [self.policy], self.notes)
        self.assertEqual(summary["scoped_source_review"]["active_answers"], 0)
        self.assertEqual(summary["scoped_source_review"]["stale_answers"], 1)
        self.assertEqual(summary["scoped_source_review"]["held_source_count"], 0)
        self.assertEqual(summary["assistant_sense_review"]["stale_or_missing_cases"], 1)
        code = next(c for c in conflicts if c["term"] == "code")
        self.assertFalse(code["assistant_review"]["active"])
        self.assertFalse(code["source_policies"][0]["active"])

    def test_offline_rebuild_versions_policy_changes_and_preserves_previous_run(self):
        spec = importlib.util.spec_from_file_location("build_vocab_fixture", ROOT / "scripts/build-vocabulary.py")
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "cache/raw"
            raw.mkdir(parents=True)
            for name in ["linguipedia.json", "microsoft-manifest.json"]:
                write_json(raw / name, {})
            (raw / "microsoft-traditional.tbx").write_text("Fixture")
            (raw / f"concised-{build.CONCISED_VERSION}.zip").write_bytes(b"Fixture")
            (raw / "concised-usage.pdf").write_bytes(b"%PDF Fixture")
            write_jsonl(root / "policies.jsonl", [self.policy])
            write_json(root / "notes.json", self.notes)
            args = SimpleNamespace(cache=root / "cache", reports=root / "reports", offline=True, online=False,
                                   refresh=False, decisions=root / "decisions.jsonl", source_policies=root / "policies.jsonl",
                                   sense_review=root / "notes.json")
            def info(records):
                return {"sha256": digest(records), "imported": len(records)}
            with patch.object(build, "linguipedia_records", return_value=([], info([]))), \
                 patch.object(build, "concised_records", return_value=([], info([]))), \
                 patch.object(build, "load_revised", return_value=([], info([]))), \
                 patch.object(build, "microsoft_records", return_value=(self.ms, info(self.ms), {})), \
                 patch.object(build, "project_records", return_value=self.project), \
                 patch.object(build, "legacy_records", return_value=[]), \
                 patch.object(build, "fetch_linguipedia", side_effect=AssertionError("No network in offline mode")), \
                 patch("builtins.print"):
                first = build.build(args)
                first_dir = Path(read_json(root / "cache/current.json")["directory"])
                self.assertEqual(first["scoped_source_review"]["held_source_count"], 1)
                with (root / "reports/conflicts.csv").open(encoding="utf-8-sig") as stream:
                    rows = list(csv.DictReader(stream))
                code = next(r for r in rows if r["term"] == "code")
                self.assertEqual(code["held_source_ids"], "microsoft:code")
                self.assertEqual(code["status"], "pending")
                raw_records = read_jsonl(first_dir / "records.jsonl")
                self.assertTrue(all("source_review" not in r for r in raw_records))
                audited = read_jsonl(first_dir / "conflict-evidence.jsonl")
                found, _ = search(raw_records, "code", mode="exact", conflicts=audited, source_policies=[self.policy])
                self.assertEqual([r["id"] for r in found], ["project:code"])
                updated = {**self.policy, "choice": "retain-context", "held_source_ids": [],
                           "decision_text": "Fixture: retain with context to verify."}
                write_jsonl(root / "policies.jsonl", [updated])
                second = build.build(args)
                self.assertNotEqual(first["run_id"], second["run_id"])
                self.assertEqual(second["scoped_source_review"]["held_source_count"], 0)
                self.assertEqual(read_json(first_dir / "full-run-summary.json"), first)
                self.assertEqual(read_jsonl(root / "reports/source-review-policies.jsonl"), [updated])
                # Invalid input must not replace a previously valid index pointer.
                pointer = (root / "cache/current.json").read_bytes()
                write_jsonl(root / "policies.jsonl", [{**updated, "kind": "invalid"}])
                with self.assertRaises(ValueError):
                    build.build(args)
                self.assertEqual((root / "cache/current.json").read_bytes(), pointer)


if __name__ == "__main__":
    unittest.main()
