"""Shared file formats. Source text is preserved; search keys are separate."""

import hashlib
import html
import json
import os
import re
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRIORITY = {"linguipedia": 1, "moe-concised": 2, "moe-revised": 3, "microsoft": 4, "project": 5,
            "microsoft-termic": 4, "legacy-reference": 6, "microsoft-tm": 7}
NCAT_NOTICE = "中華語文知識庫 Copyright © 中華文化總會（National Cultural Association of Taiwan, NCAT）版權所有。"


def cache_dir():
    return Path(os.environ.get("LOCALIZATION_TW_CACHE", Path(os.environ.get(
        "XDG_CACHE_HOME", Path.home() / ".cache")) / "localization-tw")).expanduser()


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(value):
    payload = value if isinstance(value, bytes) else json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    binary = isinstance(text, bytes)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb" if binary else "w", **({} if binary else {"encoding": "utf-8"})) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_json(path, value):
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_jsonl(path, rows):
    atomic_write(path, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def read_jsonl(path):
    if not Path(path).exists():
        return []
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def normalize(text):
    # Do not convert scripts, punctuation, or regional spellings.
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def plain(text):
    return html.unescape(re.sub(r"<[^>]+>", "", str(text or ""))).strip()


def aliases(text, english=False):
    # Parenthetical annotations remain in original, but are not part of an alias.
    value = re.sub(r"[（(][^）)]*[）)]", "", text)
    parts = re.split(r"\s+/\s+" if english else r"[/／、]", value)
    return list(dict.fromkeys(p.strip() for p in parts if p.strip() not in ("", "—", "-")))


def record(source, identity, *, en=(), tw=(), cn=(), domain="", kind="term",
           relation="", definitions=(), pronunciations=(), url="", version="", original=None, **extra):
    return {"id": f"{source}:{identity}", "source": source, "source_id": str(identity),
            "source_version": version, "url": url, "en": list(en), "tw": list(tw),
            "cn": list(cn), "domain": domain, "kind": kind, "relation": relation,
            "definitions": list(definitions), "pronunciations": list(pronunciations),
            "original": original or {}, **extra}


def cells(line):
    return [s.strip().replace(r"\|", "|") for s in re.split(r"(?<!\\)\|", line.strip())[1:-1]]


def markdown_tables(path):
    """Recognize each table independently, including nested headings."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    section, headers = "", None
    for i, line in enumerate(lines):
        heading = re.match(r"^#{1,6}\s+(.+)", line)
        if heading:
            section, headers = heading[1], None
            continue
        if not line.lstrip().startswith("|"):
            headers = None
            continue
        values = cells(line)
        if values and all(re.fullmatch(r":?-{3,}:?", v.replace(" ", "")) for v in values):
            continue
        following = cells(lines[i + 1]) if i + 1 < len(lines) and lines[i + 1].lstrip().startswith("|") else []
        if following and all(re.fullmatch(r":?-{3,}:?", v.replace(" ", "")) for v in following):
            headers = values
            continue
        if headers:
            if len(headers) != len(values):
                raise ValueError(f"{path}:{i + 1}: table has {len(values)} cells, expected {len(headers)}")
            yield section, i + 1, dict(zip(headers, values))


def project_records(path=None):
    path = Path(path or ROOT / "references/vocabulary.md")
    output = []
    for section, line, row in markdown_tables(path):
        tw = row.get("臺灣正確用語", row.get("Correct usage", ""))
        cn = row.get("避免使用（中國用語）", row.get("Wrong usage", ""))
        en = row.get("English", "")
        kind = "term" if en else "style"
        if not tw:
            raise ValueError(f"{path}:{line}: unsupported vocabulary table")
        output.append(record("project", digest([section, en, tw, cn])[:20],
            en=aliases(en, True), tw=aliases(tw), cn=aliases(cn), domain=section, kind=kind,
            source_forms={"en": en, "tw": tw, "cn": cn},
            url=f"{path.resolve()}:{line}", original=row))
    return output


def legacy_records(path=None):
    path = Path(path or ROOT / "references/linguipedia-cross-strait.md")
    return [record("legacy-reference", digest([section, row])[:20],
        tw=aliases(row.get("臺灣用語", "")), cn=aliases(row.get("大陸用語", "")),
        domain=section, relation=row.get("類型", ""), url=f"{path.resolve()}:{line}",
        source_forms={"tw": row.get("臺灣用語", ""), "cn": row.get("大陸用語", "")},
        original=row, provenance_note="既有專案參考表；未以本次來源 ID 查證")
        for section, line, row in markdown_tables(path)]
