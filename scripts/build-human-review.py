#!/usr/bin/env python3
"""Build a focused, portable questionnaire from the complete sense reassessment."""

import argparse
import hashlib
import json
from pathlib import Path

from terminology.common import ROOT, atomic_write, digest, now, read_json

# Each question concerns a remaining source/context gap, not all meanings of a word.
QUESTIONS = {
    2: {
        "focus_ids": ["microsoft:21638_779054_2087635"],
        "title": "account → 身分識別：這筆來源應如何使用？",
        "explanation": "帳戶、帳號、會計科目與客戶可以依語境並存。這次只需處理你有勾的「身分識別」：來源描述使用者可存取網路或系統的屬性集合，但未附可核對的產品原句。不能只因譯名不常見就判錯，也還不足以當成 account 的通用譯法。",
        "retain": "保留「身分識別」這筆來源，註明存取屬性語境及產品原句待補；實際採用前核對語境（建議）。",
        "hold": "先將 account → 身分識別這條對應移出使用中的詞表，原始來源與既有勾選保留。",
    },
    6: {
        "focus_ids": ["microsoft:10451_16349_16367"],
        "title": "audio：只確認這筆來源的詞性與釋義表述如何處理",
        "explanation": "技術上的「音訊／音訊檔案」可以保留；《簡編本》「音訊」的消息義另列，不用重新選。剩餘疑點只在這筆 Microsoft 資料：詞性標成 Noun，英文釋義卻採形容詞式表述。跨語言詞性本來就可能不同，這項差異本身不能證明譯名或整筆資料錯誤。",
        "retain": "保留 audio → 音訊；這筆來源的詞性與表述加註待核對，不影響其他音訊候選（建議）。",
        "hold": "暫不以這一筆有疑問的來源支撐詞義對應；其他技術音訊來源仍可使用，原始紀錄保留。",
    },
    7: {
        "focus_ids": ["microsoft:6186_418609_1380101", "microsoft:6186_418609_2510586"],
        "title": "call → 撥號／撥打：缺少原產品句子的兩筆如何處理？",
        "explanation": "程式呼叫、電話通話、撥號／撥打與 CALL 函式可以依用途並存。你有勾的這兩筆以語音通話作定義，中文則是動作詞「撥號／撥打」；如果出現在按鈕或操作指示，可能成立。尚缺原句，不能只按英文名詞標記判錯。",
        "retain": "保留這兩筆，限定為待核對的電話操作用法；取得原句後再決定適用範圍（建議）。",
        "hold": "先暫停這兩筆特定來源的對應，保留其他 call 候選及原始紀錄。",
    },
    10: {
        "focus_ids": ["microsoft:1810_33647_33662", "microsoft:3397_33620_33638"],
        "title": "code：兩條語意可疑的來源配對要先暫停嗎？",
        "explanation": "疑點一：描述符號系統的定義，中文配成「撰寫」。疑點二：描述撰寫程式指令的動作，中文配成「字碼」。這是定義與譯詞的語意疑點，不是單純詞性不同。程式碼、代碼、編碼、撰寫程式與 CODE 函式仍依語境保留。原截圖未拍到本筆勾選區，因此這裡不推定你原先選了哪個。若兩條要分別處理，可選自行說明。",
        "retain": "保留這兩條候選，但標示語意對應待查；使用時須另外核對原句。",
        "hold": "先暫停這兩條配對，保留原始來源；其他 code 對應依語境使用（建議）。",
    },
    12: {
        "focus_ids": ["microsoft:4835_39274_2104807"],
        "title": "control → 視覺效果：要保留為待查的產品用法嗎？",
        "explanation": "控制、控制項、元件與控制措施可以有不同或上下位關係。剩餘疑點是「視覺效果」這筆：來源定義為可互動、輸入、顯示資訊或設定值的物件，但沒有產品句子可證明這個譯法。不能逕自當成一般 control 的對應。原截圖未拍到本筆勾選區。",
        "retain": "保留 control → 視覺效果為待查候選；補上產品用例後才確認適用範圍。",
        "hold": "先暫停 control → 視覺效果這條配對，保留原始來源及其他 control 候選（建議）。",
    },
    33: {
        "focus_ids": ["microsoft:30904_1567776_2246024"],
        "title": "thread → 發佈反應：你有勾的這筆如何限定語境？",
        "explanation": "電腦執行緒、對話／討論串可以並存。這次只問你有勾的「發佈反應」：來源描述所有已發佈反應的集合，但缺少產品原句，需確認是功能名稱、動作標籤還是集合名稱。另外，把相同社群定義配成「執行緒」的可疑來源，你原先沒有勾；該筆維持原紀錄，不要求你重答。",
        "retain": "保留「發佈反應」，註明社群反應集合的來源語境與產品原句待補；不與電腦執行緒混為同義（建議）。",
        "hold": "先暫停 thread → 發佈反應這條來源配對，保留其他 thread 候選及原始紀錄。",
    },
    63: {
        "focus_ids": ["linguipedia:85", "linguipedia:98"],
        "title": "塑封 → 膠膜／護貝：來源未說明的使用範圍如何記錄？",
        "explanation": "中華語文知識庫列有「塑封／膠膜」與「过塑、塑封／護貝」兩組，你都有勾。現有來源未附完整材料或加工釋義，《簡編本》也沒有本次可用的直接詞目。材料、加工、成品之間的區分只能暫定，還不能宣稱兩組完全同義或互斥。",
        "retain": "依知識庫保留兩組對應，註明材料／加工／成品的細部適用範圍待補；遇到實際句子再判斷（建議）。",
        "hold": "兩組先只保留為來源候選，取得具體用例後才納入使用中的詞表。",
    },
    64: {
        "focus_ids": ["linguipedia:1657", "linguipedia:1658"],
        "title": "耳朵眼儿 → 耳洞／耳道：口語指稱的範圍如何保留？",
        "explanation": "你勾了知識庫的兩組：耳洞，以及耳道／外耳道／外聽道。《簡編本》的外聽道指外耳通往鼓膜的構造，並列外耳道。耳洞的口語指稱仍要看句子，不能直接限定為穿耳孔。需要補充的是這個語境邊界，不是重新選唯一譯名。",
        "retain": "保留兩組；解剖語境附外耳道／外聽道的釋義，耳洞的口語指稱待實際句子確認（建議）。",
        "hold": "先暫停「耳朵眼儿 → 耳洞」的使用中對應，保留原始來源；耳道／外耳道／外聽道依解剖語境使用。",
    },
    67: {
        "focus_ids": ["linguipedia:379", "linguipedia:387"],
        "title": "袜裤 → 套褲／褲襪：服裝形制尚未確認，如何處理？",
        "explanation": "你勾了知識庫的套褲與褲襪兩組。《簡編本》把褲襪解釋為像褲子的貼身長襪；本次沒有套褲的完整詞目或對應圖示。現有資料無法保證兩組在所有形制上都相同，也不足以斷言一定不同。",
        "retain": "保留兩組知識庫對應，註明服裝形制及用例待補；不先設定兩詞完全同義或互斥（建議）。",
        "hold": "先將「袜裤 → 套褲」保留為待查來源候選，褲襪則限於像褲子的貼身長襪語境。",
    },
}


