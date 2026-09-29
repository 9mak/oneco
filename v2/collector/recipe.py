"""レシピ（recipes/<slug>.yaml）の読み込みと実行。

流れ: 入口 URL → steps（follow / follow_text / follow_all / paginate / pdf_links / render）→ 文書の列
→ 各文書に rows を適用 → 行 → fields で項目を取る。
"""

from __future__ import annotations

import io
import re
import unicodedata
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import yaml
from bs4 import BeautifulSoup, Tag, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)   # RSS を HTML として読むレシピがある

from .fetch import Fetcher

_JUNK_IMAGE = re.compile(
    r"(icon|btn|button|logo|spacer|arrow|new_win|blank|banner|bnr|/common/|/design/|/img/parts|"
    r"header|footer|nav|menu|line\.|dot\.|bg_|_bg|pixel|1x1|tracking|counter|sns|facebook|twitter|"
    r"line_|instagram|youtube|\.svg$|loading|print|mail\.|tel\.|map\.|pdf\.|zoom|search)",
    re.I,
)
# 日付らしさ: 2026年9月11日 / R8.9.11 / 2026/9/11 / 9月11日（年無し。神奈川・北九州の表に多い）
_DATE_RE = re.compile(r"(令和|平成|R|H)?\s*\d{1,4}\s*[年./\-]\s*\d{1,2}\s*[月./\-]\s*\d{1,2}\s*日?|\d{1,2}\s*月\s*\d{1,2}\s*日")
# 管理番号らしさ: 26-0123 / D250299 / 8中-D0155 / No.20049 / 第12号 / 2 桁以上の数字
# （management_no は「受付番号」等の列を名指しで取った値なので、数字が 2 桁あれば番号とみなす）
_MGMT_RE = re.compile(r"[A-Za-z]?\d{1,4}[-‐\-–]\d{2,6}|[A-Za-z]{1,2}\d{3,}|No\.?\s*\d{2,}|第\s*\d+\s*号|\d{2,}")


class RecipeError(Exception):
    pass


@dataclass
class Recipe:
    steps: list[dict[str, Any]] = field(default_factory=list)
    rows: str = "body"
    row_filter: dict[str, Any] = field(default_factory=dict)
    image: str | dict[str, Any] = "img@src"
    fields: dict[str, Any] = field(default_factory=dict)
    species: dict[str, Any] = field(default_factory=dict)
    empty_text: list[str] = field(default_factory=list)
    encoding: str | None = None
    max_pages: int = 20
    base_url: str | None = None
    pdf: dict[str, Any] = field(default_factory=dict)
    rows_regex: str | None = None
    notes: str | None = None
    url: str | None = None          # 台帳の URL の代わりに開く入口（省略時は台帳の URL）

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Recipe:
        known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
        if isinstance(known.get("empty_text"), str):
            known["empty_text"] = [known["empty_text"]]
        return cls(**known)

    @classmethod
    def load(cls, path: Path) -> Recipe:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls.from_dict(raw)


# --- 文書 ------------------------------------------------------------------
@dataclass
class Doc:
    url: str
    html: str | None = None
    soup: BeautifulSoup | None = None
    pdf_tables: list[list[list[str]]] | None = None   # 表 → 行 → セル
    pdf_text: str | None = None
    rendered: bool = False

    @property
    def is_pdf(self) -> bool:
        return self.pdf_text is not None

    def text(self) -> str:
        if self.is_pdf:
            return self.pdf_text or ""
        return self.soup.get_text(" ", strip=True) if self.soup else ""


def _make_doc(url: str, html: str) -> Doc:
    return Doc(url=url, html=html, soup=BeautifulSoup(html, "lxml"))


def _make_pdf_doc(url: str, content: bytes) -> Doc:
    import pdfplumber

    tables: list[list[list[str]]] = []
    texts: list[str] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            texts.append(page.extract_text() or "")
            for t in page.extract_tables() or []:
                tables.append([[(c or "").replace("\n", " ").strip() for c in row] for row in t])
    return Doc(url=url, pdf_tables=tables, pdf_text="\n".join(texts))


