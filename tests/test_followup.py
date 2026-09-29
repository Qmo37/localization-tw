"""Portable human answers must not become inferred whole-group approvals."""
# ruff: noqa: E402

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from terminology.common import read_json, read_jsonl, record
from terminology.followup import POLICY_KIND, import_answers, prepare_answers
from terminology.searching import search


def html(payload, state):
    def safe(value):
        return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c")
    return ('<!doctype html><script id="payload" type="application/json">' + safe(payload) +
            '</script><script id="embedded-state" type="application/json">' + safe(state) + '</script>')


class FollowupImport(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.issued = self.directory / "issued.html"
        self.answer = self.directory / "answered.html"
        self.output = self.directory / "policies.jsonl"
        self.sources = [record("microsoft", "bad", en=["code"], tw=["撰寫"]),
                        record("microsoft", "good", en=["code"], tw=["程式碼"]),
                        record("moe-concised", "writing", tw=["撰寫"], definitions=[{"text": "寫作。"}]),
                        record("linguipedia", "1657", cn=["耳朵眼儿"], tw=["耳洞"]),
                        record("linguipedia", "1658", cn=["耳朵眼儿"], tw=["外耳道"])]
        self.conflicts = [dict(id="code", fingerprint="code-v1", candidates=self.sources[:2], reason="fixture", status="pending"),
                          dict(id="ear", fingerprint="ear-v1", candidates=self.sources[3:], reason="fixture", status="pending")]
        self.payload = {"kind": "localization-tw-human-only-questionnaire", "version": 1, "bundle_id": "fixture",
                        "reference_numbers": [], "transcription": {"rows": [{"observed_checked_ids": ["linguipedia:1657"]}]},
                        "reassessment": {"source_records": {s["id"]: s for s in self.sources}, "cases": [], "notice": "Fixture notice"},
                        "questions": [
                            {"id": "row-10", "number": 10, "title": "code", "explanation": "Only the flagged mapping.",
                             "conflict_id": "code", "fingerprint": "code-v1", "focus_ids": ["microsoft:bad"],
                             "options": [{"id": "hold-mapping", "text": "Pause this source mapping only."},
                                         {"id": "retain-context", "text": "Retain pending context."}]},
                            {"id": "row-64", "number": 64, "title": "耳朵眼儿", "explanation": "Two source pairs.",
                             "conflict_id": "ear", "fingerprint": "ear-v1", "focus_ids": ["linguipedia:1657", "linguipedia:1658"],
                             "options": [{"id": "hold-mapping", "text": "Hold 耳洞 only; keep 外耳道."},
                                         {"id": "retain-context", "text": "Retain both pending context."}]}]}
        self.state = {"version": 1, "bundle_id": "fixture", "reviewer": "", "answers": {
            "row-10": {"choice": "hold-mapping", "note": "", "answered_at": "2026-09-09T10:00:00Z"},
            "row-64": {"choice": "retain-context", "note": "", "answered_at": "2026-09-09T10:01:00Z"}}}
        self.issued.write_text(html(self.payload, None))
        self.save_answer()

    def save_answer(self, payload=None):
        self.answer.write_text(html(payload or self.payload, self.state))

    def import_answer(self):
        return import_answers(self.answer, self.issued, self.conflicts, self.output, self.directory / "reports")

    def test_optional_identity_scope_and_originals_are_preserved(self):
        before = self.answer.read_bytes()
        receipt = self.import_answer()
        policies = read_jsonl(self.output)
        self.assertEqual(receipt["answered_count"], 2)
        self.assertEqual(receipt["held_source_ids"], ["microsoft:bad"])
        self.assertTrue(all(p["reviewed_by"] == "" and not p["resolves_whole_conflict"] for p in policies))
        self.assertTrue(all(c["status"] == "pending" for c in self.conflicts))
        self.assertEqual(receipt["screenshot_transcription"], self.payload["transcription"])
        archive = self.directory / "reports/received-human-review" / (receipt["provenance"]["file_sha256"] + ".html")
        self.assertEqual(archive.read_bytes(), before)
        self.assertEqual(read_json(archive.with_suffix('.json'))["state"], self.state)
        self.import_answer()
        self.assertEqual(len(read_jsonl(self.output)), 2, "Importing twice does not duplicate answers")

    def test_tampered_questions_and_unknown_answers_do_not_change_policy_file(self):
        self.import_answer()
        before = self.output.read_bytes()
        altered = copy.deepcopy(self.payload)
        altered["questions"][0]["options"][0]["text"] = "Approve all meanings."
        self.save_answer(altered)
        with self.assertRaises(ValueError):
            self.import_answer()
        self.assertEqual(self.output.read_bytes(), before)
        self.state["answers"]["row-59"] = self.state["answers"]["row-10"]
        self.save_answer()
        with self.assertRaises(ValueError):
            self.import_answer()
        self.assertEqual(self.output.read_bytes(), before)

    def test_reissued_unchanged_questionnaire_accepts_saved_answers(self):
        self.payload["generated_at"] = "2026-09-09T09:00:00Z"
        self.save_answer()
        reissued = {**self.payload, "generated_at": "2026-09-29T09:00:00Z"}
        self.issued.write_text(html(reissued, None))
        self.assertEqual(self.import_answer()["answered_count"], 2)

    def test_changed_evidence_and_invalid_time_are_rejected(self):
        self.conflicts[0]["fingerprint"] = "code-v2"
        with self.assertRaises(ValueError):
            self.import_answer()
        self.assertFalse(self.output.exists())
        self.conflicts[0]["fingerprint"] = "code-v1"
        self.state["answers"]["row-10"]["answered_at"] = "2026-09-09T10:00:00"
        self.save_answer()
        with self.assertRaises(ValueError):
            self.import_answer()
        self.assertFalse(self.output.exists())

    def test_partial_answers_and_custom_notes_are_not_machine_inferred(self):
        self.state["answers"]["row-10"] = {"choice": "custom", "note": "", "answered_at": "2026-09-09T10:00:00Z"}
        self.save_answer()
        receipt = self.import_answer()
        self.assertEqual(receipt["unanswered_question_ids"], ["row-10"])
        self.assertEqual(receipt["held_source_ids"], [])
        self.state["answers"]["row-10"]["note"] = '<script>alert("custom")</script>'
        self.save_answer()
        receipt = self.import_answer()
        self.assertEqual(receipt["unanswered_question_ids"], [])
        self.assertEqual(receipt["held_source_ids"], [])
        rendered = (self.directory / "reports/review-human-only-received.html").read_text()
        self.assertNotIn('<script>alert', rendered)
        self.assertIn('&lt;script&gt;', rendered)

    def test_partial_hold_does_not_suspend_the_other_pair(self):
        self.state["answers"]["row-64"]["choice"] = "hold-mapping"
        self.save_answer()
        receipt = self.import_answer()
        self.assertEqual(receipt["held_source_ids"], ["linguipedia:1657", "microsoft:bad"])
        found, _ = search(self.sources, "耳朵眼儿", mode="exact", conflicts=self.conflicts, source_policies=receipt["policies"])
        self.assertEqual([r["id"] for r in found], ["linguipedia:1658"])

    def test_search_holds_only_chosen_source_and_does_not_link_through_it(self):
        receipt = self.import_answer()
        found, _ = search(self.sources, "code", mode="exact", conflicts=self.conflicts, source_policies=receipt["policies"])
        self.assertEqual([r["id"] for r in found], ["microsoft:good"])
        audit, _ = search(self.sources, "code", mode="exact", conflicts=self.conflicts,
                          source_policies=receipt["policies"], include_held=True)
        self.assertEqual({r["id"] for r in audit}, {"microsoft:good", "microsoft:bad", "moe-concised:writing"})
        bad = next(r for r in audit if r["id"] == "microsoft:bad")
        self.assertEqual(bad["source_use_status"], "on-hold")
        self.assertEqual(bad["preference_status"], "unresolved")
        self.conflicts[0]["fingerprint"] = "code-v2"
        changed, _ = search(self.sources, "code", mode="exact", conflicts=self.conflicts, source_policies=receipt["policies"])
        bad = next(r for r in changed if r["id"] == "microsoft:bad")
        self.assertEqual(bad["source_use_status"], "stale-policy-not-applied")
        self.assertEqual(bad["source_review"][0]["kind"], POLICY_KIND)

    def test_retained_candidates_need_context_and_do_not_resolve_a_group(self):
        _, _, policies, _, _ = prepare_answers(self.answer, self.issued, self.conflicts)
        found, _ = search(self.sources, "耳朵眼儿", mode="exact", conflicts=self.conflicts, source_policies=policies)
        self.assertEqual(len(found), 2)
        self.assertTrue(all(r["source_use_status"] == "context-or-verification-required" for r in found))
        self.assertTrue(all(r["preference_status"] == "unresolved" for r in found))


if __name__ == "__main__":
    unittest.main()
