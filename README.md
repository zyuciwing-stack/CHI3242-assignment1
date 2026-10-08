# CHI3242 作業一：兩漢至南北朝文論中「氣」的共現研究

研究主題：**兩漢至南北朝文論中「氣」的共現研究**（qhchina 搭配詞分析）。以概念「氣」（含骨气、体气等複合詞內部的氣字）為目標詞；老師已允許以概念替代人物作為分析對象。本資料夾為提交用副本，由研究工作區整理而成；正式三組分析與單字補充分析均已實際執行，本副本未重跑分析、未更改任何分析設定或結果。

- **v3（正式分析）**：根目錄 `data/`、`input/`、`scripts/`、`output/`、`reports/`——通用 jieba 基線的正式三表與一字補充三表，為本次作業的正式版本。
- **v4（詞典探索）**：`explorations/qi_scope_v4_dict/`——僅在分詞時載入教師提供的古代漢語詞目表，其餘規則與 v3 相同；屬探索性對照，不取代 v3 的正文、分詞、CSV 或日誌。
- 彙整頁 `output/results.html` 整合兩版共 **12 張搭配表**，明示版本、詞長與停用詞設定，離線可開（不依賴 fetch、伺服器或 CDN）。

## 一、語料、作者與來源

- **111 筆記錄／128 個分析單元**（以《典論·論文》為立題入口、以《詩品》為上限參照），合併作背景分析；零命中材料一律保留。
- 主要材料（書名／作者）包括：曹丕《典論·論文》《與吳質書》；曹植、楊修、陳琳、王粲相關書牋序文；陸機《文賦》；左思、皇甫謐《三都賦序》；葛洪《抱朴子外篇》〈鈞世〉〈辭義〉〈文行〉；摯虞《文章流別論》（輯佚）、李充《翰林論》（輯佚）；傅玄、陸雲《與兄平原書》諸札；沈約、陸厥、蕭子顯、蕭繹、裴子野、江淹、謝靈運諸文論篇目；劉勰《文心雕龍》五十篇；鍾嶸《詩品》序及卷上中下。
- **來源**：維基文庫公開原典電子轉錄（ctext 僅作補充）。完整書名、作者與 oldid 索引見 `01_選定材料與來源.txt`；每筆記錄的來源網址、oldid、修訂版本與正文 SHA-256 見 `input/selection.json`，全部輸入檔案由 `input_lock.json` 鎖定。
- 來源核驗：`python scripts/run_scope_qhchina.py --verify-inputs` 須通過（111 records／128 units／114 locked files／136 引詩標記）。

## 二、目錄結構

| 路徑 | 內容 |
|---|---|
| `data/texts/` | 111 份 UTF-8 原文（鎖定原文，未改動） |
| `data/processed/` | 128 單元的簡體、分句、spans、segment_index 與分析 tokens（v3 正式分析輸入） |
| `input/`＋`input_lock.json` | 選材（selection.json）、引詩規則（quote_intervals.json）、40 詞停用詞快照及鎖定清單 |
| `scripts/` | `run_scope_qhchina.py`（正式分析＋核驗）、`run_scope_minlen1.py`（單字補充）、`build_results_page.py`（合併頁面產生） |
| `output/` | v3 六張結果 CSV、兩份例句、合併版 `results.html`、兩份執行日誌、逐列核驗、單元核驗、氣字位置、方法紀錄 |
| `reports/` | 研究流程與 AI 使用說明、單字補充分析說明 |
| [docs/方法與工程紀錄.md](docs/方法與工程紀錄.md) | 方法與工程紀錄：來源、處理規則、計數依據與版本沿革（報告註5引用） |
| `explorations/qi_scope_v4_dict/` | v4 詞典探索完整套件：`resources/`（教師詞目表原檔、t2s 派生表、轉換紀錄、`preprocessing_lock.json`）、`scripts/`、`output/`（v4 六表、例句、核驗、分詞比較）、`reports/`、README |
| `01_選定材料與來源.txt` | 111 筆材料的書名、作者與維基文庫 oldid 索引 |
| `copy_manifest_sha256.json` | 前次複製（v3 基線 652 檔）的 SHA-256 清單（與原工作區逐一比對通過） |
| `copy_manifest_sha256_20261009.json` | 本輪複製／置換紀錄：v4 663 檔 SHA、置換檔前後 SHA 與歸檔備份位置 |
| `.gitattributes` | `* -text`：防止 Windows 行尾轉換破壞鎖定 SHA |

## 三、執行方法與重現

