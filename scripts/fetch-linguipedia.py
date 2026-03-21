#!/usr/bin/env python3
"""
Fetch cross-strait terminology differences from Chinese Linguipedia.
Outputs markdown tables grouped by subcategory.

Source: https://www.chinese-linguipedia.org/search_difference.html
API:    https://bs.chinese-linguipedia.org/api/web/diff/search

Usage:
    python3 scripts/fetch-linguipedia.py
    python3 scripts/fetch-linguipedia.py --type 同實異名
    python3 scripts/fetch-linguipedia.py --dry-run
    python3 scripts/fetch-linguipedia.py --output path/to/output.md
    python3 scripts/fetch-linguipedia.py --save-cache cache.json
    python3 scripts/fetch-linguipedia.py --from-cache cache.json
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from datetime import datetime, timezone, timedelta

API_URL = "https://bs.chinese-linguipedia.org/api/web/diff/search"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DEFAULT_OUTPUT = os.path.join(PROJECT_DIR, "references", "linguipedia-cross-strait.md")


def fetch_page(page, type_filter="", max_retries=3, delay=0.3):
    """Fetch a single page from the API. Returns parsed JSON."""
    params = {
        "category": "",
        "page": str(page),
        "word": "",
        "type": type_filter,
    }
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            if attempt < max_retries - 1:
                wait = delay * (2 ** attempt)
                print(f"  Retry {attempt + 1}/{max_retries} after {wait:.1f}s: {e}", file=sys.stderr)
                time.sleep(wait)
            else:
                raise RuntimeError(f"Failed to fetch page {page} after {max_retries} attempts: {e}")


def fetch_all(type_filter="", delay=0.3):
    """Fetch all pages from the API. Returns list of all items."""
    print("Fetching page 1...", file=sys.stderr)
    first = fetch_page(1, type_filter=type_filter)

    if not first.get("status"):
        raise RuntimeError(f"API returned error: {first}")

    data = first["data"]
    total = data["total"]
    last_page = data["last_page"]
    items = list(data["data"])

    print(f"Total: {total} items, {last_page} pages", file=sys.stderr)

    for page in range(2, last_page + 1):
        if page % 20 == 0 or page == last_page:
            print(f"  Fetching page {page}/{last_page}...", file=sys.stderr)
        time.sleep(delay)
        result = fetch_page(page, type_filter=type_filter, delay=delay)
        items.extend(result["data"]["data"])

    print(f"Fetched {len(items)} items total", file=sys.stderr)
    return items


def load_cache(path):
    """Load items from a JSON cache file."""
    with open(path, "r", encoding="utf-8") as f:
        items = json.load(f)
    print(f"Loaded {len(items)} items from cache: {path}", file=sys.stderr)
    return items


def save_cache(items, path):
    """Save items to a JSON cache file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    size_kb = os.path.getsize(path) / 1024
    print(f"Cache saved to {path} ({size_kb:.0f} KB)", file=sys.stderr)


def group_by_category(items):
    """Group items by subcategory name, preserving order of first appearance."""
    grouped = OrderedDict()
    for item in items:
        cat = item.get("category", "未分類")
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(item)
    return grouped


def format_markdown(grouped, total, type_filter=""):
    """Generate markdown output."""
    tz_tw = timezone(timedelta(hours=8))
    now = datetime.now(tz_tw).strftime("%Y-%m-%d")

    lines = [
        "# 兩岸詞彙差異對照表",
        "",
        f"> 資料來源：[中華語文知識庫](https://www.chinese-linguipedia.org/search_difference.html)",
        f"> 最後更新：{now}（自動產生，請勿手動編輯）",
        f"> 總筆數：{total:,}",
    ]
    if type_filter:
        lines.append(f"> 篩選條件：類型＝{type_filter}")
    lines += [
        "",
        "此表收錄中華語文知識庫「兩岸差異用詞」資料庫詞條，依子分類分節呈現。",
        "",
        "類型說明：",
        "- **同實異名**：同一事物，兩岸用詞不同",
        "- **臺灣特有**：僅臺灣使用的詞彙",
        "- **大陸特有**：僅大陸使用的詞彙",
        "",
    ]

    for category, cat_items in grouped.items():
        lines.append(f"## {category}")
        lines.append("")
        lines.append("| 臺灣用語 | 大陸用語 | 類型 |")
        lines.append("| -------- | -------- | ---- |")
        for item in cat_items:
            tw = (item.get("tw_word") or "—").replace("|", "\\|")
            cn = (item.get("cn_word") or "—").replace("|", "\\|")
            typ = item.get("type", "")
            lines.append(f"| {tw} | {cn} | {typ} |")
        lines.append("")

    return "\n".join(lines)


def print_stats(items):
    """Print summary statistics."""
    types = {}
    categories = {}
    for item in items:
        t = item.get("type", "unknown")
        types[t] = types.get(t, 0) + 1
        c = item.get("category", "unknown")
        categories[c] = categories.get(c, 0) + 1

    print(f"\n{'='*50}", file=sys.stderr)
    print(f"Total items: {len(items)}", file=sys.stderr)
    print(f"\nBy type:", file=sys.stderr)
    for t, count in sorted(types.items(), key=lambda x: -x[1]):
        print(f"  {t}: {count}", file=sys.stderr)
    print(f"\nBy subcategory ({len(categories)} subcategories):", file=sys.stderr)
    for c, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"  {c}: {count}", file=sys.stderr)
    print(f"{'='*50}\n", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Fetch cross-strait terminology from Chinese Linguipedia"
    )
    parser.add_argument(
        "--output", default=DEFAULT_OUTPUT, help="Output markdown file path"
    )
    parser.add_argument(
        "--type",
        default="",
        dest="type_filter",
        help="Filter by type: 同實異名, 臺灣特有, or 大陸特有",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and print stats only, no file output",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.3,
        help="Delay between API requests in seconds (default: 0.3)",
    )
    parser.add_argument(
        "--from-cache",
        metavar="FILE",
        help="Read items from a local JSON cache instead of fetching from API",
    )
    parser.add_argument(
        "--save-cache",
        metavar="FILE",
        help="Save fetched items to a JSON cache file (for offline reuse)",
    )
    args = parser.parse_args()

    # Load or fetch items
    if args.from_cache:
        items = load_cache(args.from_cache)
    else:
        items = fetch_all(type_filter=args.type_filter, delay=args.delay)

    # Apply type filter to cached data (API filter already applied for live fetch)
    if args.from_cache and args.type_filter:
        before = len(items)
        items = [i for i in items if i.get("type") == args.type_filter]
        print(f"Filtered by type '{args.type_filter}': {before} → {len(items)}", file=sys.stderr)

    # Optionally save cache
    if args.save_cache:
        save_cache(items, args.save_cache)

    print_stats(items)

    if args.dry_run:
        print("Dry run — no file written.", file=sys.stderr)
        return

    grouped = group_by_category(items)
    md = format_markdown(grouped, total=len(items), type_filter=args.type_filter)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(md)

    size_kb = os.path.getsize(args.output) / 1024
    print(f"Written to {args.output} ({size_kb:.0f} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()
