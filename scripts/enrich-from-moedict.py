#!/usr/bin/env python3
"""
Enrich vocabulary with data from g0v/moedict-data (教育部重編國語辭典修訂本).

Downloads (if needed) and cross-references the MOE dictionary to add:
- 注音 (bopomofo) pronunciation
- Authoritative Taiwan definitions
- Usage examples
- Part of speech

Also discovers additional daily-use TW terms from the linguipedia
cross-strait database that have moedict entries.

Source: https://github.com/g0v/moedict-data
License: CC BY-ND 3.0 TW (content), CC0 (JSON format by @kcwu)

Usage:
    python3 scripts/enrich-from-moedict.py
    python3 scripts/enrich-from-moedict.py --lookup 軟體
    python3 scripts/enrich-from-moedict.py --lookup "公車,捷運,番茄"
    python3 scripts/enrich-from-moedict.py --expand-daily
    python3 scripts/enrich-from-moedict.py --generate
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import OrderedDict
from datetime import datetime, timezone, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DICT_URL = "https://raw.githubusercontent.com/g0v/moedict-data/master/dict-revised.json.xz"
DICT_CACHE = os.path.join(PROJECT_DIR, "cache-moedict.json")
DICT_XZ = os.path.join(PROJECT_DIR, "cache-moedict.json.xz")
VOCAB_PATH = os.path.join(PROJECT_DIR, "references", "vocabulary.md")
LINGUIPEDIA_PATH = os.path.join(PROJECT_DIR, "references", "linguipedia-cross-strait.md")
OUTPUT_PATH = os.path.join(PROJECT_DIR, "references", "vocabulary-enriched.md")


def download_dict(force=False):
    """Download and decompress moedict data if not cached."""
    if os.path.exists(DICT_CACHE) and not force:
        size_mb = os.path.getsize(DICT_CACHE) / (1024 * 1024)
        print(f"Using cached dictionary: {DICT_CACHE} ({size_mb:.0f} MB)", file=sys.stderr)
        return

    print("Downloading moedict dict-revised.json.xz (~14 MB)...", file=sys.stderr)
    import urllib.request
    urllib.request.urlretrieve(DICT_URL, DICT_XZ)
    print("Decompressing...", file=sys.stderr)
    subprocess.run(["xz", "-dk", DICT_XZ], check=True)
    os.rename(DICT_XZ.replace(".xz", ""), DICT_CACHE)
    if os.path.exists(DICT_XZ):
        os.remove(DICT_XZ)
    size_mb = os.path.getsize(DICT_CACHE) / (1024 * 1024)
    print(f"Dictionary ready: {DICT_CACHE} ({size_mb:.0f} MB)", file=sys.stderr)


def load_dict():
    """Load moedict into a title-keyed dict for fast lookup."""
    download_dict()
    print("Loading dictionary...", file=sys.stderr)
    with open(DICT_CACHE, "r", encoding="utf-8") as f:
        entries = json.load(f)
    d = {}
    for entry in entries:
        title = entry.get("title", "")
        if title:
            d[title] = entry
    print(f"Loaded {len(d)} entries", file=sys.stderr)
    return d


def lookup_entry(moedict, term):
    """Look up a term and return structured info."""
    entry = moedict.get(term)
    if not entry:
        return None

    result = {
        "term": term,
        "heteronyms": [],
    }

    for h in entry.get("heteronyms", []):
        het = {
            "bopomofo": h.get("bopomofo", ""),
            "pinyin": h.get("pinyin", ""),
            "definitions": [],
        }
        for d in h.get("definitions", []):
            defn = {
                "def": _clean_html(d.get("def", "")),
                "type": d.get("type", ""),
                "examples": [_clean_html(e) for e in d.get("example", [])],
            }
            het["definitions"].append(defn)
        result["heteronyms"].append(het)

    return result


def _clean_html(text):
    """Remove HTML tags from moedict text."""
    return re.sub(r"<[^>]+>", "", text).strip()


def format_lookup(result):
    """Format a lookup result for terminal display."""
    if not result:
        return "  (not found in moedict)"

    lines = []
    for h in result["heteronyms"]:
        lines.append(f"  {result['term']}  {h['bopomofo']}")
        if h["pinyin"]:
            lines.append(f"  Pinyin: {h['pinyin']}")
        for i, d in enumerate(h["definitions"][:4], 1):
            pos = f"[{d['type']}] " if d["type"] else ""
            lines.append(f"  {i}. {pos}{d['def']}")
            for ex in d["examples"][:1]:
                lines.append(f"     例：{ex}")
    return "\n".join(lines)


SKIP_PATTERNS = re.compile(
    r"^[,.\:\;!?\"\'\(\)（）「」『』，。：；！？\s]|"
    r"^(半形|全形|直接|如果|不加|進行)"
)


def parse_vocab_md():
    """Parse vocabulary.md to get existing TW terms."""
    terms = []
    if not os.path.exists(VOCAB_PATH):
        return terms

    current_section = ""
    with open(VOCAB_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("## "):
                current_section = line[3:]
                continue
            if current_section in ("標點符號", "冗贅句式"):
                continue
            if line.startswith("|") and "---" not in line and "English" not in line and "Wrong" not in line and "避免使用" not in line:
                cells = [c.strip() for c in line.split("|")[1:-1]]
                if len(cells) >= 3:
                    en = cells[0]
                    tw_raw = cells[1]
                    cn = cells[2]
                    tw_clean = re.sub(r"[（(][^）)]*[）)]", "", tw_raw)
                    for t in re.split(r"[/／、]", tw_clean):
                        t = t.strip()
                        if t and not SKIP_PATTERNS.match(t) and len(t) <= 8:
                            terms.append({
                                "tw": t,
                                "cn": cn,
                                "en": en,
                                "section": current_section,
                            })
    return terms


def parse_linguipedia_md():
    """Parse linguipedia cross-strait data for TW terms."""
    terms = []
    if not os.path.exists(LINGUIPEDIA_PATH):
        return terms
    current_section = ""
    with open(LINGUIPEDIA_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("## "):
                current_section = line[3:]
                continue
            if line.startswith("|") and "---" not in line and "臺灣用語" not in line:
                cells = [c.strip() for c in line.split("|")[1:-1]]
                if len(cells) >= 3:
                    tw = cells[0]
                    cn = cells[1]
                    typ = cells[2]
                    for t in re.split(r"[/／]", tw):
                        t = t.strip()
                        if t and t != "—" and len(t) <= 8:
                            terms.append({
                                "tw": t,
                                "cn": cn,
                                "en": "",
                                "section": current_section,
                                "type": typ,
                            })
    return terms


DAILY_CATEGORIES = {
    "食材", "佐料", "小吃＆點心", "飲料", "餐點＆菜餚", "餐飲店",
    "日常器用", "服飾", "消費購物", "居住＆建築",
    "陸運", "空運", "水運", "交通管理",
}


def expand_daily(moedict):
    """Find daily-use TW terms from linguipedia that have moedict entries."""
    lp_terms = parse_linguipedia_md()
    daily_terms = [t for t in lp_terms
                   if t.get("section", "") in DAILY_CATEGORIES
                   and t.get("type", "") in ("同實異名", "臺灣特有")]

    enriched = []
    seen = set()
    for t in daily_terms:
        tw = t["tw"]
        if tw in seen or tw == "—":
            continue
        seen.add(tw)

        result = lookup_entry(moedict, tw)
        if result and result["heteronyms"]:
            h = result["heteronyms"][0]
            defs = h["definitions"]
            best_def = ""
            best_example = ""
            for d in defs:
                if d["def"] and not best_def:
                    best_def = d["def"]
                if d["examples"] and not best_example:
                    best_example = d["examples"][0]

            enriched.append({
                "tw": tw,
                "cn": t.get("cn", ""),
                "bopomofo": h["bopomofo"],
                "definition": best_def,
                "example": best_example,
                "section": t.get("section", ""),
                "type": t.get("type", ""),
            })

    return enriched


def generate_enriched_vocab(moedict):
    """Generate enriched vocabulary markdown with moedict data."""
    vocab_terms = parse_vocab_md()
    daily_terms = expand_daily(moedict)

    tz_tw = timezone(timedelta(hours=8))
    now = datetime.now(tz_tw).strftime("%Y-%m-%d")

    lines = [
        "# 正體中文（臺灣）用語對照表（加強版）",
        "",
        f"> 資料來源：[教育部重編國語辭典修訂本](https://dict.revised.moe.edu.tw/)（via [g0v/moedict-data](https://github.com/g0v/moedict-data)）",
        f"> 最後更新：{now}（腳本產生，請勿手動編輯）",
        "",
        "此表在原有臺灣用語對照表基礎上，加入教育部辭典的注音、定義、例句。",
        "",
    ]

    # Section 1: Enriched core vocabulary
    lines.append("## 核心用語（含注音與定義）")
    lines.append("")
    lines.append("| 臺灣用語 | 注音 | 避免用語 | English | 教育部定義 |")
    lines.append("| -------- | ---- | -------- | ------- | ---------- |")

    seen_tw = set()
    for t in vocab_terms:
        tw = t["tw"]
        if tw in seen_tw:
            continue
        seen_tw.add(tw)

        result = lookup_entry(moedict, tw)
        bopomofo = ""
        definition = ""
        if result and result["heteronyms"]:
            h = result["heteronyms"][0]
            bopomofo = h["bopomofo"]
            for d in h["definitions"]:
                if d["def"]:
                    definition = d["def"]
                    break

        cn = t["cn"].replace("|", "\\|")
        en = t["en"].replace("|", "\\|")
        defn = definition.replace("|", "\\|")
        if len(defn) > 50:
            defn = defn[:50] + "…"

        lines.append(f"| {tw} | {bopomofo} | {cn} | {en} | {defn} |")

    lines.append("")

    # Section 2: Daily-use terms from linguipedia + moedict
    section_groups = OrderedDict()
    for t in daily_terms:
        sec = t["section"]
        if sec not in section_groups:
            section_groups[sec] = []
        section_groups[sec].append(t)

    lines.append("## 日常用語（兩岸差異＋教育部定義）")
    lines.append("")
    lines.append("以下詞彙從中華語文知識庫的兩岸差異用詞中篩選日常類別，")
    lines.append("並附上教育部辭典的定義作為權威參考。")
    lines.append("")

    for section, terms in section_groups.items():
        lines.append(f"### {section}")
        lines.append("")
        lines.append("| 臺灣用語 | 注音 | 大陸用語 | 教育部定義 |")
        lines.append("| -------- | ---- | -------- | ---------- |")
        for t in terms:
            cn = t["cn"].replace("|", "\\|") if t["cn"] else "—"
            defn = t["definition"].replace("|", "\\|")
            if len(defn) > 60:
                defn = defn[:60] + "…"
            lines.append(f"| {t['tw']} | {t['bopomofo']} | {cn} | {defn} |")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Enrich vocabulary with moedict (教育部國語辭典) data"
    )
    parser.add_argument(
        "--lookup", metavar="TERMS",
        help="Look up specific terms (comma-separated)"
    )
    parser.add_argument(
        "--expand-daily", action="store_true",
        help="Show daily-use TW terms from linguipedia that have moedict entries"
    )
    parser.add_argument(
        "--generate", action="store_true",
        help="Generate enriched vocabulary file"
    )
    parser.add_argument(
        "--output", default=OUTPUT_PATH,
        help=f"Output file path (default: {OUTPUT_PATH})"
    )
    parser.add_argument(
        "--force-download", action="store_true",
        help="Re-download moedict data even if cached"
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="Show statistics about vocabulary coverage in moedict"
    )
    args = parser.parse_args()

    if not any([args.lookup, args.expand_daily, args.generate, args.stats]):
        args.generate = True

    moedict = load_dict()

    if args.lookup:
        terms = [t.strip() for t in args.lookup.split(",")]
        for term in terms:
            print(f"\n{'='*50}")
            print(f"  {term}")
            print(f"{'='*50}")
            result = lookup_entry(moedict, term)
            print(format_lookup(result))

    if args.stats:
        vocab_terms = parse_vocab_md()
        lp_terms = parse_linguipedia_md()

        vocab_found = sum(1 for t in vocab_terms if t["tw"] in moedict)
        lp_unique = set(t["tw"] for t in lp_terms if t["tw"] != "—")
        lp_found = sum(1 for t in lp_unique if t in moedict)

        print(f"\nVocabulary.md: {vocab_found}/{len(vocab_terms)} terms found in moedict")
        print(f"Linguipedia: {lp_found}/{len(lp_unique)} unique TW terms found in moedict")

    if args.expand_daily:
        daily = expand_daily(moedict)
        print(f"\nFound {len(daily)} daily-use terms with moedict entries:\n")
        for section in DAILY_CATEGORIES:
            section_terms = [t for t in daily if t["section"] == section]
            if section_terms:
                print(f"── {section} ({len(section_terms)}) ──")
                for t in section_terms[:10]:
                    cn = t["cn"] if t["cn"] else "—"
                    print(f"  {t['tw']} ({t['bopomofo']})  ←→  {cn}")
                    if t["definition"]:
                        defn = t["definition"][:60]
                        print(f"    定義：{defn}")
                if len(section_terms) > 10:
                    print(f"  ... and {len(section_terms) - 10} more")
                print()

    if args.generate:
        md = generate_enriched_vocab(moedict)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(md)
        size_kb = os.path.getsize(args.output) / 1024
        print(f"\nWritten to {args.output} ({size_kb:.0f} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()
