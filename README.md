# localization-tw — 正體中文（臺灣）在地化技能

> 正體中文（Traditional Chinese），又稱繁體中文，為臺灣官方使用的標準漢字書寫形式。本技能以「正體中文」為正式名稱，並以臺灣華語慣用方式為規範。

Claude Code 的在地化翻譯技能，確保 AI 產出的中文內容符合臺灣華語母語者的用詞習慣，避免中國用語與簡體直譯。

> **開發進度**：依語境查詞、完整匯入教育部辭典與 Microsoft 術語、人工覆核等功能正在 [PR #2](https://github.com/Qmo37/localization-tw/pull/2) 進行，延續 voidful 的 [PR #1](https://github.com/Qmo37/localization-tw/pull/1) 提案。兩者尚未合併，本頁描述的是目前 `main` 的內容。

## 功能

- **EN↔zh-TW 雙向翻譯**，也支援 EN↔JA↔zh-TW 三語翻譯
- **用詞規範**：內建臺灣 vs. 中國用語對照表（40+ 高頻詞彙速查）
- **領域污染檢查**：按電腦資訊、日常生活、娛樂、政經、交通等領域，主動檢查中國用語殘留
- **來源順序**：[中華語文知識庫](https://www.chinese-linguipedia.org/search_difference.html) 優先；教育部辭典以《簡編本》優先、《重編本》補充，Microsoft 術語等補充專業語境
- **完整建檔與搜尋**：取得兩岸差異用詞、《簡編本》文字資料、g0v 固定版本《重編本》及臺灣適用 Microsoft 術語，核對筆數後建立本地索引
- **人工覆核**：產生可篩選的離線覆核頁面、CSV 與完整證據；保留不同義項，衝突由人工決定
- **完整翻譯工作流程**：理解→翻譯→校對→潤飾四步驟，附品質檢查清單
- **語言參考文件**：正體中文、英文、日文各自的語言特性與翻譯策略

## 安裝

將此資料夾放入 Claude Code 的 skills 目錄即可：

```bash
# 方法一：直接 clone
git clone https://github.com/Qmo37/localization-tw.git ~/.claude/skills/localization-tw

# 方法二：手動下載後放入
cp -r localization-tw ~/.claude/skills/
```

## 使用方式

安裝後，Claude Code 在處理中文相關任務時會自動套用此技能。你可以：

- 翻譯英文文件為臺灣中文
- 產生符合臺灣用語的 UI 文字、註解、文件
- 檢查既有中文內容是否有中國用語殘留

### 範例

```
❌ 請您通過以下鏈接獲取軟件的默認配置信息
✅ 請透過以下連結取得軟體的預設設定資訊

❌ 服務器返回的數據需要進行一個解析的操作
✅ 伺服器回傳的資料需要解析
```

## 查詞與完整建檔

一般查詞不需安裝額外套件；完整建檔需要 Python 3.10 以上與 openpyxl：

```bash
python3 -m pip install -r requirements-import.txt
python3 scripts/build-vocabulary.py --online
python3 scripts/search.py process --mode exact --domain 電腦資訊 --json
python3 scripts/search.py 行程 --mode exact --source moe-concised
python3 scripts/search.py 行程 --mode exact --source moe-revised
```

開啟 `reports/review.html` 即可人工覆核。`--online` 對四個預定技術詞做有上限的 Termic 補查；省略時只匯入主要來源。全量紀錄、實際筆數與查詢狀態見 `reports/full-run-summary.json`，不把有上限的查詢結果宣稱為完整翻譯記憶庫。

覆核者填寫語境與理由後，按「匯出已完成決定」取得 JSON，再匯入決定並離線重建。未填完也可用「備份全部草稿」保留所有分頁的選擇；下載失敗時可直接複製頁面上的 JSON：

```bash
python3 scripts/review-conflicts.py /path/to/review-decisions.json
python3 scripts/build-vocabulary.py --offline
python3 -m unittest discover -s tests -v
```

未覆核衝突不會成為確定的推薦用語。後續更新使用 `--refresh`；原始資料與索引預設位於 `~/.cache/localization-tw`，可用 `LOCALIZATION_TW_CACHE` 或 `--cache` 指定位置。生成的 `reports/` 保留在本機，人工決定另存 `data/review-decisions.jsonl`。

指定來源的補答另存於 `data/source-review-policies.jsonl`；查詢預設略過暫停配對，可用 `--include-held` 查閱原始資料。離線重建會把補答、停用範圍及 `data/sense-review-notes.json` 的複核參考同步到 HTML、CSV 與摘要，並將這些輸入納入版本識別。審核頁可切換仍需判斷、已補答與複核參考；複核筆記不代表人工核准，來源內容改變時會重新列入待判斷。

Microsoft 術語庫的 10,770 筆並列譯法可先分流：`python3 scripts/triage-glossary-variants.py` 把縮寫、產品名、範圍長短與異體字的差異列為參考，只把含大陸或港式用語的少數項目交給人看。`build-glossary-review.py` 產生簡短問卷，`import-glossary-review.py` 匯入答案為指定來源的處理紀錄。分流是 AI 評估，不代表人工核准。

完整流程、資料範圍與搜尋限制見 [詞彙工作流程](references/terminology-workflow.md)。

## 兩岸詞彙資料庫

內建抓取腳本可從中華語文知識庫取得完整兩岸差異用詞：

```bash
# 抓取全部 ~4,800 筆詞彙
python3 scripts/fetch-linguipedia.py

# 僅抓取「同實異名」類型（同一事物，兩岸用詞不同）
python3 scripts/fetch-linguipedia.py --type 同實異名

# 先看統計資料，不寫入檔案
python3 scripts/fetch-linguipedia.py --dry-run

# 儲存原始 JSON 以便離線使用
python3 scripts/fetch-linguipedia.py --save-cache cache.json
python3 scripts/fetch-linguipedia.py --from-cache cache.json
```

抓取後的 Markdown 預設存入 `~/.cache/localization-tw/linguipedia-cross-strait.md`，可用 `--output` 另存。既有 `references/linguipedia-cross-strait.md` 保留為原有參考表，不代表完整來源。下載中斷會保存頁面進度，重新執行即可接續；`--merge-cache` 可合併舊快取，但不宣稱已驗證來源完整性。翻譯時使用 `search.py` 查詞即可。

## 檔案結構

```
localization-tw/
├── SKILL.md                          # 主技能定義（工作流程、速查表、品質清單）
├── references/
│   ├── vocabulary.md                 # 臺灣用語對照表（名詞、動詞、句式、標點）
│   ├── linguipedia-cross-strait.md   # 既有參考表，保留來源脈絡
│   ├── terminology-workflow.md      # 建檔、搜尋與人工覆核操作
│   ├── chinese-traditional.md        # 正體中文語言特性
│   ├── english.md                    # 英文語言特性
│   └── japanese.md                   # 日文語言特性
├── translation-challenges.md         # 常見翻譯挑戰範例與解法
├── tools-resources.md                # 辭典、語料庫、工具彙整
├── scripts/
│   ├── build-vocabulary.py           # 完整建檔、比對與報告
│   ├── search.py                     # 本地搜尋與選用線上補查
│   ├── review-conflicts.py           # 驗證並匯入人工決定
│   ├── build-human-review.py         # 產生剩餘人工審核的補答頁
│   ├── import-human-review.py        # 匯入補答為指定來源的處理紀錄
│   ├── build-review-followup.py      # 從截圖覆核產生接續補答頁
│   ├── triage-glossary-variants.py   # 分流 Microsoft 術語並列譯法
│   ├── build-glossary-review.py      # 產生大陸或港式用語確認問卷
│   ├── import-glossary-review.py     # 匯入問卷答案
│   ├── fetch-linguipedia.py          # 可接續的中華語文知識庫下載
│   ├── fetch-microsoft-terms.py      # Termic 查詢與批次輸出
│   └── terminology/                 # 來源解析與覆核邏輯
├── requirements-import.txt           # 匯入 XLSX 所需套件
└── tests/                            # 離線行為測試
```

## 領域污染嚴重程度

技能會根據翻譯內容涉及的領域，主動提醒檢查高風險詞彙。以下例子須配合語境，不能用來做全域替換；同字多義與兩岸共同用語應分別判斷：

| 領域 | 污染程度 | 常見錯誤 → 正確用法 |
| --- | --- | --- |
| 電腦資訊 | 🔴 嚴重 | 數據→資料、代碼→程式碼、優化→最佳化、接口→介面 |
| 日常生活／食物 | 🔴 嚴重 | 西紅柿→番茄、土豆→馬鈴薯、信息→資訊、視頻→影片 |
| 娛樂／遊戲 | 🟠 中高 | 主播→實況主、點擊→點選、下載安裝→下載並安裝 |
| 政經社會 | 🟡 中等 | 數字經濟→數位經濟、互聯網→網際網路 |
| 交通運輸 | 🟡 中等 | 出租車→計程車、地鐵→捷運、公交車→公車 |

## 致謝

完整查詞與覆核功能延續 [voidful 的 PR #1](https://github.com/Qmo37/localization-tw/pull/1) 提案；Termic 請求格式參考該貢獻。教育部以《簡編本》優先，接回原提案的 [g0v《重編本》資料](https://github.com/g0v/moedict-data)作完整義項補充，並加入 Microsoft 官方 TBX 匯入與人工覆核。

本技能基於以下兩個開源技能合併、修改而成：

- **[translation-expertise](https://agentskills.so/zh/skills/shino369-claude-code-personal-workspace-translation-expertise)** by [shino369](https://github.com/shino369/claude-code-personal-workspace) — 英日中（正體）三語翻譯方法論與最佳實踐
- **[taiwan-traditional-chinese-localization](https://mcpmarket.com/zh/tools/skills/taiwan-traditional-chinese-localization)** — 臺灣正體中文在地化規範

兩岸差異用詞資料來源：[中華語文知識庫](https://www.chinese-linguipedia.org/)
Copyright &copy; [中華文化總會](https://www.gacc.org.tw/)（National Cultural Association of Taiwan, NCAT）版權所有。本技能引用其公開資料僅供學術與翻譯參考用途。

## 授權

本技能程式碼以 MIT License 釋出。

兩岸詞彙資料庫內容之著作權屬中華文化總會所有，使用時請遵守其授權條款。

教育部《國語辭典簡編本》與《重編國語辭典修訂本》本文採 CC BY-ND 3.0 TW，使用時須保留原始內容、版本與使用說明；g0v 的格式整理與辭典本文分別標示。Microsoft 資料與 Termic 程式的授權不同；本專案程式的 MIT 授權不涵蓋外部詞庫。下載資料與生成報告保留在本機，散布前另行確認各來源條款。

---

<details>
<summary><strong>🌐 English Version</strong></summary>

# localization-tw — Standard/Traditional Chinese (Taiwan) Localization Skill

> In Taiwan, the official writing system is called 正體中文 (Standard Chinese / Orthodox Chinese), commonly referred to internationally as Traditional Chinese (繁體中文). This skill uses "Standard Chinese" as the formal name.

A Claude Code skill for localization and translation, ensuring AI-generated Chinese content follows Taiwanese Mandarin conventions and avoids mainland Chinese (CN) terms.

> **Work in progress**: source-aware lookup, full imports of the MOE dictionaries and Microsoft terminology, and human review are being developed in [PR #2](https://github.com/Qmo37/localization-tw/pull/2), continuing voidful's proposal in [PR #1](https://github.com/Qmo37/localization-tw/pull/1). Neither is merged yet; this page describes what is currently on `main`.

## Features

- **EN↔zh-TW bidirectional translation**, with EN↔JA↔zh-TW trilingual support
- **Terminology standards**: Built-in Taiwan vs. China vocabulary reference (40+ high-frequency terms)
- **Domain-aware pollution checking**: Actively flags CN term contamination across IT, daily life, entertainment, politics, transportation domains
- **Source order**: [Chinese Linguipedia](https://www.chinese-linguipedia.org/search_difference.html) first; within MOE dictionaries, Concised precedes Revised; Microsoft terminology supplements technical context
- **Complete local indexing**: Reconcile source counts and import the cross-strait database, Concised text data, a pinned g0v Revised snapshot, and Taiwan-applicable Microsoft TBX records
- **Human review**: Offline review page, CSV, and complete evidence; preserve senses and human decisions separately
- **Complete translation workflow**: Understand → Translate → Proofread → Polish, with a quality checklist
- **Language reference files**: Linguistic characteristics and translation strategies for Traditional Chinese, English, and Japanese

## Installation

Place this folder in your Claude Code skills directory:

```bash
# Option 1: Clone directly
git clone https://github.com/Qmo37/localization-tw.git ~/.claude/skills/localization-tw

# Option 2: Copy manually
cp -r localization-tw ~/.claude/skills/
```

## Usage

Once installed, Claude Code automatically applies this skill when handling Chinese-related tasks. You can:

- Translate English documents into Taiwanese Chinese
- Generate UI text, comments, and documentation in Taiwan conventions
- Check existing Chinese content for mainland Chinese term contamination

### Examples

```
❌ 請您通過以下鏈接獲取軟件的默認配置信息
   (CN: uses mainland terms like 通過, 鏈接, 軟件, 默認, 信息)

✅ 請透過以下連結取得軟體的預設設定資訊
   (TW: uses 透過, 連結, 軟體, 預設, 資訊)

❌ 服務器返回的數據需要進行一個解析的操作
   (CN: 服務器, 數據, verbose phrasing)

✅ 伺服器回傳的資料需要解析
   (TW: 伺服器, 資料, concise phrasing)
```

## Search, Full Import, and Human Review

Local search uses Python's standard library. Full import requires Python 3.10+ and openpyxl:

```bash
python3 -m pip install -r requirements-import.txt
python3 scripts/build-vocabulary.py --online
python3 scripts/search.py process --mode exact --domain 電腦資訊 --json
python3 scripts/search.py 行程 --mode exact --source moe-concised
python3 scripts/search.py 行程 --mode exact --source moe-revised
```

Open `reports/review.html`, review the candidates in context, and export human decisions. The default view prioritizes project/primary-source issues; Microsoft-internal variants remain available under a separate filter. Import decisions and rebuild offline:

Completed decisions can be exported while incomplete items remain drafts. Use the draft backup button to save selections across all pages even before entering a rationale. If a download fails, copy the visible JSON instead. Draft backups can be restored in the page and cannot be imported as final human decisions.

```bash
python3 scripts/review-conflicts.py /path/to/review-decisions.json
python3 scripts/build-vocabulary.py --offline
python3 -m unittest discover -s tests -v
```

`--online` adds bounded Termic queries for four technical terms; it is not a full translation-memory export. Unresolved candidates never become definitive preferences. Read actual counts and source versions from `reports/full-run-summary.json`. Raw data and indexes default to `~/.cache/localization-tw` (override with `LOCALIZATION_TW_CACHE` or `--cache`); generated reports stay local. Human decisions live separately in `data/review-decisions.jsonl`.

Use `--refresh` to acquire new snapshots. Matching headwords do not establish matching senses, and the CLI does not infer sentence meaning. See the [workflow reference](references/terminology-workflow.md) for scope, semantics, and review fields.

Scoped source answers live in `data/source-review-policies.jsonl`. Search excludes held mappings unless `--include-held` is set. Offline builds include these policies and the assistant notes in `data/sense-review-notes.json` in their version identity and publish both in HTML, CSV, and the summary. The review page separates open questions, received answers, and reference notes. Notes do not imply human approval; changed evidence makes earlier annotations inactive and reopens the affected items.

The 10,770 Microsoft glossary variants can be triaged with `python3 scripts/triage-glossary-variants.py`. Differences that are only abbreviations, product names, scope or spelling are marked reference-only; the few groups with mainland or Hong Kong-style forms go to a person through `build-glossary-review.py`, and `import-glossary-review.py` records the answers as source-scoped policies. Triage is an assistant assessment, not human approval.

## Cross-Strait Vocabulary Database

A built-in script fetches the complete cross-strait terminology database from Chinese Linguipedia:

```bash
# Fetch all ~4,800 entries
python3 scripts/fetch-linguipedia.py

# Fetch only "same thing, different name" entries
python3 scripts/fetch-linguipedia.py --type 同實異名

# Preview stats without writing
python3 scripts/fetch-linguipedia.py --dry-run

# Save/load raw JSON for offline use
python3 scripts/fetch-linguipedia.py --save-cache cache.json
python3 scripts/fetch-linguipedia.py --from-cache cache.json
```

Markdown output defaults to `~/.cache/localization-tw/linguipedia-cross-strait.md`; use `--output` to choose another path. The existing repository reference remains a historical subset. Failed retrieval resumes from saved pages. `--merge-cache` preserves source IDs and distinctions but does not certify source completeness. Use `search.py` for ordinary lookups.

## File Structure

```
localization-tw/
├── SKILL.md                          # Main skill definition (workflow, quick ref, checklist)
├── references/
│   ├── vocabulary.md                 # TW vs CN vocabulary table (nouns, verbs, grammar, punctuation)
│   ├── linguipedia-cross-strait.md   # Preserved historical reference
│   ├── terminology-workflow.md      # Import, search, and human review
│   ├── chinese-traditional.md        # Traditional Chinese linguistic reference
│   ├── english.md                    # English linguistic reference
│   └── japanese.md                   # Japanese linguistic reference
├── translation-challenges.md         # Common translation challenges with examples
├── tools-resources.md                # Dictionaries, corpora, and tool references
├── scripts/
│   ├── build-vocabulary.py           # Full import, comparison, and reports
│   ├── search.py                     # Local and optional online lookup
│   ├── review-conflicts.py           # Import human decisions
│   ├── build-human-review.py         # Build the remaining-questions page
│   ├── import-human-review.py        # Import answers as source-scoped policies
│   ├── build-review-followup.py      # Build the follow-up page from screenshot review
│   ├── triage-glossary-variants.py   # Triage Microsoft glossary variants
│   ├── build-glossary-review.py      # Build the regional-usage questionnaire
│   ├── import-glossary-review.py     # Import questionnaire answers
│   ├── fetch-linguipedia.py          # Resumable source download
│   ├── fetch-microsoft-terms.py      # Termic single/batch lookup
│   └── terminology/                 # Source and review implementation
├── requirements-import.txt           # XLSX import dependency
└── tests/                            # Offline behavioral checks
```

## Domain Pollution Severity

The skill checks terminology in context. These examples are not global replacement rules; distinguish shared regional terms and different senses:

| Domain | Severity | Common Mistakes → Correct TW |
| --- | --- | --- |
| IT / Computing | 🔴 Critical | 數據→資料, 代碼→程式碼, 優化→最佳化, 接口→介面 |
| Daily Life / Food | 🔴 Critical | 西紅柿→番茄, 土豆→馬鈴薯, 信息→資訊, 視頻→影片 |
| Entertainment / Gaming | 🟠 High | 主播→實況主, 點擊→點選, 下載安裝→下載並安裝 |
| Politics / Society | 🟡 Moderate | 數字經濟→數位經濟, 互聯網→網際網路 |
| Transportation | 🟡 Moderate | 出租車→計程車, 地鐵→捷運, 公交車→公車 |

## Credits

The lookup work builds on [voidful's PR #1](https://github.com/Qmo37/localization-tw/pull/1), including its Termic request format. Concised remains the preferred MOE dictionary; the original proposal's [g0v Revised data](https://github.com/g0v/moedict-data) is integrated as supplementary sense evidence, alongside official Microsoft TBX import and human review.

This skill was created by combining and extending two open-source skills:

- **[translation-expertise](https://agentskills.so/zh/skills/shino369-claude-code-personal-workspace-translation-expertise)** by [shino369](https://github.com/shino369/claude-code-personal-workspace) — Expert EN-JA-ZH (Standard/Traditional) trilingual translation methodology and best practices
- **[taiwan-traditional-chinese-localization](https://mcpmarket.com/zh/tools/skills/taiwan-traditional-chinese-localization)** — Taiwan Standard Chinese localization standards

Cross-strait vocabulary data source: [Chinese Linguipedia (中華語文知識庫)](https://www.chinese-linguipedia.org/)
Copyright &copy; [National Cultural Association of Taiwan (中華文化總會, NCAT)](https://www.gacc.org.tw/). Data referenced for academic and translation purposes only.

## License

This skill's code is released under the MIT License.

The cross-strait vocabulary database content is copyrighted by the National Cultural Association of Taiwan (NCAT). Please comply with their terms of use.

MOE Concised and Revised dictionary text is CC BY-ND 3.0 TW: preserve source content, version attribution, and usage instructions; credit g0v's format conversion separately. Microsoft's data terms are separate from Termic's software license. The project's MIT code license does not cover external dictionary content; downloaded data and reports stay local, with redistribution assessed separately.

</details>
