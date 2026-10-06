# CHI3242-assignment1

研究主題：**兩漢至南北朝文論中「氣」的共現研究**（搭配詞分析）。以概念「氣」為目標詞；老師已允許以概念替代人物作為分析對象（2026-10-07 更新）。

語料（兩漢至南北朝文論文本）**尚待系統篩選**；篩選確定前不新增下載、不執行分詞或統計。原「《詞源》《樂府指迷》《詞旨》＋姜夔」方案的資料已於 2026-10-07 清除（Git 歷史保留，未重寫）。

## 環境

- Python 3.12（`.venv`，64 位）；套件見 `requirements.txt`（qhchina、jieba、opencc-python-reimplemented、beautifulsoup4、requests）。
- 安裝：`.\.venv\Scripts\python.exe -m pip install -r requirements.txt`

## 目錄現況

- `AGENTS.md` — 課程要求與本專案方向
- `requirements.txt` — 實際安裝版本
- `.gitignore`、`.git/`、`.venv/` — 保留
- `data/`、`reports/`、`output/` — 待語料篩選後建立

## 前置處理順序（課程要求，固定）

OpenCC 繁轉簡 → 分句 → jieba 分詞 → qhchina `find_collocates`（比較窗口 5、窗口 10 與 sentence 方法；搭配詞至少兩個字、`max_p=0.05`；停用詞用 `load_stopwords`，詞長與停用詞作結果篩選，不預刪詞序而壓縮視窗）。

每組結果各存一個 CSV，集中展示於 `output/results.html`。報告要求見 AGENTS.md。
