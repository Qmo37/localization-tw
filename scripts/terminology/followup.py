"""Read portable answers and apply only their explicitly scoped source policies.

These policies do not resolve whole conflict groups or assert sense equivalence.
The optional reviewer name stays blank when the person did not supply one.
"""

import json
from collections import Counter
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

from .common import atomic_write, digest, now, read_jsonl, write_json, write_jsonl

POLICY_KIND = "localization-tw-scoped-source-policy"
CHOICES = {"retain-context", "hold-mapping", "defer", "custom"}


class EmbeddedJSON(HTMLParser):
    def __init__(self):
        super().__init__()
        self.key = None
        self.values = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and attrs.get("type") == "application/json":
            self.key = attrs.get("id")
            if self.key in self.values:
                raise ValueError("Duplicate embedded JSON section")
            self.values[self.key] = ""

    def handle_data(self, value):
        if self.key:
            self.values[self.key] += value

    def handle_endtag(self, tag):
        if tag == "script":
            self.key = None


def read_page(path):
    parser = EmbeddedJSON()
    parser.feed(Path(path).read_text(encoding="utf-8"))
    if not {"payload", "embedded-state"}.issubset(parser.values):
        raise ValueError("Expected a portable review HTML with embedded answers")
    return tuple(json.loads(parser.values[key]) for key in ("payload", "embedded-state"))


def check_timestamp(value):
    if not isinstance(value, str) or datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is None:
        raise ValueError("Answer timestamp must include a timezone")


def held_targets(question):
    # These two options suspend only the first relation, explicitly retaining the
    # other one. Other hold options apply to all sources listed in that question.
    partial = {64: ["linguipedia:1657"], 67: ["linguipedia:379"]}
    return partial.get(question["number"], question["focus_ids"])


def prepare_answers(path, expected_page, conflicts):
    payload, state = read_page(path)
    expected, _ = read_page(expected_page)
    # Reissuing the identical questionnaire changes its creation time, not its
    # questions or evidence. Previously downloaded answers must remain usable.
    stable_payload = {k: v for k, v in payload.items() if k != "generated_at"}
    stable_expected = {k: v for k, v in expected.items() if k != "generated_at"}
    if stable_payload != stable_expected or payload.get("kind") != "localization-tw-human-only-questionnaire":
        raise ValueError("Question text, evidence, or bundle differs from the issued questionnaire")
    if not isinstance(state, dict) or state.get("version") != 1 or state.get("bundle_id") != payload["bundle_id"]:
        raise ValueError("Answer state does not match this questionnaire")
    if not isinstance(state.get("reviewer"), str) or not isinstance(state.get("answers"), dict):
        raise ValueError("Invalid reviewer or answers field")
    questions = {q["id"]: q for q in payload["questions"]}
    if set(state["answers"]) - set(questions):
        raise ValueError("Answers contain questions not asked in this questionnaire")
    lookup = {c["id"]: c for c in conflicts}
    policies, unanswered = [], []
    provenance = {"file_name": Path(path).name, "file_sha256": digest(Path(path).read_bytes()),
                  "bundle_id": payload["bundle_id"], "snapshot_id": state.get("snapshot_id"), "received_at": now()}
    for identity, question in questions.items():
        answer = state["answers"].get(identity)
        if answer is None:
            unanswered.append(identity)
            continue
        if not isinstance(answer, dict) or not isinstance(answer.get("note"), str) or answer.get("choice") not in CHOICES | {None}:
            raise ValueError(f"{identity}: invalid answer")
        option = next((o for o in question["options"] if o["id"] == answer["choice"]), None)
        if answer["choice"] is None or (answer["choice"] == "custom" and not answer["note"].strip()):
            unanswered.append(identity)
            continue
        if answer["choice"] != "custom" and option is None:
            raise ValueError(f"{identity}: selected option was not offered")
        check_timestamp(answer.get("answered_at"))
        conflict = lookup.get(question["conflict_id"])
        if not conflict or conflict["fingerprint"] != question["fingerprint"]:
            raise ValueError(f"{identity}: source evidence changed; do not apply an old answer")
        allowed = {c["id"] for c in conflict["candidates"]}
        if not set(question["focus_ids"]).issubset(allowed):
            raise ValueError(f"{identity}: unknown source in question scope")
        held = held_targets(question) if answer["choice"] == "hold-mapping" else []
        if not set(held).issubset(question["focus_ids"]):
            raise ValueError(f"{identity}: hold targets exceed the question scope")
        policies.append({
            "kind": POLICY_KIND, "version": 1, "id": digest([payload["bundle_id"], identity]),
            "question_id": identity, "number": question["number"], "title": question["title"],
            "conflict_id": question["conflict_id"], "fingerprint": question["fingerprint"],
            "focus_ids": question["focus_ids"], "held_source_ids": held,
            "choice": answer["choice"], "decision_text": option["text"] if option else answer["note"],
            "scope": question["explanation"], "note": answer["note"],
            "reviewed_by": state["reviewer"], "reviewed_at": answer["answered_at"],
            "source_verification": "still-required", "resolves_whole_conflict": False,
            "provenance": provenance,
        })
    return payload, state, policies, unanswered, provenance


