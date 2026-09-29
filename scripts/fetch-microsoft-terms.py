#!/usr/bin/env python3
"""Query Termic's Microsoft glossary/TM; inspired by voidful's PR #1."""

import argparse
import json
import time
from pathlib import Path

from terminology.common import atomic_write, plain
from terminology.termic import query


def main():
    p = argparse.ArgumentParser(description=__doc__)
    inputs = p.add_mutually_exclusive_group(required=True)
    inputs.add_argument("term", nargs="?")
    inputs.add_argument("--batch", type=Path)
    p.add_argument("--reverse", action="store_true")
    p.add_argument("--mode", choices=["exact", "substring", "fuzzy", "regex"], default="exact")
    p.add_argument("--period", choices=["2017", "2020+"], default="2020+")
    p.add_argument("--limit", type=int, default=10)
    modes = p.add_mutually_exclusive_group()
    modes.add_argument("--glossary-only", action="store_true")
    modes.add_argument("--tm-only", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--output", type=Path, help="Write one JSON document with all query outcomes")
    args = p.parse_args()
    if not 1 <= args.limit <= 100:
        p.error("--limit must be between 1 and 100")
    try:
        terms = [t.strip() for t in args.batch.read_text(encoding="utf-8").splitlines() if t.strip() and not t.lstrip().startswith("#")] if args.batch else [args.term]
        if not terms:
            raise ValueError("No query terms")
        output = []
        for i, term in enumerate(terms):
            if i:
                time.sleep(0.5)
            try:
                value = query(term, reverse=args.reverse, mode=args.mode, period=args.period, limit=args.limit,
                              modes=["glossary"] if args.glossary_only else ["tm"] if args.tm_only else None)
                value.pop("raw", None)
            except Exception as e:
                value = {"query": term, "status": "unavailable", "error": str(e), "records": []}
            output.append(value)
        text = json.dumps(output, ensure_ascii=False, indent=2)
        if args.output:
            atomic_write(args.output, text + "\n")
        if args.json:
            print(text)
        elif not args.output:
            for q in output:
                print(f"{q['query']}: {q['status']}")
                if q.get("error"):
                    print(q["error"])
                for r in q["records"]:
                    print(f"  {' / '.join(r['en'])} → {' / '.join(r['tw'])} [{r['source']}]")
                    for d in r["definitions"]:
                        print("    " + plain(d["text"]))
                    if r.get("product"):
                        print(f"    {r['product']} / {r['platform']}")
        if any(q["status"] == "unavailable" for q in output):
            p.exit(1)
    except (OSError, ValueError) as e:
        p.exit(2, f"Query failed: {e}\n")


if __name__ == "__main__":
    main()
