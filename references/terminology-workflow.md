# 詞彙查詢、完整建檔與人工覆核

來源依序為中華語文知識庫、教育部《國語辭典簡編本》、《重編國語辭典修訂本》（g0v 整理），以及 Microsoft 等專業補充資料。教育部辭典以《簡編本》優先、《重編本》補充；先判斷句子的領域與詞義，再查適用的來源，來源順位不會自動裁決衝突。

中華語文知識庫 Copyright © 中華文化總會（National Cultural Association of Taiwan, NCAT）版權所有。

## 翻譯時查詞

在技能安裝目錄執行指令；若目前位於其他專案，請將 scripts 路徑改成此技能的絕對路徑。

```bash
python3 scripts/search.py 伺服器 --mode exact
python3 scripts/search.py process --mode exact --domain 電腦資訊 --json
python3 scripts/search.py 行程 --mode exact --source moe-concised
python3 scripts/search.py 行程 --mode exact --source moe-revised
python3 scripts/search.py 介面 --online --reverse
```

一般搜尋使用本地資料，不會自動下載。尚未建檔時仍可查專案既有詞庫與參考表，但輸出會標示 project-and-legacy-only。第一次完整建檔後，會使用核對過的來源快照；若修改專案詞庫，請離線重建，讓變動進入比對。

- exact：比對完整詞目或已解析的別名；不把釋義中的文字當成精確詞目。
- substring：比對包含查詢文字的詞目與釋義。fuzzy 為相容別名，沒有拼字容錯功能。
- regex：正規表達式；錯誤格式會在查詢前回報一次。
- 英文精確詞目可透過其中文譯詞找到其他來源，但會標示 linked-headword-not-verified-sense。這僅表示詞目關聯，不代表義項相同。
- domain 只篩選來源領域，一般辭典證據仍會顯示。程式不會自行理解整個句子的語意；翻譯者必須判斷適用義項。

讀取結果中的來源、領域、關係類型、完整釋義與覆核狀態。dictionary 類型提供辭典證據，不能直接當成英文術語的定義。大陸欄中的共同用語也不能全部視為禁用詞。

例如「行程」在電腦領域可以對應 process，在旅遊安排或日常活動安排中則有不同意思。依語境保留各義，不要將《簡編本》的旅遊釋義貼到電腦術語上。

## 完整建檔

需要 Python 3.10 以上；只有匯入教育部 XLSX 需要 openpyxl。可使用自己的 Python 虛擬環境安裝：

```bash
python3 -m pip install -r requirements-import.txt
python3 scripts/build-vocabulary.py

# 額外對 server、process、interface、database 各做有上限的 Termic 補查
python3 scripts/build-vocabulary.py --online

# 只用已下載資料重新比對，不連網
python3 scripts/build-vocabulary.py --offline

# 重新取得完整來源；中斷的中華語文知識庫下載會自動接續
python3 scripts/build-vocabulary.py --refresh
```

完整範圍為中華語文知識庫「兩岸差異用詞」全部頁面、《簡編本》指定版本全部文字資料列、g0v 固定提交的《重編本》全部 JSON 詞目，以及 Microsoft Traditional Chinese TBX 中明列 TWN 或 zh-TW 的紀錄。未知地區與其他地區會列入地域檢查報告。固定版本及來源網址定義在 scripts/terminology/network.py；更新版本時須重新查核官方下載頁與欄位格式。

Termic 是第三方網站。線上模式會傳送查詢詞，結果包含資料期間、筆數上限、可能截斷與失敗狀態。補查範圍可用多個 --query 指定，不宣稱已取得完整翻譯記憶庫。

原始下載、使用說明及正規化索引預設儲存在 ~/.cache/localization-tw。可設定 LOCALIZATION_TW_CACHE 或使用 --cache。每次成功建檔會保留獨立版本，只有全部主要來源核對通過才切換目前索引。下載中斷會保留進度，完整快照與既有專案參考表不會被部分資料覆蓋。

《簡編本》保留原始儲存格、注音、多音排序、例句及全部釋義，不自動挑第一義。原始辭典文字與程式的比對、呈現資料分開保存。其公眾授權使用說明保存在 raw/concised-usage.pdf；檔案來源版本也記錄在結果中。

