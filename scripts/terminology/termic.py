"""Termic adapter, building on voidful's localization-tw PR #1 request format.

https://github.com/Qmo37/localization-tw/pull/1
Termic is a third-party provider of Microsoft glossary and product string data.
"""

import re

from .common import digest, record
from .network import request_bytes

URL = "https://termic.me/"


def unlabel(text):
    return re.sub(r"^(?:(?:en[-_]?us|zh[-_]?tw)-)?(?:definition|partOfSpeech|pos):\s*", "", text, flags=re.I)


def parse_response(response, *, reverse=False, period="2020+"):
    if not isinstance(response, dict) or not {"gl_source", "gl_translation", "tm_source", "tm_translation"}.issubset(response):
        raise ValueError("Termic returned an unrecognized response")
    result = []
    for prefix, kind in (("gl", "technical"), ("tm", "product-example")):
        def array(key, optional=False):
            value = response.get(prefix + "_" + key, [])
            if value == "" or (optional and value is None):
                return []
            if optional and isinstance(value, list):
                value = ["" if v is None else v for v in value]
            if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
                raise ValueError(f"Invalid Termic field: {prefix}_{key}")
            return value
        source, target = array("source"), array("translation")
        if len(source) != len(target):
            raise ValueError("Termic source/translation arrays have different lengths")
        metadata = {k: array(k, optional=True) for k in (("source_def", "source_pos") if prefix == "gl" else ("product", "platform", "cat"))}
        if any(v and len(v) != len(source) for v in metadata.values()):
            raise ValueError("Termic metadata array length mismatch")
        for i, (src, dst) in enumerate(zip(source, target)):
            fields = {k: v[i] if v else "" for k, v in metadata.items()}
            en, tw = (dst, src) if reverse else (src, dst)
            definition = unlabel(fields.get("source_def", ""))
            r = record("microsoft-termic" if prefix == "gl" else "microsoft-tm",
                digest([en, tw, fields, period])[:24], en=[en], tw=[tw], domain="電腦資訊", kind=kind,
                definitions=[{"text": definition}] if definition else [], url=URL, version=period,
                original={"source": src, "target": dst, **fields}, identity_kind="content-fingerprint",
                provider="termic.me", period=period, product=fields.get("product", ""),
                platform=fields.get("platform", ""), part_of_speech=unlabel(fields.get("source_pos", "")))
            result.append(r)
    return result


def query(term, *, reverse=False, mode="exact", period="2020+", limit=10, modes=None):
    import json
    if not term.strip() or not 1 <= limit <= 100 or period not in ("2017", "2020+"):
        raise ValueError("Termic requires a nonempty term, a limit of 1–100, and period 2017 or 2020+")
    options = {"exact": "exact_match", "substring": "unexact_match", "fuzzy": "unexact_match", "regex": "regex"}
    if mode == "regex":
        re.compile(term)
    payload = {"term": term, "source_lang": "zh_tw" if reverse else "en_us",
               "target_lang": "en_us" if reverse else "zh_tw", "result_count_gl": limit,
               "result_count_tm": limit, "search_option": options[mode], "case_sensitive": 0,
               "modes": modes or ["glossary", "tm"], "data_period": period}
    raw = json.loads(request_bytes(URL, payload=payload, retries=2))
    records = parse_response(raw, reverse=reverse, period=period)
    return {"query": term, "reverse": reverse, "mode": mode, "period": period, "limit_per_source": limit,
            "status": "ok" if records else "no_match", "scope": "bounded-query-not-full-TM",
            "possibly_truncated": any(len(raw.get(k) or []) >= limit for k in ("gl_source", "tm_source")),
            "records": records, "raw": raw}
