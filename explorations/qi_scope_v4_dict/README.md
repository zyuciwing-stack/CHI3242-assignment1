# qi_scope_v4_dict：詞典補充分詞版（氣共現研究）

以概念「氣」為目標詞的搭配詞研究。本包為**詞典補充分詞版**：在 `qi_scope_v3`（原通用 jieba 基線）的固定選材（111 筆／128 單元）、固定規則（引詩硬邊界、气字定向拆分、窗口 5／10、sentence、p≤0.05）之上，唯一變更是**分詞時載入教師提供的詞目表**。`qi_scope_v3` 仍是基線，未修改；提交倉庫未動。

## 詞典與處理

- 原檔：工作區根目錄 `古代汉语词典.txt`（教師提供；未有書目／製作資料，不推定出版版本）。SHA-256＝`d8922e2a…c27154c7`；200,826 唯一詞目，無詞頻／詞性／釋義，505 個含標點詞目保留。
- 派生：OpenCC t2s 逐行轉換、保留行序、同形只留首現 → `resources/dictionaries/ancient_words_t2s.txt`（200,756 詞目；SHA-256＝`d5f6e769…baa6eeff`）。
- 載入：獨立 `jieba.Tokenizer()`，`initialize()` 後 `load_userdict(派生表)`，保留預設主詞典；詞頻用 jieba 原生自動推算（分詞權重，非語料頻數），導入順序鎖定。
- 本輪 128 單元**全部實際重新分詞**（reused_units=0），未沿用任何 v3 句段／tokens。

## 執行與結果

- 核驗：`python scripts/run_scope_qhchina.py --verify-inputs`（來源鎖定）；詞典鎖定（原檔／派生表／jieba 主詞典 SHA）隨分析核驗，見 `resources/preprocessing_lock.json`。
- 完整重跑（對既有 output／data/processed 拒覆寫；從零重跑須新目錄）：`python scripts/run_scope_qhchina.py --baseline-root <qi_scope_v3 路徑>`（基線僅供唯讀比較，可省略）。
- 補充組：`python scripts/run_scope_minlen1.py`；頁面：`python scripts/build_results_page.py`。

| 設定 | filters | 列數（window5／window10／sentence） |
|---|---|---|
| 正式 | min_word_length=2、max_p=0.05、40 停用詞 | 340／406／509 |
| 補充 | min_word_length=1、max_p=0.05、stopwords=[] | 381／447／569 |

- 背景：3,966 非空句段、35,411 token（v3 為 35,138）、106 个气目標；window N_fisher=35,305、R1=734／1,047；sentence N=3,966、R1=102。
- 分詞變化：1,398 句段變更、121 單元有變更；「詞采／華茂」已修正，「劉越／石仗」未修正，「徐幹時有齊氣」仍有錯切（新增疑似錯切 干时／有齐 等）。
- 詳細方法、參數、例句與限制：`reports/詞典補充分詞與重跑說明.md`；互動頁 `output/results.html`（詞典補充分詞版六表＋例句＋篩選）。

## 目錄

`data/texts/`（111 原文）、`data/processed/`（本輪分詞產物）、`input/`＋`input_lock.json`、`resources/`（詞典原檔、派生表、轉換對照、preprocessing_lock）、`scripts/`（prepare_dictionary、run_scope_qhchina、run_scope_minlen1、build_results_page）、`output/`（六表、例句、核驗、分詞對照、results.html、日誌）、`reports/`。

本輪不 commit、不 push；結果未替換提交版本。
