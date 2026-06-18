#!/usr/bin/env python3
"""
Fetch Microsoft terminology translations via termic.me (EN↔zh_TW).

termic.me is an open-source replacement for Microsoft Terminology Search,
providing access to Microsoft's Glossary (standardized term pairs with
definitions) and Translation Memory (actual shipped product strings).

Source: https://github.com/spidersouris/termic

Usage:
    python3 scripts/fetch-microsoft-terms.py "open source"
    python3 scripts/fetch-microsoft-terms.py "server" --mode exact
    python3 scripts/fetch-microsoft-terms.py "database" --glossary-only
    python3 scripts/fetch-microsoft-terms.py "介面" --reverse
    python3 scripts/fetch-microsoft-terms.py "click" --output results.md
    python3 scripts/fetch-microsoft-terms.py --batch terms.txt --output glossary.md
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

TERMIC_URL = "https://termic.me/"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def search_termic(term, source_lang="en_us", target_lang="zh_tw",
                  search_option="unexact_match", case_sensitive=False,
                  modes=None, data_period="2020+",
                  result_count_gl=25, result_count_tm=25,
                  max_retries=3):
    """Query termic.me search API. Returns parsed JSON response."""
    if modes is None:
        modes = ["glossary", "tm"]

    payload = json.dumps({
        "term": term,
        "source_lang": source_lang,
        "target_lang": target_lang,
        "result_count_gl": result_count_gl,
        "result_count_tm": result_count_tm,
        "search_option": search_option,
        "case_sensitive": 1 if case_sensitive else 0,
        "modes": modes,
        "data_period": data_period,
    }).encode("utf-8")

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(TERMIC_URL, data=payload, headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            if attempt < max_retries - 1:
                wait = 1.0 * (2 ** attempt)
                print(f"  Retry {attempt + 1}/{max_retries} after {wait:.1f}s: {e}",
                      file=sys.stderr)
                time.sleep(wait)
            else:
                raise RuntimeError(f"Failed to query termic for '{term}': {e}")


def _strip_prefix(s, prefix):
    """Remove a label prefix like 'en-US-definition: ' from a string."""
    if not s:
        return ""
    for p in (prefix, prefix.replace("-", "")):
        idx = s.find(": ")
        if idx != -1 and idx < 40:
            return s[idx + 2:]
    return s


def parse_results(response):
    """Parse termic parallel-array response into structured glossary and TM results."""
    glossary = []
    tm = []

    if not isinstance(response, dict):
        return glossary, tm

    gl_sources = response.get("gl_source", [])
    gl_translations = response.get("gl_translation", [])
    gl_defs = response.get("gl_source_def", [])
    gl_pos = response.get("gl_source_pos", [])

    for i in range(len(gl_sources)):
        glossary.append({
            "source": gl_sources[i] if i < len(gl_sources) else "",
            "target": gl_translations[i] if i < len(gl_translations) else "",
            "pos": _strip_prefix(gl_pos[i], "partOfSpeech") if i < len(gl_pos) else "",
            "definition": _strip_prefix(gl_defs[i], "definition") if i < len(gl_defs) else "",
        })

    tm_sources = response.get("tm_source", [])
    tm_translations = response.get("tm_translation", [])
    tm_products = response.get("tm_product", [])
    tm_platforms = response.get("tm_platform", [])
    tm_cats = response.get("tm_cat", [])

    for i in range(len(tm_sources)):
        tm.append({
            "source": tm_sources[i] if i < len(tm_sources) else "",
            "target": tm_translations[i] if i < len(tm_translations) else "",
            "product": tm_products[i] if i < len(tm_products) else "",
            "platform": tm_platforms[i] if i < len(tm_platforms) else "",
            "category": tm_cats[i] if i < len(tm_cats) else "",
        })

    return glossary, tm


def format_results_text(term, glossary, tm):
    """Format results as human-readable text."""
    lines = [f"Search: {term}", "=" * 60]

    if glossary:
        lines.append(f"\n📖 Glossary ({len(glossary)} results)")
        lines.append("-" * 40)
        for g in glossary:
            lines.append(f"  {g['source']}  →  {g['target']}")
            if g["pos"]:
                lines.append(f"    POS: {g['pos']}")
            if g["definition"]:
                defn = g["definition"][:120]
                if len(g["definition"]) > 120:
                    defn += "..."
                lines.append(f"    Def: {defn}")

    if tm:
        lines.append(f"\n📝 Translation Memory ({len(tm)} results)")
        lines.append("-" * 40)
        for t in tm:
            lines.append(f"  {t['source']}")
            lines.append(f"  → {t['target']}")
            meta = []
            if t["product"]:
                meta.append(t["product"])
            if t["platform"]:
                meta.append(t["platform"])
            if meta:
                lines.append(f"    [{', '.join(meta)}]")
            lines.append("")

    if not glossary and not tm:
        lines.append("\nNo results found.")

    return "\n".join(lines)


def format_results_markdown(term, glossary, tm):
    """Format results as markdown."""
    lines = [f"### {term}", ""]

    if glossary:
        lines.append(f"**Glossary** ({len(glossary)} results)")
        lines.append("")
        lines.append("| English | 臺灣用語 | POS | Definition |")
        lines.append("| ------- | -------- | --- | ---------- |")
        for g in glossary:
            src = g["source"].replace("|", "\\|")
            tgt = g["target"].replace("|", "\\|")
            pos = g["pos"].replace("|", "\\|") if g["pos"] else ""
            defn = g["definition"].replace("|", "\\|") if g["definition"] else ""
            if len(defn) > 80:
                defn = defn[:80] + "…"
            lines.append(f"| {src} | {tgt} | {pos} | {defn} |")
        lines.append("")

    if tm:
        lines.append(f"**Translation Memory** ({len(tm)} results)")
        lines.append("")
        lines.append("| Source | Translation | Product |")
        lines.append("| ------ | ----------- | ------- |")
        for t in tm:
            src = t["source"].replace("|", "\\|")
            tgt = t["target"].replace("|", "\\|")
            prod = t["product"].replace("|", "\\|") if t["product"] else ""
            lines.append(f"| {src} | {tgt} | {prod} |")
        lines.append("")

    if not glossary and not tm:
        lines.append("No results found.")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Search Microsoft terminology for EN↔zh_TW translations via termic.me"
    )
    parser.add_argument(
        "term", nargs="?", help="Term to search"
    )
    parser.add_argument(
        "--batch", metavar="FILE",
        help="Read terms from file (one per line) and search all"
    )
    parser.add_argument(
        "--mode", choices=["exact", "fuzzy", "regex"], default="fuzzy",
        help="Search mode (default: fuzzy)"
    )
    parser.add_argument(
        "--glossary-only", action="store_true",
        help="Search glossary only (no translation memory)"
    )
    parser.add_argument(
        "--tm-only", action="store_true",
        help="Search translation memory only (no glossary)"
    )
    parser.add_argument(
        "--reverse", action="store_true",
        help="Search zh_TW → EN (reverse direction)"
    )
    parser.add_argument(
        "--output", metavar="FILE",
        help="Write results to a markdown file"
    )
    parser.add_argument(
        "--limit-gl", type=int, default=25,
        help="Max glossary results per term (default: 25)"
    )
    parser.add_argument(
        "--limit-tm", type=int, default=25,
        help="Max translation memory results per term (default: 25)"
    )
    parser.add_argument(
        "--period", default="2020+",
        help="Data period: 2017 or 2020+ (default: 2020+)"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output raw JSON response"
    )
    args = parser.parse_args()

    if not args.term and not args.batch:
        parser.error("either a search term or --batch FILE is required")

    mode_map = {
        "exact": "exact_match",
        "fuzzy": "unexact_match",
        "regex": "regex",
    }
    search_option = mode_map[args.mode]

    modes = []
    if args.glossary_only:
        modes = ["glossary"]
    elif args.tm_only:
        modes = ["tm"]
    else:
        modes = ["glossary", "tm"]

    source_lang = "zh_tw" if args.reverse else "en_us"
    target_lang = "en_us" if args.reverse else "zh_tw"

    terms = []
    if args.batch:
        with open(args.batch, "r", encoding="utf-8") as f:
            terms = [line.strip() for line in f if line.strip()
                     and not line.startswith("#")]
        print(f"Loaded {len(terms)} terms from {args.batch}", file=sys.stderr)
    else:
        terms = [args.term]

    all_md = []
    for i, term in enumerate(terms):
        if len(terms) > 1:
            print(f"[{i + 1}/{len(terms)}] Searching: {term}", file=sys.stderr)

        response = search_termic(
            term,
            source_lang=source_lang,
            target_lang=target_lang,
            search_option=search_option,
            modes=modes,
            data_period=args.period,
            result_count_gl=args.limit_gl,
            result_count_tm=args.limit_tm,
        )

        if args.json:
            print(json.dumps(response, ensure_ascii=False, indent=2))
            continue

        glossary, tm = parse_results(response)

        if args.output:
            all_md.append(format_results_markdown(term, glossary, tm))
        else:
            print(format_results_text(term, glossary, tm))

        if len(terms) > 1 and i < len(terms) - 1:
            time.sleep(0.5)

    if args.output and all_md:
        tz_tw = timezone(timedelta(hours=8))
        now = datetime.now(tz_tw).strftime("%Y-%m-%d")
        header = [
            "# Microsoft Terminology — EN↔zh_TW",
            "",
            f"> Source: [termic.me]({TERMIC_URL}) (Microsoft Glossary & Translation Memory)",
            f"> Generated: {now}",
            f"> Search mode: {args.mode} | Period: {args.period}",
            "",
        ]
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("\n".join(header) + "\n".join(all_md))
        print(f"Written to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
