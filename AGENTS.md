# AGENTS.md

本檔案供 AI 助理與協作者閱讀。工作時必須同時遵守「課程要求」與「本專案方向」兩部分；兩者衝突時，以課程要求為準，並在報告中註明差異。

---

## 一、課程要求

- 課程網址：<https://mcjkurz.github.io/teaching/courses/2026-2027/CHI3242/>
- 文本預處理順序固定：先用 OpenCC 轉簡體，再分句，最後用 jieba 分詞。
- 搭配詞分析必須使用 qhchina 的 `find_collocates`，停用詞使用 `load_stopwords`。
- 比較至少兩個窗口大小（window）及 sentence 方法；搭配詞至少兩個字，`max_p=0.05`。
- 每組結果各保存為一個 CSV；所有結果集中展示於 `output/results.html`。
- 提交內容：實際使用的 `.py` 檔、UTF-8 編碼語料、README、`report.md`，以及同內容的 `report.pdf`。
- 報告長度 2500–3000 字，須記錄 AI 的使用情形；文學分析部分由學生自行完成。
- README 記錄書名、作者及來源，不包含姓名或學號。

---

## 二、本專案方向

- 本資料夾 `C:\CHI3242文本發掘\CHI3242-assignment1` 為**提交專用副本**：Git 接續自 <https://github.com/zyuciwing-stack/CHI3242-assignment1> main `96756dd`（歷史保留，不重寫），內容由原工作區 `C:\CHI3242文本發掘\第一次作業\qi_scope_v3` 扁平化複製而成（`data/`、`input/`、`scripts/`、`output/`、`reports/` 均位於根目錄，`input_lock.json` 位於根目錄）。**原工作區保持不動**；未重跑分析。
- 研究主題：**兩漢至南北朝文論中「氣」的共現研究**，以概念「氣」為目標詞；老師已允許以概念替代人物作為分析對象。
- **正式版本**：111 筆記錄／128 個分析單元（以《典論·論文》為入口、《詩品》為上限參照；三組 qhchina 分析已實際執行）。選材、原文、單元邊界、固定引詩區間、停用詞快照均由 `input_lock.json` 鎖定；`--verify-inputs` 必須通過才可視為有效輸入。
- 來源限定維基文庫（ctext 僅可作補充且須記錄來源）；已取得資料不重抓、不新增下載。語料記錄書名、作者、來源網址、oldid 與 SHA-256；保留原文；區分正文、引文、序跋、注釋。來源索引見 `01_選定材料與來源.txt`。
- 固定處理規則：OpenCC t2s → 分句（。！？；…及換行）→ 既定引詩區間硬邊界（兩端不拼接、窗口與句內共現不跨越）→ 定向拆出單字「气」→ jieba default／HMM=True → 去純標點空白；不加短句過濾。
- qhchina 正式設定：`target_words=["气"]`、`alternative="greater"`、`correction=None`、`sort_by="obs_local"` 降序、`max_sentence_length=256`；filters `min_word_length=2`、`max_p=0.05`、停用詞 zh_cl_sim 經 t2s（僅結果篩選，仍佔窗口）。p 為未校正 Fisher 單尾探索值。
- 補充分析（`scripts/run_scope_minlen1.py`）：同一背景與 tokens，僅改結果門檻 `min_word_length=1`、`stopwords=[]`；未全面拆字、未修復分詞、未完成概念辨義。詳見 `reports/單字補充分析說明.md`。
- 零命中材料保留作背景；不按氣字頻次、ratio 或 p 重新選材。引文論及不同作品之文論重引保留並分別計數；「獨立」指記錄單位分立，轉引關係仍須交代，不宣稱統計獨立。《文賦》自身正文不是被引詩。
- 待核事項（照實保留）：南齊書文學傳論及贊、內典碑銘集林序成篇年代；隱秀電子編注與爭議補文層次。「196」只作操作性下限，未考定典論成篇年，未宣稱全部材料早於《詩品》。
- 安全與操作限制：不重抓來源、不改選材與去留；分析腳本對既有 `output/`、`data/processed/` 拒絕覆寫（從零重跑須在新目錄複製 `data/texts/`、`input/`、`input_lock.json`、`scripts/`、`requirements.txt`，不複製已生成結果）；不擅自改引詩判定或新增詞義分類；不 commit／push 除非使用者明確指示。
- Git 與金鑰：OpenRouter 設定及任何金鑰留在 Git 之外（`.env*`、`.venv` 已在 `.gitignore`）。本提交副本不含 `.venv`、快取、金鑰、參考論文 PDF、Word 草稿、ZIP 或歷次研究包；參考文獻僅保留書目資訊（見 README）。
- 歸檔：較大範圍語料（218 單元）與 v1／v2／v2.1 中間結果、舊腳本、舊交接包、歷次核查包及過時執行指令存於原工作區外的歸檔 `C:\CHI3242文本發掘\研究過程歸檔\氣研究_整理_*`，**不屬於本提交副本**；本提交副本內容自足，不含對歸檔的任何執行依賴。
- 文學結論、詞義判斷與正式報告由使用者完成；AI 不代寫文學結論。