def build(directory):
    report = read_json(directory / "sense-rereview-67.json")
    transcript_path = directory / "screenshot-review.json"
    transcript = read_json(transcript_path)
    if hashlib.sha256(transcript_path.read_bytes()).hexdigest() != report["original_transcription_sha256"]:
        raise ValueError("Screenshot transcription changed since the sense reassessment")
    rows = {row["number"]: row for row in transcript["rows"]}
    cases = report["cases"]
    if len({case["number"] for case in cases}) != len(cases) or set(rows) != {c["number"] for c in cases}:
        raise ValueError("Reassessment and screenshot row coverage differ")
    questions = []
    for case in cases:
        row = rows[case["number"]]
        if any(row[key] != case[key] for key in ("conflict_id", "fingerprint")):
            raise ValueError(f"Evidence changed for row {case['number']}")
        if case["candidate_ids"] != [c["source_id"] for c in row["candidates"]]:
            raise ValueError(f"Candidate order changed for row {case['number']}")
        if case["observation"]["observed_checked_ids"] != row["observed_checked_ids"]:
            raise ValueError(f"Original selections changed for row {case['number']}")
        for key in ("candidate_ids", "moe_evidence_ids", "linguipedia_evidence_ids"):
            if any(sid not in report["source_records"] for sid in case[key]):
                raise ValueError(f"Missing full evidence for row {case['number']}")
        if not case["requires_more_evidence"]:
            continue
        spec = QUESTIONS[case["number"]]
        if not set(spec["focus_ids"]).issubset(case["candidate_ids"]):
            raise ValueError(f"Question scope changed for row {case['number']}")
        questions.append({
            "id": f"row-{case['number']}", "number": case["number"],
            "label": f"{case['number']}. {case['term']}",
            "conflict_id": case["conflict_id"], "fingerprint": case["fingerprint"],
            "title": spec["title"], "explanation": spec["explanation"],
            "focus_ids": spec["focus_ids"],
            "options": [
                {"id": "retain-context", "text": spec["retain"]},
                {"id": "hold-mapping", "text": spec["hold"]},
                {"id": "defer", "text": "目前無法決定處理方式，這筆繼續列為待查。"},
            ],
        })
    if {q["number"] for q in questions} != set(QUESTIONS):
        raise ValueError("Update focused questions to match the reassessment's remaining gaps")
    payload = {
        "kind": "localization-tw-human-only-questionnaire", "version": 1,
        "generated_at": now(), "transcription": transcript,
        "reassessment": report, "questions": questions,
        "reference_numbers": [c["number"] for c in cases if not c["requires_more_evidence"]],
    }
    payload["bundle_id"] = digest({k: v for k, v in payload.items() if k != "generated_at"})
    encoded = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    template = (ROOT / "scripts/terminology/human-review-template.html").read_text(encoding="utf-8")
    output = directory / "review-human-only.html"
    atomic_write(output, template.replace("__PAYLOAD__", encoded))
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, default=ROOT / "reports")
    print(build(parser.parse_args().reports))


if __name__ == "__main__":
    main()
