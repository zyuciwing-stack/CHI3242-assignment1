# prepare_corpus.py 執行紀錄

- 執行時間（UTC）：2026-10-06T17:06:45Z
- 環境：Python 3.12.10（64bit），Windows；套件見 requirements.txt（requests、beautifulsoup4 等，本腳本僅用標準庫）
- 執行命令：`.\.venv\Scripts\python.exe prepare_corpus.py`
- 性質：以現有原始來源與分層定位（treatises_layers.json、cizhi_layers.json）重現包內候選正文，逐字元比對、核對字數與 SHA-256。**本紀錄為機器核驗，未經作者核定；候選正文狀態仍為 machine_candidate_not_human_approved。**
- 原則：來源檔與候選檔全程唯讀；不為湊數刪補；差異如實記錄。

## 檢查結果

共 38 項檢查，通過 38 項。

| 檢查項目 | 結果 | 明細 |
|---|---|---|
| 來源檔 SHA-256：data/raw/yuefu_zhimi_oldid2527931.txt | 通過 | 與 manifest 一致 |
| 來源檔 SHA-256：data/selected/ciyuan.txt | 通過 | 與 manifest 一致 |
| 來源檔 SHA-256：data/raw/cizhi_oldid1560431.wikitext | 通過 | 與 manifest 一致 |
| 輸出檔存在：data/analysis_candidates/yuefu_zhimi.txt | 通過 | — |
| 輸出檔 SHA／非空白字數：data/analysis_candidates/yuefu_zhimi.txt | 通過 | SHA 一致、2500 字（manifest=2500） |
| 輸出檔存在：data/analysis_candidates/ciyuan.txt | 通過 | — |
| 輸出檔 SHA／非空白字數：data/analysis_candidates/ciyuan.txt | 通過 | SHA 一致、4812 字（manifest=4812） |
| 輸出檔存在：data/analysis_candidates/cizhi.txt | 通過 | — |
| 輸出檔 SHA／非空白字數：data/analysis_candidates/cizhi.txt | 通過 | SHA 一致、2534 字（manifest=2534） |
| ledger 來源檔 SHA-256：data/raw/yuefu_zhimi_oldid2527931.txt | 通過 | 與 ledger 一致 |
| ledger 來源檔 SHA-256：data/selected/ciyuan.txt | 通過 | 與 ledger 一致 |
| manifest 與 ledger 來源 SHA 互核：data/raw/yuefu_zhimi_oldid2527931.txt | 通過 | 一致 |
| manifest 與 ledger 來源 SHA 互核：data/selected/ciyuan.txt | 通過 | 一致 |
| 246 筆 ledger 片段與來源切片逐字一致 | 通過 | 246 筆全部命中 |
| included 190 筆逐字符來源映射 | 通過 | 全部一致 |
| 節數：樂府 29 節＋詞源 14 節 | 通過 | 實得 29+14 |
| 節名無重複 | 通過 | — |
| 同一節的 included 紀錄在 ledger 序中連續 | 通過 | 全部連續 |
| 重組輸出與包內檔案逐字元一致：yuefu_zhimi.txt | 通過 | 2557 字元完全相同 |
| 輸出 SHA／字數對照 ledger outputs：yuefu_zhimi | 通過 | SHA 一致、非空白 2500、總 2557 |
| sections clean_start/clean_end 重算一致：yuefu_zhimi | 通過 | 29 節位置全部吻合 |
| 重組輸出與包內檔案逐字元一致：ciyuan.txt | 通過 | 4839 字元完全相同 |
| 輸出 SHA／字數對照 ledger outputs：ciyuan | 通過 | SHA 一致、非空白 4812、總 4839 |
| sections clean_start/clean_end 重算一致：ciyuan | 通過 | 14 節位置全部吻合 |
| 樂府排除的行內校勘注（〈〉）共 11 則 | 通過 | 11 則 |
| 校勘注與序跋層未混入候選正文 | 通過 | — |
| ledger 來源檔 SHA-256：cizhi wikitext | 通過 | 與 metadata 一致 |
| 來源解碼字元數 | 通過 | 24758 |
| 877 段連續覆蓋來源（無縫隙、無重疊） | 通過 | 0→24758 全覆蓋 |
| 每段 raw_text 與來源切片逐字一致 | 通過 | 877 段全部命中 |
| 以 record_id 分組（185 段）重組與包內檔案逐字元一致 | 通過 | 185 段、2935 字元完全相同 |
| 輸出 SHA／字數對照 cizhi metadata（含分層字數） | 通過 | 非空白 2534；author_text 443/original_quotation 2058/author_word_list 33 |
| 原選句 176 條 | 通過 | 176 條（segments 176） |
| 候選段落 185 條 | 通過 | 185 段 |
| 條首符號、短出處、補入詞、疏證、序跋、標題、疑似殘片等層全部排除 | 通過 | 9 個排除層共 679 段均未納入 |
| 條首符號（■）187 段 | 通過 | 187 段 |
| 短出處 TSV 175 筆與來源切片一致 | 通過 | 全部命中 |
| ledger source_attribution 段均收錄於 TSV | 通過 | TSV 175 筆 ⊇ ledger 173 段 |

## 層次與待核摘記

- 引號疑難（needs_human_review）：12 筆——yuefu_zhimi-0069；yuefu_zhimi-0092；ciyuan-0095；ciyuan-0102；ciyuan-0111；ciyuan-0113；ciyuan-0115；ciyuan-0131；ciyuan-0132；ciyuan-0158；ciyuan-0195；ciyuan-0196。原文與標點保持原樣，未自動移動引號；最終引文層次待作者判斷。
- 詞旨 included 中經「排版空白整理」者：8 筆（cizhi_seg_0011；cizhi_seg_0035；cizhi_seg_0043；cizhi_seg_0047；cizhi_seg_0049；cizhi_seg_0055；cizhi_seg_0531；cizhi_seg_0866），均為接合段內換行／去段尾空白，不改字。
- 詞旨排除之疑似殘片（unresolved）：3 段——[1679,1685)'史梅溪在法，'；[11641,11662)'相思無處說相思。笑把畫羅，小'；[22367,22373)'■絮花寒有\n'。未補字、不改異文。
- 詞旨條首符號（■）：187 段，依交接更正視為條首符號（去符號不補字），不作缺字處理。
- 詞旨短出處（〔田不伐，探春。〕等）另存 cizhi_short_attributions.tsv（175 筆），不併入候選正文；其中部分標記《圖書集成》已有相近者，不得一概稱後人新增，範圍如改須另報字數與影響。
- 《樂府指迷》此快照正文為 29 節（非 30）；排除 11 則行內校勘注、題頭、四庫提要及四篇後人跋／後序。
- 《詞源》沿用已核定 14 節；去題頭、段內換行接合；零寬字 U+200B 共 3 個全數保留；引號疑難片段標 unresolved，未移動引號。

## 差異清單

- 無。重組輸出與包內候選檔逐字元一致；字數與 SHA-256 全部吻合。

## 待補／待核事項

- 正文清洗待核.md 提及之 `reports/cizhi_extraction_notes.md` 未隨包附上，本倉庫暫缺；精確界線以兩份 ledger 為準，該檔待原作者補交。
- 候選正文與人物名號（姜白石、樂笑翁等）未經作者核定；分詞與搭配詞統計待核定後進行（見 segment.py 備用腳本）。
- 本輪不重做來源下載（fetch_sources.py 沿用 raw／selected 快照），不重做整張核對表（僅更正 29 節與 ■ 條首符號兩處）。
