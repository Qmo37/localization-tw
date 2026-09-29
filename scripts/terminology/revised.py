"""Pinned g0v conversion of the MOE Revised dictionary, after Concised evidence.

The original entry is retained verbatim. Display text supplements each definition
with its own reading, examples, quotations and cross-references; it never attaches
a general dictionary sense to an English technical concept.
"""

import json
import lzma
import tempfile
import urllib.parse
from pathlib import Path

from .common import atomic_write, digest, now, read_json, record, write_json
from .network import (REVISED_BASE, REVISED_COMMIT, REVISED_COUNT, REVISED_NOTICE,
                      REVISED_SHA256, REVISED_URL, REVISED_VERSION, download)


def snapshot_spec():
    return {"g0v_commit": REVISED_COMMIT, "dictionary_version": REVISED_VERSION,
            "sha256": REVISED_SHA256, "expected_entries": REVISED_COUNT,
            "url": REVISED_URL,
            "version_evidence": {
                "upstream_import_commit": "2c6ffd030ad257b4923d3221b28d9d9409813c00",
                "upstream_conversion_commit": "925fa834d228d7e781d1bf9b6d0a7fe718cea308",
                "official_workbook_sha256": "df94ae4384ae3f33f573ded5c2f142041ea7530d381a285163593d6252ea4a9a",
                "upstream_workbook_git_blob_sha": "e19deb331c0ccfc13dbb6b24c4fe572fccf624c9",
                "note": "Official 2015_20260625 workbook matches the pinned g0v workbook blob; dict_revised/README.md has a stale 20220922 date."}}


def revised_directory(raw):
    return Path(raw) / "revised" / REVISED_COMMIT


def revised_records(path, spec=None):
    spec = snapshot_spec() if spec is None else spec
    data = Path(path).read_bytes()
    if digest(data) != spec["sha256"]:
        raise ValueError("Revised dictionary checksum mismatch")
    try:
        entries = json.loads(lzma.decompress(data))
    except (lzma.LZMAError, EOFError, UnicodeError, json.JSONDecodeError) as e:
        raise ValueError("Invalid Revised dictionary XZ/JSON") from e
    if not isinstance(entries, list) or len(entries) != spec["expected_entries"] or not entries:
        raise ValueError("Revised dictionary entry count mismatch")
    records, seen = [], set()
    reading_count = sense_count = 0
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("title"), str) or not entry["title"].strip():
            raise ValueError("Revised dictionary entry missing headword")
        title = entry["title"]
        if title in seen:
            raise ValueError(f"Duplicate Revised headword: {title}")
        seen.add(title)
        readings = entry.get("heteronyms")
        if not isinstance(readings, list) or not readings:
            raise ValueError(f"Revised entry has no readings: {title}")
        pronunciations, definitions = [], []
        for hi, reading in enumerate(readings, 1):
            if not isinstance(reading, dict) or not isinstance(reading.get("definitions"), list):
                raise ValueError(f"Invalid Revised reading: {title}")
            bopomofo, pinyin = reading.get("bopomofo", ""), reading.get("pinyin", "")
            if not isinstance(bopomofo, str) or not isinstance(pinyin, str):
                raise ValueError(f"Invalid Revised pronunciation: {title}")
            pronunciations.append({"order": hi, "bopomofo": bopomofo, "pinyin": pinyin})
            for di, definition in enumerate(reading["definitions"], 1):
                if not isinstance(definition, dict) or not isinstance(definition.get("def"), str):
                    raise ValueError(f"Invalid Revised definition: {title}")
                lines = [f"讀音 {hi}（{' / '.join(filter(None, [bopomofo, pinyin])) or '來源未提供'}）・義項 {di}"]
                for field, label in (("type", "詞性"), ("def", "釋義"), ("example", "例句"),
                                     ("quote", "引文"), ("link", "參見"),
                                     ("synonyms", "相似詞"), ("antonyms", "相反詞")):
                    value = definition.get(field, [] if field in ("example", "quote", "link") else "")
                    if field in ("example", "quote", "link"):
                        if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
                            raise ValueError(f"Invalid Revised {field}: {title}")
                    elif not isinstance(value, str):
                        raise ValueError(f"Invalid Revised {field}: {title}")
                    for part in value if isinstance(value, list) else [value]:
                        if part:
                            lines.append(f"{label}：{part}")
                definitions.append({"text": definition["def"], "display": "\n".join(lines),
                                    "reading_order": hi, "sense_order": di,
                                    **{k: v for k, v in definition.items() if k != "def"}})
            reading_count += 1
            sense_count += len(reading["definitions"])
        records.append(record("moe-revised", digest(title)[:24], tw=[title], kind="dictionary",
            domain="一般用語", definitions=definitions, pronunciations=pronunciations, original=entry,
            version=f"{spec['dictionary_version']}; g0v {spec['g0v_commit']}",
            url="https://dict.revised.moe.edu.tw/search.jsp?word=" + urllib.parse.quote(title),
            data_url=spec["url"], usage_note="兼收古今義項；以《簡編本》為一般用語優先參考，依語境判讀。"))
    return records, {**spec, "complete": True, "imported": len(records),
        "unique_headwords": len(seen), "readings": reading_count, "definitions": sense_count,
        "provider": "g0v/moedict-data", "publisher": "中華民國教育部",
        "notice": f"中華民國教育部。《重編國語辭典修訂本》（版本編號：{spec['dictionary_version']}）。"
                  "https://dict.revised.moe.edu.tw/；g0v 整理 JSON，辭典本文 CC BY-ND 3.0 TW；"
                  "完整使用說明及上游 README 隨快照保存。"}