# --- 行 ---------------------------------------------------------------------
@dataclass
class Row:
    doc: Doc
    el: Tag | None = None                   # HTML の行
    cells: dict[str, str] | None = None     # PDF 表の行（見出し名 → 値、"0","1".. も入れる）
    chunk: str | None = None                # PDF テキストの 1 頭分

    def text(self) -> str:
        if self.el is not None:
            return self.el.get_text(" ", strip=True)
        if self.cells is not None:
            return " ".join(v for k, v in self.cells.items() if not k.isdigit())
        return self.chunk or ""


# --- セレクタ -----------------------------------------------------------------
def parse_sel(spec: str) -> tuple[str, str]:
    """'a.x@href' → ('a.x', 'href')。@ が無ければ href。"""
    if "@" in spec:
        sel, attr = spec.rsplit("@", 1)
        return sel.strip(), attr.strip()
    return spec.strip(), "href"


def _attr(el: Tag, attr: str) -> str | None:
    if attr == "text":
        return el.get_text(" ", strip=True)
    v = el.get(attr)
    if isinstance(v, list):
        v = " ".join(v)
    return v.strip() if isinstance(v, str) and v.strip() else None


def _abs(base: str, href: str) -> str:
    return urljoin(base, href.strip())


# --- steps ------------------------------------------------------------------
class Executor:
    def __init__(self, fetcher: Fetcher, recipe: Recipe) -> None:
        self.fetcher = fetcher
        self.recipe = recipe
        self.trace: list[str] = []

    def _get(self, url: str, render: bool = False) -> Doc:
        if render:
            page = self.fetcher.render(url)
            d = _make_doc(page.final_url, page.html or "")
            d.rendered = True
            return d
        page = self.fetcher.get(url, encoding=self.recipe.encoding)
        if page.html is None:
            return _make_pdf_doc(page.final_url, page.content)
        return _make_doc(page.final_url, page.html)

    def resolve(self, entry_url: str) -> list[Doc]:
        """入口 URL から steps を辿り、rows を適用する文書の列を返す。

        recipe.url があれば台帳の URL より優先する（iframe の中身を直接指す等）。
        途中で通った文書は self.visited に残し、empty_text の照合に使う（PDF が 0 本の日など、
        最終文書が無くても入口ページの「現在いません」を拾えるように）。
        """
        entry_url = self.recipe.url or entry_url
        render_first = any(s.get("render") for s in self.recipe.steps)
        docs = [self._get(entry_url, render=render_first)]
        self.visited: list[Doc] = list(docs)
        self.trace.append(f"entry {entry_url}")
        for step in self.recipe.steps:
            if step.get("render"):
                continue
            docs = self._apply(step, docs)
            self.visited.extend(d for d in docs if d not in self.visited)
        return docs

    def _apply(self, step: dict[str, Any], docs: list[Doc]) -> list[Doc]:
        out: list[Doc] = []
        if "follow" in step:
            sel, attr = parse_sel(step["follow"])
            for d in docs:
                el = d.soup.select_one(sel) if d.soup else None
                href = _attr(el, attr) if el else None
                if not href:
                    raise RecipeError(f"follow: '{step['follow']}' が見つからない ({d.url})")
                url = _abs(self.recipe.base_url or d.url, href)
                self.trace.append(f"follow → {url}")
                out.append(self._get(url, render=step.get("rendered", False)))
        elif "follow_text" in step:
            words = step["follow_text"] if isinstance(step["follow_text"], list) else [step["follow_text"]]
            for d in docs:
                target = None
                for a in d.soup.select("a[href]") if d.soup else []:
                    t = a.get_text(" ", strip=True)
                    if any(w in t for w in words):
                        target = a
                        break
                if target is None:
                    raise RecipeError(f"follow_text: {words} を含むリンクが無い ({d.url})")
                url = _abs(self.recipe.base_url or d.url, target["href"])
                self.trace.append(f"follow_text → {url}")
                out.append(self._get(url))
        elif "follow_all" in step:
            sel, attr = parse_sel(step["follow_all"])
            limit = int(step.get("max", 200))
            for d in docs:
                seen: set[str] = set()
                for el in d.soup.select(sel) if d.soup else []:
                    href = _attr(el, attr)
                    if not href:
                        continue
                    url = _abs(self.recipe.base_url or d.url, href)
                    if url in seen or len(seen) >= limit:
                        continue
                    seen.add(url)
                    out.append(self._get(url, render=step.get("rendered", False)))
                self.trace.append(f"follow_all → {len(seen)} 件 ({d.url})")
        elif "paginate" in step:
            sel, attr = parse_sel(step["paginate"])
            limit = int(step.get("max", self.recipe.max_pages))
            for d in docs:
                out.append(d)
                cur = d
                seen = {d.url}
                while len(out) < limit + len(docs):
                    el = cur.soup.select_one(sel) if cur.soup else None
                    href = _attr(el, attr) if el else None
                    if not href:
                        break
                    url = _abs(self.recipe.base_url or cur.url, href)
                    if url in seen:
                        break
                    seen.add(url)
                    cur = self._get(url, render=cur.rendered)
                    out.append(cur)
                self.trace.append(f"paginate → {len(seen)} ページ")
        elif "pdf_links" in step:
            sel, attr = parse_sel(step["pdf_links"])
            limit = int(step.get("max", 50))
            for d in docs:
                seen = set()
                for el in d.soup.select(sel) if d.soup else []:
                    href = _attr(el, attr)
                    if not href:
                        continue
                    url = _abs(self.recipe.base_url or d.url, href)
                    if url in seen or len(seen) >= limit:
                        continue
                    seen.add(url)
                    page = self.fetcher.get(url)
                    out.append(_make_pdf_doc(page.final_url, page.content))
                self.trace.append(f"pdf_links → {len(seen)} 件")
        else:
            raise RecipeError(f"未知の step: {step}")
        return out


