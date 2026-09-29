"""Offline behavioral checks for the import, search, and human-review workflow."""
# ruff: noqa: E402 -- exercise script-local modules without installing a package

import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from terminology.common import digest, markdown_tables, project_records, read_json, read_jsonl, record, write_json
from terminology.network import fetch_linguipedia
from terminology.review import apply_decisions, detect_conflicts, import_decisions
from terminology.searching import search
from terminology.sources import concised_records, microsoft_records
from terminology.termic import parse_response, unlabel
from terminology.reports import generate


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def lp_row(identity, tw="範例", category="日常器用", relation="同實異名"):
    return {"id": identity, "tw_word": tw, "cn_word": "示例", "category": category, "type": relation}


def page(number, rows, total=3, pages=3):
    return {"status": True, "data": {"data": rows, "total": total, "last_page": pages, "current_page": number}}


class TablesAndSearch(unittest.TestCase):
    def test_each_nested_table_has_its_own_headers_and_escaped_cells(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "v.md"
            p.write_text("## 核心\n| English | 臺灣正確用語 | 避免使用（中國用語） |\n| --- | --- | --- |\n| process | 程序（process）/ 行程 | 進程 |\n### 補充\n| English | 臺灣正確用語 | 避免使用（中國用語） |\n| --- | --- | --- |\n| pipe | 管線\\|運算子 | 管道 |\n", encoding="utf-8")
            parsed = list(markdown_tables(p))
            self.assertEqual(len(parsed), 2)
            self.assertEqual(parsed[1][0], "補充")
            rows = project_records(p)
            self.assertEqual(rows[0]["tw"], ["程序", "行程"])
            results, _ = search(rows, "process", mode="exact")
            self.assertEqual(results[0]["source_forms"]["tw"], "程序（process）/ 行程")
            self.assertEqual(rows[1]["tw"], ["管線|運算子"])

    def test_priority_and_bilingual_evidence_do_not_merge_senses(self):
        rows = [record("project", "p", en=["process"], tw=["行程"]),
                record("moe-concised", "m", tw=["行程"], kind="dictionary", definitions=[{"text": "旅程安排"}]),
                record("linguipedia", "l", tw=["行程"], relation="同名異實")]
        results, total = search(rows, "process", mode="exact")
        self.assertEqual(total, 3)
        self.assertEqual([r["source"] for r in results], ["linguipedia", "moe-concised", "project"])
        self.assertEqual(results[1]["match_type"], "linked-headword-not-verified-sense")
        self.assertEqual(results[2]["definitions"], [])

    def test_same_name_different_senses_stay_separate(self):
        rows = [record("moe-concised", "a", tw=["行"], definitions=[{"text": "走路"}]),
                record("moe-concised", "b", tw=["行"], definitions=[{"text": "行列"}])]
        found, total = search(rows, "行", mode="exact")
        self.assertEqual(total, 2)
        self.assertEqual(len(detect_conflicts(rows)), 0)

    def test_regex_error_is_once_and_nonzero_even_without_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = subprocess.run([sys.executable, str(ROOT / "scripts/search.py"), "[", "--mode", "regex", "--cache", tmp], capture_output=True, text=True)
            self.assertEqual(p.returncode, 2)
            self.assertEqual(len(p.stderr.splitlines()), 1)
            self.assertEqual(p.stdout, "")

    def test_exact_does_not_match_definition_words(self):
        rows = [record("moe-concised", "a", tw=["資料庫"], definitions=[{"text": "包含資料。"}])]
        self.assertEqual(search(rows, "資料", mode="exact")[1], 0)
        self.assertEqual(search(rows, "資料", mode="substring")[1], 1)


class FetchAndMerge(unittest.TestCase):
    def test_resume_after_failure_retains_every_source_id(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            def fail(n):
                calls.append(n)
                if n == 3:
                    raise RuntimeError("interrupted")
                return page(n, [lp_row(n)])
            with self.assertRaises(RuntimeError):
                fetch_linguipedia(tmp, fetch=fail, delay=0)
            self.assertEqual(len(read_json(Path(tmp) / "linguipedia-checkpoint.json")["pages"]), 2)
            self.assertFalse((Path(tmp) / "linguipedia.json").exists())
            calls.clear()
            def resume(n):
                calls.append(n)
                return page(n, [lp_row(n)])
            result = fetch_linguipedia(tmp, fetch=resume, delay=0)
            self.assertEqual(calls, [1, 3])
            self.assertEqual([r["id"] for r in result["items"]], [1, 2, 3])

    def test_duplicate_page_records_cannot_publish_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                fetch_linguipedia(tmp, fetch=lambda n: page(n, [lp_row(1)]), delay=0)
            self.assertFalse((Path(tmp) / "linguipedia.json").exists())

    def test_failed_refresh_preserves_previous_complete_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            complete = fetch_linguipedia(tmp, fetch=lambda n: page(n, [lp_row(n)]), delay=0)
            def fail(n):
                if n == 2:
                    raise ValueError("invalid page")
                return page(n, [lp_row(n)])
            with self.assertRaises(ValueError):
                fetch_linguipedia(tmp, refresh=True, fetch=fail, delay=0)
            self.assertEqual(read_json(Path(tmp) / "linguipedia.json"), complete)

    def test_merge_keeps_distinct_ids_and_applies_filter(self):
        mod = load_script("fetch-linguipedia")
        with tempfile.TemporaryDirectory() as tmp:
            a, b, out = [Path(tmp) / p for p in ("a.json", "b.json", "out.md")]
            write_json(a, [lp_row(1)])
            write_json(b, [lp_row(2, category="電腦資訊", relation="臺灣特有")])
            self.assertEqual(len(mod.merge_caches([a, b])), 2)
            cmd = [sys.executable, str(ROOT / "scripts/fetch-linguipedia.py"), "--merge-cache", str(a), str(b), "--type", "臺灣特有", "--output", str(out)]
            p = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("本檔筆數：1", out.read_text())
            out.unlink()
            p = subprocess.run(cmd + ["--dry-run", "--save-cache", str(out)], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertFalse(out.exists())

    def test_merge_rejects_conflicting_versions_of_same_id(self):
        mod = load_script("fetch-linguipedia")
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a.json", Path(tmp) / "b.json"
            write_json(a, [lp_row(1)])
            write_json(b, [lp_row(1, tw="另一詞")])
            with self.assertRaises(ValueError):
                mod.merge_caches([a, b])


class SourceAdapters(unittest.TestCase):
    def test_concised_keeps_all_pronunciations_and_original_definition(self):
        import openpyxl
        with tempfile.TemporaryDirectory() as tmp:
            workbook = openpyxl.Workbook()
            sheet = workbook.active
            sheet.append(["字詞名", "字詞號", "注音一式", "釋義", "多音排序"])
            text = "1.甲_x000D_\n2.乙[例]原文。"
            sheet.append(["行", "001", "ㄒㄧㄥˊ", text, 0])
            sheet.append(["行", "001", "ㄏㄤˊ", "行列。", 1])
            buffer = io.BytesIO()
            workbook.save(buffer)
            archive = Path(tmp) / "d.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("dict.xlsx", buffer.getvalue())
            rows, stats = concised_records(archive)
            self.assertEqual(stats["imported"], 2)
            self.assertEqual(rows[0]["definitions"][0]["text"], text)
            self.assertEqual(rows[0]["original"]["釋義"], text)
            self.assertNotEqual(rows[0]["id"], rows[1]["id"])

    def test_microsoft_filters_geography_without_assuming_hant_is_taiwan(self):
        xml = '<martif><text><body>'
        for identity, geo in [("a", "TWN, HKG"), ("b", "HKG"), ("c", "")]:
            xml += f'<termEntry id="{identity}"><langSet xml:lang="en-US"><ntig><termGrp><term>server</term></termGrp></ntig></langSet><langSet xml:lang="zh-Hant"><ntig><termGrp><term>伺服器</term><termNote type="geographicalUsage">{geo}</termNote></termGrp></ntig></langSet></termEntry>'
        xml += '</body></text></martif>'
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "ms.tbx"
            p.write_text(xml)
            rows, stats, quarantine = microsoft_records(p, {"sha256": digest(p.read_bytes()), "expected_entries": 3, "last_modified": "test"})
            self.assertEqual([r["source_id"] for r in rows], ["a"])
            self.assertEqual(rows[0]["geographical_usage"], ["TWN, HKG"])
            self.assertEqual(stats["other_region_terms"], 1)
            self.assertEqual(len(quarantine["unknown_regions"]), 1)

    def test_termic_reverse_and_empty_results(self):
        data = {"gl_source": ["介面"], "gl_translation": ["interface"], "gl_source_def": ["en-US-definition: A UI."], "tm_source": "", "tm_translation": ""}
        result = parse_response(data, reverse=True)
        self.assertEqual(result[0]["en"], ["interface"])
        self.assertEqual(result[0]["tw"], ["介面"])
        self.assertEqual(result[0]["definitions"], [{"text": "A UI."}])
        self.assertEqual(parse_response({k: "" for k in ("gl_source", "gl_translation", "tm_source", "tm_translation")}), [])
        self.assertEqual(unlabel("URL: https://example.com"), "URL: https://example.com")
        data.update(tm_source=["介面"], tm_translation=["Interface"], tm_cat=[None], tm_product=["Office"])
        self.assertEqual(parse_response(data, reverse=True)[1]["product"], "Office")
        with self.assertRaises(ValueError):
            parse_response({"error": "unavailable"})
        data["gl_translation"] = []
        with self.assertRaises(ValueError):
            parse_response(data)


class HumanReview(unittest.TestCase):
    def records(self):
        return [record("project", "p", en=["process"], tw=["行程"], domain="一般用語"),
                record("microsoft", "m", en=["process"], tw=["處理程序"], domain="電腦資訊", definitions=[{"text": "An executing program."}])]

    def decision(self, c):
        return {"conflict_id": c["id"], "fingerprint": c["fingerprint"], "action": "select",
                "selected_ids": ["project:p"], "scope": "電腦領域", "rationale": "Fixture human choice",
                "reviewed_by": "test reviewer", "reviewed_at": "2026-09-06T12:00:00+00:00"}

    def test_conflicts_start_pending_and_cannot_create_global_preference(self):
        rows = self.records()
        c = detect_conflicts(rows)
        self.assertEqual(len(c), 1)
        self.assertEqual(c[0]["status"], "pending")
        results, _ = search(rows, "process", conflicts=c)
        self.assertTrue(all(r["preference_status"] == "unresolved" for r in results))

    def test_changed_evidence_reopens_but_snapshot_version_alone_does_not(self):
        rows = self.records()
        old = detect_conflicts(rows)[0]
        d = self.decision(old)
        rows[1]["source_version"] = "new download"
        current = detect_conflicts(rows)
        self.assertEqual(apply_decisions(current, [d]), {"resolved": 1})
        rows[1]["definitions"][0]["text"] = "A different definition."
        changed = detect_conflicts(rows)
        self.assertEqual(apply_decisions(changed, [d]), {"reopened": 1, "pending": 1})

    def test_review_import_is_atomic_and_requires_human_evidence(self):
        c = detect_conflicts(self.records())[0]
        d = self.decision(c)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "decisions.jsonl"
            import_decisions([d], [c], p)
            before = p.read_bytes()
            bad = {**d, "reviewed_by": ""}
            with self.assertRaises(ValueError):
                import_decisions([bad], [c], p)
            self.assertEqual(p.read_bytes(), before)
            self.assertEqual(read_jsonl(p)[0]["selected_ids"], ["project:p"])

    def test_missing_dictionary_is_coverage_not_a_conflict(self):
        self.assertEqual(detect_conflicts([self.records()[0]]), [])

    def test_draft_backup_cannot_be_imported_as_human_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            backup, output = Path(tmp) / "draft.json", Path(tmp) / "decisions.jsonl"
            write_json(backup, {"kind": "localization-tw-review-draft", "drafts": {}})
            result = subprocess.run([sys.executable, str(ROOT / "scripts/review-conflicts.py"),
                                     str(backup), "--decisions", str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("unfinished draft backup", result.stderr)
            self.assertFalse(output.exists())

    def test_review_html_does_not_allow_source_html_injection(self):
        rows = self.records()
        rows[1]["definitions"] = [{"text": '</script><img src=x onerror=alert(1)>'}]
        c = detect_conflicts(rows)
        with tempfile.TemporaryDirectory() as tmp:
            generate(tmp, rows, c, {"run_id": "test", "generated_at": "now"})
            output = (Path(tmp) / "review.html").read_text()
            self.assertNotIn('</script><img', output)
            self.assertIn('\\u003c/script>', output)


if __name__ == "__main__":
    unittest.main()