def load_revised(raw):
    directory = revised_directory(raw)
    try:
        manifest = read_json(directory / "manifest.json")
        if manifest.get("snapshot") != snapshot_spec():
            raise ValueError("Revised dictionary manifest does not match the pinned version")
        files = manifest.get("files")
        if not isinstance(files, dict) or set(files) != {"dict-revised.json.xz", "README.md", "revised-usage.pdf"}:
            raise ValueError("Revised dictionary manifest is incomplete")
        for name, checksum in files.items():
            if digest((directory / name).read_bytes()) != checksum:
                raise ValueError(f"Revised dictionary cached artifact mismatch: {name}")
        if not (directory / "revised-usage.pdf").read_bytes().startswith(b"%PDF"):
            raise ValueError("Revised usage instructions are not PDF")
        records, info = revised_records(directory / "dict-revised.json.xz")
    except FileNotFoundError as e:
        raise ValueError("Missing Revised snapshot; run build-vocabulary.py without --offline") from e
    if "retrieved_at" not in manifest:
        raise ValueError("Revised dictionary manifest is malformed: no retrieved_at")
    return records, {**info, "retrieved_at": manifest["retrieved_at"],
                     "artifacts": files, "usage_url": REVISED_NOTICE}


def fetch_revised(raw, *, refresh=False):
    directory = revised_directory(raw)
    if (directory / "manifest.json").exists() and not refresh:
        load_revised(raw)
        return directory
    directory.parent.mkdir(parents=True, exist_ok=True)
    # Validate every input before replacing any previous cached artifact.
    with tempfile.TemporaryDirectory(prefix=".revised-", dir=directory.parent) as temp:
        stage = Path(temp)
        for name, url in (("dict-revised.json.xz", REVISED_URL),
                          ("README.md", f"{REVISED_BASE}/README.md"), ("revised-usage.pdf", REVISED_NOTICE)):
            download(url, stage / name)
        revised_records(stage / "dict-revised.json.xz")
        if not (stage / "revised-usage.pdf").read_bytes().startswith(b"%PDF"):
            raise ValueError("Revised usage instructions are not PDF")
        if "教育部" not in (stage / "README.md").read_text(encoding="utf-8"):
            raise ValueError("Missing Revised source attribution")
        files = {p.name: digest(p.read_bytes()) for p in stage.iterdir()}
        for name in files:
            atomic_write(directory / name, (stage / name).read_bytes())
        write_json(directory / "manifest.json", {"snapshot": snapshot_spec(), "files": files, "retrieved_at": now()})
    return directory
