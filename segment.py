# -*- coding: utf-8 -*-
"""segment.py — 候選正文的前置處理（備用腳本；執行須待作者核定正文與名號後）。

依 AGENTS.md 課程要求，處理順序固定：OpenCC 繁轉簡 → 分句 → jieba 分詞。
輸入：data/analysis_candidates/ 三份機器候選正文（machine_candidate_not_human_approved）。
輸出：data/processed/{work}_sentences.json —— 每份為段落的句詞序列
      {"work": ..., "paragraphs": [{"para_id": int, "sentences": [[token, ...], ...]}, ...]}

注意：
- 段落（節／條）邊界以空行劃分；分句與視窗**不得跨段**（每組結果視窗設定另於分析腳本處理）。
- 本階段不預刪任何詞序、不做停用詞過濾；停用詞（qhchina.load_stopwords）與
  詞長（min_word_length）留待 qhchina find_collocates 的 filters 階段處理，
  避免預刪詞序而壓縮視窗。
- 本輪（2026-10-07）僅供備用，尚未執行：正文與人物名號未經作者人工核定。

用法（核定後執行）：
    .\\.venv\\Scripts\\python.exe segment.py --run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AC = ROOT / "data" / "analysis_candidates"
OUT = ROOT / "data" / "processed"

WORKS = ["yuefu_zhimi", "ciyuan", "cizhi"]

SENT_END = "。！？…‥"


def split_sentences(para: str) -> list:
    """依句末標點分句；句末標點保留在句尾。"""
    sents, cur = [], ""
    for ch in para:
        cur += ch
        if ch in SENT_END:
            if cur.strip():
                sents.append(cur.strip())
            cur = ""
    if cur.strip():
        sents.append(cur.strip())
    return sents


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true",
                    help="實際執行（須待作者核定正文與名號後）")
    args = ap.parse_args()
    if not args.run:
        print("segment.py 為備用腳本：本輪未執行（正文／名號未經作者核定）。")
        print("待核定後執行：.\\.venv\\Scripts\\python.exe segment.py --run")
        return 0

    # 延遲匯入：僅在實際執行時需要
    from opencc import OpenCC
    import jieba

    cc = OpenCC("t2s")
    OUT.mkdir(parents=True, exist_ok=True)
    for work in WORKS:
        src = AC / f"{work}.txt"
        if not src.exists():
            print(f"找不到 {src}，略過 {work}")
            continue
        text = src.read_text(encoding="utf-8")
        paras = [p for p in re.split(r"\n{2,}", text) if p.strip()]
        doc = {"work": work, "source": str(src.relative_to(ROOT)), "paragraphs": []}
        for pid, para in enumerate(paras, 1):
            simp = cc.convert(para.strip())
            sentences = [[list(jieba.cut(s)) for s in split_sentences(simp)]]
            flat = [s for chunk in sentences for s in chunk]
            doc["paragraphs"].append({"para_id": pid, "sentences": flat})
        dst = OUT / f"{work}_sentences.json"
        with open(dst, "w", encoding="utf-8", newline="\n") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
            f.write("\n")
        n_sents = sum(len(p["sentences"]) for p in doc["paragraphs"])
        print(f"{work}: {len(paras)} 段 → {n_sents} 句 → {dst.name}")
    print("完成。後續搭配詞分析用 qhchina.find_collocates（window 5/10 與 sentence 三種設定），"
          "停用詞與 min_word_length 在 filters 處理。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
