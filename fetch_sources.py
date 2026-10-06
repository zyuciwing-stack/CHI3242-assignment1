# -*- coding: utf-8 -*-
"""fetch_sources.py — 下載並保存本專案的原始資料（可重跑）。

用法（專案 venv）：
    .\\.venv\\Scripts\\python.exe fetch_sources.py

內容：
1. 以 MediaWiki API 下載維基文庫固定修訂（oldid）：
   - 《樂府指迷》沈義父，oldid=2527931
   - 《詞旨》陸輔之，oldid=1560431
   每書保存：完整頁面 HTML 原始快照、wikitext、清洗後 UTF-8 文本副本。
   文本副本移除網站導航、頁頭模板、目錄、編輯按鈕與頁腳，
   保留書內序跋、注釋、引文與原有字形（不做簡繁變體轉換）。
2. 《詞源》選定與查核：
   - 下載候選來源：欽定古今圖書集成/理學彙編/文學典/第251卷（最新修訂），
     原始快照保留於 data/raw/。
   - 語料範圍已確定：在「張炎樂府指迷」章內，完整抽取〈詞源〉至〈雜論〉14節，
     保存為 data/selected/ciyuan.txt；〈楊誠齋作詞五要〉另存附文（不併入語料）。
   - 檢查維基文庫是否存在《詞源》完整上下卷頁面；如實記錄結果（擴大搜尋留待後續）。
3. 產出 data/sources.json（來源紀錄＋SHA-256＋14節明細）與 data/來源核對清單.md。

行為說明：
- 每個網路請求 20 秒超時，失敗最多重試一次；逐步印出正在處理的書名與結果。
- 已完整下載且 SHA-256 核驗通過的檔案直接沿用（零網路請求）；只補下載缺失或不完整的部分。
- 《詞源》候選資料保留並標記完整性；擴大搜尋留待後續輪次處理。

注意：每組結果的分詞與搭配詞分析留待正文核定後進行（見 AGENTS.md）。
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "raw"
CAND_DIR = ROOT / "data" / "candidates"
SELECTED_DIR = ROOT / "data" / "selected"
SOURCES_JSON = ROOT / "data" / "sources.json"
CHECKLIST_MD = ROOT / "data" / "來源核對清單.md"

API = "https://zh.wikisource.org/w/api.php"
INDEX = "https://zh.wikisource.org/w/index.php"
UA = "CHI3242-assignment1/0.1 (academic coursework; Chinese collocation study)"
TIMEOUT = 20         # 每個網路請求的超時（秒）
MAX_RETRY = 2        # 首次請求，最多重試一次（共兩次嘗試）
DELAY = 1.5          # 每次 API 請求之間的間隔（秒）

BOOKS = [
    {
        "key": "yuefu_zhimi",
        "書名": "樂府指迷",
        "作者": "沈義父",
        "朝代": "宋",
        "title": "樂府指迷",
        "oldid": 2527931,
        "source_url": "https://zh.wikisource.org/w/index.php?title=樂府指迷&oldid=2527931",
    },
    {
        "key": "cizhi",
        "書名": "詞旨",
        "作者": "陸輔之",
        "朝代": "元",
        "title": "詞旨",
        "oldid": 1560431,
        "source_url": "https://zh.wikisource.org/w/index.php?title=詞旨&oldid=1560431",
    },
]

GJTSC_TITLE = "欽定古今圖書集成/理學彙編/文學典/第251卷"
CAND_START = "張炎樂府指迷"   # 候選段起始標題（即《詞源》選錄）
CAND_END = "陸輔之樂府指迷"   # 候選段結束（不含）

# 《詞源》語料範圍（已確定）：「張炎樂府指迷」章內〈詞源〉至〈雜論〉共 14 節；
# 〈楊誠齋作詞五要〉另存附文；原始快照保留。
CIYUAN_SECTIONS = ["《詞源》", "《製曲》", "《句法》", "《字面》", "《虛字》",
                   "《清空》", "《意趣》", "《用事》", "《詠物》", "《節序》",
                   "《賦情》", "《離情》", "《令曲》", "《雜論》"]
CIYUAN_APPENDIX = "《楊誠齋作詞五要》"
CIYUAN_RECORD_NAME = "《詞源》詞論部分（《古今圖書集成》所錄）"

session = requests.Session()
session.headers.update({"User-Agent": UA})


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def api_get(params: dict) -> dict:
    """帶限速處理的 API GET：20 秒超時，最多重試一次。"""
    p = {"format": "json", "formatversion": "2", "uselang": "zh"}
    p.update(params)
    last_err: Exception | str | None = None
    for attempt in range(MAX_RETRY):
        try:
            r = session.get(API, params=p, timeout=TIMEOUT)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", "0") or 0) or 10
                print(f"    [限速 429] 等待 {wait}s 後重試…")
                time.sleep(wait)
                last_err = "HTTP 429 限速"
                continue
            r.raise_for_status()
            time.sleep(DELAY)
            data = r.json()
            if "error" in data:
                raise RuntimeError(f"API error: {data['error'].get('info')}")
            return data
        except (requests.RequestException, RuntimeError, ValueError) as e:
            last_err = e
            if attempt < MAX_RETRY - 1:
                print(f"    [失敗] {p.get('action')}（{p.get('oldid') or p.get('page') or ''}）：{e}"
                      f"；最多重試一次…")
                time.sleep(3)
    raise RuntimeError(f"API 請求失敗（20s 超時，已重試一次）: {last_err}")


def get_page_http(url: str) -> str:
    """取得完整渲染頁面（含皮膚）作為原始快照：20 秒超時，最多重試一次。"""
    last_err: Exception | None = None
    for attempt in range(MAX_RETRY):
        try:
            r = session.get(url, timeout=TIMEOUT)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", "0") or 0) or 10
                print(f"    [限速 429] 等待 {wait}s 後重試…")
                time.sleep(wait)
                last_err = RuntimeError("HTTP 429 限速")
                continue
            r.raise_for_status()
            time.sleep(DELAY)
            return r.text
        except requests.RequestException as e:
            last_err = e
            if attempt < MAX_RETRY - 1:
                print(f"    [失敗] {url}：{e}；最多重試一次…")
                time.sleep(3)
    raise RuntimeError(f"頁面下載失敗（20s 超時，已重試一次）: {last_err}")


def get_revision_info(revid: int) -> dict:
    d = api_get({
        "action": "query", "prop": "revisions", "revids": revid,
        "rvprop": "ids|timestamp|user|comment|size", "rvslots": "main",
    })
    page = d["query"]["pages"][0]
    rev = page["revisions"][0]
    return {"title": page["title"], "oldid": rev["revid"],
            "timestamp": rev["timestamp"], "user": rev.get("user", ""),
            "comment": rev.get("comment", ""), "size": rev.get("size")}


def get_wikitext(oldid: int) -> str:
    d = api_get({"action": "parse", "oldid": oldid, "prop": "wikitext"})
    return d["parse"]["wikitext"]


def get_parsed_html(oldid: int | None = None, page: str | None = None) -> dict:
    """取得正文渲染 HTML（不含皮膚導航/頁腳；停用編輯按鈕與自動目錄）。"""
    p = {"action": "parse", "prop": "text|displaytitle|revid",
         "disableeditsection": 1, "disabletoc": 1, "disablelimitreport": 1}
    if oldid is not None:
        p["oldid"] = oldid
    else:
        p["page"] = page
    d = api_get(p)
    return d["parse"]


# ----------------------------------------------------------------------------
# HTML → 純文本
# ----------------------------------------------------------------------------

HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
DROP_SELECTORS = [
    "#headerContainer",      # 頁頭模板（書名/作者/姊妹计划/來源連結＝網站導航）
    ".noprint",              # 姊妹計劃、工具連結
    ".mw-editsection",       # 編輯按鈕（保險）
    "#toc", ".toc",          # 自動目錄（保險）
    ".printfooter", ".catlinks",
    ".licenseContainer",     # 授權橫幅（頁腳）
    "style", "script", "figure", "img", "link",   # 圖示、樣式（如「考證」SVG）
]


def _select_root(soup: BeautifulSoup) -> Tag:
    """優先取掃描頁轉錄容器；其外的卷次導航表一併移除。"""
    root = soup.select_one(".mw-parser-output") or soup.body or soup
    pp = root.select_one(".prp-pages-output")
    if pp is not None:
        for t in root.find_all("table", recursive=False):  # 卷次導航表（←前一卷｜本卷｜後一卷→）
            t.decompose()
        root = pp
    return root


def _drop_toc_before_first_heading(root: Tag) -> None:
    """移除首個標題之前、含「目錄」字樣的導言段落（如古圖書集成卷目錄）。"""
    kids = [c for c in root.children if isinstance(c, Tag)]
    first_head = None
    for c in kids:
        cls = c.get("class") or []
        if "mw-heading" in cls or c.name in HEADING_TAGS:
            first_head = c
            break
    if first_head is None:
        return
    pre = []
    for c in kids:
        if c is first_head:
            break
        pre.append(c)
    if not any(c.name == "p" and c.get_text("", strip=True).endswith("目錄") for c in pre):
        return
    for c in pre:
        c.decompose()


def _clean_text_block(s: str) -> str:
    return s.strip()


def html_to_text(html: str) -> str:
    """把正文 HTML 轉為 UTF-8 純文本：保留段落、標題（## 前綴）與原有字形。"""
    soup = BeautifulSoup(html, "html.parser")
    root = _select_root(soup)
    for sel in DROP_SELECTORS:
        for el in root.select(sel):
            el.decompose()
    _drop_toc_before_first_heading(root)
    out: list[str] = []

    def walk(node: Tag) -> None:
        for ch in node.children:
            if isinstance(ch, NavigableString):
                continue
            if not isinstance(ch, Tag):
                continue
            cls = ch.get("class") or []
            if "mw-heading" in cls:
                h = ch.find(list(HEADING_TAGS)) or ch
                txt = h.get_text("", strip=True)
                out.append(f"\n\n## {txt}\n")
                continue
            name = ch.name
            if name in HEADING_TAGS:
                out.append(f"\n\n## {ch.get_text('', strip=True)}\n")
            elif name == "p":
                t = _clean_text_block(ch.get_text("", strip=True))
                if t:
                    out.append(f"\n{t}\n")
            elif name == "blockquote":
                t = _clean_text_block(ch.get_text("", strip=True))
                if t:
                    out.append(f"\n{t}\n")
            elif name == "table":
                out.append("\n")
                for tr in ch.find_all("tr"):
                    cells = [td.get_text("", strip=True) for td in tr.find_all(["td", "th"])]
                    line = "　".join(c for c in cells if c)
                    if line:
                        out.append(line + "\n")
                out.append("\n")
            elif name in ("ul", "ol"):
                for li in ch.find_all("li", recursive=False):
                    t = _clean_text_block(li.get_text("", strip=True))
                    if t:
                        out.append(f"\n- {t}")
                out.append("\n")
            elif name in ("style", "script", "figure", "img"):
                continue
            else:  # div 及其他容器：遞迴；末層則直接取文字
                has_block_child = any(
                    isinstance(c, Tag) and (c.name in HEADING_TAGS or c.name in
                                            ("p", "div", "table", "ul", "ol", "blockquote"))
                    for c in ch.children)
                if has_block_child:
                    walk(ch)
                else:
                    t = _clean_text_block(ch.get_text("", strip=True))
                    if t:
                        out.append(f"\n{t}\n")

    walk(root)
    text = "".join(out)
    # 壓縮連續空行；去行尾空白
    lines, blank = [], 0
    for ln in text.splitlines():
        ln = ln.rstrip()
        if not ln:
            blank += 1
            if blank == 1:
                lines.append("")
        else:
            blank = 0
            lines.append(ln)
    return "\n".join(lines).strip() + "\n"


