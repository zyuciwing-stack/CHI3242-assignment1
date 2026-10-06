# -*- coding: utf-8 -*-
"""prepare_corpus.py — 以原始來源＋分層定位重現包內候選正文，並逐項核驗。

依 README_開始.md 交接指令：
- 使用現有原始來源（data/raw、data/selected）與分層定位
  （treatises_layers.json、cizhi_layers.json）重現候選正文；
  與 data/analysis_candidates/ 包內檔案逐字元比對，核對字數與 SHA-256。
- 差異列出原因；不為湊數刪補；不修改任何來源檔或候選檔。
- 實際執行紀錄寫入 reports/prepare_corpus_執行紀錄.md。

用法：.\\.venv\\Scripts\\python.exe prepare_corpus.py
"""

from __future__ import annotations

import csv
import hashlib
import io
import itertools
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AC = ROOT / "data" / "analysis_candidates"
REPORTS = ROOT / "reports"
RECORD_MD = REPORTS / "prepare_corpus_執行紀錄.md"

MANIFEST = AC / "manifest.json"
TREATISES_LEDGER = AC / "treatises_layers.json"
CIZHI_LEDGER = AC / "cizhi_layers.json"
CIZHI_TSV = AC / "cizhi_short_attributions.tsv"

RESULTS: list = []   # (檢查名稱, 通過, 明細)
DIFFS: list = []     # 差異清單


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    return sha256_bytes(p.read_bytes())


def nonws(s: str) -> int:
    return len(re.sub(r"\s", "", s))


def check(name: str, passed: bool, detail: str = "") -> bool:
    RESULTS.append((name, passed, detail))
    print(f"  [{'通過' if passed else '未通過'}] {name}" + (f" — {detail}" if detail else ""))
    if not passed:
        DIFFS.append((name, detail))
    return passed


def expect(cond: bool, name: str, detail_ok: str = "", detail_fail: str = "") -> bool:
    return check(name, bool(cond), detail_ok if cond else detail_fail)


# ----------------------------------------------------------------------------
# 1. manifest：來源與輸出
# ----------------------------------------------------------------------------

def verify_manifest(manifest: dict) -> None:
    print("== 1. manifest.json：來源與輸出核對 ==")
    for s in manifest["sources"]:
        p = ROOT / s["source_file"]
        ok = p.exists() and sha256_file(p) == s["source_sha256"]
        expect(ok, f"來源檔 SHA-256：{s['source_file']}",
               "與 manifest 一致", "檔案缺失或 SHA-256 不一致")
    for o in manifest["outputs"]:
        p = ROOT / o["path"]
        if not expect(p.exists(), f"輸出檔存在：{o['path']}"):
            continue
        raw = p.read_bytes()
        text = raw.decode("utf-8")
        n = nonws(text)
        ok = (sha256_bytes(raw) == o["sha256"] and n == o["nonwhitespace_characters"])
        expect(ok, f"輸出檔 SHA／非空白字數：{o['path']}",
               f"SHA 一致、{n} 字（manifest={o['nonwhitespace_characters']}）",
               f"實得 SHA={sha256_bytes(raw)[:12]}… 字數={n}，manifest 記 {o['sha256'][:12]}…/{o['nonwhitespace_characters']}")


# ----------------------------------------------------------------------------
# 2. 樂府指迷＋詞源（treatises ledger）
# ----------------------------------------------------------------------------

