#!/usr/bin/env python3
"""Fetch or merge Linguipedia records without silently publishing partial data.

The default output is a local cache artifact. The repository reference is kept
as historical evidence until a maintainer deliberately replaces it.
"""

import argparse
import sys
import tempfile
from pathlib import Path

from terminology.common import NCAT_NOTICE, atomic_write, cache_dir, now, read_json, write_json
from terminology.network import fetch_linguipedia

TYPES = ("同實異名", "同名異實", "臺灣特有", "大陸特有")


def load_cache(path):
    value = read_json(path)
    items = value if isinstance(value, list) else value.get("items")
    if not isinstance(items, list) or any(not isinstance(r, dict) for r in items):
        raise ValueError(f"Invalid cache: {path}")
    return items


def merge_caches(paths):
    merged = {}
    for path in paths:
        for row in load_cache(path):
            if row.get("id") is not None:
                key = ("id", str(row["id"]))
            else:
                key = ("legacy", row.get("tw_word"), row.get("cn_word"), row.get("category"), row.get("type"))
            if key in merged and merged[key] != row:
                raise ValueError(f"Conflicting cache content for {key}; choose the correct snapshot first")
            merged[key] = row
    return list(merged.values())


def format_markdown(items, complete=False, type_filter=""):
    lines = ["# 兩岸詞彙差異對照表", "", "> " + NCAT_NOTICE,
             "> 資料來源：https://www.chinese-linguipedia.org/search_difference.html",
             "> 產生時間：" + now(), f"> 本檔筆數：{len(items):,}",
             "> 完整性：" + ("來源全量已核對" if complete else "未驗證；不可視為完整資料庫"), ""]
    if type_filter:
        lines += ["> 本檔篩選類型：" + type_filter, ""]
    lines += ["類型：同實異名、同名異實、臺灣特有、大陸特有。",
              "兩岸共同用語可以同時出現在兩欄；同名異實須分辨語境。", ""]
    grouped = {}
    for row in items:
        grouped.setdefault(row.get("category") or "未分類", []).append(row)
    for category, rows in grouped.items():
        lines += ["## " + category, "", "| 臺灣用語 | 大陸用語 | 類型 |",
                  "| --- | --- | --- |"]
        for r in rows:
            values = [str(r.get(k) or "—").replace("|", r"\|").replace("\n", "<br>") for k in ("tw_word", "cn_word", "type")]
            lines.append("| " + " | ".join(values) + " |")
        lines.append("")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    inputs = p.add_mutually_exclusive_group()
    inputs.add_argument("--from-cache", type=Path)
    inputs.add_argument("--merge-cache", nargs="+", type=Path)
    p.add_argument("--cache-dir", type=Path, default=cache_dir() / "raw")
    p.add_argument("--output", type=Path, default=cache_dir() / "linguipedia-cross-strait.md")
    p.add_argument("--save-cache", type=Path)
    p.add_argument("--type", choices=TYPES, dest="type_filter", default="")
    p.add_argument("--dry-run", action="store_true", help="No persistent file writes")
    p.add_argument("--refresh", action="store_true", help="Fetch a new snapshot; existing checkpoints resume automatically")
    p.add_argument("--delay", type=float, default=0.3)
    args = p.parse_args()
    if args.delay < 0:
        p.error("--delay cannot be negative")
    try:
        complete = False
        if args.merge_cache:
            items = merge_caches(args.merge_cache)
        elif args.from_cache:
            items = load_cache(args.from_cache)
            value = read_json(args.from_cache)
            if isinstance(value, dict) and value.get("complete"):
                from terminology.sources import linguipedia_records
                linguipedia_records(value)
                complete = True
        elif args.dry_run:
            with tempfile.TemporaryDirectory() as d:
                snapshot = fetch_linguipedia(d, delay=args.delay)
                items, complete = snapshot["items"], snapshot["complete"]
        else:
            snapshot = fetch_linguipedia(args.cache_dir, refresh=args.refresh, delay=args.delay)
            items, complete = snapshot["items"], snapshot["complete"]
        if args.type_filter:
            items = [r for r in items if r.get("type") == args.type_filter]
        print(f"{len(items):,} records; source completeness verified: {complete}", file=sys.stderr)
        if args.dry_run:
            return
        if args.save_cache:
            # Exported subsets and merges do not claim full-source completeness.
            write_json(args.save_cache, items)
        atomic_write(args.output, format_markdown(items, complete, args.type_filter))
        print(str(args.output))
    except (ValueError, OSError, RuntimeError) as e:
        p.exit(1, f"Fetch failed: {e}\n")


if __name__ == "__main__":
    main()
