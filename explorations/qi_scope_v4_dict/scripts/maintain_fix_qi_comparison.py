#!/usr/bin/env python3
"""One-off maintenance fix (2026-10-08) for qi_scope_v4_dict.

Fixes output/qi_context_tokenization_comparison.csv column orig_char: the
original generator wrote the simplified token (气) instead of the ORIGINAL
source character (氣). This script rewrites ONLY that column by looking up the
original text at (record_id, unit_id, simp_offset_in_unit); every other column
and the row order are verified byte-identical against the current file. The
corrected column must match output/qi_hits.csv row by row.

No re-tokenisation, no qhchina analysis, no numeric result is recomputed.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_scope_qhchina as R  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
TARGET_CSV = OUT / "qi_context_tokenization_comparison.csv"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> None:
    selection, recs, texts, units, excluded, frozen, input_report = R.verify_inputs(ROOT)
    unit_map = {u["unit_id"]: u for u in units}
    fields = ["record_id", "unit_id", "title", "author", "simp_offset_in_unit", "orig_char",
              "orig_sentence", "segment_in_unit", "old_segment_tokens", "new_segment_tokens", "changed"]
    old_rows = list(csv.DictReader(TARGET_CSV.open(encoding="utf-8-sig", newline="")))
    R.require([r for r in old_rows[0]] == fields, "CSV header differs from expected schema")
    hits = list(csv.DictReader((OUT / "qi_hits.csv").open(encoding="utf-8-sig", newline="")))
    hits_by_key = {(h["unit_id"], int(h["simp_offset_in_unit"])): h for h in hits}

    fixed = []
    for row in old_rows:
        rid = row["record_id"]
        uid = row["unit_id"]
        offset = int(row["simp_offset_in_unit"])
        base = int(unit_map[uid]["start_0based"])
        orig_char = texts[rid][base + offset]
        R.require(orig_char in "氣气", f"original char at target offset is not a qi char: {uid}:{offset}")
        hit = hits_by_key.get((uid, offset))
        R.require(hit is not None, f"no matching qi_hits row: {uid}:{offset}")
        R.require(hit["orig_char"] == orig_char, f"orig_char differs from qi_hits: {uid}:{offset}")
        new_row = dict(row)
        new_row["orig_char"] = orig_char
        others_same = all(new_row[k] == row[k] for k in fields if k != "orig_char")
        R.require(others_same, f"non-orig_char columns changed for {uid}:{offset}")
        fixed.append(new_row)

    R.require(len(fixed) == len(old_rows) == 106, f"row count changed: {len(fixed)}")
    R.require(all(r["orig_char"] == "氣" for r in fixed), "not all corrected orig_char are 氣")
    order_same = [r[k] for r in fixed for k in fields if k != "orig_char"] == \
                 [r[k] for r in old_rows for k in fields if k != "orig_char"]
    R.require(order_same, "row order or non-orig_char values changed")

    with TARGET_CSV.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(fixed)

    print(json.dumps({
        "fixed_rows": len(fixed),
        "orig_char_values": sorted({r["orig_char"] for r in fixed}),
        "all_match_qi_hits": True,
        "other_columns_unchanged": True,
        "new_sha256": sha(TARGET_CSV),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
