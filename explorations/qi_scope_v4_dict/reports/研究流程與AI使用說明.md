# 氣研究（詞典補充分詞版）：研究流程與 AI 使用說明

> 本文件為 `qi_scope_v4_dict`（詞典補充分詞版）的技術與流程記錄，依實際檔案整理。原通用 jieba 基線 `qi_scope_v3` 的說明存於該包 `reports/`，兩者不可混用數字。文學詞義裁定與正式報告由使用者完成。

## 一、選集與來源

- **111 筆記錄／128 個分析單元**（`input/selection.json`；`expected_records=111`、`expected_units=128`；`input_lock.json` 鎖定 114 個輸入檔 SHA-256）。111 筆為記錄數，不是 111 部獨立著作；128 為分析單元。
- 立題與範圍：以《典論·論文》為立題入口、以《詩品》為上限參照；範圍縮小至「建安至梁初直接詩文論述」的操作性選集。
- 完整書名、作者與維基文庫 oldid 來源索引：`01_選定材料與來源.txt`；每筆記錄另含 `source_url`、`oldid`、`revision_url` 與正文 SHA-256（`input/selection.json`）。
- **保留條件**：整篇／整部保留；**零命中材料一律保留作背景**（本輪 87 個零命中單元）；不按氣字頻次、ratio 或 p 值重新選材。
- **待核事項**（`scope_caveats`，照實保留）：
  1. 〈南齊書·文學傳論及贊〉相對《詩品》的成篇年代仍待核。
  2. 〈內典碑銘集林序〉相對《詩品》的成篇年代仍待核。
  3. 〈隱秀〉電子編注與爭議補文層次仍待核；本輪沿用現有文字，不能把全章無條件稱為劉勰原文。
- 「196 年」只作操作性下限；本輪未考定《典論·論文》成篇年，未宣稱全部材料必定早於《詩品》。

## 二、文本處理流程（固定規則＋本輪詞典載入）

1. 原始正文不改；`input_lock.json` 鎖定原文位元組與 SHA-256。
2. OpenCC t2s 繁轉簡；逐單元核驗轉換後字元長度不變、引詩區間座標對應不變、氣／气目標位置不移位。
3. 分句：句末 `。！？；…`（連續省略號及後隨閉引號同句）及換行。
4. **引詩硬邊界**：沿用 `input/quote_intervals.json`（136 條標記、excluded=1 共 55 條）；排除區間兩端不拼接，窗口與句內共現不跨越。
5. **定向拆「气」**：保留段於每個「气」字符位置切分，其間文字以本輪詞典分詞器分詞，再按原位插回單字「气」token（研究規則；即使詞典列有骨气／体气／辞气仍拆出內部气）。
6. **詞典補充分詞**（本輪唯一分詞層變更）：獨立 `jieba.Tokenizer()`，在任何分詞之前 `initialize()` 再 `load_userdict(resources/dictionaries/ancient_words_t2s.txt)`；保留 jieba 0.42.1 預設主詞典；`mode="default"`、`HMM=True`；僅去除純標點／空白／控制格式 token；**不加短句過濾**。詞目未提供詞頻，採 jieba 原生省略詞頻的自動推算（分詞權重，非語料頻數），導入順序為鎖定派生表行序。
7. **全面重建、禁止沿用**：本輪腳本無任何 v3 句段／tokens 沿用分支，128 單元全部實際重新分詞（`reused_units=0`）。
8. 引文論及不同作品之文論重引保留並分別計數；「獨立」指記錄單位分立，轉引關係仍須交代，不宣稱統計獨立。《文賦》自身正文不是被引詩。

## 三、qhchina 六組分析（合併全選集）

- 目標：`target_words=["气"]`（含複合詞內部的氣；詞義未逐條裁定）。
- 六次呼叫：window horizon=5、window horizon=10、sentence（不傳 horizon）× 正式／補充兩組。
- 參數：`alternative="greater"`、`correction=None`、`sort_by="obs_local"`、`ascending=False`、`max_sentence_length=256`（本輪實際最大句段 78 token，未觸及截斷上限）。
- 正式組 filters：`min_word_length=2`、`max_p=0.05`、停用詞＝`qhchina.load_stopwords("zh_cl_sim")` 經同一 OpenCC t2s（40 條，與 `input/stopwords_zh_cl_sim_t2s.txt` 快照相符；僅結果篩選，仍佔窗口）。
- 補充組 filters：`min_word_length=1`、`max_p=0.05`、`stopwords=[]`（40 詞快照僅作參考並核驗；日誌區分「參考清單 40 項」與「實際套用 0 項」）。
- 實算規模：111 記錄／128 單元；非空保留句段 **3,966**；背景詞項 **35,411**（v3 為 35,138）；保留「气」目標 **106**（引詩內排除 0）；零命中單元 **87**。
- N／R1：window N=35,305、R1=734（w5）／1,047（w10）；sentence N=3,966、R1=102。
- 六表列數（obs_local 降序，p≤0.05）：正式 **340／406／509**；補充 **381／447／569**（單字 41／41／60）。