《重編本》使用 g0v/moedict-data 提交 `a6dc997417507eb510fc29822bc514de2c92728c` 的 `dict-revised.json.xz`，共 161,194 個詞目、163,918 組讀音、212,541 個義項。完整保留各讀音的定義、例句、引文、參見及相似／相反詞，並記錄讀音與義項的對應；沒有提供讀音的詞條照實留空。`original` 保存未改寫的 JSON 詞條，輸出欄位另供搜尋與閱讀。

來源版本為 `2015_20260625`：已核對官方 ZIP 的主要工作簿與 g0v 同版 XLSX 的 Git blob 相同。上游 `dict_revised/README.md` 的 20220922 日期已過時，版本依據記錄於快照 `version_evidence`。JSON 檢查碼、預期筆數、g0v 提交、README 與教育部完整使用說明一起保存在 `raw/revised/<commit>/`；`--refresh` 重新核對固定版本，不會追蹤浮動分支。第一次升級需執行一次不含 `--offline` 的建檔，之後可完全離線重建；缺檔或內容驗證失敗時保留舊索引。

《簡編本》有收詞目時也會保留《重編本》的補充義項；字面相同不代表義項相同，兩部辭典的差異也不會直接判為錯誤。與專案技術詞相關的新證據會進入既有義項核對項目，相關舊筆記標示為未套用；沒有變動的人工補答仍沿用。查詢提供原始證據，不自動把一般義、歷史義或較廣的概念當成英文技術詞的定義。

## 人工覆核

建檔後，用瀏覽器直接開啟 reports/review.html。預設先列主要來源／專案用語的候選；Microsoft 內部同一定義的不同譯法可切換範圍查看。所有項目都保留在完整證據檔中。

1. 檢查各來源的詞形、完整釋義、領域與版本。
2. 選擇採用某筆、依語境分義、確認可並用、否決配對，或保留待查。
3. 填寫適用語境、理由與覆核者姓名。
4. 按「匯出已完成決定」，再下載 review-decisions.json。填寫完整的項目可先匯出，未填完的項目會留在草稿，不會擋住整批。接著執行匯入與離線重建：

```bash
python3 scripts/review-conflicts.py /path/to/review-decisions.json
python3 scripts/build-vocabulary.py --offline
```

**無法下載、尚未填完或需要接續覆核時：**

- 按「備份全部草稿」，可將所有分頁的勾選、決定與文字存成 review-drafts.json；不要求理由或覆核者姓名。
- 下載不成功時，可按「複製 JSON」；瀏覽器若不允許直接複製，改按「選取全文」，再以 Ctrl+C（Mac：⌘C）複製。文字框中的 JSON 也可以直接貼到對話中。
- 在「還原草稿備份」開啟備份檔或貼上 JSON，即可繼續填寫。已有不同草稿時保留目前選擇，匯入版本另存於備份中。
- 更新頁面時，會在同一瀏覽器、同一網站或檔案位置嘗試接回舊版草稿；來源證據改變的項目須重新確認。瀏覽器儲存空間不是跨裝置備份，應另存 JSON。
- 「查看待補資料」會列出缺少的欄位，點選詞目可跳到該筆。只勾選候選還不算完整決定，仍須選擇「你的決定」並填寫語境與理由。

草稿備份與正式決定使用不同格式。review-conflicts.py 會拒絕把草稿備份當成已完成的人工覆核，避免將未填寫的理由或尚未確認的選擇自動補成定案。

也可以編輯 reports/conflicts-primary.csv 或 reports/conflicts.csv 後匯入 CSV。action 使用 select、separate_senses、allow_variants、reject_link 或 defer；select 必須在 selected_ids 填寫候選 ID，以分號分隔。scope、rationale、reviewed_by、reviewed_at 都必填，時間須含時區，例如 2026-09-06T23:00:00+08:00。

匯入程式會先驗證整批決定與當次證據，再更新 data/review-decisions.jsonl。未變動的證據可沿用既有決定；相關候選或比對規則改變，就重新開啟覆核。來源快照版本變更但單筆內容未變，不會單因日期不同而重複要求覆核。

