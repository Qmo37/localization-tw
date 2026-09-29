"""Glossary-variant triage must sort candidates without choosing a preferred form."""
# ruff: noqa: E402

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from terminology.triage import REGIONAL_KIND, regional_policies, regional_questions, triage


def group(term, *forms, kind="glossary_variants", english=None):
    return {"id": term, "fingerprint": "f", "kind": kind, "term": term,
            "candidates": [{"en": [english or term], "tw": [f]} for f in forms]}


class Triage(unittest.TestCase):
    def classes(self, conflicts, project=(), linguipedia=()):
        entries, summary = triage(conflicts, list(project), list(linguipedia))
        return {e["term"]: e["class"] for e in entries}, entries, summary

    def test_each_shape(self):
        result, _, summary = self.classes([
            group("record", "通話記錄", "通話紀錄"),
            group("abbr", "DPM", "資料保護管理員"),
            group("scope", "圖", "向量圖"),
            group("alt", "晶片", "積體電路"),
            group("other-kind", "a", "b", kind="regional_variants")])
        self.assertEqual(result, {"record": "spelling-or-decoration-only", "abbr": "abbreviation-or-product-name",
                                  "scope": "scope-extension", "alt": "alternative-terms"})
        self.assertEqual(summary["needs_human"], 0)
        self.assertEqual(summary["authority"], "assistant-assessment-not-human-approval")

    def test_regional_form_needs_person_only_without_counterpart(self):
        result, entries, summary = self.classes([
            group("gateway", "網絡閘道", "網路閘道"), group("widget", "介面控件", "小工具")])
        self.assertEqual(result["gateway"], "regional-form-with-taiwan-counterpart")
        self.assertEqual(result["widget"], "regional-usage-check")
        self.assertEqual(summary["needs_human"], 1)
        self.assertTrue(next(e for e in entries if e["term"] == "widget")["needs_human"])

    def test_taiwan_valid_usage_is_not_flagged(self):
        result, _, _ = self.classes([group("cellular", "行動數據", "行動網路")])
        self.assertNotIn("regional", result["cellular"])

    def test_project_term_is_covered_by_primary_review(self):
        project = [{"en": ["video"], "tw": ["影片"]}]
        primary = group("video", "x", "y", kind="translation_choice")
        result, _, _ = self.classes([primary, group("video", "視訊", "視訊通話")], project)
        self.assertEqual(result["video"], "covered-by-primary-review")
        result, _, _ = self.classes([group("video", "視訊", "視訊通話")], project)
        self.assertEqual(result["video"], "project-term-uncovered")

    def test_dictionary_supported_form_is_reported_not_chosen(self):
        _, entries, _ = self.classes([group("album", "專輯", "相簿")], linguipedia=[{"tw": ["相簿"]}])
        self.assertEqual(entries[0]["class"], "dictionary-supported")
        self.assertEqual(entries[0]["supported_forms"], ["相簿"])
        self.assertNotIn("preferred", entries[0])

    def test_questions_group_by_definition_and_flag_only_uncovered_forms(self):
        conflicts = [
            {**group("widget / aa11", "介面控件", "小工具", english="widget"), "fingerprint": "f1"},
            {**group("gadget / aa11", "介面控件", "小工具", english="gadget"), "fingerprint": "f2"},
            group("gateway / bb22", "網絡閘道", "網路閘道")]
        for c in conflicts:
            for x in c["candidates"]:
                x["definitions"] = [{"text": "A small control."}]
        entries, _ = triage(conflicts, [], [])
        questions = regional_questions(entries, conflicts)
        self.assertEqual(len(questions), 1)
        q = questions[0]
        self.assertEqual(q["id"], "aa11")
        self.assertEqual(q["flagged_forms"], ["介面控件"])
        self.assertEqual(q["english"], ["gadget", "widget"])
        self.assertEqual(set(q["fingerprints"]), {"widget / aa11", "gadget / aa11"})
        self.assertEqual(q["definition"], "A small control.")

    def test_answered_groups_are_not_asked_again(self):
        conflicts, _ = self.regional_fixture()
        policies = [{"conflict_id": conflicts[0]["id"], "fingerprint": conflicts[0]["fingerprint"], "choice": "hold-mapping"}]
        entries, summary = triage(conflicts, [], [], policies)
        self.assertEqual(next(e for e in entries if e["conflict_id"] == conflicts[0]["id"])["answered_choice"], "hold-mapping")
        self.assertEqual((summary["needs_human"], summary["answered"]), (1, 1))
        stale = [{**policies[0], "fingerprint": "old"}]
        self.assertEqual(triage(conflicts, [], [], stale)[1]["answered"], 0)

    def test_deferred_answer_keeps_the_group_open(self):
        conflicts, _ = self.regional_fixture()
        policies = [{"conflict_id": conflicts[0]["id"], "fingerprint": conflicts[0]["fingerprint"], "choice": "defer"}]
        entries, summary = triage(conflicts, [], [], policies)
        self.assertEqual((summary["needs_human"], summary["answered"]), (2, 0))

    def test_project_term_question_has_no_regional_forms(self):
        project = [{"en": ["video"], "tw": ["影片"]}]
        conflicts = [group("video", "視訊", "視訊通話")]
        for x in conflicts[0]["candidates"]:
            x["definitions"] = []
        entries, summary = triage(conflicts, project, [])
        self.assertEqual(entries[0]["class"], "project-term-uncovered")
        self.assertEqual(regional_questions(entries, conflicts)[0]["flagged_forms"], [])

    def regional_fixture(self):
        conflicts = [{**group("widget / aa11", "介面控件", "小工具", english="widget"), "fingerprint": "f1"},
                     {**group("mashup / bb22", "交互式應用", "混搭", english="mashup"), "fingerprint": "f2"}]
        for c in conflicts:
            for i, x in enumerate(c["candidates"]):
                x.update(id=f"{c['id']}#{i}", definitions=[{"text": "d"}])
        entries, _ = triage(conflicts, [], [])
        return conflicts, regional_questions(entries, conflicts)

    def answers(self, questions, **override):
        return {"kind": REGIONAL_KIND, "version": 1, "authority": "human-answers", "reviewer": "", "answers": [
            {"question_id": q["id"], "choice": "block" if q["id"] == "aa11" else "defer", "note": "備註",
             "fingerprints": q["fingerprints"], "answered_at": "2026-09-29T11:00:00Z", **override} for q in questions]}

    def test_answers_become_scoped_policies_that_hold_only_flagged_candidates(self):
        conflicts, questions = self.regional_fixture()
        policies = regional_policies(self.answers(questions), questions, conflicts, {})
        by_choice = {p["choice"]: p for p in policies}
        self.assertEqual(by_choice["hold-mapping"]["held_source_ids"], ["widget / aa11#0"])
        self.assertEqual(by_choice["hold-mapping"]["focus_ids"], ["widget / aa11#0"])
        self.assertEqual(by_choice["defer"]["held_source_ids"], [])
        self.assertFalse(any(p["resolves_whole_conflict"] for p in policies))
        self.assertEqual(by_choice["hold-mapping"]["note"], "備註")

    def test_stale_evidence_or_unasked_question_is_rejected(self):
        conflicts, questions = self.regional_fixture()
        stale = self.answers(questions)
        stale["answers"][0]["fingerprints"] = {k: "old" for k in stale["answers"][0]["fingerprints"]}
        with self.assertRaisesRegex(ValueError, "evidence changed"):
            regional_policies(stale, questions, conflicts, {})
        unknown = self.answers(questions)
        unknown["answers"][0]["question_id"] = "zzzz"
        with self.assertRaisesRegex(ValueError, "not in the current evidence"):
            regional_policies(unknown, questions, conflicts, {})
        with self.assertRaisesRegex(ValueError, "invalid answer"):
            regional_policies(self.answers(questions, choice="delete"), questions, conflicts, {})


if __name__ == "__main__":
    unittest.main()