# --- rows -------------------------------------------------------------------
def extract_rows(recipe: Recipe, doc: Doc) -> list[Row]:
    if doc.is_pdf:
        return _pdf_rows(recipe, doc)
    assert doc.soup is not None
    rows = [Row(doc=doc, el=el) for el in doc.soup.select(recipe.rows)]
    return _filter_rows(recipe, rows)


def _filter_rows(recipe: Recipe, rows: list[Row]) -> list[Row]:
    f = recipe.row_filter or {}
    out = []
    for r in rows:
        t = r.text()
        if f.get("text_has_any") and not any(w in t for w in f["text_has_any"]):
            continue
        if f.get("text_has_all") and not all(w in t for w in f["text_has_all"]):
            continue
        if f.get("text_lacks") and any(w in t for w in f["text_lacks"]):
            continue
        if len(t) < int(f.get("min_text_length", 0)):
            continue
        out.append(r)
    return out


def _pdf_rows(recipe: Recipe, doc: Doc) -> list[Row]:
    mode = (recipe.pdf or {}).get("mode", "table")
    rows: list[Row] = []
    if mode == "text" or recipe.rows_regex:
        pat = re.compile(recipe.rows_regex or r"^.+$", re.M)
        text = doc.pdf_text or ""
        starts = [m.start() for m in pat.finditer(text)]
        for i, s in enumerate(starts):
            e = starts[i + 1] if i + 1 < len(starts) else len(text)
            rows.append(Row(doc=doc, chunk=text[s:e].strip()))
        return _filter_rows(recipe, rows)
    header_row = int((recipe.pdf or {}).get("header_row", 0))
    header_has = (recipe.pdf or {}).get("header_has")   # 見出し行にこの語があれば表とみなす
    for table in doc.pdf_tables or []:
        hr = header_row
        if header_has:
            # 見出し行の位置はページによってずれる（1 ページ目だけ「掲載日」行が先頭に付く等）ので、先頭 5 行から探す
            found = next((i for i, r in enumerate(table[:5]) if any(header_has in (h or "") for h in r)), None)
            if found is None:
                continue
            hr = found
        if len(table) <= hr:
            continue
        header = table[hr]
        for raw in table[hr + 1:]:
            cells: dict[str, str] = {}
            for i, v in enumerate(raw):
                cells[str(i)] = v
                h = (header[i] if i < len(header) else "").replace("\n", "").replace(" ", "")
                if h:
                    cells[h] = v
            if any(v for k, v in cells.items()):
                rows.append(Row(doc=doc, cells=cells))
    return _filter_rows(recipe, rows)


# --- fields -----------------------------------------------------------------
def _text(t: Tag) -> str | None:
    return t.get_text(" ", strip=True) or None


