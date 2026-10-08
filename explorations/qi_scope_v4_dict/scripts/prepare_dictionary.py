#!/usr/bin/env python3
"""Dictionary preparation for qi_scope_v4_dict (one-time, deterministic).

1. Byte-verifies resources/dictionaries/古代汉语词典_original.txt against the
   teacher-provided file characteristics (SHA-256, size, line/unique counts,
   UTF-8 no BOM, LF, trailing newline, no empty lines).
2. Converts every entry with OpenCC t2s (0.1.7), keeping the original line
   order; post-conversion duplicates keep the FIRST occurrence. Writes the
   derived table resources/dictionaries/ancient_words_t2s.txt (UTF-8 no BOM,
   LF, trailing newline) plus a conversion/merge log CSV.
3. Records dictionary-format checks (incl. punctuation-containing entries) and
   writes resources/preprocessing_lock.json (original/derived/jieba main dict
   SHA-256, versions, policies, this script's SHA).

Policies recorded and enforced:
- t2s per line, locked order; dedupe keeps first occurrence.
- No entry is added, removed, split, or joined; internal punctuation is kept.
- Frequencies are NOT supplied to jieba: jieba's native no-frequency
  auto-estimation is used at load_userdict time (segmentation weights, not
  corpus frequencies); import order is the locked derived-table order.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "resources" / "dictionaries"
ORIG = RES / "古代汉语词典_original.txt"
DERIVED = RES / "ancient_words_t2s.txt"
CONV_LOG = RES / "ancient_words_t2s_conversion_log.csv"
LOCK = ROOT / "resources" / "preprocessing_lock.json"

EXPECTED_ORIG_SHA = "d8922e2aeb42f7dd8317da60aea07be8b99ac8bb2e740956329df0d0c27154c7"
EXPECTED_ORIG_SIZE = 1625712
EXPECTED_DERIVED_SHA = "d5f6e7694e3c71786232cbdad09b535ed5af730bd793a447e9476c42baa6eeff"


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(p: Path) -> str:
    return sha_bytes(p.read_bytes())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main() -> None:
    require(ORIG.is_file(), f"missing original dictionary: {ORIG}")
    orig_bytes = ORIG.read_bytes()
    require(not orig_bytes.startswith(b"\xef\xbb\xbf"), "original dictionary must have no BOM")
    require(b"\r" not in orig_bytes, "original dictionary must use LF line endings")
    require(orig_bytes.endswith(b"\n"), "original dictionary must end with a newline")
    require(len(orig_bytes) == EXPECTED_ORIG_SIZE,
            f"original size differs: {len(orig_bytes)} != {EXPECTED_ORIG_SIZE}")
    orig_sha = sha_bytes(orig_bytes)
    require(orig_sha == EXPECTED_ORIG_SHA, f"original SHA-256 differs: {orig_sha}")
    entries = orig_bytes.decode("utf-8").split("\n")[:-1]  # splitlines-equivalent, LF only
    require(len(entries) == 200826 and len(set(entries)) == 200826,
            f"original line/unique counts differ: {len(entries)}/{len(set(entries))}")
    require(all(e.strip() for e in entries), "original dictionary contains empty lines")
    punct_entries = [e for e in entries
                     if any(unicodedata.category(c).startswith("P") for c in e)]

    import opencc
    cc = opencc.OpenCC("t2s")
    opencc_version = importlib.metadata.version("opencc-python-reimplemented")
    jieba_version = importlib.metadata.version("jieba")
    require(opencc_version == "0.1.7" and jieba_version == "0.42.1",
            f"version mismatch: opencc={opencc_version}, jieba={jieba_version}")

    converted, seen, changed, dupes = [], {}, 0, 0
    conv_rows = []
    for i, entry in enumerate(entries):
        out = cc.convert(entry)
        if out != entry:
            changed += 1
        dup_of = seen.get(out)
        if dup_of is None:
            seen[out] = i
            converted.append(out)
        else:
            dupes += 1
        conv_rows.append([i + 1, entry, out, "" if dup_of is None else dup_of + 1,
                          "" if dup_of is None else entries[dup_of]])
    require(changed == 966, f"t2s changed-form count differs: {changed} != 966")
    require(dupes == 70, f"post-conversion duplicate count differs: {dupes} != 70")
    require(len(converted) == 200756, f"derived entry count differs: {len(converted)} != 200756")
    require(len(set(converted)) == len(converted), "derived table still contains duplicates")

    derived_text = "\n".join(converted) + "\n"
    DERIVED.write_bytes(derived_text.encode("utf-8"))
    derived_sha = sha_file(DERIVED)
    require(derived_sha == EXPECTED_DERIVED_SHA,
            f"derived SHA-256 differs from spec: {derived_sha} != {EXPECTED_DERIVED_SHA}")

    with CONV_LOG.open("w", encoding="utf-8", newline="") as fh:
        fh.write("line_no,original,converted,duplicate_of_line_no,duplicate_of_entry\n")
        for row in conv_rows:
            fh.write(",".join([
                str(row[0]),
                '"' + row[1].replace('"', '""') + '"',
                '"' + row[2].replace('"', '""') + '"',
                str(row[3]) if row[3] != "" else "",
                '"' + row[4].replace('"', '""') + '"' if row[4] != "" else "",
            ]) + "\n")

    import jieba
    jieba_dict_path = Path(jieba.__file__).parent / jieba.DEFAULT_DICT_NAME
    require(jieba_dict_path.is_file(), f"jieba main dictionary missing: {jieba_dict_path}")
    jieba_dict_sha = sha_file(jieba_dict_path)

    lock = {
        "status": "complete",
        "prepared_utc": datetime.now(timezone.utc).isoformat(),
        "original_dictionary": {
            "path": "resources/dictionaries/古代汉语词典_original.txt",
            "sha256": orig_sha, "size_bytes": len(orig_bytes),
            "lines": len(entries), "unique_entries": len(set(entries)),
            "encoding": "utf-8 (no BOM)", "line_ending": "LF", "trailing_newline": True,
            "empty_lines": 0, "has_frequency": False, "has_pos": False,
            "has_gloss": False, "punctuation_containing_entries": len(punct_entries),
            "source_note": "教師提供的詞目表；未有書目／製作資料，不推定出版詞典版本、時代覆蓋或準確率；內容含近現代詞目",
            "expected_spec_sha256": EXPECTED_ORIG_SHA, "expected_spec_size": EXPECTED_ORIG_SIZE,
        },
        "derived_dictionary": {
            "path": "resources/dictionaries/ancient_words_t2s.txt",
            "sha256": derived_sha, "entries": len(converted),
            "conversion_changed_forms": changed, "post_conversion_duplicates_removed": dupes,
            "policy": "OpenCC t2s per line, locked order; duplicates keep first occurrence; "
                      "no entry added/removed/split/joined; internal punctuation kept",
            "encoding": "utf-8 (no BOM)", "line_ending": "LF", "trailing_newline": True,
            "expected_spec_sha256": EXPECTED_DERIVED_SHA,
            "conversion_log": "resources/dictionaries/ancient_words_t2s_conversion_log.csv",
        },
        "jieba": {
            "version": jieba_version,
            "main_dict_path": jieba_dict_path.name, "main_dict_sha256": jieba_dict_sha,
            "policy": "independent jieba.Tokenizer(); initialize() then load_userdict(derived) "
                      "BEFORE any segmentation; default main dictionary retained (no set_dictionary); "
                      "default mode, HMM=True",
            "frequency_policy": "no frequencies supplied; jieba native no-frequency auto-estimation "
                               "(segmentation weights only, not corpus frequencies); locked import order",
        },
        "opencc": {"version": opencc_version, "mode": "t2s"},
        "preparer_sha256": sha_file(Path(__file__)),
        "python": sys.version,
    }
    LOCK.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8", newline="\n")
    print(json.dumps({
        "original_sha256": orig_sha, "derived_sha256": derived_sha,
        "conversion_changed_forms": changed, "post_conversion_duplicates_removed": dupes,
        "derived_entries": len(converted), "punctuation_containing_entries": len(punct_entries),
        "jieba_main_dict_sha256": jieba_dict_sha, "lock": str(LOCK),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
