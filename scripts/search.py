#!/usr/bin/env python3
"""
Unified terminology search across all vocabulary sources.

Searches vocabulary.md, linguipedia-cross-strait.md, and optionally
queries termic.me for Microsoft terminology.

Usage:
    python3 scripts/search.py 軟體
    python3 scripts/search.py software
    python3 scripts/search.py "open source" --online
    python3 scripts/search.py 資料 --mode exact
    python3 scripts/search.py "serve" --mode regex
"""

import argparse
import json
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
VOCAB_PATH = os.path.join(PROJECT_DIR, "references", "vocabulary.md")
LINGUIPEDIA_PATH = os.path.join(PROJECT_DIR, "references", "linguipedia-cross-strait.md")
ENRICHED_PATH = os.path.join(PROJECT_DIR, "references", "vocabulary-enriched.md")


def parse_markdown_table(filepath):
    """Parse a markdown file containing tables. Returns list of dicts."""
    entries = []
    if not os.path.exists(filepath):
        return entries

    current_section = ""
    headers = []

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip()
            if line.startswith("## "):
                current_section = line[3:].strip()
                headers = []
                continue

            if line.startswith("| ") and "---" not in line:
                cells = [c.strip() for c in line.split("|")[1:-1]]
                if not headers:
                    headers = cells
                    continue
                entry = {"_section": current_section, "_source_file": filepath}
                for i, h in enumerate(headers):
                    if i < len(cells):
                        entry[h] = cells[i]
                entries.append(entry)

    return entries


def load_vocabulary():
    """Load vocabulary.md entries, normalized to a common schema."""
    raw = parse_markdown_table(VOCAB_PATH)
    entries = []
    for r in raw:
        en = r.get("English", r.get("避免使用（中國用語）", "")).strip()
        tw = r.get("臺灣正確用語", r.get("臺灣正確用語", "")).strip()
        cn = r.get("避免使用（中國用語）", "").strip()
        if r.get("Wrong usage"):
            cn = r.get("Wrong usage", "")
            tw = r.get("Correct usage", "")
            en = r.get("說明", "")

        entries.append({
            "en": en,
            "tw": tw,
            "cn": cn,
            "section": r["_section"],
            "source": "vocabulary.md",
            "type": "curated",
        })
    return entries


def load_enriched():
    """Load vocabulary-enriched.md entries (with bopomofo and MOE definitions)."""
    if not os.path.exists(ENRICHED_PATH):
        return []
    raw = parse_markdown_table(ENRICHED_PATH)
    entries = []
    seen = set()
    for r in raw:
        tw = r.get("臺灣用語", "").strip()
        if not tw or tw in seen:
            continue
        seen.add(tw)

        entries.append({
            "en": r.get("English", "").strip(),
            "tw": tw,
            "cn": r.get("避免用語", r.get("大陸用語", "")).strip(),
            "bopomofo": r.get("注音", "").strip(),
            "definition": r.get("教育部定義", "").strip(),
            "section": r["_section"],
            "source": "moedict",
            "type": "moe-enriched",
        })
    return entries


def load_linguipedia():
    """Load linguipedia-cross-strait.md entries."""
    raw = parse_markdown_table(LINGUIPEDIA_PATH)
    entries = []
    for r in raw:
        entries.append({
            "en": "",
            "tw": r.get("臺灣用語", "").strip(),
            "cn": r.get("大陸用語", "").strip(),
            "section": r["_section"],
            "source": "linguipedia",
            "type": r.get("類型", ""),
        })
    return entries


def match_entry(entry, query, mode="fuzzy"):
    """Check if an entry matches the query. Returns match score or 0."""
    fields = [entry.get("en", ""), entry.get("tw", ""), entry.get("cn", ""),
              entry.get("definition", "")]
    text = " ".join(fields).lower()
    q = query.lower()

    if mode == "exact":
        for f in fields:
            if f.lower() == q:
                return 3
            for part in re.split(r"[/／、,，\s]+", f):
                if part.strip().lower() == q:
                    return 2
        return 0
    elif mode == "regex":
        try:
            pattern = re.compile(query, re.IGNORECASE)
        except re.error:
            print(f"Invalid regex: {query}", file=sys.stderr)
            return 0
        for f in fields:
            if pattern.search(f):
                return 2
        return 0
    else:
        for f in fields:
            if f.lower() == q:
                return 3
        if q in text:
            return 1
        return 0