def extract_section(html: str, start_heading: str, end_heading: str) -> str:
    """截取 start_heading 標題之後、end_heading 標題之前的內容（含子標題）。"""
    soup = BeautifulSoup(html, "html.parser")
    root = _select_root(soup)
    for sel in DROP_SELECTORS:
        for el in root.select(sel):
            el.decompose()
    capturing = False
    parts: list[str] = []
    for ch in root.children:
        if not isinstance(ch, Tag):
            continue
        cls = ch.get("class") or []
        is_heading = "mw-heading" in cls or ch.name in HEADING_TAGS
        if is_heading:
            h = ch.find(list(HEADING_TAGS)) or ch
            txt = h.get_text("", strip=True)
            if not capturing and txt == start_heading:
                capturing = True
                parts.append(f"## {txt}\n")
                continue
            if capturing and txt == end_heading:
                break
            if capturing:
                parts.append(f"\n## {txt}\n")
                continue
        if capturing:
            t = _clean_text_block(ch.get_text("", strip=True))
            if t:
                parts.append(f"\n{t}\n")
    return "\n".join(parts).strip() + "\n"


def sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def extract_chapter_sections(html: str, start_heading: str, end_heading: str) -> list:
    """取得 start_heading 至 end_heading 之間，以標題切分的各節（依文件順序）。"""
    soup = BeautifulSoup(html, "html.parser")
    root = _select_root(soup)
    for sel in DROP_SELECTORS:
        for el in root.select(sel):
            el.decompose()
    _drop_toc_before_first_heading(root)
    capturing = False
    sections: list = []
    cur = None
    for ch in root.children:
        if not isinstance(ch, Tag):
            continue
        cls = ch.get("class") or []
        is_heading = "mw-heading" in cls or ch.name in HEADING_TAGS
        if is_heading:
            h = ch.find(list(HEADING_TAGS)) or ch
            txt = h.get_text("", strip=True)
            if not capturing:
                if txt == start_heading:
                    capturing = True
                    cur = None
                continue
            if txt == end_heading:
                break
            cur = {"標題": txt, "塊": []}
            sections.append(cur)
            continue
        if capturing and cur is not None:
            t = _clean_text_block(ch.get_text("", strip=True))
            if t:
                cur["塊"].append(t)
    return [{"標題": s["標題"], "內文": "\n".join(s["塊"])} for s in sections]


