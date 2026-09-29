#!/usr/bin/env python3
"""Search Taiwan terminology evidence locally, with optional Termic lookup."""

import argparse
import json
import re
from pathlib import Path

from terminology.common import ROOT, PRIORITY, cache_dir, legacy_records, plain, project_records, read_json, read_jsonl
from terminology.followup import index_policies
from terminology.searching import search
from terminology.termic import query


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("query")
    p.add_argument("--cache", type=Path, default=cache_dir())
    p.add_argument("--mode", choices=["exact", "substring", "fuzzy", "regex"], default="substring")
    p.add_argument("--domain", default="", help="Source domain; general dictionary evidence remains visible")
    p.add_argument("--source", choices=list(PRIORITY), help="Restrict local source")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true")
    p.add_argument("--source-policies", type=Path, default=ROOT / "data/source-review-policies.jsonl")
    p.add_argument("--include-held", action="store_true", help="Include source mappings suspended by a scoped human answer")
    online = p.add_mutually_exclusive_group()
    online.add_argument("--online", action="store_true")
    online.add_argument("--local-only", action="store_true")
    p.add_argument("--reverse", action="store_true", help="Online zh-TW → English direction")
    args = p.parse_args()
    try:
        # Validate once before any source loading or networking.
        search([], args.query, mode=args.mode, limit=args.limit)
        pointer = args.cache / "current.json"
        coverage, conflicts = "project-and-legacy-only", []
        if pointer.exists():
            directory = Path(read_json(pointer)["directory"])
            records = read_jsonl(directory / "records.jsonl")
            conflicts = read_jsonl(directory / "conflict-evidence.jsonl")
            coverage = read_json(directory / "full-run-summary.json")["run_id"]
        else:
            records = project_records() + legacy_records()
        if args.source:
            records = [r for r in records if r["source"] == args.source]
        source_policies = read_jsonl(args.source_policies)
        policy_index = index_policies(source_policies, conflicts)
        results, total = search(records, args.query, mode=args.mode, domain=args.domain, limit=args.limit, conflicts=conflicts,
                                source_policies=source_policies, include_held=args.include_held)
        provider = {"status": "not-requested"}
        if args.online:
            try:
                provider = query(args.query, reverse=args.reverse, mode=args.mode, limit=min(args.limit, 100))
                results.extend({k: v for k, v in r.items() if k != "original"} for r in provider.pop("records"))
                provider.pop("raw", None)
            except Exception as e:
                provider = {"status": "unavailable", "error": str(e)}
        output = {"query": args.query, "domain": args.domain, "coverage": coverage,
                  "source_policy_filter": {"include_held": args.include_held,
                      "held_source_ids": sorted(sid for sid, policies in policy_index.items()
                                                if any(p["use_status"] == "on-hold" for p in policies)),
                      "stale_policy_ids": sorted({p["id"] for policies in policy_index.values() for p in policies if not p["active"]})},
                  "local_total": total, "local_returned": min(total, args.limit), "online": provider, "results": results}
        if args.json:
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            print(f"{args.query}：本地 {total} 筆符合，顯示 {min(total, args.limit)} 筆。資料：{coverage}")
            if source_policies:
                held_count = len(output["source_policy_filter"]["held_source_ids"])
                print(f"  已載入人工來源處理紀錄；共 {held_count} 條配對暫停。" +
                      ("本次包含暫停來源供查閱。" if args.include_held else "預設略過暫停來源；可加 --include-held 查閱。"))
            for r in results:
                print(f"\n[{r['source']}] {' / '.join(r['en'])} → {' / '.join(r['tw'])}")
                if r["cn"]:
                    print("  大陸／專案避免用語：" + " / ".join(r["cn"]))
                print(f"  領域：{r['domain']}；{r.get('relation') or r['kind']}")
                if r.get("usage_note"):
                    print("  用途：" + r["usage_note"])
                if r.get("linked_via"):
                    print("  關聯：透過相同中文詞目找到；尚未確認是否為相同義項。")
                for field, value in r.get("source_forms", {}).items():
                    if value and value != " / ".join(r[field]):
                        print("  原始詞形（" + {"en": "英文", "tw": "臺灣", "cn": "大陸／專案避免用語"}[field] + "）：" + value)
                for pron in r["pronunciations"]:
                    print("  注音：" + pron["bopomofo"])
                if r.get("part_of_speech"):
                    print("  詞性：" + r["part_of_speech"])
                if r.get("product") or r.get("platform"):
                    print("  產品／平台：" + " / ".join(filter(None, [r.get("product"), r.get("platform")])))
                for d in r["definitions"]:
                    print("  釋義：" + plain(d.get("display", d["text"])))
                for review in r.get("review", []):
                    print(f"  覆核：{review['status']} ({review['conflict_id']}) {review['reason']}")
                    if review.get("decision"):
                        print("  人工決定：" + json.dumps(review["decision"], ensure_ascii=False))
                for policy in r.get("source_review", []):
                    label = {"on-hold": "暫停此來源配對", "context-or-verification-required": "語境／來源仍待核對",
                             "stale-policy-not-applied": "證據已變動，舊補答未套用"}[policy["use_status"]]
                    print(f"  人工補答（{label}）：{policy['decision_text']}")
                print("  來源：" + r["url"])
                if r.get("source_version"):
                    print("  版本：" + r["source_version"])
            if provider["status"] != "not-requested":
                print("\n線上查詢：" + json.dumps(provider, ensure_ascii=False))
    except (ValueError, OSError, re.error) as e:
        p.exit(2, f"Search failed: {e}\n")


if __name__ == "__main__":
    main()