def search_local(query, mode="fuzzy"):
    """Search all local vocabulary sources."""
    vocab = load_vocabulary()
    lp = load_linguipedia()
    enriched = load_enriched()
    all_entries = vocab + lp + enriched

    results = []
    for entry in all_entries:
        score = match_entry(entry, query, mode)
        if score > 0:
            results.append((score, entry))

    results.sort(key=lambda x: -x[0])
    return [r[1] for r in results]


def search_online(query, mode="fuzzy"):
    """Search termic.me for Microsoft terminology."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "fetch_microsoft_terms",
        os.path.join(SCRIPT_DIR, "fetch-microsoft-terms.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    search_termic = mod.search_termic
    parse_results = mod.parse_results

    mode_map = {"exact": "exact_match", "fuzzy": "unexact_match", "regex": "regex"}
    response = search_termic(query, search_option=mode_map.get(mode, "unexact_match"))
    glossary, tm = parse_results(response)

    results = []
    for g in glossary:
        results.append({
            "en": g["source"],
            "tw": g["target"],
            "cn": "",
            "section": g.get("pos", ""),
            "source": "microsoft-glossary",
            "type": g.get("definition", ""),
        })
    for t in tm:
        results.append({
            "en": t["source"],
            "tw": t["target"],
            "cn": "",
            "section": t.get("product", ""),
            "source": "microsoft-tm",
            "type": t.get("category", ""),
        })
    return results


def format_text(results, query, show_source=True):
    """Format results as terminal text."""
    if not results:
        return f"No results for: {query}"

    lines = [f"Found {len(results)} result(s) for: {query}", ""]

    source_groups = {}
    for r in results:
        src = r["source"]
        if src not in source_groups:
            source_groups[src] = []
        source_groups[src].append(r)

    source_labels = {
        "vocabulary.md": "Curated Vocabulary",
        "linguipedia": "Chinese Linguipedia (Cross-Strait)",
        "moedict": "MOE Dictionary (教育部辭典)",
        "microsoft-glossary": "Microsoft Glossary",
        "microsoft-tm": "Microsoft Translation Memory",
    }

    for src, entries in source_groups.items():
        if show_source:
            label = source_labels.get(src, src)
            lines.append(f"── {label} ({len(entries)}) ──")
        for e in entries:
            parts = []
            if e["en"]:
                parts.append(f"EN: {e['en']}")
            if e["tw"]:
                parts.append(f"TW: {e['tw']}")
            if e.get("bopomofo"):
                parts.append(f"({e['bopomofo']})")
            if e["cn"]:
                parts.append(f"CN: {e['cn']}")
            lines.append("  " + "  |  ".join(parts))
            if e.get("definition"):
                defn = e["definition"]
                if len(defn) > 80:
                    defn = defn[:80] + "…"
                lines.append(f"    定義：{defn}")
            meta = []
            if e["section"]:
                meta.append(e["section"])
            if e["type"] and e["type"] not in ("curated", "moe-enriched"):
                meta.append(e["type"])
            if meta:
                lines.append(f"    [{', '.join(meta)}]")
        lines.append("")

    return "\n".join(lines)


def format_json(results):
    """Format results as JSON."""
    return json.dumps(results, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Search terminology across all vocabulary sources"
    )
    parser.add_argument("query", help="Term to search (EN, zh_TW, or zh_CN)")
    parser.add_argument(
        "--mode", choices=["exact", "fuzzy", "regex"], default="fuzzy",
        help="Search mode (default: fuzzy)"
    )
    parser.add_argument(
        "--online", action="store_true",
        help="Also search termic.me for Microsoft terminology"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output as JSON"
    )
    parser.add_argument(
        "--local-only", action="store_true",
        help="Search local data only (default behavior)"
    )
    args = parser.parse_args()

    results = search_local(args.query, args.mode)

    if args.online and not args.local_only:
        try:
            online_results = search_online(args.query, args.mode)
            results.extend(online_results)
        except Exception as e:
            print(f"Online search failed: {e}", file=sys.stderr)

    if args.json:
        print(format_json(results))
    else:
        print(format_text(results, args.query))


if __name__ == "__main__":
    main()