def select_ciyuan_corpus(oldid: int) -> dict:
    """從既有快照選定《詞源》語料：〈詞源〉至〈雜論〉14 節＋〈楊誠齋作詞五要〉附文。

    純本地處理（讀取 data/raw 快照，不做任何網路請求），可重跑。
    """
    snap = RAW_DIR / f"gujin_tushu_jicheng_wenxuedian_251_oldid{oldid}.html"
    if not snap.exists():
        raise RuntimeError(f"找不到原始快照 {snap.name}，請先下載")
    print(f"[處理中] 《詞源》語料選定（依快照 oldid={oldid}，本地處理）…")
    secs = extract_chapter_sections(snap.read_text(encoding="utf-8"),
                                   CAND_START, CAND_END)
    got = [s["標題"] for s in secs]
    if got[:len(CIYUAN_SECTIONS)] != CIYUAN_SECTIONS:
        raise RuntimeError(f"十四節順序或名稱不符，實得：{got}")
    if got[len(CIYUAN_SECTIONS):len(CIYUAN_SECTIONS) + 1] != [CIYUAN_APPENDIX]:
        raise RuntimeError(f"附文〈楊誠齋作詞五要〉位置異常，實得：{got}")
    main_secs = secs[:len(CIYUAN_SECTIONS)]
    app = secs[len(CIYUAN_SECTIONS)]

    main_txt = "\n\n".join(f"## {s['標題']}\n\n{s['內文']}" for s in main_secs).strip() + "\n"
    app_txt = f"## {app['標題']}\n\n{app['內文']}".strip() + "\n"
    f_main = save(SELECTED_DIR / "ciyuan.txt", main_txt,
                  "選定語料（《詞源》詞論部分，共14節：〈詞源〉至〈雜論〉）")
    f_app = save(SELECTED_DIR / "ciyuan_附文_楊誠齋作詞五要.txt", app_txt,
                 "附文（〈楊誠齋作詞五要〉，不併入選定語料）")
    for f_ in (f_main, f_app):
        print(f"   成功 {f_['路徑']}  sha256={f_['sha256'][:12]}…  字數={f_['字數_不含空白']}")
    detail = [{"節名": s["標題"], "字數_不含空白": len(re.sub(r"\s", "", s["內文"])),
               "sha256": sha256_str(s["內文"])} for s in main_secs]
    print(f"   十四節字數（不含空白）合計：{sum(d['字數_不含空白'] for d in detail)}")
    return {"檔案_選定": [f_main, f_app], "選定語料十四節明細": detail}


