# CHI3242 候選正文：從 OpenCode 腳本接續

把壓縮檔解壓到現有 CHI3242-assignment1 根目錄，合併 data/ 與 reports/。包內不包含 README.md、AGENTS.md、raw/、selected/ 或任何 .py，不覆寫既有來源或程式。本包整理的是機器輔助候選正文，不是已由作者核定的正式分析語料。

目前已完成原始來源保存及本輪候選正文抽取；尚未分詞、歸一人物名號或執行搭配詞分析。來源是倉庫提交 1f96595 所保存的三項固定修訂；原有文字、標點及疑字保持來源原貌。《詞源》採已核定14節，不含五要附文。《詞旨》的短出處姓名另存，不能一概稱後人新增，也未混入首輪保守正文。

請在 OpenCode 貼上：

```text
讀取 README_開始.md、data/analysis_candidates/manifest.json、
reports/正文清洗待核.md、reports/姜夔稱謂待核.csv，以及各書分層清單。
沿用已完成的 reports/02_三書正文範圍核對表.md。

從寫 prepare_corpus.py 開始：以現有原始來源和分層定位重現包內候選正文，
逐字比對結果、字數和 SHA-256；差異列出原因，不為湊數刪补。
保存可重跑腳本和實際執行紀錄，不重做來源下載或整張核對表。

更正核對表／來源紀錄：樂府此快照正文29小節；詞旨的■多是條首符號。
更正 AGENTS.md 舊「選題仍待確認」：老師已同意三詞論與姜夔方向。

保留raw與selected，不擅改OCR疑字或補缺文；人物名號維持原樣。
本轮實際執行限於文本重現與核驗，作者尚未核定的正文／名號不標成人工已核。
可以編寫segment.py備用；後續按OpenCC→分句→jieba順序，
停用詞及詞長作搭配詞結果篩選，不預刪詞序而壓縮視窗。

核驗後把現有核對表、候選資料、腳本與AI用途紀錄一起commit、push。
回報真實執行結果、差異和Git狀態；文學分析由作者完成。
```

接續正式統計時三書分開，以 qhchina 的 find_collocates 做 window5、window10、sentence 共九組，每組CSV，集中於 output/results.html。正文收錄政策和名號指涉須先核定；稀少用例不能靠混入後人疏證增加次數。

課程依據：

- <https://mcjkurz.github.io/teaching/courses/2026-2027/CHI3242/>
- <https://mcjkurz.github.io/teaching/courses/2026-2027/CHI3242/assignments/assignment-1/>
- <https://mcjkurz.github.io/teaching/courses/2026-2027/CHI3242/notes/week-04/>
