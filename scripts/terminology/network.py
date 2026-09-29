"""Bounded, validated HTTPS acquisition and resumable Linguipedia retrieval."""

import io
import json
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from .common import atomic_write, digest, now, read_json, write_json

USER_AGENT = "localization-tw/1.0 (+https://github.com/Qmo37/localization-tw)"
LP_API = "https://bs.chinese-linguipedia.org/api/web/diff/search"
CONCISED_VERSION = "2014_20260626"
CONCISED_URL = f"https://language.moe.gov.tw/001/Upload/Files/site_content/M0001/respub/download/dict_concised_{CONCISED_VERSION}.zip"
CONCISED_NOTICE = "https://language.moe.gov.tw/001/Upload/Files/site_content/M0001/respub/conciseddict_10312.pdf"
REVISED_COMMIT = "a6dc997417507eb510fc29822bc514de2c92728c"
REVISED_VERSION = "2015_20260625"
REVISED_BASE = f"https://raw.githubusercontent.com/g0v/moedict-data/{REVISED_COMMIT}"
REVISED_URL = f"{REVISED_BASE}/dict-revised.json.xz"
REVISED_SHA256 = "5cc4ec0efd7e549621edf9b46d261989230c1729d9dc2c8e2056f4b21c8a93da"
REVISED_COUNT = 161194
REVISED_NOTICE = "https://language.moe.gov.tw/001/Upload/Files/site_content/M0001/respub/reviseddict_10312.pdf"
MS_URL = "https://download.microsoft.com/download/b/2/d/b2db7a7c-8d33-47f3-b2c1-ee5e6445cf45/MicrosoftTermCollection.zip"
MS_MEMBER = "CHINESE (TRADITIONAL).tbx"


def request_bytes(url, *, payload=None, timeout=30, retries=3):
    for attempt in range(retries):
        try:
            headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
            data = json.dumps(payload).encode() if payload is not None else None
            if data is not None:
                headers["Content-Type"] = "application/json"
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code not in (408, 429, 500, 502, 503, 504) or attempt == retries - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries - 1:
                raise
        time.sleep(min(2 ** attempt, 4))


def download(url, path, *, refresh=False):
    path = Path(path)
    if path.exists() and not refresh:
        return path
    try:
        data = request_bytes(url, retries=1)
    except urllib.error.URLError as e:
        if not isinstance(e.reason, ssl.SSLCertVerificationError):
            raise
        # Some MOE certificates fail Python's stricter X.509 profile. curl still
        # verifies certificates and hostnames; never disable TLS verification.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d) / "download"
            subprocess.run(["curl", "--fail", "--location", "--silent", "--show-error",
                            "--max-time", "60", "--output", str(tmp), url], check=True)
            data = tmp.read_bytes()
    atomic_write(path, data)
    return path


def validate_lp_page(value, page):
    if not isinstance(value, dict) or value.get("status") is not True:
        raise ValueError(f"Linguipedia page {page}: invalid status")
    d = value.get("data", {})
    if not isinstance(d.get("data"), list) or not isinstance(d.get("total"), int) or not isinstance(d.get("last_page"), int):
        raise ValueError(f"Linguipedia page {page}: invalid schema")
    if d.get("current_page", page) != page:
        raise ValueError(f"Linguipedia returned wrong page for {page}")
    for row in d["data"]:
        if not isinstance(row, dict) or not row.get("id") or row.get("type") not in (
                "同實異名", "同名異實", "臺灣特有", "大陸特有"):
            raise ValueError(f"Linguipedia page {page}: invalid record")
    return d