# ----------------------------------------------------------------------------
# 檔案與雜湊
# ----------------------------------------------------------------------------

def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def files_ok(record: dict) -> bool:
    """核驗既有紀錄的每個檔案：存在、非空、SHA-256 與紀錄一致。"""
    try:
        for f in record["檔案"]:
            p = ROOT / f["路徑"]
            if not p.exists() or p.stat().st_size == 0:
                return False
            if sha256_of(p) != f["sha256"]:
                return False
        return True
    except (KeyError, OSError):
        return False


def load_existing_records() -> dict:
    """讀取上次執行的 sources.json（以書名為鍵），供沿用完整檔案。"""
    if not SOURCES_JSON.exists():
        return {}
    try:
        d = json.loads(SOURCES_JSON.read_text(encoding="utf-8"))
        return {rec["書名"]: rec for rec in d.get("語料", [])}
    except (json.JSONDecodeError, KeyError, TypeError):
        return {}


def save(path: Path, content: str, role: str) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    n_all = len(content.replace("\n", "").replace("\r", ""))
    n_nows = len(re.sub(r"\s", "", content))
    return {"路徑": path.relative_to(ROOT).as_posix(), "用途": role,
            "sha256": sha256_of(path), "字數_不含換行": n_all, "字數_不含空白": n_nows}


# ----------------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------------