- 環境（實際執行版本）：Python 3.12.10；qhchina 0.2.7、jieba 0.42.1、opencc-python-reimplemented 0.1.7、scipy 1.18.1、pandas 3.0.6（見 `requirements.txt` 與 `output/analysis_log.json`）。
- 核驗輸入（唯讀，不寫結果）：`python scripts/run_scope_qhchina.py --verify-inputs`
- **從零重跑 v3**：分析腳本對既有 `output/`、`data/processed/` 拒絕覆寫。請在新目錄複製 `data/texts/`、`input/`、`input_lock.json`、`scripts/`、`requirements.txt`（不複製已生成結果），執行 `python scripts/run_scope_qhchina.py`；單字補充：`python scripts/run_scope_minlen1.py`；頁面重建：`python scripts/build_results_page.py`（自動讀取根 `output/` 與 `explorations/qi_scope_v4_dict/output/`）。
- **重現 v4 詞典探索（含分詞比較）**：在新目錄複製 `explorations/qi_scope_v4_dict/` 全部內容（保留其內部相對結構），執行 `python explorations/qi_scope_v4_dict/scripts/run_scope_qhchina.py --baseline-root <本提交倉庫根目錄>`。`--baseline-root` 必須指向**本提交倉庫根目錄**（v3 基線所在），不依賴原工作區或研究歸檔；不傳時基線比較會被略過。詞典核驗另需唯讀核對 `resources/preprocessing_lock.json` 的原始詞目表、派生表與 jieba 主詞典 SHA 及套件版本（`--verify-inputs` 通過不等於詞典已核驗）。

## 四、正式分析與補充分析的差異

| 版本 | 設定 | filters | 結果列數（window5／window10／sentence） |
|---|---|---|---|
| v3 正式 | 正式（作業要求） | `min_word_length=2`、`max_p=0.05`、40 項停用詞（僅結果篩選，仍佔窗口） | 332／409／511 |
| v3 補充 | 一字補充 | `min_word_length=1`、`max_p=0.05`、`stopwords=[]` | 381／457／578（單字 49／48／67） |
| v4 探索 | 正式（作業要求） | 同 v3 正式（分詞載入教師詞目表） | 340／406／509 |
| v4 探索 | 一字補充 | 同 v3 補充（分詞載入教師詞目表） | 381／447／569（單字 41／41／60） |

- v3 背景：3,966 非空句段、35,138 tokens、106 個氣字目標、87 個零命中單元；v4 背景：同一 3,966 句段、35,411 tokens（唯一變更為分詞詞表）。
- 兩組版本皆用 window（5／10）及 sentence 方法、`alternative="greater"`、`correction=None`；僅結果顯示門檻不同。補充版字長≥2 的列與同版正式表**七欄數值及順序完全一致**。
- 補充分析**只取消結果中的停用詞篩選**，沒有全面拆字、修復分詞或完成概念辨義；單字 token 不等於已核定的文學概念（詳見 `reports/單字補充分析說明.md` 與 v4 的 `reports/`）。
- p 值均為未校正 Fisher 單尾探索結果（未作多重比較校正），不是詞義成立的概率。
- v4 詞目表如實稱為**教師提供的古代漢語詞目表**（200,826 詞目，t2s 派生 200,756 詞目）：未有書目／製作資料，不推定出版版本或開源許可；切分變化不等於準確率提升（詳見 `explorations/qi_scope_v4_dict/reports/詞典補充分詞與重跑說明.md`）。

## 五、結果位置與待核事項

- 彙整頁：`output/results.html`——12 張搭配表（v3 六表＋v4 六表）以「版本／詞長設定／分析設定」切換，附搜尋、共現≥2 與只看單字篩選、逐列代表例句（例句按「版本＋分析設定＋搭配詞」對應，兩版不混用）及 CSV 下載連結；離線可開。
- v3 CSV／例句／核驗：`output/collocates*.csv`、`output/collocate_examples*.csv`、`table_verification*.csv`、`unit_verification.csv`、`qi_hits.csv`；日誌：`output/analysis_log.json`、`output/analysis_log_minlen1.json`、`output/method_notes.txt`；頁面更新紀錄：`output/page_update_note*.txt`（含合併頁 `page_update_note_combined.txt`；歷史分析日誌未倒填）。
- v4 CSV／例句／核驗：`explorations/qi_scope_v4_dict/output/` 同名結構，另含分詞比較表與詞典維護紀錄。
- 待核事項：〈南齊書·文學傳論及贊〉、〈內典碑銘集林序〉相對《詩品》的成篇年代仍待核；〈隱秀〉電子編注與爭議補文層次仍待核（方法限制如實保留，本輪未修改語料、未重新分詞、未重跑分析）。

## 六、報告與工程紀錄（已提供）

- `report.md` 與同內容之 `report.pdf`：已提供。報告 2,500–3,000 字、記錄 AI 使用情形；文學分析部分由學生自行完成。
- `docs/方法與工程紀錄.md`：已提供，記錄來源、處理規則、計數依據與版本沿革（報告註5引用）。

## 七、參考文獻（僅保留書目；PDF 不入庫）

- 池世樺：〈劉楨詩「氣過其文，雕潤恨少」之歧見〉。
- 王令：〈突出之個性、清剛之詩文——劉楨人格心態與文學審美探析〉。

## 八、AI 使用聲明

選材對接與腳本準備、本地核驗與執行階段的 AI 使用情形，如實記錄於 `reports/研究流程與AI使用說明.md` 第六節（v4 另見 `explorations/qi_scope_v4_dict/reports/研究流程與AI使用說明.md`）；文本覆核、詞義裁定與文學解讀由研究者完成。
