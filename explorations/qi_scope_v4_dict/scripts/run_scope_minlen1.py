#!/usr/bin/env python3
"""Supplementary single-character collocation analysis (min_word_length=1,
no stopword result filter) for qi_scope_v4_dict.

Reads the EXACT analysis tokens produced by the v4 dictionary-augmented formal
run from data/processed/segments/*.txt (no re-OpenCC, no re-splitting, no
re-tokenising). Compared with the v4 formal run, the RESULT filters change
twice: min_word_length 2 -> 1, and the frozen 40-word reference stopword list
is NO LONGER applied (stopwords=[]). All other settings (target, background
units, segment/unit/quote hard boundaries, horizon 5/10, sentence, max_p=0.05,
alternative="greater", correction=None, sort_by obs_local desc,
max_sentence_length=256) are unchanged. Stopwords were only ever a result
filter: they still occupy windows and the background statistics N/R1/C1 are
untouched.

The frozen input/stopwords_zh_cl_sim_t2s.txt snapshot (40 items) is NOT
modified; it is still verified read-only against
qhchina.load_stopwords('zh_cl_sim') + OpenCC t2s and is logged as the
reference list (applied count = 0 this round).

The v4 formal runner (scripts/run_scope_qhchina.py) is NOT modified; its verify
and simulate helpers are imported read-only. Verification here uses min length 1
with no stopword filter and is therefore not a copy of the formal ≥2 checks.

Optional --old-dir points at a previous minlen1 output directory; when given,
every previously kept row is checked value-identical in the new tables and newly
added rows are checked to be single-character words from the frozen reference
stopword list that still pass the original p threshold.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import inspect
import json
import math
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_scope_qhchina as R  # noqa: E402  (stdlib-only at import time)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
PROC = ROOT / "data/processed"
TARGET = "气"
MINLEN = 1
VERSIONS = {"qhchina": "0.2.7", "jieba": "0.42.1", "opencc-python-reimplemented": "0.1.7"}
RUNS = (("window5", "window", 5), ("window10", "window", 10), ("sentence", "sentence", None))
EXAMPLE_FIELDS = ["method", "collocate", "obs_local", "p_value", "record_id", "unit_id", "title",
                  "author", "orig_sentence", "counted_orig_segment", "counted_segment_tokens",
                  "target_orig_char", "target_orig_offset_in_record", "target_simp_offset_in_unit",
                  "collocate_orig_text", "collocate_orig_start_in_record", "collocate_orig_end_in_record",
                  "collocate_simp_start_in_unit", "collocate_simp_end_in_unit", "token_distance",
                  "orig_sentence_contains_excluded_quote", "token_length", "at_split_boundary",
                  "original_abuts_target", "note"]
TABLE_FIELDS = ["method", "collocate", "a", "b", "c", "d", "N", "R1", "C1",
                "exp_verified", "ratio_verified", "p_verified", "passed", "token_length"]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def digest_of_processed() -> str:
    entries = []
    for p in sorted(PROC.rglob("*")):
        if p.is_file():
            entries.append((p.relative_to(PROC).as_posix(), p.stat().st_size, sha(p)))
    return hashlib.sha256(json.dumps(entries).encode("utf-8")).hexdigest()


def load_segments(selection):
    """Rebuild the exact non-empty kept segments from the formal processed output."""
    segments = []
    unit_map = {}
    for unit in selection["units"]:
        uid = unit["unit_id"]
        unit_map[uid] = unit
        seg_file = PROC / "segments" / f"{uid}.txt"
        spans = R.read_tsv(PROC / "spans" / f"{uid}.tsv", R.SPAN_COLUMNS)
        indexes = R.read_tsv(PROC / "segment_index" / f"{uid}.tsv", R.INDEX_COLUMNS)
        simp = (PROC / "simplified" / f"{uid}.txt").read_bytes().decode("utf-8")
        sentences = R.split_sentences(simp)
        grouped = {}
        for row in spans:
            grouped.setdefault(int(row["segment_in_unit"]), []).append(row)
        lines = seg_file.read_bytes().decode("utf-8").splitlines()
        R.require(len(lines) == len(indexes), f"segment line/index count differs: {uid}")
        for n, line in enumerate(lines):
            tokens = line.split()
            if not tokens:
                continue
            source_rows = sorted(grouped.get(n, []), key=lambda row: int(row["token_index_in_segment"]))
            R.require([row["token"] for row in source_rows] == tokens, f"spans/tokens differ: {uid}#{n}")
            idx = indexes[n]
            start = int(idx["start_in_unit"])
            sentence = next(((ss, se) for ss, se in sentences if ss <= start < se), None)
            R.require(sentence is not None, f"segment lacks sentence: {uid}#{n}")
            segments.append({
                "record_id": unit["record_id"], "unit_id": uid,
                "segment_in_unit": n,
                "sentence_index": int(idx["sentence_index"]),
                "start": start, "end": int(idx["end_in_unit"]),
                "sentence_start": sentence[0], "sentence_end": sentence[1],
                "sentence_contains_excluded_quote": int(idx["sentence_contains_excluded_quote"]),
                "spans": [(int(s["simp_start_in_unit"]), int(s["simp_end_in_unit"]), s["token"],
                           s["is_target_token"] == "True") for s in source_rows],
                "tokens": tokens,
            })
    return segments, unit_map


def verify_rows(df, stats, run, fisher_exact):
    checks = []
    require = R.require
    require(set(R.RESULT_COLUMNS) <= set(df.columns), f"result columns missing: {run}")
    require(not df["collocate"].duplicated().any(), f"duplicate collocate rows: {run}")
    for row in df.to_dict("records"):
        word = row["collocate"]
        require(row["target"] == TARGET and len(word) >= MINLEN,
                f"result filter mismatch: {run}:{word}")
        a = stats["local"][word]
        R1, C1, N = stats["R1"], stats["global"][word], stats["N_fisher"]
        b, c = R1 - a, C1 - a
        d = N - a - b - c
        require(min(a, b, c, d) >= 0 and N > 0, f"invalid contingency table: {run}:{word}")
        expected = R1 * C1 / N
        ratio = a / expected
        p = float(fisher_exact([[a, b], [c, d]], alternative="greater").pvalue)
        for field, actual in (("obs_local", a), ("obs_global", C1), ("exp_local", expected),
                              ("ratio_local", ratio), ("p_value", p)):
            require(math.isclose(float(row[field]), actual, rel_tol=1e-7, abs_tol=1e-10),
                    f"independent {field} mismatch: {run}:{word}; qhchina={row[field]}, independent={actual}")
        require(p <= 0.05 + 1e-12, f"max_p filter failed: {run}:{word}")
        checks.append({"method": run, "collocate": word, "a": a, "b": b, "c": c, "d": d,
                       "N": N, "R1": R1, "C1": C1, "exp_verified": expected,
                       "ratio_verified": ratio, "p_verified": p, "passed": True,
                       "token_length": len(word)})
    observed = df["obs_local"].tolist()
    require(observed == sorted(observed, reverse=True), f"not sorted by obs_local desc: {run}")
    eligible = set()
    for word, a in stats["local"].items():
        if len(word) < MINLEN:
            continue
        R1, C1, N = stats["R1"], stats["global"][word], stats["N_fisher"]
        b, c = R1 - a, C1 - a
        d = N - a - b - c
        require(min(a, b, c, d) >= 0, f"invalid candidate table: {run}:{word}")
        if float(fisher_exact([[a, b], [c, d]], alternative="greater").pvalue) <= 0.05:
            eligible.add(word)
    require(set(df["collocate"]) == eligible,
            f"result row set differs from independent minlen1-no-stopword filters: {run}; "
            f"missing={sorted(eligible - set(df['collocate']))[:8]}, "
            f"extra={sorted(set(df['collocate']) - eligible)[:8]}")
    return checks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-dir", type=Path, default=None,
                        help="Optional previous minlen1 output directory for value-identity checks")
    args = parser.parse_args()
    for name, expected in VERSIONS.items():
        actual = importlib.metadata.version(name)
        R.require(actual == expected, f"version mismatch: {name}={actual}")
    import opencc
    import pandas as pd
    import qhchina
    from qhchina.analytics.collocations import find_collocates
    from scipy.stats import fisher_exact

    pre_shas = {p.name: sha(p) for p in OUT.glob("*.csv")}
    pre_shas["analysis_log.json"] = sha(OUT / "analysis_log.json")
    pre_processed = digest_of_processed()

    verified = R.verify_inputs(ROOT)
    selection, recs, texts, units, excluded, frozen, input_report = verified
    segments, unit_map = load_segments(selection)

    original_log = json.loads((OUT / "analysis_log.json").read_text(encoding="utf-8"))
    n_seg = len(segments)
    n_tok = sum(len(s["tokens"]) for s in segments)
    n_tgt = sum(s["tokens"].count(TARGET) for s in segments)
    max_seg = max(len(s["tokens"]) for s in segments)
    R.require(n_seg == original_log["nonempty_background_segments"], f"segment count differs from formal run: {n_seg}")
    R.require(n_tok == original_log["background_tokens"], f"token count differs from formal run: {n_tok}")
    R.require(n_tgt == original_log["retained_target_tokens"], f"target count differs from formal run: {n_tgt}")
    R.require(max_seg <= R.MAX_SENTENCE_LENGTH, f"segment exceeds {R.MAX_SENTENCE_LENGTH}: {max_seg}")

    cc = opencc.OpenCC("t2s")
    loaded = sorted({cc.convert(w) for w in qhchina.load_stopwords("zh_cl_sim")})
    R.require(set(loaded) == set(frozen), "stopword snapshot mismatch")
    stopwords = sorted(frozen)
    R.require(len(stopwords) == 40 and len(set(stopwords)) == 40,
              "frozen reference stopword list must contain 40 distinct entries")
    filters = {"min_word_length": MINLEN, "max_p": 0.05, "stopwords": []}

    run_stats, table_checks, examples_all, results = {}, [], [], {}
    for run, method, horizon in RUNS:
        kwargs = {"method": method}
        if horizon is not None:
            kwargs["horizon"] = horizon
        df = find_collocates(sentences=[s["tokens"] for s in segments], target_words=[TARGET],
                             filters=filters, alternative="greater", correction=None,
                             sort_by="obs_local", ascending=False, return_type="dataframe",
                             max_sentence_length=R.MAX_SENTENCE_LENGTH, **kwargs)
        stats = R.simulate(segments, method, horizon)
        checks = verify_rows(df, stats, run, fisher_exact)
        table_checks.extend(checks)
        # examples: one verified event per row
        for row in df.to_dict("records"):
            word = row["collocate"]
            R.require(word in stats["examples"], f"result lacks a real example: {run}:{word}")
            base = R.example_row(run, row, stats["examples"][word], recs, texts, unit_map)
            seg_ex, ci, ti = stats["examples"][word]
            spans = seg_ex["spans"]
            ts, te, targ, flag = spans[ti]
            cs, ce, coll, _ = spans[ci]
            token_len = len(word)
            at_boundary = 1 if abs(ci - ti) == 1 else 0
            abuts = 1 if (ce == ts or cs == te) else 0
            note = base["note"]
            if token_len == 1:
                extra = []
                if at_boundary:
                    extra.append("位於氣字定向切分邊界")
                else:
                    extra.append(f"與氣字相距 {abs(ci - ti)} 詞")
                if abuts:
                    extra.append("原文連寫（如骨氣、體氣一類表達）")
                if word in stopwords:
                    extra.append("此詞原屬參考停用清單，本輪補充設定未篩除（僅取消結果篩選，未改動文本）")
                extra.append("此為切分位置說明，非詞義分類")
                note = ("；".join([x for x in (note, "單字詞項（min_word_length=1 補充設定）") if x])
                        + "。" + "；".join(extra) + "。" if extra else note)
            base.update({"token_length": token_len, "at_split_boundary": at_boundary,
                         "original_abuts_target": abuts, "note": note})
            examples_all.append(base)
        run_stats[run] = {k: v for k, v in stats.items() if k not in ("global", "local", "examples")}
        run_stats[run].update(rows=int(len(df)), single_char_rows=int(sum(1 for w in df["collocate"] if len(w) == 1)),
                              candidate_types_tested=sum(1 for w in stats["local"] if len(w) >= MINLEN),
                              independent_obs_exp_ratio_fisher_check="passed", correction=None)
        results[run] = df
        df.to_csv(OUT / f"collocates_minlen1_{run}.csv", index=False, encoding="utf-8-sig")
        print(f"[完成] minlen1 {run}：{len(df)} 列（單字 {run_stats[run]['single_char_rows']} 列）；前20列：", flush=True)
        print(df.head(20).to_string(index=False), flush=True)

    # cross-check: all len>=2 rows identical to the formal tables (all 7 columns, same order)
    cross = {}
    for run, _, _ in RUNS:
        formal = pd.read_csv(OUT / f"collocates_{run}.csv", encoding="utf-8-sig")
        new = results[run]
        new_ge2 = new[new["collocate"].str.len() >= 2].reset_index(drop=True)
        same_len = len(new_ge2) == len(formal)
        same_vals = True
        if same_len:
            for col in R.RESULT_COLUMNS:
                if col == "target":
                    same_vals &= bool((new_ge2["target"] == formal["target"]).all())
                elif col == "collocate":
                    same_vals &= bool((new_ge2["collocate"] == formal["collocate"]).all())
                else:
                    same_vals &= bool(pd.Series(
                        [math.isclose(a, b, rel_tol=1e-7, abs_tol=1e-10) for a, b in
                         zip(new_ge2[col].astype(float), formal[col].astype(float))]).all())
        R.require(same_len and same_vals, f"len>=2 rows differ from formal table: {run}")
        cross[run] = {"len_ge2_rows": int(len(new_ge2)), "identical_to_formal": True,
                      "formal_rows": int(len(formal))}

    # optional comparison against the previous minlen1 tables (stopword-filtered version):
    # every previously kept row must keep identical values; every NEW row must be a
    # single-character word from the frozen reference stopword list (its p<=0.05 is
    # already guaranteed by verify_rows).
    old_check = None
    if args.old_dir is not None:
        old_dir = args.old_dir.resolve()
        R.require(old_dir.is_dir(), f"old-dir not found: {old_dir}")
        old_check = {}
        for run, _, _ in RUNS:
            old = pd.read_csv(old_dir / f"collocates_minlen1_{run}.csv", encoding="utf-8-sig")
            new = results[run]
            R.require(set(R.RESULT_COLUMNS) <= set(old.columns) and set(R.RESULT_COLUMNS) <= set(new.columns),
                      f"old/new result columns missing: {run}")
            old_words = set(old["collocate"])
            new_words = set(new["collocate"])
            retained = old_words & new_words
            missing = old_words - new_words
            R.require(not missing, f"previously kept rows missing from new table: {run}: {sorted(missing)[:8]}")
            same_vals = True
            for w in sorted(retained):
                o = old[old["collocate"] == w].iloc[0]
                n = new[new["collocate"] == w].iloc[0]
                for col in R.RESULT_COLUMNS:
                    if col == "collocate":
                        same_vals &= o[col] == n[col]
                    elif col == "target":
                        same_vals &= o[col] == n[col]
                    else:
                        same_vals &= math.isclose(float(o[col]), float(n[col]), rel_tol=1e-7, abs_tol=1e-10)
            R.require(same_vals, f"retained row values changed: {run}")
            added = sorted(new_words - old_words)
            bad = [w for w in added if not (len(w) == 1 and w in stopwords)]
            R.require(not bad, f"new rows are not single-char reference stopwords: {run}: {bad[:8]}")
            new_rows = new[new["collocate"].isin(added)].set_index("collocate")
            old_check[run] = {
                "old_rows": int(len(old)), "retained_rows_identical": int(len(retained)),
                "missing_rows": int(len(missing)), "new_rows": int(len(added)),
                "new_words_with_obs_local": {w: int(new_rows.loc[w, "obs_local"]) for w in added},
                "new_words_all_reference_stopwords_single_char": True,
            }

    with open(OUT / "collocate_examples_minlen1.csv", "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=EXAMPLE_FIELDS)
        writer.writeheader()
        writer.writerows(examples_all)
    with open(OUT / "table_verification_minlen1.csv", "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=TABLE_FIELDS)
        writer.writeheader()
        writer.writerows(table_checks)

    single_words = Counter()
    for run, _, _ in RUNS:
        for w in results[run]["collocate"]:
            if len(w) == 1:
                single_words[w] += 1

    post_shas = {p.name: sha(p) for p in OUT.glob("*.csv")}
    post_shas["analysis_log.json"] = sha(OUT / "analysis_log.json")
    unchanged = {k: (pre_shas.get(k) == post_shas.get(k)) for k in
                 ["collocates_window5.csv", "collocates_window10.csv", "collocates_sentence.csv",
                  "collocate_examples.csv", "analysis_log.json"]}

    log = {
        "status": "complete", "analysis": "supplementary single-character (min_word_length=1, stopwords not applied)",
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version, "versions": {n: importlib.metadata.version(n) for n in [*VERSIONS, "scipy", "pandas"]},
        "input_source": "data/processed/segments/*.txt (formal tokens; no re-tokenisation)",
        "input_verification": input_report,
        "input_processed_digest_pre": pre_processed,
        "input_processed_digest_post": digest_of_processed(),
        "background_matches_formal": {
            "nonempty_segments": n_seg, "tokens": n_tok, "targets": n_tgt, "max_segment_tokens": max_seg,
            "equals_formal_log": bool(n_seg == original_log["nonempty_background_segments"]
                                      and n_tok == original_log["background_tokens"]
                                      and n_tgt == original_log["retained_target_tokens"])},
        "filters": {"min_word_length": MINLEN, "max_p": 0.05,
                    "stopwords_reference_frozen_items": len(stopwords),
                    "stopwords_applied_this_run": 0,
                    "stopwords_reference_matches_qhchina_load": bool(set(loaded) == set(stopwords)),
                    "stopwords_reference_input_sha256": sha(ROOT / "input" / "stopwords_zh_cl_sim_t2s.txt"),
                    "alternative": "greater", "correction": None,
                    "sort_by": "obs_local desc", "max_sentence_length": R.MAX_SENTENCE_LENGTH},
        "runs": run_stats,
        "cross_check_len_ge2_identical_to_formal": cross,
        "comparison_against_previous_stopword_filtered_minlen1": old_check,
        "single_char_words_in_any_table": dict(sorted(single_words.items())),
        "formal_files_unchanged": unchanged,
        "runner_sha256": sha(Path(__file__)),
        "formal_runner_sha256": sha(ROOT / "scripts" / "run_scope_qhchina.py"),
        "verification": {"input_lock": "passed", "background_matches_formal": "passed",
                         "obs_exp_ratio_fisher_all_rows": "passed",
                         "significant_row_completeness_minlen1_no_stopwords": "passed",
                         "real_examples": "passed",
                         "len_ge2_identical_to_formal_tables": "passed",
                         "previous_rows_identical_new_rows_reference_stopwords":
                             None if old_check is None else "passed"},
    }
    (OUT / "analysis_log_minlen1.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="")
    print(json.dumps({"runs": run_stats, "cross": cross, "old_check": old_check,
                      "single_char_words": dict(sorted(single_words.items())),
                      "formal_files_unchanged": unchanged}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
