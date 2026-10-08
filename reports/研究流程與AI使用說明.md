# 氣研究：研究流程與 AI 使用說明

> 依實際檔案機器整理，待使用者核閱。整理時間見歸檔資料夾名稱與《整理摘要》；本文件只整理可查證的技術與流程事實，不代寫文學結論，亦不替代課程要求的 2,500–3,000 字正式報告（report.md／report.pdf 由使用者撰寫）。

## 一、最終選集與來源

- **111 筆記錄／128 個分析單元**（`input/selection.json`；`expected_records=111`、`expected_units=128`；`input_lock.json` 鎖定 114 個輸入檔 SHA-256）。
- 立題與範圍：以《典論·論文》為立題入口、以《詩品》為上限參照；範圍由較大語料（曾達 218 單元）縮小至「建安至梁初直接詩文論述」的操作性選集。
- 完整書名、作者與維基文庫 oldid 來源索引：`qi_scope_v3/01_選定材料與來源.txt`；每筆記錄另含 `source_url`、`oldid`、`revision_url` 與正文 SHA-256（`input/selection.json`）。
- **保留條件**：整篇／整部保留；**零命中材料一律保留作背景**（本輪 87 個零命中單元）；不按氣字頻次、ratio 或 p 值重新選材。
- **待核事項**（`scope_caveats`，照實保留）：
  1. 〈南齊書·文學傳論及贊〉相對《詩品》的成篇年代仍待核。
  2. 〈內典碑銘集林序〉相對《詩品》的成篇年代仍待核。
  3. 〈隱秀〉電子編注與爭議補文層次仍待核；本輪沿用現有文字，不能把全章無條件稱為劉勰原文。
- 「196 年」只作操作性下限；本輪未考定《典論·論文》成篇年，未宣稱全部材料必定早於《詩品》。文心雕龍整本保留不等於《隱秀》爭議補文已終校。

## 二、文本處理流程（固定規則）

1. 原始正文不改；`input_lock.json` 鎖定原文位元組與 SHA-256。
2. OpenCC t2s 繁轉簡；逐單元核驗轉換後字元長度不變、引詩區間座標對應不變、氣／气目標位置不移位。
3. 分句：句末 `。！？；…`（連續省略號及後隨閉引號同句）及換行。
4. **引詩硬邊界**：沿用已固定之 `input/quote_intervals.json`（excluded=1 共 55 條）；排除區間兩端不拼接，窗口與句內共現不跨越；引詩文字不入計數輸入。
5. **定向拆「气」**：保留段於每個「气」字符位置切分，其間文字用 jieba 分詞，再按原位插回單字「气」token（研究所需之定向切分，非 jieba 原始結果）。
6. jieba：`mode="default"`、`HMM=True`；僅去除純標點／空白／控制格式 token；**不加「至少五詞」短句過濾**。
7. 引文論及不同作品之文論重引保留並分別計數；「獨立」指記錄單位分立，轉引關係仍須交代，不宣稱統計獨立。《文賦》自身正文不是被引詩。

## 三、qhchina 三組分析（合併全選集）

- 目標：`target_words=["气"]`（含複合詞內部的氣；詞義未逐條裁定）。
- 三次呼叫：`method="window", horizon=5`；`method="window", horizon=10`；`method="sentence"`（不傳 horizon）。
- 參數：`alternative="greater"`、`correction=None`、`sort_by="obs_local"`、`ascending=False`、`max_sentence_length=256`（本輪實際最大句段 77 token，未觸及截斷上限）。
- filters（僅結果篩選，不預刪背景）：`min_word_length=2`、`max_p=0.05`、停用詞＝`qhchina.load_stopwords("zh_cl_sim")` 經同一 OpenCC t2s 轉簡（40 條，與 `input/stopwords_zh_cl_sim_t2s.txt` 快照核對相符；停用詞仍佔窗口位置）。
- 實算規模：111 記錄／128 單元；非空保留句段 **3,966**；背景詞項 **35,138**；保留「气」目標 **106**（引詩內排除 0）；零命中單元 **87**。
- N／R1：window N=35,032（全部詞項數−目標詞數）、R1=729（w5）／1,036（w10）；sentence N=3,966（非空句段數）、R1=102。
- 三表列數（obs_local 降序，p≤0.05、詞長≥2、停用詞隱藏）：**window5＝332、window10＝409、sentence＝511**。