def import_answers(path, expected_page, conflicts, output, reports):
    payload, state, policies, unanswered, provenance = prepare_answers(path, expected_page, conflicts)
    if not policies:
        raise ValueError("The HTML contains no completed answers")
    existing = read_jsonl(output)
    # New answers replace only the same bundle/question, without changing other reviews.
    incoming_ids = {p["id"] for p in policies}
    combined = [p for p in existing if p["id"] not in incoming_ids] + policies
    held = sorted({sid for p in policies for sid in p["held_source_ids"]})
    receipt = {
        "kind": "localization-tw-received-human-answers", "version": 1, "provenance": provenance,
        "answered_count": len(policies), "unanswered_question_ids": unanswered,
        "choices": dict(Counter(p["choice"] for p in policies)), "held_source_ids": held,
        "state": state, "policies": policies, "reference_numbers": payload["reference_numbers"],
        "reference_status": "assistant-rereview-not-human-approval", "whole_conflict_decisions_applied": False,
        "screenshot_transcription": payload["transcription"],
    }
    reports = Path(reports)
    archive = reports / "received-human-review" / provenance["file_sha256"]
    atomic_write(archive.with_suffix(".html"), Path(path).read_bytes())
    write_json(archive.with_suffix(".json"), receipt)
    write_json(reports / "review-human-only-received.json", receipt)
    write_receipt_html(reports / "review-human-only-received.html", receipt, payload)
    # Answers, evidence and the receipt all succeed before the policy file changes.
    write_jsonl(output, combined)
    return receipt


def index_policies(policies, conflicts):
    """Apply only current evidence-bound policies; surface stale ones as inactive."""
    current = {c["id"]: c for c in conflicts}
    result = {}
    for policy in policies:
        if policy.get("kind") != POLICY_KIND or policy.get("version") != 1:
            raise ValueError("Unsupported scoped source policy")
        conflict = current.get(policy["conflict_id"])
        allowed = {c["id"] for c in conflict["candidates"]} if conflict else set()
        active = bool(conflict and conflict["fingerprint"] == policy["fingerprint"]
                      and set(policy["focus_ids"]).issubset(allowed))
        if not set(policy["held_source_ids"]).issubset(policy["focus_ids"]):
            raise ValueError("Policy hold targets exceed its source scope")
        for sid in policy["focus_ids"]:
            annotation = {**policy, "active": active,
                          "use_status": "on-hold" if active and sid in policy["held_source_ids"] else
                          "context-or-verification-required" if active else "stale-policy-not-applied"}
            result.setdefault(sid, []).append(annotation)
    return result


