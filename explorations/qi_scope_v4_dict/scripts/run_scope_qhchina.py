#!/usr/bin/env python3
"""qi_scope_v4_dict runner: dictionary-augmented re-tokenisation + 3 formal
pooled qhchina analyses (min_word_length=2, 40-word stopword result filter).

Differences from the qi_scope_v3 runner (read-only baseline):
- ALL reuse branches (reuse_roots / try_reuse / validated_v21_reuse) are
  removed. Every one of the 128 units is re-tokenised from the locked source
  text with ONE shared jieba.Tokenizer that has been initialize()d and had
  resources/dictionaries/ancient_words_t2s.txt load_userdict()ed BEFORE any
  segmentation. No segment or token is carried over from v3.
- resources/preprocessing_lock.json is verified (original/derived dictionary
  SHA-256, jieba main dictionary SHA-256, versions, policies).
- The fixed preprocessing rules are unchanged: OpenCC t2s, sentence splitting
  on 。！？；… and newlines, fixed quote intervals as hard boundaries (no
  joining across), directed splitting of every 气 character into its own
  target token, jieba default mode + HMM=True, pure punctuation/whitespace
  tokens dropped, no short-sentence filter.
- Optional --baseline-root (default sibling qi_scope_v3) enables read-only
  tokenisation comparisons: output/tokenization_changes.csv,
  output/qi_context_tokenization_comparison.csv, output/tokenization_summary.csv.

Verification uses the standard library only; third-party imports occur only in
run_analysis(). No source, selection, quote annotation, or lock is modified.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import importlib.metadata
import inspect
import json
import math
import platform
import shutil
import sys
import tempfile
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


TARGET = "气"
MAX_SENTENCE_LENGTH = 256
VERSIONS = {"qhchina": "0.2.7", "jieba": "0.42.1",
            "opencc-python-reimplemented": "0.1.7"}
RESULT_COLUMNS = ["target", "collocate", "exp_local", "obs_local",
                  "ratio_local", "obs_global", "p_value"]
SPAN_COLUMNS = ["record_id", "unit_id", "segment_in_unit", "token_index_in_segment",
                "token", "simp_start_in_unit", "simp_end_in_unit", "is_target_token"]
INDEX_COLUMNS = ["segment_in_unit", "sentence_index", "start_in_unit", "end_in_unit",
                 "sentence_contains_excluded_quote"]
DICT_ORIGINAL = "resources/dictionaries/古代汉语词典_original.txt"
DICT_DERIVED = "resources/dictionaries/ancient_words_t2s.txt"
PREPROC_LOCK = "resources/preprocessing_lock.json"
EXPECTED_ORIG_SHA = "d8922e2aeb42f7dd8317da60aea07be8b99ac8bb2e740956329df0d0c27154c7"
EXPECTED_DERIVED_SHA = "d5f6e7694e3c71786232cbdad09b535ed5af730bd793a447e9476c42baa6eeff"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_bytes().decode("utf-8"))


def safe_path(root, relative):
    p = Path(relative)
    require(not p.is_absolute() and ".." not in p.parts, f"Unsafe relative path: {relative}")
    result = (root / p).resolve()
    require(result.is_relative_to(root.resolve()), f"Path escapes package: {relative}")
    return result


def verify_inputs(root):
    """Validate every locked byte, record, unit slice, and fixed quote position."""
    root = root.resolve()
    lock_path = root / "input_lock.json"
    if not lock_path.is_file():
        lock_path = root / "input/input_lock.json"
    lock = read_json(lock_path)
    files = lock.get("files", lock)
    require(isinstance(files, dict) and files, "input_lock.json must contain relative path -> SHA-256")
    actual = {p.relative_to(root).as_posix() for folder in (root / "input", root / "data/texts")
              for p in folder.rglob("*") if p.is_file() and p != lock_path}
    require(set(files) == actual, f"Lock file set mismatch: missing={sorted(actual-set(files))}, extra={sorted(set(files)-actual)}")
    for relative, expected in files.items():
        if isinstance(expected, dict):
            expected = expected.get("sha256")
        require(isinstance(expected, str) and len(expected) == 64, f"Invalid lock hash: {relative}")
        require(sha(safe_path(root, relative).read_bytes()) == expected, f"Locked file changed: {relative}")
    selection = read_json(root / "input/selection.json")
    quotes = read_json(root / "input/quote_intervals.json")
    require(isinstance(quotes, list), "quote_intervals.json must be a list")
    records = selection["records"]
    units = selection["units"]
    require(len(records) == int(selection["expected_records"]), "Record count differs from selection metadata")
    require(len(units) == int(selection["expected_units"]), "Unit count differs from selection metadata")
    recs, texts, unit_map = {}, {}, {}
    for record in records:
        rid = record["id"]
        require(rid not in recs, f"Duplicate record: {rid}")
        p = safe_path(root, record["text_file"])
        require(p.parent == (root / "data/texts").resolve(), f"Unexpected text location: {p}")
        data = p.read_bytes()
        require(sha(data) == record["sha256"], f"Record hash failed: {rid}")
        texts[rid] = data.decode("utf-8")  # Do not normalize newline bytes.
        recs[rid] = record
    require({r["text_file"] for r in records} == {p.relative_to(root).as_posix() for p in (root / "data/texts").glob("*.txt")}, "Text file list differs from selected records")
    units_by_record = defaultdict(list)
    for unit in units:
        uid, rid = unit["unit_id"], unit["record_id"]
        require(uid not in unit_map and rid in recs, f"Duplicate unit or unknown record: {uid}")
        require(Path(uid).name == uid and uid not in (".", ".."), f"Unsafe unit ID: {uid}")
        a, b = int(unit["start_0based"]), int(unit["end_exclusive"])
        require(0 <= a < b <= len(texts[rid]), f"Unit coordinates invalid: {uid}")
        require(sha(texts[rid][a:b].encode("utf-8")) == unit["sha256"], f"Unit slice hash failed: {uid}")
        unit_map[uid] = unit
        units_by_record[rid].append((a, b, uid))
    require(set(units_by_record) == set(recs), "Some selected records have no unit")
    for rid, intervals in units_by_record.items():
        ordered = sorted(intervals)
        require(all(x[1] <= y[0] for x, y in zip(ordered, ordered[1:])), f"Selected units overlap: {rid}")
    excluded = defaultdict(list)
    for n, quote in enumerate(quotes):
        rid = quote["record_id"]
        require(rid in recs, f"Quote {n} references unselected record")
        a, b = int(quote["start_0based"]), int(quote["end_exclusive"])
        require(0 <= a < b <= len(texts[rid]), f"Quote coordinates invalid: {rid}:{a}-{b}")
        require(texts[rid][a:b] == quote["content"], f"Quote content differs from locked source: {rid}:{a}-{b}")
        require(str(quote["excluded"]) in ("0", "1"), f"Invalid quote exclusion flag: {n}")
        if quote.get("unit_id"):
            unit = unit_map.get(quote["unit_id"])
            require(unit is not None and unit["record_id"] == rid, f"Quote unit does not match: {n}")
            require(int(unit["start_0based"]) <= a < b <= int(unit["end_exclusive"]), f"Quote outside annotated unit: {n}")
        if str(quote["excluded"]) == "1":
            excluded[rid].append((a, b))
    frozen = (root / "input/stopwords_zh_cl_sim_t2s.txt").read_bytes().decode("utf-8").splitlines()
    require(len(frozen) == 40 and len(set(frozen)) == 40 and all(w and w == w.strip() for w in frozen), "Frozen stopword list must contain 40 distinct nonempty entries")
    rules = selection["rules"]
    require(rules.get("opencc") == "t2s" and rules.get("target") == TARGET,
            "Unsupported OpenCC or target rule")
    require(rules.get("jieba_mode") == "default" and rules.get("jieba_HMM") is True
            and rules.get("directed_qi_segmentation") is True
            and rules.get("short_sentence_filter") is False
            and rules.get("stopwords_result_filter_only") is True, "Segmentation rules differ from this runner")
    report = {"status": "input_verification_passed", "records": len(records), "units": len(units),
              "locked_files": len(files), "quote_annotations": len(quotes),
              "excluded_quote_annotations": sum(str(q["excluded"]) == "1" for q in quotes),
              "stopwords": len(frozen), "input_lock_sha256": sha(lock_path.read_bytes()),
              "locked_files_digest": sha(json.dumps(files, sort_keys=True, ensure_ascii=False,
                                                    separators=(",", ":")).encode("utf-8")),
              "analysis_executed": False}
    return selection, recs, texts, units, excluded, frozen, report


def verify_dictionary_lock(root, jieba):
    """Verify the prepared dictionary resources against resources/preprocessing_lock.json."""
    lock = read_json(root / PREPROC_LOCK)
    orig_path = root / DICT_ORIGINAL
    derived_path = root / DICT_DERIVED
    require(orig_path.is_file() and derived_path.is_file(), "dictionary files missing")
    orig_sha = sha(orig_path.read_bytes())
    derived_sha = sha(derived_path.read_bytes())
    lock_orig = lock["original_dictionary"]["sha256"]
    lock_derived = lock["derived_dictionary"]["sha256"]
    require(orig_sha == lock_orig == EXPECTED_ORIG_SHA,
            f"original dictionary SHA mismatch: file={orig_sha}, lock={lock_orig}")
    require(derived_sha == lock_derived == EXPECTED_DERIVED_SHA,
            f"derived dictionary SHA mismatch: file={derived_sha}, lock={lock_derived}")
    require(orig_path.stat().st_size == int(lock["original_dictionary"]["size_bytes"]),
            "original dictionary size mismatch")
    require(int(lock["original_dictionary"]["lines"]) == 200826
            and int(lock["original_dictionary"]["unique_entries"]) == 200826,
            "original dictionary line/unique counts mismatch")
    require(int(lock["derived_dictionary"]["entries"]) == 200756, "derived entry count mismatch")
    main_dict = Path(jieba.__file__).parent / jieba.DEFAULT_DICT_NAME
    require(main_dict.is_file(), "jieba main dictionary missing")
    require(sha(main_dict.read_bytes()) == lock["jieba"]["main_dict_sha256"],
            "jieba main dictionary SHA mismatch")
    require(lock["jieba"]["version"] == importlib.metadata.version("jieba")
            and lock["opencc"]["version"] == importlib.metadata.version("opencc-python-reimplemented"),
            "preprocessing_lock version mismatch")
    derived_bytes = derived_path.read_bytes()
    require(not derived_bytes.startswith(b"\xef\xbb\xbf") and b"\r" not in derived_bytes
            and derived_bytes.endswith(b"\n"), "derived dictionary encoding/line-ending mismatch")
    entries = derived_bytes.decode("utf-8").split("\n")[:-1]
    require(len(entries) == 200756 and len(set(entries)) == 200756,
            "derived dictionary duplicates or line count mismatch")
    return lock


def drop_char(char):
    category = unicodedata.category(char)
    return category[0] in ("P", "Z") or category in ("Cc", "Cf")


def split_sentences(text):
    spans, start, i = [], 0, 0
    while i < len(text):
        char = text[i]
        if char in "\n\r":
            if i > start:
                spans.append((start, i))
            start = i + 1
            i += 1
            continue
        if char in "。！？；…":
            j = i + 1
            if char == "…":
                while j < len(text) and text[j] == "…":
                    j += 1
            while j < len(text) and text[j] in "」』）］｝》\"'″＇":
                j += 1
            if j > start:
                spans.append((start, j))
            start, i = j, j
            continue
        i += 1
    if start < len(text):
        spans.append((start, len(text)))
    return [(a, b) for a, b in spans if text[a:b].strip()]


def segment_plan(simplified, intervals):
    """Retained and excluded runs; every quote edge remains a hard boundary."""
    plan = []
    for sentence_index, (ss, se) in enumerate(split_sentences(simplified)):
        cuts = sorted({ss, se} | {x for interval in intervals for x in interval if ss < x < se})
        contains = any(a < se and ss < b for a, b in intervals)
        for a, b in zip(cuts, cuts[1:]):
            inside = any(x <= a and b <= y for x, y in intervals)
            plan.append({"sentence_index": sentence_index, "start": a, "end": b,
                         "sentence_start": ss, "sentence_end": se,
                         "excluded": inside, "sentence_contains_excluded_quote": int(contains)})
    return plan


def read_tsv(path, columns):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        require(reader.fieldnames is not None and set(columns) <= set(reader.fieldnames),
                f"Missing required TSV header in {path}: expected {columns}")
        return list(reader)


def rebuild(unit, simp, kept_plan, tokenizer):
    """Re-tokenise a unit with the shared dictionary-augmented tokenizer.

    The directed 气 split is preserved: every 气 character position is cut out
    and re-inserted as its own single target token, regardless of any
    dictionary entry such as 骨气/体气/辞气.
    """
    segments = []
    for number, part in enumerate(kept_plan):
        a, b = part["start"], part["end"]
        targets = [p for p in range(a, b) if simp[p] == TARGET]
        spans, previous = [], a
        for p in targets + [b]:
            if previous < p:
                for token, start, end in tokenizer.tokenize(simp[previous:p], mode="default", HMM=True):
                    if not all(drop_char(ch) for ch in token):
                        spans.append((previous + start, previous + end, token, False))
            if p < b:
                spans.append((p, p + 1, TARGET, True))
            previous = p + 1
        require("".join(s[2] for s in spans) == "".join(ch for ch in simp[a:b] if not drop_char(ch)), f"Rebuilt token reconstruction failed: {unit['unit_id']}:{a}-{b}")
        require({s[0] for s in spans if s[3]} == set(targets), "Rebuilt targets incomplete")
        segments.append({**part, "segment_in_unit": number, "spans": spans,
                         "tokens": [s[2] for s in spans], "unit_id": unit["unit_id"], "record_id": unit["record_id"]})
    return segments


def write_rows(path, rows, fields, delimiter=","):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig" if delimiter == "," else "utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter=delimiter)
        writer.writeheader()
        writer.writerows(rows)


def simulate(segments, method, horizon=None):
    global_counts, local, examples = Counter(), Counter(), {}
    total = context = targets = 0
    for segment in segments:
        tokens = segment["tokens"]
        targets += tokens.count(TARGET)
        if method == "sentence":
            total += 1
            words = set(tokens)
            global_counts.update(words)
            if TARGET in words:
                context += 1
                j = tokens.index(TARGET)
                for word in sorted(words - {TARGET}):
                    local[word] += 1
                    examples.setdefault(word, (segment, tokens.index(word), j))
        else:
            total += len(tokens)
            global_counts.update(tokens)
            for i, word in enumerate(tokens):
                if word == TARGET:
                    continue
                active = [j for j in range(max(0, i-horizon), min(len(tokens), i+horizon+1))
                          if j != i and tokens[j] == TARGET]
                if active:
                    context += 1
                    local[word] += 1
                    j = min(active, key=lambda j: (abs(j-i), j))
                    examples.setdefault(word, (segment, i, j))
    return {"N_all_tokens_or_segments": total, "N_fisher": total-targets if method == "window" else total,
            "R1": context, "target_tokens": targets, "global": global_counts,
            "local": local, "examples": examples}


def verify_table(df, stats, run, stopwords, fisher_exact):
    require(set(RESULT_COLUMNS) <= set(df.columns), f"qhchina result columns missing: {run}")
    require(not df["collocate"].duplicated().any(), f"Duplicate collocate rows: {run}")
    checks = []
    for row in df.to_dict("records"):
        word = row["collocate"]
        require(row["target"] == TARGET and len(word) >= 2 and word not in stopwords, f"Result filter mismatch: {run}:{word}")
        a = stats["local"][word]
        R1, C1, N = stats["R1"], stats["global"][word], stats["N_fisher"]
        b, c = R1-a, C1-a
        d = N-a-b-c
        require(min(a, b, c, d) >= 0 and N > 0, f"Invalid contingency table: {run}:{word}")
        expected = R1*C1/N
        ratio = a/expected
        p = float(fisher_exact([[a, b], [c, d]], alternative="greater").pvalue)
        for field, actual in (("obs_local", a), ("obs_global", C1), ("exp_local", expected),
                              ("ratio_local", ratio), ("p_value", p)):
            require(math.isclose(float(row[field]), actual, rel_tol=1e-7, abs_tol=1e-10),
                    f"Independent {field} verification failed: {run}:{word}; qhchina={row[field]}, independent={actual}")
        require(p <= 0.05 + 1e-12, f"max_p filter failed: {run}:{word}")
        checks.append({"method": run, "collocate": word, "a": a, "b": b, "c": c, "d": d,
                       "N": N, "R1": R1, "C1": C1, "exp_verified": expected,
                       "ratio_verified": ratio, "p_verified": p, "passed": True})
    observed = df["obs_local"].tolist()
    require(observed == sorted(observed, reverse=True), f"Result is not sorted by obs_local descending: {run}")
    eligible = set()
    for word, a in stats["local"].items():
        if len(word) < 2 or word in stopwords:
            continue
        R1, C1, N = stats["R1"], stats["global"][word], stats["N_fisher"]
        b, c = R1-a, C1-a
        d = N-a-b-c
        require(min(a, b, c, d) >= 0, f"Invalid candidate table: {run}:{word}")
        if float(fisher_exact([[a, b], [c, d]], alternative="greater").pvalue) <= 0.05:
            eligible.add(word)
    require(set(df["collocate"]) == eligible, f"Result row set differs from independent filters: {run}; missing={sorted(eligible-set(df['collocate']))}, extra={sorted(set(df['collocate'])-eligible)}")
    return checks


def example_row(run, row, example, recs, texts, units):
    segment, ci, ti = example
    uid, rid = segment["unit_id"], segment["record_id"]
    base = int(units[uid]["start_0based"])
    ts, te, target, flag = segment["spans"][ti]
    cs, ce, collocate, _ = segment["spans"][ci]
    require(target == TARGET and flag and collocate == row["collocate"], "Example token/target mismatch")
    distance = abs(ci-ti)
    if run.startswith("window"):
        require(1 <= distance <= int(run.removeprefix("window")), "Example lies outside counted window")
    record = recs[rid]
    return {"method": run, "collocate": collocate, "obs_local": row["obs_local"],
            "p_value": row["p_value"], "record_id": rid, "unit_id": uid,
            "title": record.get("title", ""), "author": record.get("author", ""),
            "orig_sentence": texts[rid][base+segment["sentence_start"]:base+segment["sentence_end"]],
            "counted_orig_segment": texts[rid][base+segment["start"]:base+segment["end"]],
            "counted_segment_tokens": " ".join(segment["tokens"]),
            "target_orig_char": texts[rid][base+ts:base+te],
            "target_orig_offset_in_record": base+ts, "target_simp_offset_in_unit": ts,
            "collocate_orig_text": texts[rid][base+cs:base+ce],
            "collocate_orig_start_in_record": base+cs, "collocate_orig_end_in_record": base+ce,
            "collocate_simp_start_in_unit": cs, "collocate_simp_end_in_unit": ce,
            "token_distance": distance if run.startswith("window") else "same_segment",
            "orig_sentence_contains_excluded_quote": segment["sentence_contains_excluded_quote"],
            "note": "原文句內被排除引詩未參與計數" if segment["sentence_contains_excluded_quote"] else ""}


def build_tokenization_comparisons(new_processed_root, baseline_root, recs, texts, units, all_kept):
    """Read-only alignment of v4 re-tokenisation against the v3 baseline.

    Alignment is by original character ranges (segment start/end in unit),
    never by token index. Returns comparison rows, per-unit summaries and a
    dict of counts; raises on structural misalignment.
    """
    if baseline_root is None or not (baseline_root / "data/processed").is_dir():
        return None
    change_rows, qi_rows, summary_rows = [], [], []
    counts = Counter()
    for unit in units:
        uid, rid = unit["unit_id"], unit["record_id"]
        base = int(unit["start_0based"])
        old_lines = (baseline_root / "data/processed/segments" / f"{uid}.txt").read_bytes().decode("utf-8").splitlines()
        old_index = read_tsv(baseline_root / "data/processed/segment_index" / f"{uid}.tsv", INDEX_COLUMNS)
        old_simp = (baseline_root / "data/processed/simplified" / f"{uid}.txt").read_bytes().decode("utf-8")
        new_simp = (new_processed_root / "simplified" / f"{uid}.txt").read_bytes().decode("utf-8")
        require(old_simp == new_simp, f"simplified text differs from baseline: {uid}")
        require(len(old_lines) == len(old_index) == len(all_kept[uid]),
                f"kept-segment count differs from baseline: {uid}")
        old_tok_total = new_tok_total = changed_seg = 0
        for n, seg in enumerate(all_kept[uid]):
            require(int(old_index[n]["start_in_unit"]) == seg["start"]
                    and int(old_index[n]["end_in_unit"]) == seg["end"],
                    f"segment char range differs from baseline: {uid}#{n}")
            old_tokens = old_lines[n].split()
            new_tokens = seg["tokens"]
            old_tok_total += len(old_tokens)
            new_tok_total += len(new_tokens)
            changed = old_tokens != new_tokens
            if changed:
                changed_seg += 1
            change_rows.append({
                "record_id": rid, "unit_id": uid,
                "title": recs[rid].get("title", ""), "author": recs[rid].get("author", ""),
                "segment_in_unit": n, "start_in_unit": seg["start"], "end_in_unit": seg["end"],
                "orig_segment": texts[rid][base+seg["start"]:base+seg["end"]],
                "old_tokens": " ".join(old_tokens), "new_tokens": " ".join(new_tokens),
                "old_token_count": len(old_tokens), "new_token_count": len(new_tokens),
                "changed": 1 if changed else 0})
        counts["old_tokens"] += old_tok_total
        counts["new_tokens"] += new_tok_total
        counts["changed_segments"] += changed_seg
        if changed_seg:
            counts["changed_units"] += 1
        summary_rows.append({"unit_id": uid, "title": recs[rid].get("title", ""),
                             "author": recs[rid].get("author", ""),
                             "old_tokens": old_tok_total, "new_tokens": new_tok_total,
                             "segments": len(all_kept[uid]), "changed_segments": changed_seg})
    # qi-context comparison: old target positions from baseline spans; new from new spans.
    old_targets = []
    for unit in units:
        uid = unit["unit_id"]
        old_spans = read_tsv(baseline_root / "data/processed/spans" / f"{uid}.tsv", SPAN_COLUMNS)
        old_lines = (baseline_root / "data/processed/segments" / f"{uid}.txt").read_bytes().decode("utf-8").splitlines()
        for row in old_spans:
            if row["is_target_token"] == "True":
                n = int(row["segment_in_unit"])
                old_targets.append((uid, n, int(row["simp_start_in_unit"])))
    new_targets = []
    for unit in units:
        uid = unit["unit_id"]
        for seg in all_kept[uid]:
            for s in seg["spans"]:
                if s[3]:
                    new_targets.append((uid, seg["segment_in_unit"], s[0]))
    require(len(old_targets) == len(new_targets) == 106, "target position count differs from baseline")
    require(sorted(old_targets) == sorted(new_targets), "target positions differ from baseline")
    counts["qi_positions"] = len(new_targets)
    qi_changed = 0
    for unit in units:
        uid, rid = unit["unit_id"], unit["record_id"]
        base = int(unit["start_0based"])
        old_lines = (baseline_root / "data/processed/segments" / f"{uid}.txt").read_bytes().decode("utf-8").splitlines()
        for seg in all_kept[uid]:
            targets = [s for s in seg["spans"] if s[3]]
            if not targets:
                continue
            n = seg["segment_in_unit"]
            old_tokens = old_lines[n].split()
            new_tokens = seg["tokens"]
            changed = old_tokens != new_tokens
            if changed:
                qi_changed += 1
            for (ts, te, tok, flag) in targets:
                qi_rows.append({
                    "record_id": rid, "unit_id": uid,
                    "title": recs[rid].get("title", ""), "author": recs[rid].get("author", ""),
                    "simp_offset_in_unit": ts, "orig_char": texts[rid][base + ts],
                    "orig_sentence": texts[rid][base+seg["sentence_start"]:base+seg["sentence_end"]],
                    "segment_in_unit": n,
                    "old_segment_tokens": " ".join(old_tokens),
                    "new_segment_tokens": " ".join(new_tokens),
                    "changed": 1 if changed else 0})
    counts["qi_hit_segments"] = sum(1 for unit in units for seg in all_kept[unit["unit_id"]] if any(s[3] for s in seg["spans"]))
    counts["qi_hit_segments_changed"] = qi_changed
    return {"change_rows": change_rows, "qi_rows": qi_rows, "summary_rows": summary_rows, "counts": dict(counts)}


def run_analysis(root, verified, baseline_root):
    # Keep verification usable without any of these packages.
    for name, expected in VERSIONS.items():
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError as error:
            raise RuntimeError(f"Missing dependency {name}=={expected}; install requirements before analysis") from error
        require(actual == expected, f"Dependency version mismatch: {name}={actual}, expected {expected}")
    import jieba
    import opencc
    import pandas as pd
    import qhchina
    from qhchina.analytics.collocations import find_collocates
    from scipy.stats import fisher_exact

    dict_lock = verify_dictionary_lock(root, jieba)
    selection, recs, texts, units, excluded, frozen, input_report = verified
    output = root / "output"
    processed = root / "data/processed"
    require(not output.exists() or not any(p.name != ".gitkeep" for p in output.iterdir()),
            "Output already contains files; refusing to overwrite a previous or completed run")
    require(not processed.exists() or not any(processed.iterdir()),
            "data/processed is not empty; refusing to overwrite processed data")
    cc = opencc.OpenCC("t2s")
    stopword_source = "qhchina.load_stopwords('zh_cl_sim') + OpenCC t2s; matched frozen input"
    stopword_error = None
    try:
        loaded = qhchina.load_stopwords("zh_cl_sim")
        loaded = sorted({cc.convert(word) for word in loaded})
    except Exception as error:
        loaded = sorted(frozen)
        stopword_source = "offline frozen input/stopwords_zh_cl_sim_t2s.txt after load_stopwords failure"
        stopword_error = f"{type(error).__name__}: {error}"
    require(set(loaded) == set(frozen), "Current qhchina stopword list changed; refusing to silently replace frozen input")
    stopwords = sorted(frozen)
    filters = {"min_word_length": 2, "max_p": 0.05, "stopwords": stopwords}

    # One shared dictionary-augmented tokenizer for ALL 128 units (incl. zero-hit
    # background units). No reuse of any v3 segments/tokens anywhere in this run.
    tokenizer = jieba.Tokenizer()
    tokenizer.initialize()
    tokenizer.load_userdict(str(root / DICT_DERIVED))

    unit_map = {unit["unit_id"]: unit for unit in units}
    segments, unit_checks, hits, all_kept = [], [], [], {}
    stage = Path(tempfile.mkdtemp(prefix=".scope_run_", dir=root))
    stage_processed, stage_output = stage / "processed", stage / "output"
    stage_processed.mkdir(); stage_output.mkdir()
    try:
        for unit in units:
            uid, rid = unit["unit_id"], unit["record_id"]
            base, end = int(unit["start_0based"]), int(unit["end_exclusive"])
            original = texts[rid][base:end]
            simp = cc.convert(original)
            require(len(simp) == len(original), f"OpenCC changed character length; source/quote coordinates need a new mapping: {uid}")
            require("炁" not in original, f"Unconfigured variant 炁 requires a documented target rule: {uid}")
            require({i for i, ch in enumerate(original) if ch in "氣气"}
                    == {i for i, ch in enumerate(simp) if ch == TARGET},
                    f"OpenCC target positions shifted or changed: {uid}")
            intervals = sorted({(max(a, base)-base, min(b, end)-base) for a, b in excluded[rid]
                                if a < end and base < b})
            for a, b in intervals:
                require(simp[a:b] == cc.convert(original[a:b]),
                        f"OpenCC quote-coordinate mapping changed: {uid}:{a}-{b}")
            plan = segment_plan(simp, intervals)
            kept = [part for part in plan if not part["excluded"]]
            current = rebuild(unit, simp, kept, tokenizer)
            retained_positions = {a for s in current for a, b, word, flag in s["spans"] if flag}
            all_positions = {i for i, char in enumerate(simp) if char == TARGET}
            excluded_positions = {p for p in all_positions if any(a <= p < b for a, b in intervals)}
            require(retained_positions.isdisjoint(excluded_positions) and retained_positions | excluded_positions == all_positions,
                    f"Target-position conservation failed: {uid}")
            for s in current:
                require(not any(a < s["end"] and s["start"] < b for a, b in intervals), f"Kept segment crosses excluded quote: {uid}")
                require(len(s["tokens"]) <= MAX_SENTENCE_LENGTH,
                        f"Segment exceeds explicit max_sentence_length={MAX_SENTENCE_LENGTH}; refusing truncation: {uid}, segment {s['segment_in_unit']}, {len(s['tokens'])} tokens")
            spans, indexes = [], []
            for s in current:
                indexes.append({"segment_in_unit": s["segment_in_unit"], "sentence_index": s["sentence_index"],
                                "start_in_unit": s["start"], "end_in_unit": s["end"],
                                "sentence_contains_excluded_quote": s["sentence_contains_excluded_quote"]})
                for ti, (a, b, word, flag) in enumerate(s["spans"]):
                    spans.append(dict(zip(SPAN_COLUMNS, [rid, uid, s["segment_in_unit"], ti, word, a, b, flag])))
            for p in sorted(all_positions):
                sentence = next(((ss, se) for ss, se in split_sentences(simp) if ss <= p < se), None)
                require(sentence is not None, f"Target lacks sentence: {uid}:{p}")
                ss, se = sentence
                hits.append({"record_id": rid, "unit_id": uid, "title": recs[rid].get("title", ""),
                             "author": recs[rid].get("author", ""), "orig_char": original[p],
                             "orig_offset_in_record": base+p, "simp_offset_in_unit": p,
                             "counted": p in retained_positions,
                             "status": "retained_target" if p in retained_positions else "excluded_fixed_quote",
                             "orig_sentence": original[ss:se]})
            unit_checks.append({"record_id": rid, "unit_id": uid, "mode": "rebuilt_with_userdict",
                                "reused_v21": False,
                                "userdict_sha256": dict_lock["derived_dictionary"]["sha256"],
                                "source_slice_sha256": unit["sha256"], "simplified_sha256": sha(simp.encode("utf-8")),
                                "all_qi_chars": len(all_positions), "retained_target_tokens": len(retained_positions),
                                "excluded_quote_qi_chars": len(excluded_positions), "kept_segments_all": len(current),
                                "kept_segments_nonempty": sum(bool(s["tokens"]) for s in current),
                                "tokens": sum(len(s["tokens"]) for s in current),
                                "max_segment_tokens": max((len(s["tokens"]) for s in current), default=0),
                                "quote_boundary_check": "passed", "target_conservation": "passed",
                                "token_reconstruction": "passed"})
            for folder in ("simplified", "segments"):
                (stage_processed / folder).mkdir(exist_ok=True)
            (stage_processed / "simplified" / f"{uid}.txt").write_text(simp, encoding="utf-8", newline="")
            (stage_processed / "segments" / f"{uid}.txt").write_text("\n".join(" ".join(s["tokens"]) for s in current) + ("\n" if current else ""), encoding="utf-8", newline="")
            write_rows(stage_processed / "spans" / f"{uid}.tsv", spans, SPAN_COLUMNS, "\t")
            write_rows(stage_processed / "segment_index" / f"{uid}.tsv", indexes, INDEX_COLUMNS, "\t")
            segments.extend(s for s in current if s["tokens"])
            all_kept[uid] = current
        require(len(unit_checks) == selection["expected_units"], "Not all selected units were processed")
        require(sum(c["mode"] == "rebuilt_with_userdict" for c in unit_checks) == len(unit_checks)
                and all(not c["reused_v21"] for c in unit_checks), "A unit was not re-tokenised with the dictionary tokenizer")
        target_total = sum(s["tokens"].count(TARGET) for s in segments)
        require(target_total == sum(row["counted"] for row in hits), "Global target conservation failed")
        require(target_total > 0 and segments, "Selected corpus has no retained target or nonempty background")

        comparison = build_tokenization_comparisons(stage_processed, baseline_root, recs, texts, units, all_kept)

        results, run_stats, table_checks, examples = {}, {}, [], []
        for run, method, horizon in (("window5", "window", 5), ("window10", "window", 10), ("sentence", "sentence", None)):
            kwargs = {"method": method}
            if horizon is not None:
                kwargs["horizon"] = horizon
            df = find_collocates(sentences=[s["tokens"] for s in segments], target_words=[TARGET],
                                 filters=filters, alternative="greater", correction=None,
                                 sort_by="obs_local", ascending=False, return_type="dataframe",
                                 max_sentence_length=MAX_SENTENCE_LENGTH, **kwargs)
            stats = simulate(segments, method, horizon)
            checks = verify_table(df, stats, run, set(stopwords), fisher_exact)
            table_checks.extend(checks)
            for row in df.to_dict("records"):
                require(row["collocate"] in stats["examples"], f"Result lacks a real example: {run}:{row['collocate']}")
                examples.append(example_row(run, row, stats["examples"][row["collocate"]], recs, texts, unit_map))
            run_stats[run] = {k: v for k, v in stats.items() if k not in ("global", "local", "examples")}
            run_stats[run].update(rows=len(df), candidate_types_tested=sum(len(w) >= 2 and w not in stopwords for w in stats["local"]),
                                  independent_obs_exp_ratio_fisher_check="passed", correction=None)
            results[run] = df
            df.to_csv(stage_output / f"collocates_{run}.csv", index=False, encoding="utf-8-sig")
            print(f"\n[完成] {run}：{len(df)}列；前20列（obs_local降序）", flush=True)
            print(df.head(20).to_string(index=False), flush=True)
        ex_fields = ["method", "collocate", "obs_local", "p_value", "record_id", "unit_id", "title", "author",
                     "orig_sentence", "counted_orig_segment", "counted_segment_tokens", "target_orig_char",
                     "target_orig_offset_in_record", "target_simp_offset_in_unit", "collocate_orig_text",
                     "collocate_orig_start_in_record", "collocate_orig_end_in_record", "collocate_simp_start_in_unit",
                     "collocate_simp_end_in_unit", "token_distance", "orig_sentence_contains_excluded_quote", "note"]
        write_rows(stage_output / "collocate_examples.csv", examples, ex_fields)
        write_rows(stage_output / "qi_hits.csv", hits, ["record_id", "unit_id", "title", "author", "orig_char",
                   "orig_offset_in_record", "simp_offset_in_unit", "counted", "status", "orig_sentence"])
        write_rows(stage_output / "unit_verification.csv", unit_checks, list(unit_checks[0]))
        write_rows(stage_output / "table_verification.csv", table_checks, ["method", "collocate", "a", "b", "c", "d", "N", "R1", "C1", "exp_verified", "ratio_verified", "p_verified", "passed"])
        comparison_info = None
        if comparison is not None:
            write_rows(stage_output / "tokenization_changes.csv", comparison["change_rows"],
                       ["record_id", "unit_id", "title", "author", "segment_in_unit", "start_in_unit", "end_in_unit",
                        "orig_segment", "old_tokens", "new_tokens", "old_token_count", "new_token_count", "changed"])
            write_rows(stage_output / "qi_context_tokenization_comparison.csv", comparison["qi_rows"],
                       ["record_id", "unit_id", "title", "author", "simp_offset_in_unit", "orig_char",
                        "orig_sentence", "segment_in_unit", "old_segment_tokens", "new_segment_tokens", "changed"])
            write_rows(stage_output / "tokenization_summary.csv", comparison["summary_rows"],
                       ["unit_id", "title", "author", "old_tokens", "new_tokens", "segments", "changed_segments"])
            comparison_info = comparison["counts"]
        caution = ("本次為探索性分析，Fisher 單尾 greater，p≤0.05，correction=None，未作多重檢定校正；"
                   "顯著列不是詞義分類或文學結論，低頻及重引材料須回看例句與語料構成。"
                   "所有所選單元（含零命中）合併作背景，沒有前後期分組；文論重引保留並分別計数，不能宣稱觀察值統計獨立。")
        caveats = selection.get("scope_caveats", [])
        require(caveats, "Selection scope caveats are missing")
        notes = ("氣字搭配詞本地運行方法紀錄（qi_scope_v4_dict：詞典補充分詞版）\n\n" + selection.get("scope_statement", "") + "\n\n" + caution + "\n\n"
                 + "範圍注意：\n" + "\n".join("- " + str(item) for item in caveats) + "\n\n"
                 + f"核驗輸入：{len(recs)} records，{len(units)} units；全部單元以詞典補充分詞器實際重新分詞（reused_units=0），保留氣字target={target_total}（從實際字符與tokens計算）。\n"
                 + "詞典：教師提供之詞目表（原檔 SHA " + dict_lock["original_dictionary"]["sha256"][:16] + "…；派生表 SHA " + dict_lock["derived_dictionary"]["sha256"][:16] + "…，200,756 詞目）。"
                 + "使用獨立 jieba.Tokenizer()，initialize() 後 load_userdict(派生表) 再分詞；保留 jieba 預設主詞典；詞目未提供詞頻，採用 jieba 原生省略詞頻的自動推算（分詞權重，非語料頻數），導入順序為鎖定派生表行序。\n"
                 + "OpenCC t2s後先核字符長度及quote座標；句界為。！？；…（連續省略號及閉引號同句）及換行；固定excluded=1區間作硬邊界，不拼接兩側。\n"
                 + "保留段在每個气位置定向拆分並重插單字，再以載入詞典的 Tokenizer（default、HMM=True）分詞；只去純標點／空白／控制格式token，不刪短句。空段留在單元核驗，qhchina輸入為所有非空保留段。\n"
                 + f"qhchina max_sentence_length={MAX_SENTENCE_LENGTH}明示傳入；任一保留段超限即停止，避免靜默截斷。\n"
                 + "window5/window10：obs_local是被至少一個氣窗口覆蓋的非目標詞位置數，重疊窗口只計一次；N為全部token數−氣target數，R1為窗口覆蓋非目標位置數。\n"
                 + "sentence：每個非空保留句段每詞只計一次；N為非空句段數，R1為含氣句段數。引詩切斷後的句段不等同未切斷原句。\n"
                 + "三表各自核驗obs_local、obs_global、exp=R1×C1/N、ratio=obs/exp及scipy Fisher p；列聯表[[a,R1-a],[C1-a,N-R1-C1+a]]，並核驗顯著結果清單完整性。\n"
                 + "filters只用於結果：min_word_length=2、max_p=0.05及固定40條stopwords，沒有先刪背景token。sort_by=obs_local，ascending=False。\n"
                 + "停用詞來源：" + stopword_source + ("；失敗原因：" + stopword_error if stopword_error else "") + "\n"
                 + "本輪全部128單元實際重建，未沿用任何舊句段／tokens；逐單元記錄mode=rebuilt_with_userdict。\n"
                 + "真實例句來自實際計數事件，保留原文及字符位置；原句含排除引詩的情況已標記，排除片段沒有參與窗口或同段計算。\n\n"
                 + json.dumps(run_stats, ensure_ascii=False, indent=2) + "\n")
        (stage_output / "method_notes.txt").write_text(notes.replace("計数", "計數"), encoding="utf-8", newline="")
        log = {"status": "complete", "analysis_executed": True, "package": "qi_scope_v4_dict",
               "completed_utc": datetime.now(timezone.utc).isoformat(),
               "python": sys.version, "python_executable": sys.executable,
               "platform": platform.platform(),
               "find_collocates_signature": str(inspect.signature(find_collocates)),
               "runner_sha256": sha(Path(__file__).read_bytes()),
               "input_verification": input_report, "versions": {name: importlib.metadata.version(name) for name in [*VERSIONS, "scipy", "pandas"]},
               "scope_statement": selection.get("scope_statement"), "scope_caveats": caveats,
               "rules": selection["rules"], "selection_records": len(recs), "selection_units": len(units),
               "dictionary": dict_lock,
               "tokenizer": {"class": "jieba.Tokenizer", "initialize_called": True,
                             "userdict_loaded": str(root / DICT_DERIVED), "main_dict_retained": True,
                             "mode": "default", "HMM": True, "reused_units": 0,
                             "rebuilt_units": len(unit_checks)},
               "all_qi_chars": len(hits), "retained_target_tokens": target_total,
               "excluded_quote_qi_chars": sum(not row["counted"] for row in hits),
               "zero_target_units_included": sum(row["retained_target_tokens"] == 0 for row in unit_checks),
               "nonempty_background_segments": len(segments), "background_tokens": sum(len(s["tokens"]) for s in segments),
               "max_segment_tokens": max(len(s["tokens"]) for s in segments), "max_sentence_length": MAX_SENTENCE_LENGTH,
               "stopwords": {"count": len(stopwords), "source": stopword_source, "fallback_error": stopword_error},
               "runs": run_stats, "example_rows": len(examples),
               "tokenization_comparison_vs_v3": comparison_info,
               "verification": {"input_lock": "passed", "dictionary_lock": "passed",
                                "all_selected_units_processed": "passed",
                                "all_units_rebuilt_with_userdict_reused_units_0": "passed",
                                "target_position_conservation": "passed", "quote_boundaries": "passed",
                                "token_reconstruction": "passed", "obs_exp_ratio_fisher_all_rows": "passed",
                                "significant_row_completeness": "passed", "real_examples": "passed"},
               "output_sha256": {p.name: sha(p.read_bytes()) for p in stage_output.iterdir()},
               "processed_sha256": {p.relative_to(stage_processed).as_posix(): sha(p.read_bytes()) for p in stage_processed.rglob("*") if p.is_file()}}
        (stage_output / "analysis_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2)+"\n", encoding="utf-8", newline="")
        require(not output.exists() or not any(p.name != ".gitkeep" for p in output.iterdir()), "Output changed during analysis; refusing publication")
        require(not processed.exists() or not any(processed.iterdir()), "Processed directory changed during analysis; refusing publication")
        if processed.exists():
            processed.rmdir()
        shutil.move(str(stage_processed), str(processed))
        output.mkdir(exist_ok=True)
        for p in stage_output.iterdir():
            require(not (output / p.name).exists(), f"Output already exists: {p.name}")
            shutil.move(str(p), str(output / p.name))
        return {"status": "complete", "records": len(recs), "units": len(units),
                "retained_targets": target_total, "runs": run_stats, "output": str(output),
                "tokenization_comparison_vs_v3": comparison_info}
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-inputs", action="store_true", help="Standard-library-only input checks; do not run analysis or write results")
    parser.add_argument("--baseline-root", type=Path, default=None,
                        help="Optional v3 package root for read-only tokenisation comparison "
                             "(default: sibling qi_scope_v3)")
    parser.add_argument("--package-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        root = args.package_root.resolve()
        verified = verify_inputs(root)
        if args.verify_inputs:
            print(json.dumps(verified[-1], ensure_ascii=False, indent=2))
            return 0
        baseline = args.baseline_root
        if baseline is None:
            candidate = root.parent / "qi_scope_v3"
            if (candidate / "data/processed").is_dir():
                baseline = candidate
        result = run_analysis(root, verified, baseline)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as error:
        print(f"ERROR: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
