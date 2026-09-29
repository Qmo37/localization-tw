**PR #1 與目前本地實作的差異**

比較日期：2026-09-29。原版固定為 voidful 的 [PR #1](https://github.com/Qmo37/localization-tw/pull/1)，提交 `ee782a186ddf0dae8cbf43e8eb027410148a3095`；本地版本為 `feat/source-aware-terminology` 尚未提交的工作目錄，最新建檔版本見 `reports/full-run-summary.json`。已依後續要求接回 g0v《重編本》，《簡編本》仍是教育部辭典內的優先來源；推送及合併尚未進行。

原 PR 帶來了這次工作的主要功能方向：Microsoft 術語與翻譯記憶庫查詢、教育部辭典補充、跨來源查詢，以及兩岸詞彙擴充。它也已有反向／批次查詢、詞性與產品脈絡、JSON／Markdown 輸出、抓取中斷後保留結果等實用功能。這些貢獻應在後續整合中持續標示。[原提案說明](https://github.com/Qmo37/localization-tw/pull/1)

我們後續加入的工作，主要來自使用者明確指定的來源順序、《簡編本》、全量執行、多對多語意關係與人工覆核流程。變更包含需求選擇、功能擴充、個別程式行為修正，也有命令列相容性的取捨。尚未做兩個版本的翻譯品質基準評測，因此不能由資料量或測試數推論哪個版本的翻譯一定較正確。

| 比較面向 | 原 PR 已有的能力 | 目前本地版本 | 差異性質與代價 |
| --- | --- | --- | --- |
| Microsoft 查詢 | 透過 Termic 查詢術語及翻譯記憶庫；有正反向、批次、詞性與產品資訊。 | 延續 Termic，另加入官方 TBX 的本地完整匯入與臺灣地域篩選；保留查詢上限、資料期間及失敗狀態。 | 功能擴充；首次建檔及維護成本增加。 |
| 教育部來源 | 使用 g0v 整理的《重編國語辭典修訂本》。 | 官方《簡編本》XLSX 優先，g0v 固定版本《重編本》JSON 補充；兩者各自保留。 | 保留原提案的資料來源並擴充順位與版本驗證；兩部辭典不能視為完全互換。 |
| 多義查詢 | `lookup_entry()` 會保留各讀音及其多筆釋義。終端顯示最多四個義項及各一個例句。 | 保留兩部辭典完整詞條、多音與全部釋義；《重編本》例句、引文、參見依義項顯示，一般義與技術來源分筆呈現。 | 呈現與來源保存方式不同；原 PR 並非完全不支援多義。 |
| 加強版詞表 | 從第一個讀音取首個非空釋義，生成便於閱讀的 Markdown；核心與日常釋義分別截至約 50／60 字。 | 不將詞目相同視為已確認義項；保留完整證據，字面關聯標示為待判讀。 | 生成詞表的語意與資訊完整性調整；原版精簡表格有直接閱讀的便利。 |
| 多對多關係 | 同一詞可有多筆查詢結果，原始詞表也含斜線分隔的替代詞。 | 明確分開候選詞形、來源定義與人工處理範圍，允許候選並存、分義及部分重疊。 | 增加對應關係的管理。兩版都沒有自動理解整句、完成所有義項對齊的能力。 |
| 中華語文知識庫 | 抓取程式已能遍歷全部頁面；PR 實際隨附 1,400 筆 Markdown 快照。 | 本次完整核對 241 頁、4,814 筆，另檢查總數、ID、檢查碼與完整性。 | 增加完整性驗證。1,400 筆是原版隨附快照的大小，不是程式的抓取上限。 |
| 離線使用 | 專案隨附擴充詞表，取得專案後即可查閱這些資料。 | 大型來源快照與報告留在本機，完整索引需先建檔；未建檔時仍可查專案與既有參考表。 | 原版初次使用較直接；新版完整建檔需 openpyxl、下載時間與儲存空間。 |
| 來源順位 | 依搜尋分數排列，整合專案詞表、知識庫與辭典結果。 | 依使用者規則標示知識庫、《簡編本》、《重編本》、專業補充來源順序；同等相關程度下依順位排序，適用義項仍由讀者判斷。 | 需求選擇。來源排序本身不等於語意判定。 |
| 人工覆核 | 此次 PR 內容沒有人工決定匯入及更新後沿用的流程。 | HTML／CSV／可攜式補答頁；9 筆來源處理決定、3 條暫停配對、62 筆非人工核准的複核參考各自保存。 | 新增維護流程，操作與資料結構較複雜。 |
| 更新與接續 | 已有部分儲存、指定起始頁與快取合併。 | 自動接續檢查點，完整驗證後才切換索引；把資料、答案、筆記與程式內容納入版本識別，證據改變則停用舊判讀。 | 延伸既有接續能力；需要維護更多版本與狀態。 |
| 驗證 | PR 說明列有作者完成的手動檢查項目；此 PR 沒有新增自動測試檔。 | 46 項離線測試、瀏覽器流程測試，以及 266,775 筆現有快照的離線整合驗證。 | 增加可重跑的檢查；不代表原作者沒有自行測試，也不等於全庫詞義已核准。 |

原版依據：[Microsoft 查詢腳本](https://github.com/voidful/localization-tw/blob/ee782a186ddf0dae8cbf43e8eb027410148a3095/scripts/fetch-microsoft-terms.py)、[辭典查詢與詞表產生](https://github.com/voidful/localization-tw/blob/ee782a186ddf0dae8cbf43e8eb027410148a3095/scripts/enrich-from-moedict.py)、[統一查詢](https://github.com/voidful/localization-tw/blob/ee782a186ddf0dae8cbf43e8eb027410148a3095/scripts/search.py)、[知識庫抓取](https://github.com/voidful/localization-tw/blob/ee782a186ddf0dae8cbf43e8eb027410148a3095/scripts/fetch-linguipedia.py)。本地依據：[來源匯入](scripts/terminology/sources.py)、[查詢](scripts/terminology/searching.py)、[完整建檔](scripts/build-vocabulary.py)、[覆核狀態整合](scripts/terminology/review_state.py)。

**需要更精確說明的義項差異**

原版詞表把 audio、「音訊」及消息義放在同一列；process、「行程」及路程義也放在同一列。[原版詞表](https://github.com/voidful/localization-tw/blob/ee782a186ddf0dae8cbf43e8eb027410148a3095/references/vocabulary-enriched.md#L15)

這些辭典釋義本身可以成立，譯詞也不因此失效。讀者若把該列的辭典欄當成英文技術術語的定義，就可能誤讀。新版的處理是維持這些義項並存，讓字面查詢關聯與已確認的語意關係分開；不否定一般用法，也不設定英文、臺灣用語及中國大陸用語只能一對一。

本次用小型測試資料再次核對：原版 `lookup_entry()` 確實保留了兩個讀音、三個義項；同份資料經核心詞表產生流程時，只輸出第一個義項。因此，應把這項差異描述為「精簡詞表的義項選取與連結方式」，不應概括成原版不支援多義。[原版多義查詢](https://github.com/voidful/localization-tw/blob/ee782a186ddf0dae8cbf43e8eb027410148a3095/scripts/enrich-from-moedict.py#L78)、[詞表產生](https://github.com/voidful/localization-tw/blob/ee782a186ddf0dae8cbf43e8eb027410148a3095/scripts/enrich-from-moedict.py#L248)

**可具體重現的程式修正**

| 情境 | 原版行為 | 本地處理 |
| --- | --- | --- |
| 連續的 `###` 分類表格 | 表格解析只在 `##` 重設表頭；對原版加強詞表載入時，會多出一筆名為「臺灣用語」的結果。 | 每張表獨立辨識表頭，保留各層標題並檢查欄數。 |
| 無效的正規表示式 | 在逐筆比對時重複輸出錯誤並回傳不符合；本次兩筆測試資料輸出兩次錯誤。 | 查詢前檢查一次，失敗回報非零結束碼。 |
| 同詞形但來源 ID 或類型不同的快取資料 | 合併鍵只有臺灣詞與大陸詞，可能把不同來源紀錄合併。 | 優先保留來源 ID；舊格式的備援鍵另含分類與關係，同 ID 內容衝突時要求處理。 |

以上修正只描述可定位的程式路徑與輸入條件。原版對一般查詞、辭典閱讀與術語蒐集仍有實用價值。原版程式依據：[表格與搜尋](https://github.com/voidful/localization-tw/blob/ee782a186ddf0dae8cbf43e8eb027410148a3095/scripts/search.py#L29)、[快取合併](https://github.com/voidful/localization-tw/blob/ee782a186ddf0dae8cbf43e8eb027410148a3095/scripts/fetch-linguipedia.py#L114)。小型核對紀錄存於本機 `reports/pr-comparison/behavior-checks.json`。

**新版尚未維持的相容性**

| 介面 | 原 PR | 本地版本與影響 |
| --- | --- | --- |
| `fetch-microsoft-terms.py --output` | 輸出 Markdown。 | 改為 JSON；依賴舊表格格式的流程需調整，Markdown 匯出尚未接回。 |
| Termic 筆數上限 | `--limit-gl`、`--limit-tm` 可分別設定，預設各 25 筆。 | 統一為 `--limit`，預設每來源 10 筆；尚未保留兩個獨立上限參數。 |
| Microsoft 查詢預設模式 | `fuzzy`，實際使用包含比對。 | 預設 `exact`；仍提供 `fuzzy` 作包含比對的相容名稱，兩者都不是拼字容錯搜尋。 |
| 知識庫接續 | 可指定 `--start-page`。 | 改用自動接續檢查點，未保留這個參數。 |
| `search.py --json` | 結果陣列，主要詞形為字串。 | 含查詢、覆蓋範圍、處理狀態與結果的物件，詞形以陣列保存；舊 JSON 消費端需調整。 |
| 辭典查詢／詞表產生指令 | `enrich-from-moedict.py --lookup`、`--generate`。 | 改由 `search.py` 與 `build-vocabulary.py` 承擔查詢、建檔；沒有提供相同指令的相容包裝。 |

因此，目前應稱為延續原提案、依專案需求完成的後續整合，不能稱為完全相容的直接替換。合併前應在 PR 說明列出上述命令列變更；若既有使用者依賴原格式，可將相容輸出與參數別名作為後續小幅修正。

《重編本》已接回，使用 `search.py <中文詞目> --source moe-revised` 查詢，原 `enrich-from-moedict.py` 介面仍未提供相容包裝。建議與作者討論精簡 Markdown 匯出及舊參數相容性，這些是原版有實用價值的介面。我們增加的全量來源與人工覆核流程可另作擴充能力說明，並持續保留 voidful、原 PR、g0v 與 Termic 的貢獻連結。這份文件尚未發送或張貼到 GitHub。