## 四、驗證（本輪實際執行）

- 既有來源鎖定：`--verify-inputs` 通過（114 鎖定檔、111 原文、128 單元邊界 SHA、136 引詩標記文字切片、唯一 ID、40 停用詞快照）。
- 詞典鎖定：`resources/preprocessing_lock.json` 核驗通過（原詞目表／派生表／jieba 主詞典 SHA、版本、政策）。
- 128 單元全部 `mode=rebuilt_with_userdict`、`reused_units=0`；目標位置守恆、不越 unit／句／引詩邊界、token 重建、最大句段長核驗全部通過。
- 六表**逐列**獨立重算 obs_local、obs_global、exp=R1×C1/N、ratio=obs/exp 與 scipy Fisher 單尾 greater p 值；顯著結果清單完整性核驗通過；例句均取自實際共現事件。
- **p 值為未校正 Fisher 單尾探索結果**（correction=None）；不是詞義成立的概率，也不等於兩期間顯著差異檢定。

## 五、實際環境與重現

- 環境：Python 3.12.10；qhchina 0.2.7、jieba 0.42.1、opencc-python-reimplemented 0.1.7、scipy 1.18.1、pandas 3.0.6（見 `output/analysis_log.json`）。
- 詞典原檔：工作區根目錄 `古代汉语词典.txt`（教師提供；未有書目／製作資料），SHA-256＝`d8922e2a…c27154c7`；派生表 SHA-256＝`d5f6e769…baa6eeff`（200,756 詞目）。
- 核驗輸入（不寫結果）：`& ".\.venv\Scripts\python.exe" ".\qi_scope_v4_dict\scripts\run_scope_qhchina.py" --verify-inputs`（或進入 `qi_scope_v4_dict` 後 `python scripts\run_scope_qhchina.py --verify-inputs`）。
- 完整分析：`python scripts\run_scope_qhchina.py --baseline-root <qi_scope_v3 路徑>`（基線僅供唯讀分詞比較，可省略；**不使用** `--existing-project-root`——該參數屬 v3 歷史版本）。腳本對既有 `output/`、`data/processed/` 拒絕覆寫；從零重跑須在新目錄複製 `data/texts/`、`input/`、`input_lock.json`、`resources/`、`scripts/`、`requirements.txt`。
- 補充組：`python scripts\run_scope_minlen1.py`；頁面重建：`python scripts\build_results_page.py`；詞典派生（一次性）：`python scripts\prepare_dictionary.py`。

## 六、AI 使用聲明（如實區分）

- **ChatGPT/Codex**：v3 管線的選材對接、輸入鎖定包與腳本準備；本輪 v4 的預檢（**只重新分詞預覽**：35,411 token、1,398 句段、121 單元、106 位置、45 位置所在句段變更；未跑 qhchina）。
- **OpenCode 本地執行模型**（`deepseek/deepseek-v4-pro`）：本輪 v4 的詞典派生、腳本改寫（禁沿用＋詞典 Tokenizer）、六組 qhchina 分析與核驗、頁面與說明文件。
- **使用者**：提供詞典原檔與指令；文本覆核、詞義裁定、文學解讀與正式 report.md／report.pdf 撰寫。

## 七、結果位置

- 六表：`output/collocates_{window5,window10,sentence}.csv`、`output/collocates_minlen1_{window5,window10,sentence}.csv`
- 彙整頁：`output/results.html`（詞典補充分詞版；正式／補充、三方法、搜尋、共現≥2、只看單字、例句展開；不依賴伺服器／CDN）
- 例句／氣位置／核驗：`output/collocate_examples*.csv`、`qi_hits.csv`、`unit_verification.csv`、`table_verification*.csv`
- 分詞對照：`output/tokenization_changes.csv`、`qi_context_tokenization_comparison.csv`、`tokenization_summary.csv`
- 方法與執行日誌：`output/method_notes.txt`、`output/analysis_log.json`、`output/analysis_log_minlen1.json`