def write_receipt_html(path, receipt, payload):
    from html import escape
    from urllib.parse import quote

    labels = {"retain-context": "保留，語境／來源待核對", "hold-mapping": "暫停指定配對",
              "defer": "繼續待查", "custom": "依補充內容整理"}
    sources = payload["reassessment"]["source_records"]
    table = []
    for policy in receipt["policies"]:
        candidates = "；".join("／".join(sources[sid]["tw"]) for sid in policy["focus_ids"])
        table.append(f'<tr><td>{policy["number"]}. {escape(policy["title"])}</td>'
                     f'<td>{escape(labels[policy["choice"]])}</td><td>{escape(policy["decision_text"])}'
                     f'<details><summary>涉及來源與原始回答</summary><p>{escape(candidates)}</p>'
                     f'<p>{escape(policy["scope"])}</p><p>補充：{escape(policy["note"]) or "未填寫"}</p>'
                     f'<p>回答時間：{escape(policy["reviewed_at"])}</p></details></td></tr>')
    references = []
    for case in payload["reassessment"]["cases"]:
        if case["number"] in receipt["reference_numbers"]:
            references.append(f'<tr><td>{case["number"]}. {escape(case["term"])}</td>'
                              f'<td>{escape(case["assessment"])}</td><td>{escape(case["relationship_guidance"])}</td></tr>')
    held = ''.join(f'<li>{escape(" / ".join(sources[sid]["en"]))} → '
                   f'{escape("／".join(sources[sid]["tw"]))} <small>（{escape(sid)}）</small></li>'
                   for sid in receipt["held_source_ids"])
    archive = 'received-human-review/' + quote(receipt["provenance"]["file_sha256"]) + '.html'
    answered = receipt["answered_count"]
    reference_count = len(receipt["reference_numbers"])
    recovered = sum(bool(r["observed_checked_ids"]) for r in payload["transcription"]["rows"])
    retained = receipt["choices"].get("retain-context", 0)
    html = f'''<!doctype html><html lang="zh-Hant-TW"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>人工補答・已收錄結果</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f4f6f2;color:#223d39;font:16px/1.75 system-ui,"Noto Sans CJK TC",sans-serif}}main{{max-width:1120px;margin:auto;padding:32px 22px}}h1{{font-size:30px}}a{{color:#186553}}section,details.panel{{background:white;border:1px solid #d6e0d8;border-radius:12px;padding:22px;margin:22px 0}}table{{width:100%;border-collapse:collapse;table-layout:fixed}}th,td{{text-align:left;vertical-align:top;padding:13px 10px;border-bottom:1px solid #d6e0d8;overflow-wrap:anywhere}}th:first-child{{width:25%}}th:nth-child(2){{width:22%}}summary{{cursor:pointer;font-weight:600}}small,footer{{color:#596e68}}footer{{font-size:12px;overflow-wrap:anywhere}}.badge{{display:inline-block;background:#e7f0e8;border-radius:8px;padding:10px 18px;margin:4px}}
@media(max-width:700px){{table,tbody,tr,td{{display:block;width:100%}}thead{{display:none}}tr{{border-bottom:1px solid #d6e0d8;padding:10px 0}}td{{border:0;padding:5px 0}}section,details.panel{{padding:16px}}}}
</style><main><p>LOCALIZATION-TW / 人工補答已收錄</p><h1>你的 {answered} 筆處理決定</h1>
<p><span class="badge">{receipt["answered_count"]} 筆已補答</span><span class="badge">{len(receipt["unanswered_question_ids"])} 筆未答</span><span class="badge">{len(receipt["held_source_ids"])} 條來源配對暫停</span></p>
<p>依你在 HTML 選定的內容記錄；保留 {recovered} 筆截圖勾選與原始來源。{retained} 筆保留項目的語境／來源疑點仍待核對，未直接標成同義或全部核准。</p>
<p><a href="{archive}">開啟你交回的原始 HTML（含答案與完整釋義）</a> · <a href="review-human-only-received.json">下載整理後的 JSON</a></p>
<section><h2>已暫停的 {len(receipt["held_source_ids"])} 條配對</h2><ul>{held}</ul><p>本地查詢預設略過這些特定來源；加上 <code>--include-held</code> 可查閱原始紀錄。其他同詞或同譯名候選不受影響。</p></section>
<section><h2>{answered} 筆人工補答</h2><table><thead><tr><th>原編號／問題</th><th>處理方式</th><th>你選定的內容</th></tr></thead><tbody>{''.join(table)}</tbody></table></section>
<details class="panel"><summary>其餘 {reference_count} 筆・參考區，不需重答</summary><p>保留上次的複核建議；這 {reference_count} 筆沒有被代填成人工核准。</p><table><thead><tr><th>原編號／詞彙</th><th>複核結論</th><th>語境與對應關係</th></tr></thead><tbody>{''.join(references)}</tbody></table></details>
<footer><p>審核者姓名為選填，原檔留白，紀錄亦維持留白。答案檔 SHA-256：{receipt["provenance"]["file_sha256"]}</p><p>{escape(payload["reassessment"]["notice"])}</p></footer></main></html>'''
    atomic_write(path, html)
