# CHI3242-assignment1

以三部詞論為語料進行搭配詞分析，分析對象為姜夔（CHI3242 作業一）。

## 語料來源

| 書名 | 作者 | 來源 |
|---|---|---|
| 樂府指迷 | 沈義父（宋） | 中文維基文庫，固定修訂 oldid 2527931：<https://zh.wikisource.org/w/index.php?title=樂府指迷&oldid=2527931> |
| 詞旨 | 陸輔之（元） | 中文維基文庫，固定修訂 oldid 1560431：<https://zh.wikisource.org/w/index.php?title=詞旨&oldid=1560431> |
| 詞源（詞論部分，《古今圖書集成》所錄） | 張炎（宋） | 中文維基文庫《欽定古今圖書集成·理學彙編·文學典》第251卷，快照 oldid 1944678；選定「張炎樂府指迷」章內〈詞源〉至〈雜論〉共14節（data/selected/ciyuan.txt）；〈楊誠齋作詞五要〉另存為附文，不併入語料 |

版本、SHA-256、字數與完整性說明見 `data/sources.json` 與 `data/來源核對清單.md`。

## 環境與重跑

```powershell
py -3.12 -m venv .venv          # 已建立
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe fetch_sources.py
```

- `fetch_sources.py`：下載、清洗、選定語料並產生來源紀錄；每個網路請求 20 秒超時、最多重試一次；已完整下載且 SHA-256 核驗通過的檔案自動沿用。
- 文本預處理順序（後續分析）：OpenCC 繁轉簡 → 分句 → jieba 分詞 → qhchina 搭配詞分析（見 AGENTS.md）。

## 目錄結構

- `fetch_sources.py` — 語料下載與選定流程（可重跑）
- `data/raw/` — 維基文庫原始快照（html／wikitext）與清洗後 UTF-8 文本副本
- `data/selected/` — 選定語料：`ciyuan.txt`（《詞源》詞論14節）與附文（〈楊誠齋作詞五要〉）
- `data/sources.json` — 來源紀錄：oldid、修訂時間、下載時間、SHA-256、十四節明細、完整性狀態
- `data/來源核對清單.md` — 正文、序跋、校勘、疏證、增補詞作層次核對
- `requirements.txt` — 實際安裝版本