def _label_value(el: Tag, label: str) -> str | None:
    """「性別」と書かれたセルに対応する値。

    対応順: aria-label 属性 → th/dt の隣の td/dd → 見出し行の同じ列（次の tr）→ 表の先頭行が見出し
    → 「性別：メス」のようにテキスト内に書かれたもの。
    """
    c = el.select_one(f'[aria-label*="{label}"]')
    if c is not None:
        return _text(c)
    for cell in el.find_all(["th", "td", "dt"]):
        t = cell.get_text(" ", strip=True)
        if label not in t or len(t) > len(label) + 12:
            continue
        sib = cell.find_next_sibling(["td", "dd"])
        if sib is not None and label not in sib.get_text():
            return _text(sib)
        tr = cell.find_parent("tr")
        if tr is not None:
            kids = tr.find_all(["th", "td"], recursive=False)
            nxt = tr.find_next_sibling("tr")
            if cell in kids and nxt is not None:
                idx = kids.index(cell)
                cells = nxt.find_all(["th", "td"], recursive=False)
                if idx < len(cells) and label not in cells[idx].get_text():
                    return _text(cells[idx])
    if el.name == "tr":
        table = el.find_parent("table")
        head = table.find("tr") if table else None
        if head is not None and head is not el:
            heads = [c.get_text(" ", strip=True) for c in head.find_all(["th", "td"])]
            for i, h in enumerate(heads):
                if label in h:
                    cells = el.find_all(["td", "th"])
                    if i < len(cells):
                        return _text(cells[i])
    m = re.search(re.escape(label) + r"\s*[:：]\s*([^\s　]+)", el.get_text(" ", strip=True))
    return m.group(1) if m else None


def field_value(spec: Any, row: Row) -> str | None:
    if spec is None:
        return None
    if isinstance(spec, str):
        spec = {"selector": spec}
    val: str | None = None
    base_text = row.text()
    if row.cells is not None:
        if "header" in spec:
            key = str(spec["header"]).replace(" ", "")
            val = next((v for k, v in row.cells.items() if key in k), None)
        elif "index" in spec:
            val = row.cells.get(str(spec["index"]))
        elif "label" in spec:
            val = next((v for k, v in row.cells.items() if spec["label"] in k), None)
    elif row.el is not None:
        if "selector" in spec:
            el = row.el.select_one(spec["selector"]) if spec["selector"] not in (".", "self") else row.el
            if el is not None:
                val = _attr(el, spec.get("attr", "text"))
        elif "label" in spec:
            val = _label_value(row.el, spec["label"])
        elif "attr" in spec:
            val = _attr(row.el, spec["attr"])
    if "regex" in spec:
        m = re.search(spec["regex"], val if val is not None and ("selector" in spec or "label" in spec or "header" in spec) else base_text, re.S)
        val = (m.group(1) if m.groups() else m.group(0)).strip() if m else None
    if val is None and "default" in spec:
        val = spec["default"]
    if isinstance(val, str):
        val = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", val)).strip() or None
    return val


def image_url(recipe: Recipe, row: Row) -> tuple[str | None, str | None]:
    """(絶対 URL, 生の src)。ゴミ画像は除く。"""
    if row.el is None:
        return None, None
    spec = recipe.image
    if isinstance(spec, str):
        spec = {"selector": spec}
    sel, attr = parse_sel(spec.get("selector", "img@src"))
    if attr == "href" and sel.startswith("img"):
        attr = "src"
    exclude = [re.compile(x, re.I) for x in spec.get("exclude", [])]
    for el in row.el.select(sel):
        src = _attr(el, attr) or _attr(el, "data-src") or _attr(el, "data-original")
        if not src or src.startswith("data:"):
            continue
        if _JUNK_IMAGE.search(src) or any(p.search(src) for p in exclude):
            continue
        if spec.get("strip_query"):
            src = src.split("?", 1)[0]     # 取得ごとに変わるクエリ（キャッシュ避け）を外して ID を安定させる
        return _abs(recipe.base_url or row.doc.url, src), src
    return None, None


def looks_like_date(s: str | None) -> bool:
    return bool(s and _DATE_RE.search(s))


def looks_like_mgmt(s: str | None) -> bool:
    return bool(s and _MGMT_RE.search(s))