def fetch_linguipedia(directory, *, refresh=False, delay=0.3, fetch=None, max_pages=None):
    """Page checkpoints survive failure. The published raw snapshot stays intact."""
    directory = Path(directory)
    checkpoint = directory / "linguipedia-checkpoint.json"
    complete = directory / "linguipedia.json"
    if complete.exists() and not refresh and not checkpoint.exists():
        result = read_json(complete)
        if result.get("complete") is True:
            items = result.get("items", [])
            if (len(items) != result.get("expected_total") or len({r.get("id") for r in items}) != len(items)
                    or digest(items) != result.get("sha256")):
                raise ValueError("Linguipedia cached snapshot is invalid; refresh it")
            return result
    if checkpoint.exists():
        state = read_json(checkpoint)
        if state.get("api") != LP_API or state.get("schema") != 1:
            raise ValueError("Incompatible Linguipedia checkpoint")
    else:
        state = {"schema": 1, "api": LP_API, "started_at": now(), "pages": {}, "complete": False}
    def get(page):
        if fetch:
            return fetch(page)
        query = urllib.parse.urlencode({"category": "", "page": page, "word": "", "type": ""})
        return json.loads(request_bytes(f"{LP_API}?{query}"))
    first = validate_lp_page(get(1), 1)
    expected, last = first["total"], first["last_page"]
    if state["pages"] and (state.get("expected_total"), state.get("last_page")) != (expected, last):
        raise ValueError("Source counts changed during resume; move the checkpoint aside and refresh")
    if state["pages"] and state["pages"].get("1") != first["data"]:
        raise ValueError("Source first page changed during resume; restart the snapshot")
    state.update(expected_total=expected, last_page=last)
    state["pages"]["1"] = first["data"]
    write_json(checkpoint, state)
    for page in range(2, last + 1):
        if str(page) in state["pages"]:
            continue
        if max_pages and len(state["pages"]) >= max_pages:
            return state
        time.sleep(delay)
        d = validate_lp_page(get(page), page)
        if (d["total"], d["last_page"]) != (expected, last):
            raise ValueError("Source counts changed during fetch; checkpoint retained")
        state["pages"][str(page)] = d["data"]
        write_json(checkpoint, state)
        if page % 20 == 0 or page == last:
            print(f"Linguipedia: {page}/{last} pages", flush=True)
    items = [r for page in range(1, last + 1) for r in state["pages"][str(page)]]
    ids = [r["id"] for r in items]
    if len(ids) != expected or len(set(ids)) != expected:
        raise ValueError(f"Linguipedia completeness failed: rows={len(ids)}, unique={len(set(ids))}, expected={expected}")
    result = {k: v for k, v in state.items() if k != "pages"}
    result.update(complete=True, fetched_at=now(), completed_pages=last, items=items, sha256=digest(items))
    write_json(complete, result)
    checkpoint.unlink()
    return result


class RangeFile(io.RawIOBase):
    """Read one ZIP member without downloading every language's archive."""

    def __init__(self, url):
        self.url, self.pos = url, 0
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as r:
            self.size = int(r.headers["Content-Length"])
            self.modified = r.headers.get("Last-Modified", "")
            self.validator = r.headers.get("ETag") or self.modified

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = offset if whence == 0 else self.pos + offset if whence == 1 else self.size + offset
        if self.pos < 0:
            raise ValueError("Negative ZIP offset")
        return self.pos

    def seekable(self):
        return True

    def read(self, size=-1):
        if size < 0:
            size = self.size - self.pos
        if size <= 0 or self.pos >= self.size:
            return b""
        end = min(self.size - 1, self.pos + size - 1)
        headers = {"Range": f"bytes={self.pos}-{end}", "User-Agent": USER_AGENT}
        if self.validator:
            headers["If-Range"] = self.validator
        with urllib.request.urlopen(urllib.request.Request(self.url, headers=headers), timeout=30) as r:
            if r.status != 206 or not r.headers.get("Content-Range", "").startswith(f"bytes {self.pos}-{end}/"):
                raise ValueError("Range response invalid or Microsoft archive changed; retry acquisition")
            data = r.read(size)
        if len(data) != end - self.pos + 1:
            raise ValueError("Truncated range response")
        self.pos += len(data)
        return data


def fetch_microsoft(directory, refresh=False):
    directory = Path(directory)
    target, meta = directory / "microsoft-traditional.tbx", directory / "microsoft-manifest.json"
    if target.exists() and meta.exists() and not refresh:
        info = read_json(meta)
        if digest(target.read_bytes()) != info["sha256"]:
            raise ValueError("Microsoft cached TBX checksum mismatch")
        return info
    remote = RangeFile(MS_URL)
    with zipfile.ZipFile(remote) as archive:
        data = archive.read(MS_MEMBER)  # zipfile also validates the member CRC.
    import xml.etree.ElementTree as ET
    root = ET.fromstring(data)
    count = sum(1 for _ in root.iter("termEntry"))
    if not count:
        raise ValueError("Microsoft TBX has no entries")
    info = {"url": MS_URL, "member": MS_MEMBER, "archive_bytes": remote.size,
            "last_modified": remote.modified, "fetched_at": now(), "sha256": digest(data),
            "member_bytes": len(data), "expected_entries": count}
    atomic_write(target, data)
    write_json(meta, info)
    return info
