#!/usr/bin/env python3
"""Build a portable follow-up questionnaire from the screenshot transcription."""

import argparse
import json
from pathlib import Path

from terminology.common import NCAT_NOTICE, ROOT, atomic_write, digest, now, read_json, read_jsonl


def build(directory):
    transcript = read_json(directory / "screenshot-review.json")
    proposals = read_json(directory / "chat-review-questions.json")
    evidence = {row["id"]: row for row in read_jsonl(directory / "conflict-evidence.jsonl")}
    rows = transcript["rows"]
    for row in rows:
        source = evidence[row["conflict_id"]]
        if source["fingerprint"] != row["fingerprint"]:
            raise ValueError(f"Evidence changed for row {row['number']}; recheck the screenshot first")
        if [c["id"] for c in source["candidates"]] != [c["source_id"] for c in row["candidates"]]:
            raise ValueError(f"Candidate order changed for row {row['number']}")
        if row["observed_checked_ids"] != [c["source_id"] for c in row["candidates"] if c["observed"] == "checked"]:
            raise ValueError(f"Inconsistent checkbox transcription for row {row['number']}")
        row["evidence"] = source["candidates"]

    by_number = {row["number"]: row for row in rows}
    questions = []
    for question in proposals["questions"]:
        number = question["number"]
        if number is not None:
            row = by_number[number]
            if (question["conflict_id"], question["fingerprint"]) != (row["conflict_id"], row["fingerprint"]):
                raise ValueError(f"Question evidence changed for row {number}")
        questions.append({**question, "id": f"row-{number}" if number is not None else "selection-meaning",
                          "label": f"{number}. {by_number[number]['term']}" if number is not None else "52 筆勾選的共同含意"})

    payload = {
        "kind": "localization-tw-followup-questionnaire", "version": 1,
        "generated_at": now(), "notice": NCAT_NOTICE,
        "transcription": transcript, "questions": questions,
        "context_rules": ["電腦作業系統的 process 使用「行程」；旅程與時間安排的行程另分義。",
                          "依語境優先查中華語文知識庫，其次為《國語辭典簡編本》，Microsoft 術語庫與翻譯記憶庫作補充。"],
        "concerns": [
            {"numbers": [59], "title": "音訊／audio：義項關聯需要修正",
             "text": "截圖勾了《簡編本》與專案的「音訊」。但此筆辭典釋義是「消息」，不能拿來定義技術上的 audio。「音訊」這個譯名可保留，一般義與技術義應分開。"},
            {"numbers": [27, 48, 50], "title": "process／程序／行程：保留語境差異",
             "text": "依你已說明的原則，作業系統 process 用「行程」。旅程安排、工作流程、處理動作與 SmartArt 流程圖各有不同意思；《簡編本》的旅程義不能當成作業系統行程的定義。第 27 與第 50 筆的原始勾選不同，已分別保留。"},
            {"numbers": [2, 8, 31], "title": "會計科目、回撥、支架：分義即可，不能僅憑譯名判錯",
             "text": "account、callback、support 的這些候選在會計、電話、實體支撐等語境可以成立；只有將它們當成所有語境皆可互換時才有問題。"},
            {"numbers": [33], "title": "thread：你已避開一筆可疑配對",
             "text": "將社群貼文反應定義配成「執行緒」的候選未被勾選；真正電腦執行緒的候選有勾。這裡保留你的原始選擇。"},
        ],
    }
    payload["bundle_id"] = digest({"transcription": transcript, "questions": questions,
                                    "context_rules": payload["context_rules"], "concerns": payload["concerns"]})
    encoded = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    template = (ROOT / "scripts/terminology/followup-template.html").read_text(encoding="utf-8")
    output = directory / "review-followup.html"
    atomic_write(output, template.replace("__PAYLOAD__", encoded))
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, default=ROOT / "reports")
    args = parser.parse_args()
    print(build(args.reports))


if __name__ == "__main__":
    main()
