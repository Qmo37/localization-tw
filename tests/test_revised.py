"""Behavioral checks for the secondary MOE dictionary and evidence changes."""
# ruff: noqa: E402

import copy
import json
import lzma
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from terminology.common import digest, record
from terminology.followup import POLICY_KIND
from terminology.revised import fetch_revised, load_revised, revised_directory, revised_records
from terminology.review import apply_decisions, content_hash, detect_conflicts
from terminology.review_state import integrate_review_state
from terminology.searching import search


ENTRIES = [
    {"title": "行程", "heteronyms": [
        {"bopomofo": "注音甲", "pinyin": "reading-a", "definitions": [
            {"def": "測試：旅程。", "quote": ["測試引文甲", "測試引文乙"], "type": "名",
             "example": ["測試例句。"], "synonyms": "旅途", "antonyms": "測試反義", "link": ["參見測試詞"]},
            {"def": "測試：啟程。"}]},
        {"definitions": [{"def": "測試：另一義項。"}]}]},
    {"title": "套褲", "heteronyms": [{"bopomofo": "注音乙", "pinyin": "reading-b",
                                      "definitions": [{"def": "測試：穿在褲外。"}]}]},
]


class RevisedDictionary(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = lzma.compress(json.dumps(ENTRIES, ensure_ascii=False).encode())
        self.path = self.root / "fixture.xz"
        self.path.write_bytes(self.data)
        self.spec = {"sha256": digest(self.data), "expected_entries": 2, "dictionary_version": "fixture",
                     "g0v_commit": "fixture-commit", "url": "https://example.invalid/fixture.xz"}

    def test_preserves_all_readings_and_full_sense_evidence(self):
        rows, info = revised_records(self.path, self.spec)
        self.assertEqual(rows[0]["original"], ENTRIES[0])
        self.assertEqual((info["imported"], info["readings"], info["definitions"]), (2, 3, 4))
        self.assertEqual(len(rows[0]["pronunciations"]), 2)
        self.assertEqual(rows[0]["pronunciations"][1]["bopomofo"], "")
        self.assertEqual([(d["reading_order"], d["sense_order"]) for d in rows[0]["definitions"]], [(1, 1), (1, 2), (2, 1)])
        full = rows[0]["definitions"][0]["display"]
        for expected in ["reading-a", "測試引文甲", "測試引文乙", "測試例句。", "旅途", "測試反義", "參見測試詞"]:
            self.assertIn(expected, full)
        self.assertEqual(rows[0]["en"], [])

    def test_rejects_corruption_truncation_duplicate_heads_and_bad_senses(self):
        for label, data, spec in [
            ("checksum", self.data + b"tampered", self.spec),
            ("count", self.data, {**self.spec, "expected_entries": 3}),
            ("xz", b"invalid", {**self.spec, "sha256": digest(b"invalid")}),
        ]:
            with self.subTest(label=label):
                self.path.write_bytes(data)
                with self.assertRaises(ValueError):
                    revised_records(self.path, spec)
        for bad in [[ENTRIES[0], ENTRIES[0]], [{"title": "bad", "heteronyms": [{}]}],
                    [{"title": "bad", "heteronyms": [{"definitions": [{"def": "a", "quote": "not a list"}]}]}]]:
            data = lzma.compress(json.dumps(bad).encode())
            self.path.write_bytes(data)
            with self.assertRaises(ValueError):
                revised_records(self.path, {**self.spec, "sha256": digest(data), "expected_entries": len(bad)})

    def test_priority_missing_concised_headwords_and_many_to_many_links(self):
        revised, _ = revised_records(self.path, self.spec)
        rows = revised + [record("linguipedia", "lp", tw=["行程"]),
                          record("moe-concised", "concised", tw=["行程"], kind="dictionary"),
                          record("microsoft", "process", en=["process"], tw=["行程", "處理程序"], domain="電腦資訊"),
                          record("project", "itinerary", en=["itinerary"], tw=["行程"], domain="旅遊")]
        found, _ = search(rows, "process", mode="exact", domain="電腦資訊")
        self.assertEqual([r["source"] for r in found], ["linguipedia", "moe-concised", "moe-revised", "microsoft"])
        self.assertEqual(found[2]["match_type"], "linked-headword-not-verified-sense")
        self.assertEqual(found[2]["en"], [])
        self.assertEqual(found[3]["definitions"], [])
        self.assertIn(revised[0]["id"], [r["id"] for r in search(rows, "itinerary", mode="exact")[0]])
        self.assertEqual(search(rows, "套褲", mode="exact")[0][0]["source"], "moe-revised")
        self.assertEqual(detect_conflicts(revised + [rows[3]]), [])  # Dictionary overlap alone is not a conflict.

    def test_only_changed_evidence_reopens_review_and_scoped_hold_survives(self):
        project = [record("project", "p", en=["process"], tw=["行程"], domain="一般用語"),
                   record("project", "c", en=["code"], tw=["程式碼"], domain="一般用語")]
        rows = project + [record("moe-concised", "m", tw=["行程"], kind="dictionary"),
                          record("microsoft", "c", en=["code"], tw=["撰寫"])]
        old = detect_conflicts(rows)
        sense = next(c for c in old if c["kind"] == "sense_alignment")
        code = next(c for c in old if c["term"] == "code")
        decision = {"conflict_id": sense["id"], "fingerprint": sense["fingerprint"], "action": "separate_senses",
                    "reviewed_by": "Fixture", "reviewed_at": "2026-09-29T00:00:00Z", "rationale": "Fixture", "scope": "Fixture"}
        policy = {"kind": POLICY_KIND, "version": 1, "id": "fixture", "conflict_id": code["id"],
                  "fingerprint": code["fingerprint"], "focus_ids": ["microsoft:c"], "held_source_ids": ["microsoft:c"],
                  "choice": "hold-mapping", "decision_text": "Fixture", "scope": "Fixture"}
        revised, _ = revised_records(self.path, self.spec)
        current = detect_conflicts(rows + revised)
        self.assertEqual(apply_decisions(current, [decision])["reopened"], 1)
        self.assertEqual(integrate_review_state(current, [policy])["scoped_source_review"]["held_source_count"], 1)
        self.assertEqual(next(c for c in current if c["id"] == code["id"])["fingerprint"], code["fingerprint"])
        updated = {**revised[0], "source_version": "new snapshot", "data_url": "https://example.invalid/new"}
        self.assertEqual(content_hash(updated), content_hash(revised[0]))
        changed = copy.deepcopy(updated)
        changed["definitions"][0]["text"] = "Changed sense"
        self.assertNotEqual(content_hash(changed), content_hash(revised[0]))

    def test_failed_refresh_keeps_cache_and_offline_load_never_downloads(self):
        def fake_download(url, path):
            path.write_bytes(self.data if path.name.endswith(".xz") else
                             b"%PDF fixture" if path.suffix == ".pdf" else "教育部 test attribution".encode())
            return path
        raw = self.root / "raw"
        with patch("terminology.revised.snapshot_spec", return_value=self.spec), \
             patch("terminology.revised.download", side_effect=fake_download):
            directory = fetch_revised(raw)
            before = {p.name: p.read_bytes() for p in directory.iterdir()}
            with patch("terminology.revised.download", side_effect=RuntimeError("interrupted")):
                with self.assertRaises(RuntimeError):
                    fetch_revised(raw, refresh=True)
                self.assertEqual(len(load_revised(raw)[0]), 2)
            self.assertEqual({p.name: p.read_bytes() for p in directory.iterdir()}, before)
            (revised_directory(raw) / "dict-revised.json.xz").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "artifact mismatch"):
                load_revised(raw)


if __name__ == "__main__":
    unittest.main()