def check_ciyuan_presence() -> dict:
    """查核維基文庫是否存在《詞源》完整上下卷頁面；如實記錄。"""
    result: dict = {"檢查時間": now_iso(), "wiki": "zh.wikisource.org"}
    titles = ["詞源", "詞源/卷上", "詞源/卷下", "詞源 (張炎)", "詞源/張炎"]
    d = api_get({"action": "query", "titles": "|".join(titles)})
    result["直接頁名查核"] = [
        {"title": p["title"], "存在": "missing" not in p} for p in d["query"]["pages"]]
    d = api_get({"action": "query", "list": "prefixsearch", "pssearch": "詞源", "pslimit": 20})
    result["前綴搜尋_詞源"] = [r["title"] for r in d["query"]["prefixsearch"]]
    d = api_get({"action": "query", "list": "search",
                 "srsearch": "intitle:詞源", "srlimit": 10, "srnamespace": 0})
    result["標題搜尋_intitle_詞源"] = [r["title"] for r in d["query"]["search"]]
    # 過濾與書籍無關之頁面（如司法判決書）
    irrelevant_kw = ("有限公司", "判決", "判决", "糾紛", "纠纷", "民事", "合同")
    relevant = [t for t in result["前綴搜尋_詞源"] + result["標題搜尋_intitle_詞源"]
                if "詞源" in t and not any(k in t for k in irrelevant_kw)]
    result["不相關搜尋結果_已排除"] = [t for t in result["標題搜尋_intitle_詞源"]
                                      if any(k in t for k in irrelevant_kw)]
    all_missing = all(not x["存在"] for x in result["直接頁名查核"])
    if all_missing and not relevant:
        result["結論"] = (
            "查無《詞源》完整上下卷頁面：直接頁名（詞源、詞源/卷上、詞源/卷下等）均不存在，"
            "前綴搜尋無結果；標題搜尋僅命中不相關頁面。"
            "《歷代文論典》《詞話叢編》目錄雖列《詞源》書名，其連結為未建立頁面之紅連結。"
            "故《詞源》目前僅能以選錄作候選資料，不得標為全書。")
    else:
        result["結論"] = (
            "存在《詞源》相關頁面：" + "；".join(relevant) +
            "。須逐一核對是否為完整上下卷，方可作為全書語料。")
    return result


def fetch_book(book: dict, prev: dict | None = None) -> dict:
    oldid = book["oldid"]
    prev = prev if (prev and prev.get("oldid") == oldid) else None
    print(f"[處理中] 《{book['書名']}》 指定版本 oldid={oldid} …")
    if prev and files_ok(prev):
        for f in prev["檔案"]:
            print(f"   沿用 {f['路徑']}（SHA-256 核驗通過）")
        print(f"   結果：✓ 沿用現有檔案，本書本輪零網路請求。")
        prev["本次處理"] = "沿用現有檔案（SHA-256 核驗通過）"
        return prev
    try:
        info = get_revision_info(oldid)
        if info["title"] != book["title"]:
            raise RuntimeError(f"頁名不符：預期 {book['title']}，實得 {info['title']}")
        print(f"   修訂時間 {info['timestamp']}（{info['user']}）")

        wt = get_wikitext(oldid)
        parsed = get_parsed_html(oldid=oldid)
        html_body = parsed["text"]
        full_url = f"{INDEX}?title={requests.utils.quote(book['title'])}&oldid={oldid}"
        full_html = get_page_http(full_url)

        text = html_to_text(html_body)
        files = [
            save(RAW_DIR / f"{book['key']}_oldid{oldid}.html", full_html, "原始快照（完整頁面 HTML）"),
            save(RAW_DIR / f"{book['key']}_oldid{oldid}.wikitext", wt, "原始快照（wikitext）"),
            save(RAW_DIR / f"{book['key']}_oldid{oldid}.txt", text, "UTF-8 文本副本（清洗後）"),
        ]
        for f_ in files:
            print(f"   成功 {f_['路徑']}  sha256={f_['sha256'][:12]}…  字數={f_['字數_不含空白']}")
        print(f"   結果：✓ 成功下載《{book['書名']}》oldid={oldid}。")
        return {
            "書名": book["書名"], "作者": book["作者"], "朝代": book["朝代"],
            "角色": "正式語料（正文核定後使用）",
            "來源網站": "中文維基文庫 (zh.wikisource.org)",
            "來源網址": book["source_url"], "oldid": oldid,
            "修訂時間": info["timestamp"], "修訂者": info["user"], "修訂摘要": info["comment"],
            "下載時間": now_iso(),
            "本次處理": "成功下載",
            "檔案": files,
            "文本副本字數": {"含空白不含換行": files[-1]["字數_不含換行"],
                             "不含空白": files[-1]["字數_不含空白"]},
            "完整性狀態": "",  # 於主流程依書填寫
            "字形": "維基文庫原始字形（繁體，未做地區變體轉換；■ 等原書佔位符一律保留）",
        }
    except Exception as e:
        print(f"   結果：✗ 失敗——《{book['書名']}》oldid={oldid}：{e}")
        raise