人工決定只適用於記錄的語境，搜尋會顯示其範圍。未定案衝突維持 unresolved，不能據此產生確定的偏好用語或全域替換規則。程式產生的建議、頁面草稿與未標示衝突的項目，都不代表人工認可。AI 不得代填覆核者或把自己的推論標記為人工決定。

### 完整釋義複核後的 9 筆補答

本次重新讀取 67 筆候選的完整來源釋義後，剩餘 9 筆列在 `reports/review-human-only.html`；其餘 58 筆放在參考區，不要求重答，也不代填成人工核准。產生頁面時會核對原截圖勾選與證據，保留一對多、多對一及多對多的語境關係。

```bash
python3 scripts/build-human-review.py
python3 scripts/import-human-review.py ~/Downloads/review-human-only-answered.html
```

匯入程式只讀 HTML 內嵌的 JSON，不執行其程式碼；先核對整份題目、選項、來源指紋與回答時間，再將明確補答寫入 `data/source-review-policies.jsonl`。審核者姓名為選填，原檔留白就保留空白。原始答案檔及整理結果另存於 `reports/received-human-review/`，最新結果頁是 `reports/review-human-only-received.html`。

這些決定只針對題目指定的來源關係。「保留並補充語境」仍帶有待核對標記；「暫停配對」只暫停指定來源，不把整個英文詞或中文詞禁用。自行說明的內容保持原文，不自動推定要停用哪條配對；尚未回答的題目不會產生決定。它們也不會把整組衝突改成已解決。

本地查詢會直接載入這份來源處理紀錄，不必重新下載或重建索引。預設略過暫停來源；需要查閱原始資料時可加 `--include-held`：

```bash
python3 scripts/search.py code --mode exact
python3 scripts/search.py code --mode exact --include-held --json
```

來源證據改變時，舊補答會顯示為未套用，不能自動延用到新的義項。未被問到的其他 58 筆、原始 52 筆勾選以及正式整組決定各自保留，不互相推定。

`python3 scripts/build-vocabulary.py --offline` 會同步產生新版全量報告。摘要中的 `scoped_source_review` 統計已收錄／仍適用／證據過期的補答、指定來源暫停與待核對範圍；`assistant_sense_review` 統計複核筆記，`human_review` 則維持原本的整組決定統計。因此 9 筆補答完成，不等於有 9 組詞義全部定案。

複核筆記另存 `data/sense-review-notes.json`，只包含判讀、候選識別與證據指紋，不收錄完整外部辭典。來源處理紀錄與筆記都納入建檔版本識別，並保存於每次建檔快照；單獨變更答案也會產生新版本，不會沿用舊報告。可用 `--source-policies` 與 `--sense-review` 指定其他檔案。

新版 `review.html` 預設顯示仍需判斷的項目。接回《重編本》後，23 筆舊筆記及 4 筆新項目已讀完完整釋義並更新 AI 參考；主要範圍中 9 筆可切換到「已補答／已有決定」查閱，62 筆位於「複核參考，不用重答」。原人工答案未改寫，原 67 筆補答頁及收件紀錄仍保留為當時的快照。只有證據改變或新增而尚未釐清的問題才會回到待判斷區；AI 參考不代表人工核准，原始來源與尚待核對的標示都會保留。

### 10,770 筆術語並列的分流

`glossary_variants` 是同一英文詞與定義下出現多種臺灣譯法的補充候選，多數只是縮寫、產品全名、範圍長短或異體字並列，不是需要逐筆裁決的衝突。可用下列指令分流；結果只是 AI 評估，不會寫入人工決定，也不會挑出偏好用語：

```bash
python3 scripts/triage-glossary-variants.py
```

輸出 `reports/glossary-triage.json` 與 `reports/glossary-triage.csv`。只有「形式含大陸或港式用語，且同組沒有逐字對應的臺灣形式」（`regional-usage-check`）標為需要人看；與專案詞條共用英文詞但已有主要複核題的（`covered-by-primary-review`），以及其他類別，都視為參考。分流規則見 `scripts/terminology/triage.py`。

標為需要人看的項目，可依相同定義合併成一頁簡短問卷，回答只存在你下載的 JSON，匯入前不會改動任何詞表：

```bash
python3 scripts/build-glossary-review.py
```

輸出 `reports/glossary-regional-review.html`。答案 JSON 保留每個題目的來源指紋，證據改變時可辨識為過期。

