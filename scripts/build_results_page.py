#!/usr/bin/env python3
"""Combined page generator for <repo-root>/output/results.html.

Covers BOTH versions and BOTH result sets of each version (12 tables total):

- v3 (正式分析, 通用 jieba 基線) — CSV 來源：本倉庫根目錄 output/
  - minlen2: 正式三表（min_word_length=2、40 項停用詞僅結果篩選）
  - minlen1: 補充三表（min_word_length=1、stopwords=[]）
- v4 (詞典探索, 教師詞目表補充分詞版) — CSV 來源：
  explorations/qi_scope_v4_dict/output/
  - minlen2: 正式三表（min_word_length=2、40 項停用詞僅結果篩選）
  - minlen1: 補充三表（min_word_length=1、stopwords=[]）

Presentation/interaction layer only. No analysis is re-run, no numeric value is
recomputed, and no CSV/example/log file is modified. Examples are keyed by
(version, method, collocate) and are never mixed across versions. The page is
fully offline (no fetch, no server, no CDN). Historical analysis logs are NOT
rewritten; each page update is recorded in its own
output/page_update_note_combined.txt.
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
V4_ROOT = ROOT / "explorations" / "qi_scope_v4_dict"

METHODS = [
    ("window5", "左右5詞"),
    ("window10", "左右10詞"),
    ("sentence", "同一句段"),
]
MODES = [
    ("minlen2", "正式：最低兩字，使用停用詞", "min_word_length=2（正式三表，40 項停用詞僅結果篩選；原數值與順序完整保留）"),
    ("minlen1", "補充：最低一字，不使用停用詞", "min_word_length=1、stopwords=[]（僅放寬結果顯示門檻；背景、目標、窗口與 p 門檻不變）"),
]
COLUMNS = [
    ("target", "目標字（target）"),
    ("collocate", "搭配詞（collocate）"),
    ("exp_local", "期望共現數（exp_local）"),
    ("obs_local", "實際共現數（obs_local）"),
    ("ratio_local", "實際／期望倍數（ratio_local）"),
    ("obs_global", "背景頻次（obs_global）"),
    ("p_value", "原始 p 值（p_value）"),
]
COLUMN_KEYS = [c for c, _ in COLUMNS]

FIELD_NOTES = [
    ("target", "目標「气」；本研究把複合詞內部的氣定向拆成單字目標。"),
    ("collocate", "與目標共現的詞；點選可查看一條代表原文例句。"),
    ("exp_local", "依本次背景頻率算出的期望共現數（R1×C1/N），不是手動設定。"),
    ("obs_local", "實際共現數；window 按候選詞位置，sentence 按非空保留句段計數。"),
    ("ratio_local", "obs_local/exp_local：實際為期望的多少倍；高倍數須同看實際次數。"),
    ("obs_global", "候選詞在全背景的頻次；window 為 token 次數，sentence 為含詞句段數。"),
    ("p_value", "Fisher 單尾原始 p；不是詞義正確率，也未作多重比較校正。"),
]

CAUTION = ("本次為探索性分析，Fisher 單尾 greater，p≤0.05，correction=None，未作多重檢定校正；"
           "顯著列不是詞義分類或文學結論，低頻及重引材料須回看例句與語料構成。"
           "所有所選單元（含零命中）合併作背景，沒有前後期分組；文論重引保留並分別計數，不能宣稱觀察值統計獨立。")
CAVEATS = [
    "〈南齊書·文學傳論及贊〉相對《詩品》的成篇年代仍待核。",
    "〈內典碑銘集林序〉相對《詩品》的成篇年代仍待核。",
    "〈隱秀〉電子編注與爭議補文層次仍待核；本輪沿用現有文字，不能把全章無條件稱為劉勰原文。",
]
MINLEN1_NOTE = ("補充設定允許一字詞項進入結果，且不套用停用詞篩選（stopwords=[]），並非全部單字的頻次表；"
                "入表詞項仍須通過 p≤0.05。補充設定只取消結果中的停用詞篩選，沒有全面拆字、修復分詞或完成概念辨義。"
                "降低字長門檻與取消停用詞都不會修復既有分詞：例如「文以氣為主」若已切為「文以／气／为主」，"
                "單字「文」仍不會因此自動被辨認。單字詞項為既有分詞下的 token，不等於已核定的獨立文論概念。")
V3_NOTE = ("本版本為 v3（正式分析）：111 筆記錄／128 單元，通用 jieba 基線（default／HMM=True），"
           "3,966 個非空句段、35,138 token、106 個氣字目標。正式三表 332／409／511 列、"
           "補充三表 381／457／578 列（單字 49／48／67）。本頁例句僅來自 v3 的例句 CSV。")
V4_NOTE = ("本版本為 v4（詞典探索）：同一選材與規則，唯一變更為分詞時載入教師提供的古代漢語詞目表"
           "（200,826 詞目，OpenCC t2s 派生 200,756 詞目）的獨立 jieba.Tokenizer 重新分詞，"
           "3,966 個非空句段、35,411 token、106 個氣字目標。正式三表 340／406／509 列、"
           "補充三表 381／447／569 列（單字 41／41／60）。詞目表未有書目／製作資料，不推定出版版本或"
           "開源許可；切分變化不等於準確率提升，詞典版結果尚須原文核讀（見 explorations/qi_scope_v4_dict/reports/）。"
           "本頁例句僅來自 v4 的例句 CSV；兩版例句按「版本＋分析設定＋搭配詞」對應，不互相混用。")

PAGE_TEMPLATE = r"""<!doctype html>
<html lang="zh-Hant"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>氣字搭配詞：所選語料合併分析（互動版·v3正式＋v4詞典探索）</title>
<style>
body{font-family:system-ui,"Microsoft JhengHei",sans-serif;margin:2rem;max-width:1400px;color:#1c1c1c}
h1{font-size:1.5rem} h2{font-size:1.15rem;margin-top:1.5rem}
table{border-collapse:collapse;font-size:14px;width:100%}
td,th{border:1px solid #aaa;padding:.35rem .6rem;text-align:left}
th{background:#f0f3f7;position:sticky;top:0}
tr:nth-child(even){background:#fafbfc}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.word{color:#0b5394;cursor:pointer;text-decoration:underline}
.word:hover{color:#b31b1b}
.toolbar{display:flex;flex-wrap:wrap;gap:1rem;align-items:center;margin:1rem 0}
.toolbar label{display:inline-flex;gap:.4rem;align-items:center}
select,input[type=text]{font:inherit;padding:.3rem .5rem}
button{font:inherit;padding:.3rem .8rem;cursor:pointer}
.counter{color:#555}
.summary{color:#333;background:#f4f7fb;border:1px solid #c8d4e4;padding:.4rem .8rem;margin:.6rem 0;font-size:14px}
ul.caveats{font-size:14px}
details{margin:1rem 0}
.minlen1note{background:#eef6ff;border-left:4px solid #5b8dd9;padding:.5rem .8rem;margin:.8rem 0;font-size:14px}
.vnote{background:#f3f8ef;border-left:4px solid #6aa84f;padding:.5rem .8rem;margin:.8rem 0;font-size:14px}
dialog{max-width:860px;width:90%;border:1px solid #999;border-radius:6px;padding:1rem 1.4rem;box-shadow:0 6px 24px rgba(0,0,0,.25)}
dialog h2{margin-top:0}
dialog .kv{display:grid;grid-template-columns:11rem 1fr;gap:.35rem .8rem;font-size:14px}
dialog .kv dt{color:#555} dialog .kv dd{margin:0}
dialog .warn{background:#fff4e5;border-left:4px solid #e5a13c;padding:.5rem .8rem;margin:.6rem 0}
dialog .rep{background:#eef2f7;border-left:4px solid #7d97b8;padding:.5rem .8rem;margin:.6rem 0}
pre{white-space:pre-wrap;font-size:14px;margin:.3rem 0}
.orig{font-family:"SimSun","Microsoft JhengHei",serif}
@media print{.toolbar,details,dialog{display:none}}
</style>
<h1>氣字搭配詞：所選語料合併分析（互動版·v3正式＋v4詞典探索）</h1>
<p>__CAUTION__</p>
<ul class="caveats">__CAVEATS__</ul>
<div class="vnote" id="vnote">__V3_NOTE__</div>
<div class="minlen1note">__MINLEN1_NOTE__</div>
<div class="toolbar">
  <label>版本
    <select id="version">
      <option value="v3" selected>v3（正式分析）：通用 jieba 基線</option>
      <option value="v4">v4（詞典探索）：加入古代漢語詞典輔助分詞</option>
    </select>
  </label>
  <label>詞長設定
    <select id="mode">
      <option value="minlen2" selected>正式：最低兩字，使用停用詞</option>
      <option value="minlen1">補充：最低一字，不使用停用詞</option>
    </select>
  </label>
  <label>分析設定
    <select id="method">
      <option value="window5" selected>左右5詞（window5）</option>
      <option value="window10">左右10詞（window10）</option>
      <option value="sentence">同一句段（sentence）</option>
    </select>
  </label>
  <label>搭配詞搜尋
    <input type="text" id="query" placeholder="如：公干／公幹">
  </label>
  <label><input type="checkbox" id="ge2"> 只顯示共現≥2次</label>
  <label id="singleWrap" hidden><input type="checkbox" id="single"> 只看單字詞項</label>
  <button id="clear">清除搜尋與篩選</button>
  <span class="counter" id="counter"></span>
</div>
<div class="summary" id="summary"></div>
<div id="tablebox"></div>
<p id="source-links">
  完整CSV（v3 正式：最低兩字）：<a href="collocates_window5.csv">window5</a> ·
  <a href="collocates_window10.csv">window10</a> ·
  <a href="collocates_sentence.csv">sentence</a><br>
  完整CSV（v3 補充：最低一字）：<a href="collocates_minlen1_window5.csv">minlen1-window5</a> ·
  <a href="collocates_minlen1_window10.csv">minlen1-window10</a> ·
  <a href="collocates_minlen1_sentence.csv">minlen1-sentence</a><br>
  完整CSV（v4 正式：最低兩字）：<a href="../explorations/qi_scope_v4_dict/output/collocates_window5.csv">window5</a> ·
  <a href="../explorations/qi_scope_v4_dict/output/collocates_window10.csv">window10</a> ·
  <a href="../explorations/qi_scope_v4_dict/output/collocates_sentence.csv">sentence</a><br>
  完整CSV（v4 補充：最低一字）：<a href="../explorations/qi_scope_v4_dict/output/collocates_minlen1_window5.csv">minlen1-window5</a> ·
  <a href="../explorations/qi_scope_v4_dict/output/collocates_minlen1_window10.csv">minlen1-window10</a> ·
  <a href="../explorations/qi_scope_v4_dict/output/collocates_minlen1_sentence.csv">minlen1-sentence</a><br>
  例句／核驗（v3）：<a href="collocate_examples.csv">完整例句CSV</a> ·
  <a href="collocate_examples_minlen1.csv">補充設定例句CSV</a> ·
  <a href="table_verification.csv">逐列核驗</a> ·
  <a href="table_verification_minlen1.csv">補充逐列核驗</a> ·
  <a href="unit_verification.csv">單元核驗</a> ·
  <a href="qi_hits.csv">氣字位置</a> ·
  <a href="method_notes.txt">方法紀錄</a><br>
  例句／核驗（v4，詞典探索）：<a href="../explorations/qi_scope_v4_dict/output/collocate_examples.csv">完整例句CSV</a> ·
  <a href="../explorations/qi_scope_v4_dict/output/collocate_examples_minlen1.csv">補充設定例句CSV</a> ·
  <a href="../explorations/qi_scope_v4_dict/output/table_verification.csv">逐列核驗</a> ·
  <a href="../explorations/qi_scope_v4_dict/output/table_verification_minlen1.csv">補充逐列核驗</a> ·
  <a href="../explorations/qi_scope_v4_dict/output/unit_verification.csv">單元核驗</a> ·
  <a href="../explorations/qi_scope_v4_dict/output/qi_hits.csv">氣字位置</a> ·
  <a href="../explorations/qi_scope_v4_dict/output/method_notes.txt">方法紀錄</a>
</p>
<details open>
  <summary>表格欄位怎麼讀</summary>
  <ul>__FIELD_NOTES__</ul>
  <p>p_value 為 Fisher 單尾原始 p（correction=None），屬探索性未校正結果；「一期顯著、另一期不顯著」不等於兩期間有顯著差異。本頁搜尋、「共現≥2」與「只看單字詞項」勾選只控制顯示，不刪除結果、不更改統計門檻。</p>
</details>
<details>
  <summary>版本與詞長設定怎麼讀</summary>
  <p>「v3（正式分析）」＝通用 jieba 基線：正式三表 __V3_MINLEN2_ROWS__ 列（min_word_length=2、40 項停用詞僅結果篩選）；補充三表 __V3_MINLEN1_ROWS__ 列（min_word_length=1、stopwords=[]，單字 __V3_SINGLE_ROWS__）。</p>
  <p>「v4（詞典探索）」＝教師提供古代漢語詞目表補充分詞版：正式三表 __V4_MINLEN2_ROWS__ 列；補充三表 __V4_MINLEN1_ROWS__ 列（單字 __V4_SINGLE_ROWS__）。詞目表未有書目／製作資料，不推定出版版本或開源許可；切分變化不等於準確率提升。</p>
  <p>「正式：最低兩字，使用停用詞」＝作業要求的 min_word_length=2 結果（40 項停用詞僅結果篩選，仍佔窗口與背景；數值與順序原樣保留）。</p>
  <p>「補充：最低一字，不使用停用詞」＝min_word_length=1、stopwords=[] 的結果；同一背景、同一目標、同一窗口與 p 門檻，只放寬結果字長並取消停用詞篩選。一字詞項（含原停用詞）仍須通過 p≤0.05 才出現，並非全部單字的頻次表。</p>
  <p>兩版例句按「版本＋分析設定＋搭配詞」對應，不互相混用；單字例句的「位於氣字定向切分邊界」「原文連寫」為切分位置說明，「原屬參考停用清單，本輪補充設定未篩除」為篩選說明，均不是詞義分類；單字 token 不等於已核定的獨立文論概念。</p>
</details>
<dialog id="detail">
  <h2 id="d-head"></h2>
  <div id="d-body"></div>
  <button id="d-close">關閉</button>
</dialog>
<script id="payload" type="application/json">__PAYLOAD__</script>
<script>
var PAYLOAD = JSON.parse(document.getElementById('payload').textContent);
var DATA = PAYLOAD.data;
var VERSIONS = PAYLOAD.versions;
var COLUMNS = __COLUMNS_JS__;
var versionSel = document.getElementById('version');
var modeSel = document.getElementById('mode');
var methodSel = document.getElementById('method');
var queryEl = document.getElementById('query');
var ge2El = document.getElementById('ge2');
var singleEl = document.getElementById('single');
var singleWrap = document.getElementById('singleWrap');
var counter = document.getElementById('counter');
var summary = document.getElementById('summary');
var vnote = document.getElementById('vnote');
var tablebox = document.getElementById('tablebox');
var detail = document.getElementById('detail');
var dHead = document.getElementById('d-head');
var dBody = document.getElementById('d-body');
function esc(s){
  return String(s).replace(/[&<>"']/g, function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
  });
}
function matches(row, ex, q){
  if(!q) return true;
  var qq = q.toLowerCase();
  var fields = [row.collocate, ex.collocate_orig_text || '', ex.orig_sentence || '', ex.counted_orig_segment || ''];
  return fields.some(function(f){ return String(f).toLowerCase().indexOf(qq) >= 0; });
}
function render(){
  var version = versionSel.value;
  var mode = modeSel.value;
  var method = methodSel.value;
  var info = DATA[version][mode][method];
  var q = queryEl.value.trim();
  var minObs = ge2El.checked ? 2 : 0;
  var singleOnly = (mode === 'minlen1') && singleEl.checked;
  var shown = 0;
  var parts = ['<table><thead><tr>'];
  for(var i=0;i<COLUMNS.length;i++){
    parts.push('<th>' + esc(COLUMNS[i][1]) + '</th>');
  }
  parts.push('</tr></thead><tbody>');
  for(var r=0;r<info.rows.length;r++){
    var row = info.rows[r];
    var ex = info.examples[row.collocate];
    if(Number(row.obs_local) < minObs) continue;
    if(singleOnly && row.collocate.length !== 1) continue;
    if(!matches(row, ex, q)) continue;
    shown += 1;
    parts.push('<tr>');
    parts.push('<td>' + esc(row.target) + '</td>');
    parts.push('<td><span class="word" data-coll="' + esc(row.collocate) + '">' + esc(row.collocate) + '</span></td>');
    var keys = ['exp_local','obs_local','ratio_local','obs_global','p_value'];
    for(var k=0;k<keys.length;k++){
      parts.push('<td class="num">' + esc(row[keys[k]]) + '</td>');
    }
    parts.push('</tr>');
  }
  parts.push('</tbody></table>');
  tablebox.innerHTML = parts.join('');
  counter.textContent = '目前顯示 ' + shown + ' 列／完整結果 ' + info.total + ' 列';
  summary.textContent = '版本：' + VERSIONS[version].shortLabel +
    '｜詞長設定：' + (mode === 'minlen1' ? '補充（最低一字，不使用停用詞）' : '正式（最低兩字，使用停用詞）') +
    '｜分析設定：' + info.label;
  vnote.textContent = VERSIONS[version].note;
  var words = tablebox.querySelectorAll('.word');
  for(var w=0;w<words.length;w++){
    (function(el){
      el.addEventListener('click', function(){ openDetail(versionSel.value, modeSel.value, methodSel.value, el.dataset.coll); });
    })(words[w]);
  }
}
function openDetail(version, mode, method, coll){
  var ex = DATA[version][mode][method].examples[coll];
  var methodLabel = DATA[version][mode][method].label;
  var versionLabel = VERSIONS[version].shortLabel;
  var modeLabel = (mode === 'minlen1') ? '補充設定（最低一字，不使用停用詞）' : '正式設定（最低兩字，使用停用詞）';
  dHead.textContent = '搭配詞「' + coll + '」 — ' + versionLabel + ' · ' + modeLabel + ' · ' + methodLabel;
  var isWindow = method.indexOf('window') === 0;
  var dist = isWindow
    ? '詞距：' + ex.token_distance + ' 詞（該方法窗口內）'
    : '同一句段共現（sentence 方法）';
  var quoteWarn = String(ex.orig_sentence_contains_excluded_quote) === '1'
    ? '<div class="warn">原文句內含被排除的引詩；引詩未參與本次計數。</div>'
    : '';
  var posNote = '';
  if(mode === 'minlen1'){
    var b = String(ex.at_split_boundary) === '1' ? '是' : '否';
    var a = String(ex.original_abuts_target) === '1' ? '原文連寫（如骨氣、體氣一類表達）' : '未與氣字連寫';
    posNote = '<p>單字詞項切分位置：位於氣字定向切分邊界＝' + b + '；' + esc(a) + '。此為切分位置說明，非詞義分類。</p>';
  }
  var extra = '';
  if(ex.note){ extra = '<p>' + esc(ex.note) + '</p>'; }
  var ver = VERSIONS[version];
  var mainCsv = ver.examplesCsv + '#' + method;
  var min1Csv = ver.examplesMin1Csv + '#' + method;
  dBody.innerHTML =
    '<div class="kv">' +
    '<dt>版本</dt><dd>' + esc(versionLabel) + '</dd>' +
    '<dt>篇名</dt><dd>' + esc(ex.title) + '</dd>' +
    '<dt>作者</dt><dd>' + esc(ex.author) + '</dd>' +
    '<dt>記錄／單元</dt><dd>' + esc(ex.record_id) + '／' + esc(ex.unit_id) + '</dd>' +
    '<dt>搭配詞（計數詞形）</dt><dd>' + esc(ex.collocate_orig_text) + '（簡體詞形：' + esc(coll) + '）</dd>' +
    '<dt>實際共現數</dt><dd>' + esc(ex.obs_local) + '（原始 p：' + esc(ex.p_value) + '）</dd>' +
    '</div>' +
    quoteWarn +
    posNote +
    '<p>原文完整句（orig_sentence）：</p><pre class="orig">' + esc(ex.orig_sentence) + '</pre>' +
    '<p>實際參與計數的句段（counted_orig_segment）：</p><pre>' + esc(ex.counted_orig_segment) + '</pre>' +
    '<p>計數句段詞序：</p><pre>' + esc(ex.counted_segment_tokens) + '</pre>' +
    '<p>' + esc(dist) + '</p>' +
    extra +
    '<div class="rep">本視窗展示的是一條代表例句，並非該搭配詞的全部共現例證；完整例句見對應版本與設定的例句CSV（<a href="' + esc(ver.examplesCsv) + '">正式設定例句CSV</a>／<a href="' + esc(ver.examplesMin1Csv) + '">補充設定例句CSV</a>）。兩版例句不互相混用。</div>';
  detail.showModal();
}
function onModeChange(){
  singleWrap.hidden = (modeSel.value !== 'minlen1');
  if(modeSel.value !== 'minlen1') singleEl.checked = false;
  render();
}
versionSel.addEventListener('change', render);
modeSel.addEventListener('change', onModeChange);
methodSel.addEventListener('change', render);
queryEl.addEventListener('input', render);
ge2El.addEventListener('change', render);
singleEl.addEventListener('change', render);
document.getElementById('clear').addEventListener('click', function(){
  queryEl.value = '';
  ge2El.checked = false;
  singleEl.checked = false;
  render();
});
document.getElementById('d-close').addEventListener('click', function(){ detail.close(); });
singleWrap.hidden = true;
render();
</script>
</html>
"""


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_table(path: Path):
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            rows.append({c: row[c] for c in COLUMN_KEYS})
    return rows


def load_examples(path: Path):
    out = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            key = (row["method"], row["collocate"])
            assert key not in out, f"duplicate example: {key}"
            out[key] = row
    return out


VERSION_SPECS = {
    "v3": {
        "short_label": "v3（正式分析）：通用 jieba 基線",
        "note": V3_NOTE,
        "out_root": ROOT / "output",
        "examples_csv_rel": "collocate_examples.csv",
        "examples_min1_csv_rel": "collocate_examples_minlen1.csv",
    },
    "v4": {
        "short_label": "v4（詞典探索）：加入古代漢語詞典輔助分詞",
        "note": V4_NOTE,
        "out_root": V4_ROOT / "output",
        "examples_csv_rel": "../explorations/qi_scope_v4_dict/output/collocate_examples.csv",
        "examples_min1_csv_rel": "../explorations/qi_scope_v4_dict/output/collocate_examples_minlen1.csv",
    },
}


def build_version_data(out_root: Path):
    """Build {mode: {method: {...}}} for one version's output dir."""
    examples_min2 = load_examples(out_root / "collocate_examples.csv")
    examples_min1 = load_examples(out_root / "collocate_examples_minlen1.csv")
    data = {}
    checks = []
    for mode, mode_label, mode_note in MODES:
        examples = examples_min2 if mode == "minlen2" else examples_min1
        csv_name = "collocates_{run}.csv" if mode == "minlen2" else "collocates_minlen1_{run}.csv"
        data[mode] = {}
        for method, label in METHODS:
            rows = load_table(out_root / csv_name.format(run=method))
            missing = [r["collocate"] for r in rows if (method, r["collocate"]) not in examples]
            assert not missing, f"{mode}/{method}: rows without examples: {missing[:5]}"
            n_ge2 = sum(1 for r in rows if int(r["obs_local"]) >= 2)
            n_single = sum(1 for r in rows if len(r["collocate"]) == 1)
            data[mode][method] = {
                "label": label,
                "rows": rows,
                "examples": {r["collocate"]: examples[(method, r["collocate"])] for r in rows},
                "total": len(rows),
                "ge2": n_ge2,
                "single": n_single,
            }
            checks.append((mode, method, len(rows), n_ge2, n_single))

    # row-by-row cross-check: every len>=2 row of the supplementary tables must
    # be value-identical (all 7 columns, same order) to the formal tables.
    len2_cross = {}
    for method, _ in METHODS:
        formal = load_table(out_root / f"collocates_{method}.csv")
        supp = [r for r in load_table(out_root / f"collocates_minlen1_{method}.csv") if len(r["collocate"]) >= 2]
        assert len(supp) == len(formal), f"{method}: len>=2 row count differs: {len(supp)} vs {len(formal)}"
        for f_row, s_row in zip(formal, supp):
            assert f_row == s_row, f"{method}: len>=2 row differs: {f_row} vs {s_row}"
        len2_cross[method] = {"len_ge2_rows": len(supp), "identical_to_formal": True, "formal_rows": len(formal)}
    return data, checks, len2_cross


def main() -> None:
    input_shas = {}
    for p in sorted((ROOT / "output").glob("*.csv")) + sorted((V4_ROOT / "output").glob("*.csv")):
        input_shas[p.relative_to(ROOT).as_posix()] = sha(p)

    payload_data = {}
    checks = {}
    len2_cross = {}
    for version, spec in VERSION_SPECS.items():
        data, chk, cross = build_version_data(spec["out_root"])
        payload_data[version] = data
        checks[version] = chk
        len2_cross[version] = cross

    versions_meta = {
        version: {
            "shortLabel": spec["short_label"],
            "note": spec["note"],
            "examplesCsv": spec["examples_csv_rel"],
            "examplesMin1Csv": spec["examples_min1_csv_rel"],
        }
        for version, spec in VERSION_SPECS.items()
    }
    payload = json.dumps({"versions": versions_meta, "data": payload_data},
                         ensure_ascii=False).replace("<", "\\u003c")
    columns_js = json.dumps(COLUMNS, ensure_ascii=False)
    field_notes_html = "".join(
        "<li><b>" + html.escape(z) + "</b>：" + html.escape(n) + "</li>" for z, n in FIELD_NOTES)
    caveats_html = "".join("<li>" + html.escape(c) + "</li>" for c in CAVEATS)
    rows_str = lambda v, mode: "／".join(str(payload_data[v][mode][m]["total"]) for m, _ in METHODS)
    single_str = lambda v: "／".join(str(payload_data[v]["minlen1"][m]["single"]) for m, _ in METHODS)

    page = (PAGE_TEMPLATE
            .replace("__CAUTION__", html.escape(CAUTION))
            .replace("__CAVEATS__", caveats_html)
            .replace("__V3_NOTE__", html.escape(V3_NOTE))
            .replace("__MINLEN1_NOTE__", html.escape(MINLEN1_NOTE))
            .replace("__V3_MINLEN2_ROWS__", rows_str("v3", "minlen2"))
            .replace("__V3_MINLEN1_ROWS__", rows_str("v3", "minlen1"))
            .replace("__V3_SINGLE_ROWS__", single_str("v3"))
            .replace("__V4_MINLEN2_ROWS__", rows_str("v4", "minlen2"))
            .replace("__V4_MINLEN1_ROWS__", rows_str("v4", "minlen1"))
            .replace("__V4_SINGLE_ROWS__", single_str("v4"))
            .replace("__FIELD_NOTES__", field_notes_html)
            .replace("__PAYLOAD__", payload)
            .replace("__COLUMNS_JS__", columns_js))

    out_path = ROOT / "output" / "results.html"
    out_path.write_text(page, encoding="utf-8", newline="")

    note_lines = [
        "results.html 頁面更新紀錄（合併版：v3 正式六表＋v4 詞典探索六表；僅呈現與互動層）",
        f"generated_utc: {datetime.now(timezone.utc).isoformat()}",
        f"generator: scripts/build_results_page.py sha256={sha(Path(__file__))}",
        f"results_html_sha256: {sha(out_path)}",
        "本頁輸入（唯讀，未改動）：根 output/*.csv（v3）與 explorations/qi_scope_v4_dict/output/*.csv（v4）",
        "例句按「版本＋分析設定＋搭配詞」對應，兩版不混合；頁面離線可開，不依賴 fetch／伺服器／CDN。",
        "v3 頁面（SHA 3705fc8c…，本輪前版本）與 v3 頁面產生器已備份至研究過程歸檔（見備份紀錄）。",
        "input csv sha256 (read-only):",
    ]
    for name, h in input_shas.items():
        note_lines.append(f"  {name}: {h}")
    note_lines.append("驗證：")
    for version in ("v3", "v4"):
        for mode, method, total, ge2, single in checks[version]:
            note_lines.append(f"  {version}/{mode}/{method}: 完整 {total} 列；obs>=2 共 {ge2} 列；單字 {single} 列；每列均有代表例句。")
        for method, info in len2_cross[version].items():
            note_lines.append(f"  {version} len>=2 cross-check {method}: {info}")
    note_lines.append("output/analysis_log.json、analysis_log_minlen1.json 及 v4 兩份日誌均未改寫其歷史雜湊欄位。")
    (ROOT / "output" / "page_update_note_combined.txt").write_text(
        "\n".join(note_lines) + "\n", encoding="utf-8", newline="")
    print(json.dumps({"page": str(out_path), "checks": checks, "len2_cross": len2_cross,
                      "csv_sha_count": len(input_shas)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