def fetch_ciyuan_candidate(prev: dict | None = None) -> dict:
    prev = prev if (prev and ("選錄" in prev.get("書名", "")
                              or "詞論部分" in prev.get("書名", ""))) else None
    print(f"[處理中] 《詞源》候選來源：{GJTSC_TITLE} …")
    if prev and files_ok(prev):
        for f in prev["檔案"]:
            if f["路徑"].startswith("data/selected"):
                continue
            print(f"   沿用 {f['路徑']}（SHA-256 核驗通過）")
        print("   結果：✓ 原始快照沿用，零網路請求。")
        rec = prev
        rec["本次處理"] = "沿用原始快照（SHA-256 核驗通過）"
        oldid = rec["oldid"]
    else:
        try:
            d = api_get({"action": "query", "prop": "revisions", "titles": GJTSC_TITLE,
                         "rvprop": "ids|timestamp|user|size", "rvlimit": 1, "redirects": 1})
            page = d["query"]["pages"][0]
            if "missing" in page:
                raise RuntimeError("候選來源頁面不存在")
            rev = page["revisions"][0]
            oldid = rev["revid"]
            print(f"   最新修訂 oldid={oldid}（{rev['timestamp']}）")
            wt = get_wikitext(oldid)
            parsed = get_parsed_html(page=GJTSC_TITLE)
            html_body = parsed["text"]
            full_url = f"https://zh.wikisource.org/wiki/{requests.utils.quote(GJTSC_TITLE, safe='/')}"
            full_html = get_page_http(full_url)

            seg = extract_section(html_body, CAND_START, CAND_END)
            if len(seg) < 200:
                raise RuntimeError("候選段過短，疑似擷取失敗，請人工檢查")

            slug = "gujin_tushu_jicheng_wenxuedian_251"
            files = [
                save(RAW_DIR / f"{slug}_oldid{oldid}.html", full_html, "原始快照（完整頁面 HTML）"),
                save(RAW_DIR / f"{slug}_oldid{oldid}.wikitext", wt, "原始快照（wikitext，含 OCR 掃描頁轉錄指令）"),
                save(RAW_DIR / f"{slug}_oldid{oldid}.txt", html_to_text(html_body), "UTF-8 文本副本（整卷，清洗後）"),
                save(CAND_DIR / f"詞源_選錄_張炎樂府指迷段_{slug}_oldid{oldid}.txt", seg,
                     "歷史候選檔（章段未分節，已由 data/selected/ 取代，保留備查）"),
            ]
            for f_ in files:
                print(f"   成功 {f_['路徑']}  sha256={f_['sha256'][:12]}…  字數={f_['字數_不含空白']}")
            checks = check_ciyuan_presence()
            print(f"   《詞源》完整上下卷查核：{checks['結論']}")
            rec = {
                "書名": CIYUAN_RECORD_NAME, "作者": "張炎", "朝代": "宋",
                "角色": "本次選定語料（詞論部分，共14節）",
                "來源網站": "中文維基文庫 (zh.wikisource.org)：欽定古今圖書集成·理學彙編·文學典·第251卷（詞曲部總論）",
                "來源網址": full_url, "oldid": oldid,
                "修訂時間": rev["timestamp"], "修訂者": rev.get("user", ""),
                "下載時間": now_iso(),
                "本次處理": "成功下載",
                "檔案": files,
                "完整性狀態": "",
                "詞源完整版查核": checks,
                "字形": "維基文庫原始字形（繁體；OCR 轉錄，異體字待核）",
            }
        except Exception as e:
            print(f"   結果：✗ 失敗——《詞源》候選資料：{e}")
            raise

    # ---- 選定語料（本地處理，沿用或新下載皆執行）----
    sel = select_ciyuan_corpus(oldid)
    # 統一歷史候選檔用途標記
    for f in rec["檔案"]:
        if f["路徑"].startswith("data/candidates"):
            f["用途"] = "歷史候選檔（章段未分節，已由 data/selected/ 取代，保留備查）"
    rec["檔案"] = rec["檔案"] + sel["檔案_選定"]
    rec["選定語料十四節明細"] = sel["選定語料十四節明細"]
    rec["書名"] = CIYUAN_RECORD_NAME
    rec["作者"] = "張炎"
    rec["角色"] = "本次選定語料（詞論部分，共14節）"
    rec["選定狀態"] = "本次選定詞論範圍已取得，共14節"
    rec["完整性狀態"] = (
        "本次選定詞論範圍已取得，共14節（「張炎樂府指迷」章內〈詞源〉至〈雜論〉，見 data/selected/ciyuan.txt）；"
        "〈楊誠齋作詞五要〉另存為附文（不併入語料），原始快照保留。"
        "注：選錄出自《古今圖書集成·詞曲部總論》節錄（標題「張炎樂府指迷」沿襲書名混稱），非全書；"
        "卷上未取得、全文完整性待核；來源為掃描頁 OCR 轉錄並經機器標點，文字與標點待人工核對。"
        "維基文庫現無《詞源》完整上下卷頁面（詳見〈詞源完整版查核〉；擴大搜尋暫停，留待後續）。")
    print(f"   結果：✓ {rec['選定狀態']}；附文另存，原始快照保留。")
    return rec