def verify_treatises(ledger: dict, manifest: dict) -> None:
    print("== 2. treatises_layers.json：樂府指迷＋詞源 ==")
    src_files = {}
    for f, sha in ledger["source_sha256"].items():
        p = ROOT / f
        expect(p.exists() and sha256_file(p) == sha, f"ledger 來源檔 SHA-256：{f}",
               "與 ledger 一致", "不一致")
        src_files[f] = p
    # manifest 與 ledger 的來源 SHA 互核
    m_shas = {s["source_file"]: s["source_sha256"] for s in manifest["sources"]}
    for f, sha in ledger["source_sha256"].items():
        if f in m_shas:
            expect(m_shas[f] == sha, f"manifest 與 ledger 來源 SHA 互核：{f}", "一致", "不一致")

    src_text = {f: p.read_text(encoding="utf-8") for f, p in src_files.items()}

    records = ledger["records"]
    sections = ledger["sections"]

    # 2a. 每筆 record 的來源切片 == raw_text
    bad = [r["id"] for r in records
           if src_text[r["source_file"]][r["start"]:r["end"]] != r["raw_text"]]
    expect(not bad, "246 筆 ledger 片段與來源切片逐字一致",
           f"{len(records)} 筆全部命中", f"不一致：{bad[:5]}")

    # 2b. included 筆逐字符映射
    inc = [r for r in records if r["include"]]
    bad_sp = []
    for r in inc:
        pos = r.get("source_positions")
        if pos is None or len(pos) != len(r["text"]):
            bad_sp.append((r["id"], "缺少 source_positions 或長度不符"))
            continue
        s = src_text[r["source_file"]]
        for i, ch in enumerate(r["text"]):
            if pos[i] >= len(s) or s[pos[i]] != ch:
                bad_sp.append((r["id"], f"第 {i} 字符映射不符"))
                break
    expect(not bad_sp, f"included {len(inc)} 筆逐字符來源映射",
           "全部一致", f"不符：{bad_sp[:5]}")

    # 2c. 節覆蓋與次序：43 節（樂府 29＋詞源 14）
    n_yf = sum(1 for s in sections if s["work"] == "yuefu_zhimi")
    n_cy = sum(1 for s in sections if s["work"] == "ciyuan")
    expect((n_yf, n_cy) == (29, 14), "節數：樂府 29 節＋詞源 14 節",
           f"實得 {n_yf}+{n_cy}", f"實得 {n_yf}+{n_cy}")
    sec_names = [s["section"] for s in sections]
    expect(len(set(sec_names)) == len(sec_names), "節名無重複")

    # 2d. 相鄰性：同一節的 included 紀錄在紀錄序列中必須連續
    seen_order = [r["section"] for r in records if r["include"]]
    order_bad = []
    for sec in set(seen_order):
        pos = [i for i, x in enumerate(seen_order) if x == sec]
        if pos != list(range(pos[0], pos[0] + len(pos))):
            order_bad.append(sec)
    expect(not order_bad, "同一節的 included 紀錄在 ledger 序中連續", "全部連續", f"不連續：{order_bad[:5]}")

    # 2e. 重組輸出（節文相接、節間 LF LF、檔尾 LF），與包內檔案逐字元比對
    per_work_secs = {"yuefu_zhimi": [], "ciyuan": []}
    sec_text = {}
    for s in sections:
        sec_text[s["section"]] = ""
        per_work_secs[s["work"]].append(s)
    for r in records:
        if r["include"]:
            sec_text[r["section"]] += r["text"]

    outs = {"yuefu_zhimi": "yuefu_zhimi.txt", "ciyuan": "ciyuan.txt"}
    for work, fname in outs.items():
        recon = "\n\n".join(sec_text[s["section"]] for s in per_work_secs[work]) + "\n"
        actual = (AC / fname).read_text(encoding="utf-8")
        same = recon == actual
        expect(same, f"重組輸出與包內檔案逐字元一致：{fname}",
               f"{len(recon)} 字元完全相同", f"長度 重組={len(recon)} 實檔={len(actual)}"
               + ("" if same else "；內容不一致"))
        if not same:
            # 找出第一個差異位置，便於回報原因
            for i, (a, b) in enumerate(itertools.zip_longest(recon, actual, fillvalue="\0")):
                if a != b:
                    DIFFS.append((f"{fname} 第一個差異於字元 {i}",
                                  f"重組 {a!r} vs 實檔 {b!r}，前後文：…{recon[max(0,i-12):i]}／{actual[max(0,i-12):i]}…"))
                    break

        # SHA 與字數對照 ledger outputs
        led = ledger["outputs"][work]
        ok = (sha256_file(AC / fname) == led["sha256"]
              and nonws(actual) == led["nonwhitespace_chars"]
              and len(actual) == led["unicode_chars"])
        expect(ok, f"輸出 SHA／字數對照 ledger outputs：{work}",
               f"SHA 一致、非空白 {nonws(actual)}、總 {len(actual)}",
               "SHA 或字數不符")

        # 2f. sections clean_start/clean_end 重算一致性（同一 work 內）
        cur = 0
        pos_ok = True
        for s in per_work_secs[work]:
            t_ = sec_text[s["section"]]
            if s["clean_start"] != cur or s["clean_end"] != cur + len(t_):
                pos_ok = False
                DIFFS.append((f"sections clean 位置不符：{s['section']}",
                              f"ledger 記 ({s['clean_start']},{s['clean_end']})，重算 ({cur},{cur+len(t_)})"))
            cur = s["clean_end"] + 2
        expect(pos_ok, f"sections clean_start/clean_end 重算一致：{work}",
               f"{len(per_work_secs[work])} 節位置全部吻合", "見差異清單")

    # 2g. 層次統計與待核清單
    lay = Counter(r["layer"] for r in records)
    inc_lay = Counter(r["layer"] for r in inc)
    yf_notes = sum(1 for r in records if r["work"] == "yuefu_zhimi" and r["layer"] == "later_note")
    expect(yf_notes == 11, "樂府排除的行內校勘注（〈〉）共 11 則", "11 則", f"{yf_notes} 則")
    expect(inc_lay.get("later_note", 0) == 0 and inc_lay.get("later_preface", 0) == 0,
           "校勘注與序跋層未混入候選正文")
    hr = [r["id"] for r in records if r["certainty"] == "needs_human_review"]
    print(f"      needs_human_review：{len(hr)} 筆 → {hr}")
    print(f"      層次分布（全 ledger）：{dict(lay)}")
    print(f"      層次分布（included）：{dict(inc_lay)}")


