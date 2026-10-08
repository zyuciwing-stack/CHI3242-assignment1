#!/usr/bin/env python3
"""Verify the locked scope package or run its three pooled qhchina analyses.

Verification uses the standard library only. Third party imports occur only in
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


def reuse_roots(root, explicit):
    candidates = []
    if explicit:
        p = explicit.resolve()
        require(p.is_dir(), f"Existing project root does not exist: {p}")
        candidates.append(p if p.name == "qi_corpus_analysis_v21" else p / "data/qi_corpus_analysis_v21")
    for parent in [root, *list(root.parents)[:4]]:
        candidates.append(parent / "data/qi_corpus_analysis_v21")
    seen = set()
    return [p for p in candidates if p.is_dir() and not (p in seen or seen.add(p))]


def try_reuse(base, unit, simp, kept_plan):
    """Accept a unit only when all index/token/source checks pass."""
    uid = unit["unit_id"]
    found = {}
    for name, suffix in (("segments", ".txt"), ("spans", ".tsv"), ("segment_index", ".tsv")):
        matches = list((base / name).glob(f"*/{uid}{suffix}"))
        if len(matches) != 1:
            return None, f"{name}: expected one file, found {len(matches)}"
        found[name] = matches[0]
    # A malformed present TSV is an explicit error, never an empty background.
    rows = read_tsv(found["spans"], SPAN_COLUMNS)
    indexes = read_tsv(found["segment_index"], INDEX_COLUMNS)
    lines = found["segments"].read_bytes().decode("utf-8").splitlines()
    try:
        require(len(indexes) == len(kept_plan) == len(lines), "Segment/index/plan counts differ")
        grouped = defaultdict(list)
        for row in rows:
            require(row["record_id"] == unit["record_id"] and row["unit_id"] == uid, "Span unit/record mismatch")
            grouped[int(row["segment_in_unit"])].append(row)
        require(set(grouped) <= set(range(len(kept_plan))), "Unexpected segment in spans")
        segments = []
        for n, (index, part, line) in enumerate(zip(indexes, kept_plan, lines)):
            require(int(index["segment_in_unit"]) == n, "Non-contiguous segment index")
            for name, expected in (("sentence_index", part["sentence_index"]),
                                   ("start_in_unit", part["start"]), ("end_in_unit", part["end"]),
                                   ("sentence_contains_excluded_quote", part["sentence_contains_excluded_quote"])):
                require(int(index[name]) == expected, f"Segment plan mismatch: {name}")
            spans = []
            source_rows = sorted(grouped[n], key=lambda row: int(row["token_index_in_segment"]))
            require([int(row["token_index_in_segment"]) for row in source_rows] == list(range(len(source_rows))), "Token indexes are incomplete or duplicated")
            for row in source_rows:
                a, b = int(row["simp_start_in_unit"]), int(row["simp_end_in_unit"])
                token = row["token"]
                flag = row["is_target_token"]
                require(flag in ("True", "False"), "Invalid target flag")
                require(part["start"] <= a < b <= part["end"] and simp[a:b] == token, "Token/source position mismatch")
                require(not all(drop_char(ch) for ch in token), "Pure punctuation token retained")
                require((flag == "True") == (token == TARGET), "Directed target flag mismatch")
                require(TARGET not in token or token == TARGET, "Unsplit compound target")
                spans.append((a, b, token, flag == "True"))
            require(all(x[1] <= y[0] for x, y in zip(spans, spans[1:])), "Token spans overlap")
            require(line.split() == [s[2] for s in spans], "Segment tokens differ from span tokens")
            require("".join(s[2] for s in spans) == "".join(ch for ch in simp[part["start"]:part["end"]] if not drop_char(ch)), "Token reconstruction differs from source")
            expected = {p for p in range(part["start"], part["end"]) if simp[p] == TARGET}
            require({a for a, b, token, flag in spans if flag} == expected, "Target positions incomplete")
            segments.append({**part, "segment_in_unit": n, "spans": spans,
                             "tokens": [s[2] for s in spans], "unit_id": uid, "record_id": unit["record_id"]})
        return segments, {"root": str(base), "files": {str(p): sha(p.read_bytes()) for p in found.values()}}
    except (ValueError, KeyError, TypeError) as error:
        return None, str(error)


def rebuild(unit, simp, kept_plan, jieba):
    segments = []
    for number, part in enumerate(kept_plan):
        a, b = part["start"], part["end"]
        targets = [p for p in range(a, b) if simp[p] == TARGET]
        spans, previous = [], a
        for p in targets + [b]:
            if previous < p:
                for token, start, end in jieba.tokenize(simp[previous:p], mode="default", HMM=True):
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
    # Verify completeness too, rather than merely validating the rows that survived.
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


def run_analysis(root, verified, existing_project_root):
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
    old_roots = reuse_roots(root, existing_project_root)
    unit_map = {unit["unit_id"]: unit for unit in units}
    segments, unit_checks, hits, reuse_log = [], [], [], []
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
            reused, attempts = None, []
            for old_root in old_roots:
                reused, reason = try_reuse(old_root, unit, simp, kept)
                attempts.append({"root": str(old_root), "detail": reason, "accepted": reused is not None})
                if reused is not None:
                    break
            current = reused if reused is not None else rebuild(unit, simp, kept, jieba)
            reuse_log.append({"unit_id": uid, "mode": "validated_v21_reuse" if reused is not None else "rebuilt", "attempts": attempts})
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
            unit_checks.append({"record_id": rid, "unit_id": uid, "mode": reuse_log[-1]["mode"],
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
        require(len(unit_checks) == selection["expected_units"], "Not all selected units were processed")
        target_total = sum(s["tokens"].count(TARGET) for s in segments)
        require(target_total == sum(row["counted"] for row in hits), "Global target conservation failed")
        require(target_total > 0 and segments, "Selected corpus has no retained target or nonempty background")
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
        # Native result DataFrame exports; audit tables use explicit schemas, including empty results.
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
        caution = ("本次為探索性分析，Fisher 單尾 greater，p≤0.05，correction=None，未作多重檢定校正；"
                   "顯著列不是詞義分類或文學結論，低頻及重引材料須回看例句與語料構成。"
                   "所有所選單元（含零命中）合併作背景，沒有前後期分組；文論重引保留並分別計数，不能宣稱觀察值統計獨立。")
        caveats = selection.get("scope_caveats", [])
        require(caveats, "Selection scope caveats are missing")
        notes = ("氣字搭配詞本地運行方法紀錄\n\n" + selection.get("scope_statement", "") + "\n\n" + caution + "\n\n"
                 + "範圍注意：\n" + "\n".join("- " + str(item) for item in caveats) + "\n\n"
                 + f"核驗輸入：{len(recs)} records，{len(units)} units；全部單元參與處理，保留氣字target={target_total}（從實際字符與tokens計算）。\n"
                 + "OpenCC t2s後先核字符長度及quote座標；句界為。！？；…（連續省略號及閉引號同句）及換行；固定excluded=1區間作硬邊界，不拼接兩側。\n"
                 + "保留段在每個气位置定向拆分並重插單字，再以jieba default、HMM=True分詞；只去純標點／空白／控制格式token，不刪短句。空段留在單元核驗，qhchina輸入為所有非空保留段。\n"
                 + f"qhchina max_sentence_length={MAX_SENTENCE_LENGTH}明示傳入；任一保留段超限即停止，避免靜默截斷。\n"
                 + "window5/window10：obs_local是被至少一個氣窗口覆蓋的非目標詞位置數，重疊窗口只計一次；N為全部token數−氣target數，R1為窗口覆蓋非目標位置數。\n"
                 + "sentence：每個非空保留句段每詞只計一次；N為非空句段數，R1為含氣句段數。引詩切斷後的句段不等同未切斷原句。\n"
                 + "三表各自核驗obs_local、obs_global、exp=R1×C1/N、ratio=obs/exp及scipy Fisher p；列聯表[[a,R1-a],[C1-a,N-R1-C1+a]]，並核驗顯著結果清單完整性。\n"
                 + "filters只用於結果：min_word_length=2、max_p=0.05及固定40條stopwords，沒有先刪背景token。sort_by=obs_local，ascending=False。\n"
                 + "停用詞來源：" + stopword_source + ("；失敗原因：" + stopword_error if stopword_error else "") + "\n"
                 + "重用v21只在全部segment_index、spans、tokens、source及fixed-quote切分逐單元一致時接受；未通過／缺失單元重新分詞，缺必需TSV header則明報停止。\n"
                 + "真實例句來自實際計數事件，保留原文及字符位置；原句含排除引詩的情況已標記，排除片段沒有參與窗口或同段計算。\n\n"
                 + json.dumps(run_stats, ensure_ascii=False, indent=2) + "\n")
        (stage_output / "method_notes.txt").write_text(notes.replace("計数", "計數"), encoding="utf-8", newline="")
        panels = "".join(f'<section id="{run}" class="result"'+('' if i == 0 else ' hidden')+f'><h2>{run}（{len(df)}列）</h2><p><a href="collocates_{run}.csv">完整CSV</a></p>'+df.to_html(index=False, border=0)+"</section>" for i, (run, df) in enumerate(results.items()))
        page = ("<!doctype html><html lang=\"zh-Hant\"><meta charset=\"utf-8\"><title>氣字搭配詞：所選語料合併分析</title>"
                "<style>body{font-family:system-ui,sans-serif;margin:2rem;max-width:1400px}table{border-collapse:collapse;font-size:14px}td,th{border:1px solid #aaa;padding:.35rem}select{font:inherit;padding:.4rem}section{overflow:auto}li{margin:.5rem 0}pre{white-space:pre-wrap}</style>"
                "<h1>氣字搭配詞：所選語料合併分析</h1><p>" + html.escape(caution.replace("計数", "計數")) + "</p><ul>"
                + "".join("<li>"+html.escape(str(item))+"</li>" for item in caveats) + "</ul>"
                + f"<p>{len(recs)} records／{len(units)} units；實算保留target {target_total}；非空保留句段 {len(segments)}；最大段長 {max(len(s['tokens']) for s in segments)} token（上限256，超限即拒絕）。</p>"
                + '<label>顯示分析表 <select id="method">'+"".join(f'<option value="{run}">{run}</option>' for run in results)+"</select></label>"
                + '<details><summary>表格欄位怎麼讀</summary><ul>'
                + '<li>target：目標「气」；collocate：與目標共現的詞。</li>'
                + '<li>obs_local：實際共現數；window按候選詞位置，sentence按非空保留句段計數。</li>'
                + '<li>exp_local：依本次背景頻率算出的期望共現數（R1×C1/N），不是手動設定。</li>'
                + '<li>ratio_local＝obs_local/exp_local：實際為期望的多少倍，可以大於1；高倍數須同看實際次數。</li>'
                + '<li>obs_global：候選詞在全背景的頻次；window為token次數，sentence為含詞句段數。</li>'
                + '<li>p_value：Fisher單尾原始p；在無額外關聯的檢定模型下，出現至少同樣強共現的機率。不是詞義正確率，也未作多重比較校正。</li>'
                + '</ul></details>' + panels
                + '<p><a href="collocate_examples.csv">真實例句CSV</a> · <a href="table_verification.csv">逐列核驗</a> · <a href="unit_verification.csv">單元核驗</a> · <a href="qi_hits.csv">氣字位置</a> · <a href="method_notes.txt">方法紀錄</a></p>'
                + '<script>document.getElementById("method").addEventListener("change",function(){document.querySelectorAll(".result").forEach(x=>x.hidden=x.id!==this.value);});</script></html>')
        (stage_output / "results.html").write_text(page, encoding="utf-8", newline="")
        log = {"status": "complete", "analysis_executed": True, "completed_utc": datetime.now(timezone.utc).isoformat(),
               "python": sys.version, "python_executable": sys.executable,
               "platform": platform.platform(),
               "find_collocates_signature": str(inspect.signature(find_collocates)),
               "runner_sha256": sha(Path(__file__).read_bytes()),
               "input_verification": input_report, "versions": {name: importlib.metadata.version(name) for name in [*VERSIONS, "scipy", "pandas"]},
               "scope_statement": selection.get("scope_statement"), "scope_caveats": caveats,
               "rules": selection["rules"], "selection_records": len(recs), "selection_units": len(units),
               "all_qi_chars": len(hits), "retained_target_tokens": target_total,
               "excluded_quote_qi_chars": sum(not row["counted"] for row in hits),
               "zero_target_units_included": sum(row["retained_target_tokens"] == 0 for row in unit_checks),
               "nonempty_background_segments": len(segments), "background_tokens": sum(len(s["tokens"]) for s in segments),
               "max_segment_tokens": max(len(s["tokens"]) for s in segments), "max_sentence_length": MAX_SENTENCE_LENGTH,
               "stopwords": {"count": len(stopwords), "source": stopword_source, "fallback_error": stopword_error},
               "reuse": reuse_log, "runs": run_stats, "example_rows": len(examples),
               "verification": {"input_lock": "passed", "all_selected_units_processed": "passed",
                                "target_position_conservation": "passed", "quote_boundaries": "passed",
                                "token_reconstruction": "passed", "obs_exp_ratio_fisher_all_rows": "passed",
                                "significant_row_completeness": "passed", "real_examples": "passed"},
               "output_sha256": {p.name: sha(p.read_bytes()) for p in stage_output.iterdir()},
               "processed_sha256": {p.relative_to(stage_processed).as_posix(): sha(p.read_bytes()) for p in stage_processed.rglob("*") if p.is_file()}}
        (stage_output / "analysis_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2)+"\n", encoding="utf-8", newline="")
        # Publish only after all checks. Never replace existing generated files.
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
                "retained_targets": target_total, "runs": run_stats, "output": str(output)}
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-inputs", action="store_true", help="Standard-library-only input checks; do not run analysis or write results")
    parser.add_argument("--existing-project-root", type=Path, help="Optional original project containing data/qi_corpus_analysis_v21")
    parser.add_argument("--package-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        root = args.package_root.resolve()
        verified = verify_inputs(root)
        result = verified[-1] if args.verify_inputs else run_analysis(root, verified, args.existing_project_root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as error:
        print(f"ERROR: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