def main() -> int:
    print("下載原始資料（zh.wikisource.org；每請求 20s 超時、最多重試一次）…")
    existing = load_existing_records()
    if existing:
        print(f"發現既有 sources.json（{len(existing)} 筆紀錄）：完整檔案將直接沿用。")

    records = []
    for b in BOOKS:
        records.append(fetch_book(b, existing.get(b["書名"])))

    # 完整性狀態（人工初核，依頁面結構；沿用時已有則不覆寫）
    if not records[0].get("完整性狀態"):
        records[0]["完整性狀態"] = (
            "頁面含四庫全書總目提要（提要，置卷首）、正文三十節（論作詞之法至詠物最忌説出題字）、"
            "附錄四跋（翁校本跋、翁重刊本跋、半塘老人跋、陳校本百尺樓叢書後序）。"
            "Textquality 標記 75%（已有校對，未達完美）；無獨立注釋節。"
            "正文完整性待逐節與他本核對。")
    if not records[1].get("完整性狀態"):
        records[1]["完整性狀態"] = (
            "頁面結構：詞旨敘（民國二年去病記）→ 詞旨上（陸輔之識）→ 詞說七則 → 屬對凡三十八則 → "
            "樂笑翁奇對凡二十三則 → 樂笑翁警句凡十三則 → 詞眼凡二十六則 → 單字集虛凡三十三字 → 詞旨暢舊序。"
            "文中以 ■ 佔位之缺字多處；單字集虛之下明言「兩字集虛 文缺」「三字集虛 文缺」；"
            "另有多則「詞未見」；部分文字經〔〕內疏證與「去病案」校勘。完整性待人工核對（缺字與引詞須與他本互校）。")

    records.append(fetch_ciyuan_candidate(
        existing.get(CIYUAN_RECORD_NAME) or existing.get("詞源（選錄：張炎樂府指迷段）")))

    payload = {
        "專案": "CHI3242-assignment1",
        "生成程式": "fetch_sources.py",
        "生成時間": now_iso(),
        "說明": [
            "原始快照為下載當時之頁面存檔；文本副本已移除網站導航、頁頭模板、目錄、編輯按鈕與頁腳，",
            "保留序跋、注釋、引文與原有字形；SHA-256 為存檔當時校驗值，重跑本程式會重新下載並覆寫。",
            "分詞與搭配詞分析留待正文核定後進行（見 AGENTS.md 與 來源核對清單）。",
        ],
        "語料": records,
    }
    SOURCES_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(SOURCES_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"== 已寫入 {SOURCES_JSON.relative_to(ROOT)} ==")
    write_checklist(records)
    print(f"== 已寫入 {CHECKLIST_MD.relative_to(ROOT)} ==")
    return 0