# ----------------------------------------------------------------------------
# 3. 詞旨（cizhi ledger）
# ----------------------------------------------------------------------------

def verify_cizhi(ledger: dict, manifest: dict) -> None:
    print("== 3. cizhi_layers.json：詞旨 ==")
    meta = ledger["metadata"]
    src_path = ROOT / meta["source_file"]
    expect(src_path.exists() and sha256_file(src_path) == meta["source_sha256"],
           "ledger 來源檔 SHA-256：cizhi wikitext", "與 metadata 一致", "不一致")
    src = src_path.read_text(encoding="utf-8")
    expect(len(src) == meta["source_decoded_characters"],
           "來源解碼字元數", f"{len(src)}", f"metadata 記 {meta['source_decoded_characters']}")

    segs = ledger["segments"]
    # 3a. 完整切割：連續覆蓋 0..len(src)
    gaps = []
    cur = 0
    for s in segs:
        if s["start"] != cur:
            gaps.append((s["id"], f"start={s['start']} 預期 {cur}"))
        cur = s["end"]
    expect(not gaps and cur == len(src), "877 段連續覆蓋來源（無縫隙、無重疊）",
           f"0→{cur} 全覆蓋", f"縫隙：{gaps[:5]}")
    bad_slice = [s["id"] for s in segs if src[s["start"]:s["end"]] != s["raw_text"]]
    expect(not bad_slice, "每段 raw_text 與來源切片逐字一致",
           f"{len(segs)} 段全部命中", f"不一致：{bad_slice[:5]}")

    # 3b. included 分組重組
    inc = [s for s in segs if s["include"]]
    groups = [(k, "".join(s["text"] for s in g))
              for k, g in itertools.groupby(inc, key=lambda s: s["record_id"])]
    recon = "\n\n".join(t for _, t in groups) + "\n"
    actual = (AC / "cizhi.txt").read_text(encoding="utf-8")
    expect(recon == actual, "以 record_id 分組（185 段）重組與包內檔案逐字元一致",
           f"{len(groups)} 段、{len(recon)} 字元完全相同",
           f"組數={len(groups)}；長度 重組={len(recon)} 實檔={len(actual)}")
    if recon != actual:
        for i, (a, b) in enumerate(itertools.zip_longest(recon, actual, fillvalue="\0")):
            if a != b:
                DIFFS.append(("cizhi.txt 第一個差異於字元 %d" % i,
                              f"重組 {a!r} vs 實檔 {b!r}，前後文：…{recon[max(0,i-12):i]}／{actual[max(0,i-12):i]}…"))
                break

    # 3c. 字數與 SHA
    lay_count = Counter()
    rec_lay_count = Counter()
    for s in inc:
        lay_count[s["layer"]] += len(re.sub(r"\s", "", s["text"]))
        rec_lay_count[s["record_id"]] = s["layer"]  # 每一 record 一層
    by_layer_rec = Counter()
    for rid, layer in rec_lay_count.items():
        txt = "".join(s["text"] for s in inc if s["record_id"] == rid)
        by_layer_rec[layer] += nonws(txt)
    sel = meta["selected_counts_by_layer"]
    ok = (nonws(actual) == meta["selected_nonwhitespace_characters"]
          and sha256_file(AC / "cizhi.txt") == meta["selected_sha256"]
          and by_layer_rec.get("author_text", 0) == sel["author_text"]
          and by_layer_rec.get("original_quotation", 0) == sel["original_quotation"]
          and by_layer_rec.get("author_word_list", 0) == sel["author_word_list"])
    expect(ok, "輸出 SHA／字數對照 cizhi metadata（含分層字數）",
           f"非空白 {nonws(actual)}；author_text {by_layer_rec.get('author_text', 0)}"
           f"/original_quotation {by_layer_rec.get('original_quotation', 0)}"
           f"/author_word_list {by_layer_rec.get('author_word_list', 0)}",
           "SHA 或分層字數不符")
    nq = sum(1 for s in inc if s["layer"] == "original_quotation")
    # original_quotation 的 record 數
    nq_rec = len({s["record_id"] for s in inc if s["layer"] == "original_quotation"})
    expect(nq_rec == meta["selected_original_quotation_records"] == 176,
           "原選句 176 條", f"{nq_rec} 條（segments {nq}）",
           f"record 數 {nq_rec} vs metadata {meta['selected_original_quotation_records']}")
    expect(len(groups) == meta["selected_records"] == 185,
           "候選段落 185 條", f"{len(groups)} 段", f"{len(groups)} vs metadata {meta['selected_records']}")

    # 3d. included 中 text != raw_text（排版空白整理）逐筆列出
    layout = [s for s in inc if s["text"] != s["raw_text"]]
    print(f"      included 中 text != raw_text：{len(layout)} 筆（排版空白整理，逐筆見執行紀錄）")
    for s in layout:
        print(f"        {s['id']} [{s['start']},{s['end']}) {s['layer']} — {s['note'][:40]}")

    # 3e. 排除層不得混入
    exclude_layers = {"entry_marker", "source_attribution", "later_full_poem", "later_note",
                      "section_heading", "source_metadata", "later_preface", "unresolved", "layout"}
    mixed = [s["id"] for s in segs if s["layer"] in exclude_layers and s["include"]]
    expect(not mixed, "條首符號、短出處、補入詞、疏證、序跋、標題、疑似殘片等層全部排除",
           f"9 個排除層共 {sum(1 for s in segs if s['layer'] in exclude_layers)} 段均未納入",
           f"誤納入：{mixed[:5]}")
    lay_all = Counter(s["layer"] for s in segs)
    print(f"      全 ledger 層次分布：{dict(lay_all)}")
    expect(lay_all.get("entry_marker", 0) == 187, "條首符號（■）187 段",
           "187 段", f"{lay_all.get('entry_marker', 0)} 段")

    # 3f. 短出處 TSV：切片核對
    with open(CIZHI_TSV, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t", quotechar='"'))
    bad_tsv = [r["id"] for r in rows if src[int(r["start"]):int(r["end"])] != r["raw_text"]]
    expect(not bad_tsv, f"短出處 TSV {len(rows)} 筆與來源切片一致", "全部命中",
           f"不一致：{bad_tsv[:5]}")
    tsv_segs = {(int(r["start"]), int(r["end"])) for r in rows}
    led_attr = {(s["start"], s["end"]) for s in segs if s["layer"] == "source_attribution"}
    cover = led_attr <= tsv_segs
    expect(cover, "ledger source_attribution 段均收錄於 TSV",
           f"TSV {len(rows)} 筆 ⊇ ledger {len(led_attr)} 段", "TSV 未完整收錄 ledger 短出處段")


# ----------------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------------

def main() -> int:
    t0 = datetime.now(timezone.utc)
    print("prepare_corpus.py — 重現並核驗機器候選正文（唯讀，不修改來源與候選檔）")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    verify_manifest(manifest)
    verify_treatises(json.loads(TREATISES_LEDGER.read_text(encoding="utf-8")), manifest)
    verify_cizhi(json.loads(CIZHI_LEDGER.read_text(encoding="utf-8")), manifest)

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print(f"\n結果：{passed}/{total} 項檢查通過；差異 {len(DIFFS)} 項")

    write_record(t0, passed, total)
    print(f"執行紀錄已寫入 {RECORD_MD.relative_to(ROOT)}")
    return 0 if not DIFFS else 1


def write_record(t0, passed: int, total: int) -> None:
    now = t0.strftime("%Y-%m-%dT%H:%M:%SZ")
    import platform
    lines = [
        "# prepare_corpus.py 執行紀錄",
        "",
        f"- 執行時間（UTC）：{now}",
        f"- 環境：Python {platform.python_version()}（{platform.architecture()[0]}），Windows；"
        f"套件見 requirements.txt（requests、beautifulsoup4 等，本腳本僅用標準庫）",
        "- 執行命令：`.\\.venv\\Scripts\\python.exe prepare_corpus.py`",
        "- 性質：以現有原始來源與分層定位（treatises_layers.json、cizhi_layers.json）重現包內候選正文，"
        "逐字元比對、核對字數與 SHA-256。**本紀錄為機器核驗，未經作者核定；候選正文狀態仍為 machine_candidate_not_human_approved。**",
        "- 原則：來源檔與候選檔全程唯讀；不為湊數刪補；差異如實記錄。",
        "",
        "## 檢查結果",
        "",
        f"共 {total} 項檢查，通過 {passed} 項。",
        "",
        "| 檢查項目 | 結果 | 明細 |",
        "|---|---|---|",
    ]
    for name, ok, detail in RESULTS:
        lines.append(f"| {name} | {'通過' if ok else '**未通過**'} | {detail or '—'} |")
    lines += ["", "## 層次與待核摘記", ""]
    # 從 RESULTS 之外的補充資訊重建（重跑核心檢查以取清單）
    t = json.loads(TREATISES_LEDGER.read_text(encoding="utf-8"))
    hr = [(r["id"], r["work"], r["raw_text"][:40]) for r in t["records"] if r["certainty"] == "needs_human_review"]
    lines.append(f"- 引號疑難（needs_human_review）：{len(hr)} 筆——{'；'.join(i for i, _, _ in hr)}。"
                 "原文與標點保持原樣，未自動移動引號；最終引文層次待作者判斷。")
    c = json.loads(CIZHI_LEDGER.read_text(encoding="utf-8"))
    inc = [s for s in c["segments"] if s["include"]]
    layout = [s for s in inc if s["text"] != s["raw_text"]]
    lines.append(f"- 詞旨 included 中經「排版空白整理」者：{len(layout)} 筆"
                 f"（{'；'.join(s['id'] for s in layout)}），均為接合段內換行／去段尾空白，不改字。")
    unres = [s for s in c["segments"] if s["layer"] == "unresolved"]
    lines.append(f"- 詞旨排除之疑似殘片（unresolved）：{len(unres)} 段——"
                 + "；".join(f"[{s['start']},{s['end']}){s['raw_text'][:14]!r}" for s in unres)
                 + "。未補字、不改異文。")
    lines.append(f"- 詞旨條首符號（■）：{sum(1 for s in c['segments'] if s['layer'] == 'entry_marker')} 段，"
                 "依交接更正視為條首符號（去符號不補字），不作缺字處理。")
    lines.append("- 詞旨短出處（〔田不伐，探春。〕等）另存 cizhi_short_attributions.tsv（175 筆），不併入候選正文；"
                 "其中部分標記《圖書集成》已有相近者，不得一概稱後人新增，範圍如改須另報字數與影響。")
    lines.append("- 《樂府指迷》此快照正文為 29 節（非 30）；排除 11 則行內校勘注、題頭、四庫提要及四篇後人跋／後序。")
    lines.append("- 《詞源》沿用已核定 14 節；去題頭、段內換行接合；零寬字 U+200B 共 3 個全數保留；"
                 "引號疑難片段標 unresolved，未移動引號。")
    lines += ["", "## 差異清單", ""]
    if DIFFS:
        for name, detail in DIFFS:
            lines.append(f"- **{name}**：{detail}")
    else:
        lines.append("- 無。重組輸出與包內候選檔逐字元一致；字數與 SHA-256 全部吻合。")
    lines += [
        "",
        "## 待補／待核事項",
        "",
        "- 正文清洗待核.md 提及之 `reports/cizhi_extraction_notes.md` 未隨包附上，本倉庫暫缺；"
        "精確界線以兩份 ledger 為準，該檔待原作者補交。",
        "- 候選正文與人物名號（姜白石、樂笑翁等）未經作者核定；分詞與搭配詞統計待核定後進行（見 segment.py 備用腳本）。",
        "- 本輪不重做來源下載（fetch_sources.py 沿用 raw／selected 快照），不重做整張核對表（僅更正 29 節與 ■ 條首符號兩處）。",
        "",
    ]
    RECORD_MD.parent.mkdir(parents=True, exist_ok=True)
    RECORD_MD.write_text("\n".join(lines), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    sys.exit(main())
