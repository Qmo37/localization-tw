# localization-tw — 正體中文（臺灣）在地化技能

> 正體中文（Traditional Chinese），又稱繁體中文，為臺灣官方使用的標準漢字書寫形式。本技能以「正體中文」為正式名稱，並以臺灣華語慣用方式為規範。

Claude Code 的在地化翻譯技能，確保 AI 產出的中文內容符合臺灣華語母語者的用詞習慣，避免中國用語與簡體直譯。

## 功能

- **EN↔zh-TW 雙向翻譯**，也支援 EN↔JA↔zh-TW 三語翻譯
- **用詞規範**：內建臺灣 vs. 中國用語對照表（40+ 高頻詞彙速查）
- **領域污染檢查**：按電腦資訊、日常生活、娛樂、政經、交通等領域，主動檢查中國用語殘留
- **兩岸詞彙資料庫**：整合[中華語文知識庫](https://www.chinese-linguipedia.org/search_difference.html) 4,800+ 筆兩岸差異用詞
- **教育部辭典整合**：透過 [g0v/moedict-data](https://github.com/g0v/moedict-data) 為 357 筆日常用語加注注音、權威定義
- **Microsoft 術語庫**：透過 [termic.me](https://termic.me/) 查詢 Microsoft Glossary 與 Translation Memory 的 EN↔zh_TW 譯法（含詞性、定義、產品上下文）
- **統一搜尋工具**：一次搜尋所有本地詞庫＋線上 Microsoft 術語，支援精確、模糊、正規表達式
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

## 術語查詢工具

翻譯時遇到不確定的詞彙，可用以下工具查詢：

```bash
# 統一搜尋（本地所有詞庫）
python3 scripts/search.py 軟體
python3 scripts/search.py "interface" --mode exact

# 統一搜尋 + Microsoft 術語（需網路）
python3 scripts/search.py "server" --online

# 直接查 Microsoft 術語庫（Glossary + Translation Memory）
python3 scripts/fetch-microsoft-terms.py "database"
python3 scripts/fetch-microsoft-terms.py "介面" --reverse  # zh_TW→EN

# 查教育部辭典（注音、定義、例句）
python3 scripts/enrich-from-moedict.py --lookup "軟體,捷運,番茄"

# 批次查詢
python3 scripts/fetch-microsoft-terms.py --batch terms.txt --output glossary.md
```

Microsoft 術語資料來自 [termic.me](https://termic.me/)（開源 Microsoft Terminology Search 替代方案），提供微軟產品實際採用的 zh_TW 譯法，含詞性標注、英文定義、產品來源。

教育部辭典資料來自 [g0v/moedict-data](https://github.com/g0v/moedict-data)（教育部重編國語辭典修訂本 CC BY-ND 3.0 TW），提供注音、權威定義與例句。首次執行會自動下載約 14 MB 的辭典資料。

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

# 合併多次抓取的部分結果
python3 scripts/fetch-linguipedia.py --merge-cache cache1.json cache2.json
```

抓取後的資料會存入 `references/linguipedia-cross-strait.md`，依子分類分節呈現。由於檔案較大，翻譯時建議用 `search.py` 搜尋或直接 Grep 特定詞彙，而非全文載入。

## 檔案結構

```
localization-tw/
├── SKILL.md                          # 主技能定義（工作流程、速查表、品質清單）
├── references/
│   ├── vocabulary.md                 # 臺灣用語對照表（名詞、動詞、句式、標點）
│   ├── linguipedia-cross-strait.md   # 兩岸差異用詞（4,800+ 筆，腳本產生）
│   ├── chinese-traditional.md        # 正體中文語言特性
│   ├── english.md                    # 英文語言特性
│   └── japanese.md                   # 日文語言特性
├── translation-challenges.md         # 常見翻譯挑戰範例與解法
├── tools-resources.md                # 辭典、語料庫、工具彙整
└── scripts/
    ├── fetch-linguipedia.py          # 中華語文知識庫抓取腳本
    ├── fetch-microsoft-terms.py      # Microsoft 術語查詢腳本（via termic.me）
    ├── enrich-from-moedict.py        # 教育部辭典整合腳本（注音、定義）
    └── search.py                     # 統一術語搜尋工具
```

## 領域污染嚴重程度

技能會根據翻譯內容涉及的領域，主動提醒檢查高風險詞彙：

| 領域 | 污染程度 | 常見錯誤 → 正確用法 |
| --- | --- | --- |
| 電腦資訊 | 🔴 嚴重 | 數據→資料、代碼→程式碼、優化→最佳化、接口→介面 |
| 日常生活／食物 | 🔴 嚴重 | 西紅柿→番茄、土豆→馬鈴薯、信息→資訊、視頻→影片 |
| 娛樂／遊戲 | 🟠 中高 | 主播→實況主、點擊→點選、下載安裝→下載並安裝 |
| 政經社會 | 🟡 中等 | 數字經濟→數位經濟、互聯網→網際網路 |
| 交通運輸 | 🟡 中等 | 出租車→計程車、地鐵→捷運、公交車→公車 |

## 致謝

本技能基於以下兩個開源技能合併、修改而成：

- **[translation-expertise](https://agentskills.so/zh/skills/shino369-claude-code-personal-workspace-translation-expertise)** by [shino369](https://github.com/shino369/claude-code-personal-workspace) — 英日中（正體）三語翻譯方法論與最佳實踐
- **[taiwan-traditional-chinese-localization](https://mcpmarket.com/zh/tools/skills/taiwan-traditional-chinese-localization)** — 臺灣正體中文在地化規範

兩岸差異用詞資料來源：[中華語文知識庫](https://www.chinese-linguipedia.org/)
Copyright &copy; [中華文化總會](https://www.gacc.org.tw/)（National Cultural Association of Taiwan, NCAT）版權所有。本技能引用其公開資料僅供學術與翻譯參考用途。

Microsoft 術語查詢由 [termic.me](https://termic.me/) 提供（[GitHub](https://github.com/spidersouris/termic)，MIT License）。

教育部辭典資料來自 [g0v/moedict-data](https://github.com/g0v/moedict-data)。內容著作權屬教育部所有（CC BY-ND 3.0 TW），JSON 格式由 @kcwu 轉換（CC0）。

## 授權

本技能程式碼以 MIT License 釋出。

兩岸詞彙資料庫內容之著作權屬中華文化總會所有，使用時請遵守其授權條款。

---

<details>
<summary><strong>🌐 English Version</strong></summary>

# localization-tw — Standard/Traditional Chinese (Taiwan) Localization Skill

> In Taiwan, the official writing system is called 正體中文 (Standard Chinese / Orthodox Chinese), commonly referred to internationally as Traditional Chinese (繁體中文). This skill uses "Standard Chinese" as the formal name.

A Claude Code skill for localization and translation, ensuring AI-generated Chinese content follows Taiwanese Mandarin conventions and avoids mainland Chinese (CN) terms.

## Features

- **EN↔zh-TW bidirectional translation**, with EN↔JA↔zh-TW trilingual support
- **Terminology standards**: Built-in Taiwan vs. China vocabulary reference (40+ high-frequency terms)
- **Domain-aware pollution checking**: Actively flags CN term contamination across IT, daily life, entertainment, politics, transportation domains
- **Cross-strait vocabulary database**: Integrated with [Chinese Linguipedia](https://www.chinese-linguipedia.org/search_difference.html) — 4,800+ cross-strait terminology entries
- **MOE Dictionary integration**: 357 daily-use terms enriched with bopomofo and authoritative definitions via [g0v/moedict-data](https://github.com/g0v/moedict-data)
- **Microsoft Terminology**: Query Microsoft Glossary & Translation Memory for EN↔zh_TW via [termic.me](https://termic.me/) — with POS, definitions, and product context
- **Unified search tool**: Search all local vocabularies + online Microsoft terminology in one command (exact, fuzzy, regex)
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

## Terminology Search Tools

Use these tools to look up uncertain terms during translation:

```bash
# Unified search (all local vocabularies)
python3 scripts/search.py 軟體
python3 scripts/search.py "interface" --mode exact

# Unified search + Microsoft terminology (requires network)
python3 scripts/search.py "server" --online

# Query Microsoft terminology directly (Glossary + Translation Memory)
python3 scripts/fetch-microsoft-terms.py "database"
python3 scripts/fetch-microsoft-terms.py "介面" --reverse  # zh_TW→EN

# Look up MOE Dictionary (bopomofo, definitions, examples)
python3 scripts/enrich-from-moedict.py --lookup "軟體,捷運,番茄"

# Batch query
python3 scripts/fetch-microsoft-terms.py --batch terms.txt --output glossary.md
```

Microsoft terminology data is sourced from [termic.me](https://termic.me/) (open-source Microsoft Terminology Search replacement), providing actual zh_TW translations used in Microsoft products, with POS, English definitions, and product source.

MOE Dictionary data is sourced from [g0v/moedict-data](https://github.com/g0v/moedict-data) (教育部重編國語辭典修訂本, CC BY-ND 3.0 TW), providing bopomofo, authoritative definitions, and usage examples. The dictionary (~14 MB) is automatically downloaded on first use.

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

# Merge partial fetches
python3 scripts/fetch-linguipedia.py --merge-cache cache1.json cache2.json
```

Output is saved to `references/linguipedia-cross-strait.md`, organized by subcategory. Since the file is large, use `search.py` or Grep to search for specific terms during translation rather than loading the full file.

## File Structure

```
localization-tw/
├── SKILL.md                          # Main skill definition (workflow, quick ref, checklist)
├── references/
│   ├── vocabulary.md                 # TW vs CN vocabulary table (nouns, verbs, grammar, punctuation)
│   ├── vocabulary-enriched.md        # Enriched: core + 357 daily terms with bopomofo & MOE definitions
│   ├── linguipedia-cross-strait.md   # Cross-strait terms (4,800+, script-generated)
│   ├── chinese-traditional.md        # Traditional Chinese linguistic reference
│   ├── english.md                    # English linguistic reference
│   └── japanese.md                   # Japanese linguistic reference
├── translation-challenges.md         # Common translation challenges with examples
├── tools-resources.md                # Dictionaries, corpora, and tool references
└── scripts/
    ├── fetch-linguipedia.py          # Chinese Linguipedia fetcher script
    ├── fetch-microsoft-terms.py      # Microsoft terminology search (via termic.me)
    ├── enrich-from-moedict.py        # MOE Dictionary enrichment (bopomofo, definitions)
    └── search.py                     # Unified terminology search tool
```

## Domain Pollution Severity

The skill actively checks for CN term contamination based on the translation domain:

| Domain | Severity | Common Mistakes → Correct TW |
| --- | --- | --- |
| IT / Computing | 🔴 Critical | 數據→資料, 代碼→程式碼, 優化→最佳化, 接口→介面 |
| Daily Life / Food | 🔴 Critical | 西紅柿→番茄, 土豆→馬鈴薯, 信息→資訊, 視頻→影片 |
| Entertainment / Gaming | 🟠 High | 主播→實況主, 點擊→點選, 下載安裝→下載並安裝 |
| Politics / Society | 🟡 Moderate | 數字經濟→數位經濟, 互聯網→網際網路 |
| Transportation | 🟡 Moderate | 出租車→計程車, 地鐵→捷運, 公交車→公車 |

## Credits

This skill was created by combining and extending two open-source skills:

- **[translation-expertise](https://agentskills.so/zh/skills/shino369-claude-code-personal-workspace-translation-expertise)** by [shino369](https://github.com/shino369/claude-code-personal-workspace) — Expert EN-JA-ZH (Standard/Traditional) trilingual translation methodology and best practices
- **[taiwan-traditional-chinese-localization](https://mcpmarket.com/zh/tools/skills/taiwan-traditional-chinese-localization)** — Taiwan Standard Chinese localization standards

Cross-strait vocabulary data source: [Chinese Linguipedia (中華語文知識庫)](https://www.chinese-linguipedia.org/)
Copyright &copy; [National Cultural Association of Taiwan (中華文化總會, NCAT)](https://www.gacc.org.tw/). Data referenced for academic and translation purposes only.

Microsoft terminology search powered by [termic.me](https://termic.me/) ([GitHub](https://github.com/spidersouris/termic), MIT License).

MOE Dictionary data from [g0v/moedict-data](https://github.com/g0v/moedict-data). Content is CC BY-ND 3.0 TW by the Ministry of Education; JSON format is CC0 by @kcwu.

## License

This skill's code is released under the MIT License.

The cross-strait vocabulary database content is copyrighted by the National Cultural Association of Taiwan (NCAT). Please comply with their terms of use.

</details>