下載答案後匯入。每個答案會依來源指紋轉成只針對指定來源的處理紀錄，寫入 `data/source-review-policies.jsonl`；「不採用」會暫停紅底形式對應的來源，「待查」不暫停任何來源，兩者都不會把整組衝突標為已解決：

```bash
python3 scripts/import-glossary-review.py ~/Downloads/glossary-regional-review-answered.json
```

匯入前會驗證整份答案，證據已改變、題目不存在或選項不合法就整批拒絕。原檔與轉換結果另存於 `reports/received-human-review/`。暫停的來源預設不會出現在 `search.py` 結果，加上 `--include-held` 可查閱。

### 舊版：從截圖接續的 16 題補答

本次 67 筆截圖已整理為 `reports/screenshot-review.json`，待補問題保存在 `reports/chat-review-questions.json`。兩者及原始 `conflict-evidence.jsonl` 都存在時，可產生獨立補答頁：

```bash
python3 scripts/build-review-followup.py
```

用瀏覽器開啟 `reports/review-followup.html`。頁面已帶入截圖中能辨識的 52 筆勾選，只需補答 15 筆及 1 題共同處理原則。每題附完整說明與來源釋義；建議不會預先當成答案。既有勾選可展開更正，原始截圖紀錄仍另行保留。

按「儲存含答案的 HTML」可將當前答案直接寫入下載的 HTML，換瀏覽器或裝置仍可接續；也可下載、複製或重新載入 JSON。頁面不要求重新輸入 52 筆讀不清楚的理由。這份補答檔保存處理原則、人工補充與原始勾選，後續用來整理具體義項；它不是 `review-conflicts.py` 的正式決定格式，不能將待查或尚未回答項目直接匯入為已核可資料。

補答頁的存檔、接續與勾選保留可用 `node tests/review-followup-ui.cjs` 檢查，Playwright 與 Chromium 設定方式同下方測試。

## 產出與檢查

| 檔案 | 內容 |
| --- | --- |
| reports/full-run-summary.json | 每個來源的版本、實際筆數、完整性、覆蓋率與覆核統計 |
| reports/review.html | 離線覆核頁面，可篩選與匯出決定 |
| reports/conflicts-primary.csv | 主要來源／專案用語的待查項目 |
| reports/conflicts.csv | 全部待查候選，包含補充來源內部變體 |
| reports/conflict-evidence.jsonl | 每筆候選的完整來源證據及覆核狀態 |
| reports/unflagged-sample.jsonl | 按來源與領域抽出的未標示衝突樣本，供人工抽查 |
| reports/microsoft-region-audit.json | 排除或地區不明的 Microsoft 紀錄 |
| reports/termic-supplements.json | 有範圍的線上補查結果與錯誤 |
| reports/candidate-vocabulary.jsonl | 專案與兩岸詞彙的草稿狀態；不是已核可替換清單 |

來源缺詞、明確不同義項與跨來源的詞形差異不一定是衝突。比對使用可重現的詞目與欄位規則來找疑點，無法保證偵測所有語意問題。人工需抽查未標示衝突的資料，並用實際句子驗證。

```bash
python3 -m unittest discover -s tests -v
```

匯出與草稿接續另有 `node tests/review-ui.cjs` 瀏覽器回歸測試，需要可用的 Playwright 與 Chromium。可透過 PLAYWRIGHT_MODULE 與 CHROMIUM_EXECUTABLE 指定既有安裝。測試只使用臨時產生的候選與瀏覽器設定檔，不會匯入實際人工決定。

原始資料與產生的 reports 保留在本機，未列入 Git；人工決定可獨立追蹤。程式的 MIT 授權不涵蓋外部詞庫內容，散布資料時須另外確認各來源的條款與標示要求。

本功能延續 voidful 的 [PR #1](https://github.com/Qmo37/localization-tw/pull/1) 提案；Termic 查詢格式參考該 PR 與 [Termic 原始碼](https://github.com/spidersouris/termic)。教育部辭典以[《國語辭典簡編本》](https://dict.concised.moe.edu.tw/)優先，並接回原 PR 使用的 [g0v《重編本》資料](https://github.com/g0v/moedict-data)作完整義項補充。