## 四、驗證（本輪實際執行）

- `--verify-inputs` 通過：114 鎖定檔、111 原文、128 單元邊界 SHA、136 條引詩標記文字切片（55 排除）、唯一 ID、40 停用詞快照全部相符。
- 128 單元全部經逐單元核驗後**沿用** `data/qi_corpus_analysis_v21`（正文、spans、segment_index、tokens、固定引詩區間一致；重建 0 單元）。該舊副本已於整理時移至工作區外歸檔（見《整理摘要》），`analysis_log.json` 中歷史來源路徑記錄保持不變。
- 目標位置守恆、不越 unit／句／引詩邊界、token 重建、最大句段長核驗全部通過。
- 三表**逐列**獨立重算 obs_local、obs_global、exp=R1×C1/N、ratio=obs/exp 與 scipy Fisher 單尾 greater p 值；顯著結果清單完整性核驗通過；1,252 條例句均取自實際共現事件（含字符位置與 window 實距／sentence 同句段標記）。
- **p 值為未校正 Fisher 單尾探索結果**（correction=None，未作多重比較校正）；不是詞義成立的概率，也不等於兩期間顯著差異檢定。

## 五、實際環境與重現

- 環境（沿用原專案 `.venv`，未重裝）：Python 3.12.10；qhchina 0.2.7、jieba 0.42.1、opencc-python-reimplemented 0.1.7、scipy 1.18.1、pandas 3.0.6（見 `output/analysis_log.json` 之 versions 欄）。
- 核驗輸入（不寫結果）：`& ".\.venv\Scripts\python.exe" ".\qi_scope_v3\scripts\run_scope_qhchina.py" --verify-inputs`
- 完整分析：`& ".\.venv\Scripts\python.exe" ".\qi_scope_v3\scripts\run_scope_qhchina.py" --existing-project-root <專案根目錄>`
- 腳本對既有 `output/`、`data/processed/` 拒絕覆寫（本輪後已非空，屬正常保護）。**從零重跑方法**：在新目錄複製 `data/texts/`、`input/`（含 `input_lock.json` 與停用詞快照）、`scripts/`、`requirements.txt`；不複製已生成的 `data/processed/` 與 `output/`；以相同核心套件執行。本輪整理**未**執行此完整重跑。

## 六、AI 使用聲明（如實區分）

- **ChatGPT/Codex**：準備選材對接、輸入鎖定包（`qi_scope_v3`）、`run_scope_qhchina.py` 腳本與方法設定（依 `00_先讀說明.txt` 記載）。
- **OpenCode 本地執行模型**（使用者選擇之 DeepSeek Pro，`deepseek/deepseek-v4-pro`）：負責本地輸入核驗、三組分析執行與工作區整理。此為本輪執行與整理階段的模型，**不得倒填**為選材準備或更早歷史步驟的執行模型。
- **更早各輪**：執行模型與日期未記錄者一律寫「未記錄」，不虛構。
- **使用者**：文本覆核、詞義裁定、文學解讀與正式 report.md／report.pdf 撰寫。

## 七、結果位置

- 三表：`qi_scope_v3/output/collocates_window5.csv`、`collocates_window10.csv`、`collocates_sentence.csv`
- 彙整頁：`qi_scope_v3/output/results.html`（三組切換＋欄位說明）
- 例句／氣位置／核驗：`output/collocate_examples.csv`、`qi_hits.csv`、`unit_verification.csv`、`table_verification.csv`
- 方法與執行日誌：`output/method_notes.txt`、`output/analysis_log.json`