def write_checklist(records: list[dict]) -> None:
    yf, cz, cy = records[0], records[1], records[2]
    md = f"""# 來源核對清單

> 生成：`fetch_sources.py`（{now_iso()}）。逐項人工核對後，方將該層併入分析語料。
> 分詞與搭配詞分析留待正文核定後進行。

## 一、《樂府指迷》（沈義父，宋）— oldid {yf['oldid']}

| 層次 | 頁面內容 | 核對狀態 |
|---|---|---|
| 正文 | 論作詞之法、作詞當以清真爲主、康柳詞得失、姜詞得失、吳詞得失、施詞得失、孫詞得失、論起句、論過處、論結句、論詠物用事、要求字面當看唐詩、詠物不可直説、論造句、論押韻、詞中去聲字最緊要、坊間歌詞之病、詠花卉及賦情、句上虛字、誤讀柳詞、豪放與協律、壽詞須打破舊曲規模、用事須不用人姓名、腔以古雅爲主、詞多句中韵、詞腔、作大詞與作小詞法、作詞須推敲吟嚼、詠物最忌説出題字（共三十節） | 待人工核對（Textquality 75%） |
| 序跋 | 附錄：翁校本跋、翁重刊本跋、半塘老人跋、陳校本《百尺樓叢書後序》（清人跋語） | 待核對；分析時另列，不併入正文 |
| 校勘 | 卷首《四庫全書總目提要》（提要性質，非沈氏原文）；正文個別異體字（如「巻」「爲」） | 待核對 |
| 注釋 | 無獨立注釋節；人名以 ProperNoun 模板標記 | 已核（頁面現狀） |
| 疏證 | 無 | 已核（頁面現狀） |
| 增補詞作 | 無 | 已核（頁面現狀） |

## 二、《詞旨》（陸輔之，元）— oldid {cz['oldid']}

| 層次 | 頁面內容 | 核對狀態 |
|---|---|---|
| 序 | 卷首《詞旨敘》（民國二年，去病記於上海）；卷末《詞旨暢舊序》；《詞旨上》小序（「予從樂笑翁游…陸輔之識」） | 待核對；另列，不併入正文 |
| 正文 | 詞說七則；屬對凡三十八則；樂笑翁奇對凡二十三則；樂笑翁警句凡十三則；詞眼凡二十六則；單字集虛凡三十三字 | 待人工核對（■ 佔位缺字多處） |
| 疏證 | 〔〕內之胡元儀疏證（隨文小注，含引《詞源》語） | 待核對；分析時須與正文分離或分層統計 |
| 校勘 | 「去病案：…」各條；「○○選作○○／集本作○○／胡本作○○」異文記錄 | 待核對 |
| 注釋 | 與疏證同見〔〕內（含「詞未見」標注） | 待核對 |
| 增補詞作／引文 | 各則所附全詞引文（周、姜、吳、張等家詞）；「去病案：此則胡本脫去，今據他刻補」「均從草窗詞補入」等增補條目 | 待核對；引詞非《詞旨》正文 |
| 缺損 | ■ 佔位字；「兩字集虛 文缺」「三字集虛 文缺」；若干「詞未見」 | 已標記，完整性待核 |

## 三、《詞源》詞論部分（《古今圖書集成》所錄）（張炎，宋）— oldid {cy['oldid']}

| 層次 | 頁面內容 | 核對狀態 |
|---|---|---|
| 選定語料 | 《欽定古今圖書集成·文學典》第251卷〈詞曲部總論〉「張炎樂府指迷」章內，〈詞源〉至〈雜論〉共14節（data/selected/ciyuan.txt）：詞源、製曲、句法、字面、虛字、清空、意趣、用事、詠物、節序、賦情、離情、令曲、雜論 | **本次選定詞論範圍已取得，共14節**；OCR 文字與標點（含引號錯置、掃描硬換行）待人工核對 |
| 附文 | 〈楊誠齋作詞五要〉（data/selected/ciyuan_附文_楊誠齋作詞五要.txt） | 已另存，不併入選定語料 |
| 原始快照 | data/raw/gujin_tushu_jicheng_wenxuedian_251_oldid{cy['oldid']}.html／.wikitext／.txt（整卷） | 已保留 |
| 同卷其他內容 | 陸輔之樂府指迷（即《詞旨》選錄）、涵虛子詞品、徐炬《事物原始》、吳訥《文章辯體》、徐師曾《詩體明辯》等 | 僅供比對，不併入語料 |
| 完整版 | 維基文庫查無《詞源》完整上下卷頁面（《歷代文論典》《詞話叢編》目錄所列《詞源》為未建立之紅連結）；擴大搜尋暫停，留待後續 | 已查核（詳 sources.json〈詞源完整版查核〉） |

## 後續流程

1. 逐書人工核定正文層次與缺字；與他本（如《詞話叢編》本、《叢書集成》本）互校。
2. 第251卷及《詞源》選定語料為掃描頁 OCR 轉錄＋機器標點：含掃描硬換行、引號錯置等問題，核定時須合併斷行並校字；分詞前須去除「## 」節名行。
3. 核定後再依 AGENTS.md 流程：OpenCC 繁轉簡 → 分句 → jieba 分詞 → qhchina 搭配詞分析。
4. 名號指涉（姜夔、白石、白石道人、樂笑翁等）經人工核實後才合併統計。
"""
    CHECKLIST_MD.parent.mkdir(parents=True, exist_ok=True)
    with open(CHECKLIST_MD, "w", encoding="utf-8", newline="\n") as f:
        f.write(md)


if __name__ == "__main__":
    sys.exit(main())
