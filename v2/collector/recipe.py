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
from typing import Any, Callable, TypeVar
from urllib.parse import urljoin

import yaml
from bs4 import BeautifulSoup, CData, NavigableString, Tag, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)   # RSS を HTML として読むレシピがある

from .fetch import FetchError, Fetcher, page_gone

T = TypeVar("T")

_JUNK_IMAGE = re.compile(
    r"(icon|btn|button|logo|spacer|arrow|new_win|blank|banner|bnr|/common/|/design/|/img/parts|"
    r"header|footer|nav|menu|line\.|dot\.|bg_|_bg|pixel|1x1|tracking|counter|sns|facebook|twitter|"
    r"line_|instagram|youtube|\.svg$|loading|print|mail\.|tel\.|map\.|pdf\.|zoom|"
    r"search(?=[^/]*$)|"   # 検索ボタン。ファイル名にだけ効かせる（町田市は写真が search_cat.images/ 配下にある）
    r"noimage|no[-_]?image|no[-_]?photo|nophoto|placeholder|dummy|junbichu|準備中)",   # 「写真なし」のプレースホルダ（山梨 noimage01.jpg 等）
    re.I,
)
# 日付らしさ: 2026年9月11日 / R8.9.11 / 2026/9/11 / 9月11日（年無し。神奈川・北九州の表に多い）
_DATE_RE = re.compile(r"(令和|平成|R|H)?\s*\d{1,4}\s*[年./\-]\s*\d{1,2}\s*[月./\-]\s*\d{1,2}\s*日?|\d{1,2}\s*月\s*\d{1,2}\s*日")
# 管理番号らしさ: 26-0123 / D250299 / 8中-D0155 / No.20049 / 第12号 / R8-6-5（岩手県奥州、元号＋1 桁区切り）/ 2 桁以上の数字
# （management_no は「受付番号」等の列を名指しで取った値なので、数字が 2 桁あれば番号とみなす）
_MGMT_RE = re.compile(r"[A-Za-z]?\d{1,4}[-‐\-–]\d{2,6}|[A-Za-z]\d{1,2}[-‐\-–]\d{1,3}[-‐\-–]\d{1,3}|[A-Za-z]{1,2}\d{3,}|No\.?\s*\d{2,}|第\s*\d+\s*号|\d{2,}")


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
    empty_selector: list[str] = field(default_factory=list)   # 0 頭の日に空になる一覧の器（文言が出ないサイト用）。extract.build で照合
    encoding: str | None = None
    max_pages: int = 20
    base_url: str | None = None
    pdf: dict[str, Any] = field(default_factory=dict)
    rows_regex: str | None = None
    notes: str | None = None
    url: str | None = None          # 台帳の URL の代わりに開く入口（省略時は台帳の URL）
    transpose: str | None = None    # 転置表（1 列 = 1 頭）の table セレクタ。指定時は rows の代わりに列を行にする
    row_until: str | None = None    # 指定時は rows の要素を 1 頭の始まりとし、後ろの兄弟要素を次の始まりかこの要素の手前までまとめて 1 行にする
    source_url: str | None = None   # PDF の子の元ページリンク。既定は入口ページ（日次で差し替わる PDF は翌日 404 になる）。"doc" で PDF そのもの

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Recipe:
        known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
        for key in ("empty_text", "empty_selector"):
            if isinstance(known.get(key), str):
                known[key] = [known[key]]
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
    captured: list[Any] = field(default_factory=list)   # 描画中に捕まえた JSON 応答（render_json 用）

    @property
    def is_pdf(self) -> bool:
        return self.pdf_text is not None

    def text(self) -> str:
        if self.is_pdf:
            return self.pdf_text or ""
        return self.soup.get_text(" ", strip=True) if self.soup else ""


def _make_doc(url: str, html: str) -> Doc:
    return Doc(url=url, html=html, soup=BeautifulSoup(html, "lxml"))


def _make_pdf_doc(url: str, content: bytes, columns: int = 1) -> Doc:
    """PDF を文字と表にする。columns > 1 なら各ページを左右に等分して列ごとに読む
    （茨城県のように 1 ページ 2 段組みで、丸ごと読むと左右の行が 1 行に混ざる PDF のため）。"""
    import pdfplumber

    tables: list[list[list[str]]] = []
    texts: list[str] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            parts = [page]
            if columns > 1:
                w = page.width / columns
                parts = [page.crop((i * w, 0, (i + 1) * w, page.height)) for i in range(columns)]
            for part in parts:
                texts.append(part.extract_text() or "")
                for t in part.extract_tables() or []:
                    tables.append([[(c or "").replace("\n", " ").strip() for c in row] for row in t])
    return Doc(url=url, pdf_tables=tables, pdf_text="\n".join(texts))


# --- 行 ---------------------------------------------------------------------
@dataclass
class Row:
    doc: Doc
    el: Tag | None = None                   # HTML の行
    cells: dict[str, str] | None = None     # PDF 表の行（見出し名 → 値、"0","1".. も入れる）
    chunk: str | None = None                # PDF テキストの 1 頭分
    anchor: Tag | None = None               # row_until でまとめた行の、元の文書上の始まりの要素（el は複製なので位置を持たない）

    @property
    def origin(self) -> Tag | None:
        """文書上の位置の基準（from: heading・prev/next_siblings 用）。まとめた行は元の始まりの要素。"""
        return self.anchor if self.anchor is not None else self.el

    def text(self) -> str:
        """行の全文（row_filter・種別・捨てた理由の表示に使う）。要素の境目は全部空白。"""
        if self.el is not None:
            return self.el.get_text(" ", strip=True)
        if self.cells is not None:
            return " ".join(v for k, v in self.cells.items() if not k.isdigit())
        return self.chunk or ""

    def field_text(self) -> str:
        """項目の regex を当てる全文。インライン要素の境目は詰める（visible_text）。

        text() は変えない: row_filter の text_lacks が「<span>0</span>匹」の境目の空白込みの文言
        （福島県「0 匹の情報があります」）で書かれているため。
        """
        if self.el is not None:
            return visible_text(self.el)
        return self.text()


# --- 文字の連結 ---------------------------------------------------------------
# 見た目で文字が続くインライン要素。この境目には空白を入れない（佐世保市「<span>令</span>和8年…」）
_INLINE_TAGS = frozenset({
    "a", "abbr", "b", "bdi", "bdo", "big", "cite", "code", "data", "del", "dfn", "em", "font", "i", "ins", "kbd",
    "label", "mark", "nobr", "q", "rb", "ruby", "s", "samp", "small", "span", "strike", "strong", "sub", "sup",
    "time", "tt", "u", "var", "wbr",
})


def visible_text(el: Tag) -> str:
    """要素の文字。get_text(" ", strip=True) と同じだが、インライン要素の境目には空白を入れない。

    ブロック要素（td・th・li・p・div・dt・dd・h1-6 等）・br・img の境目と、元の HTML にある空白は
    今まで通り空白 1 つ（「犬」「オス」が別のセルなら「犬 オス」のまま）。文字列ごとの前後の空白は落とす。
    """
    parts: list[str] = []
    gap = False     # 次の文字列との間に空白を入れるか

    def walk(node: Tag) -> None:
        nonlocal gap
        for c in node.children:
            if isinstance(c, Tag):
                inline = c.name in _INLINE_TAGS
                if not inline:
                    gap = True
                walk(c)
                if not inline:
                    gap = True
            elif type(c) in (NavigableString, CData):     # get_text と同じく注釈・script 等は除く
                s = str(c)
                t = s.strip()
                if not t:
                    gap = gap or bool(s)
                    continue
                if parts:
                    parts.append(" " if gap or s[0] != t[0] else "")
                parts.append(t)
                gap = s[-1] != t[-1]

    walk(el)
    return "".join(parts)


# --- セレクタ -----------------------------------------------------------------
def parse_sel(spec: str) -> tuple[str, str]:
    """'a.x@href' → ('a.x', 'href')。@ が無ければ href。"""
    if "@" in spec:
        sel, attr = spec.rsplit("@", 1)
        return sel.strip(), attr.strip()
    return spec.strip(), "href"


def _attr(el: Tag, attr: str) -> str | None:
    if attr == "text":
        return visible_text(el)
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

    def _get(self, url: str, render: bool = False, capture: str | None = None) -> Doc:
        if render:
            page = self.fetcher.render(url, capture=capture, **self._render_opts())
            d = _make_doc(page.final_url, page.html or "")
            d.rendered = True
            d.captured = list(page.captured)
            return d
        page = self.fetcher.get(url, encoding=self.recipe.encoding)
        if page.html is None:
            return _make_pdf_doc(page.final_url, page.content, columns=self._pdf_columns())
        return _make_doc(page.final_url, page.html)

    def _render_opts(self) -> dict[str, Any]:
        """steps の `render:` が辞書（{wait_for: セレクタ, wait_ms: ミリ秒}）なら、その指定を fetcher.render に渡す。"""
        spec = next((s["render"] for s in self.recipe.steps if s.get("render")), None)
        if not isinstance(spec, dict):
            return {}
        opt: dict[str, Any] = {}
        if spec.get("wait_for"):
            opt["wait_for"] = str(spec["wait_for"])
        if spec.get("wait_ms") is not None:
            opt["wait_ms"] = int(spec["wait_ms"])
        return opt

    def _pdf_columns(self) -> int:
        return int((self.recipe.pdf or {}).get("columns", 1))

    def resolve(self, entry_url: str) -> list[Doc]:
        """入口 URL から steps を辿り、rows を適用する文書の列を返す。

        recipe.url があれば台帳の URL より優先する（iframe の中身を直接指す等）。
        途中で通った文書は self.visited に残し、empty_text の照合に使う（PDF が 0 本の日など、
        最終文書が無くても入口ページの「現在いません」を拾えるように）。
        """
        entry_url = self.recipe.url or entry_url
        rj = next((s["render_json"] for s in self.recipe.steps if "render_json" in s), None)
        render_first = any(s.get("render") for s in self.recipe.steps) or rj is not None
        docs = [self._get(entry_url, render=render_first, capture=rj.get("match") if rj else None)]
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
            tried = 0
            failed: list[str] = []
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
                    tried += 1
                    doc = self._child(step, url, failed, lambda u=url: self._get(u, render=step.get("rendered", False)))
                    if doc is not None:
                        out.append(doc)
                self.trace.append(f"follow_all → {len(seen)} 件 ({d.url})")
            self._raise_if_all_failed("follow_all", tried, failed)
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
            tried = 0
            failed = []
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
                    tried += 1
                    page = self._child(step, url, failed, lambda u=url: self.fetcher.get(u))
                    if page is not None:
                        out.append(_make_pdf_doc(page.final_url, page.content, columns=self._pdf_columns()))
                self.trace.append(f"pdf_links → {len(seen)} 件")
            self._raise_if_all_failed("pdf_links", tried, failed)
        elif "render_json" in step:
            # 描画中に捕まえた JSON 応答（match の URL）から path の値を抜き、follow の {value} に差し込んで辿る。
            # 一覧が API 応答にしか無く <a href> が無い SPA（愛知わんにゃんナビ = Bubble）用
            spec = step["render_json"]
            limit = int(spec.get("max", 100))
            for d in docs:
                values = _json_values(d.captured, spec["path"])
                if not values:
                    raise RecipeError(f"render_json: '{spec['match']}' の応答に '{spec['path']}' が無い ({d.url})")
                seen: list[str] = []
                for v in values:
                    s = str(v)
                    if s in seen or len(seen) >= limit:
                        continue
                    seen.append(s)
                    out.append(self._get(spec["follow"].replace("{value}", s), render=spec.get("render", True)))
                self.trace.append(f"render_json → {len(seen)} 件")
        else:
            raise RecipeError(f"未知の step: {step}")
        return out

    def _child(self, step: dict[str, Any], url: str, failed: list[str], fetch: Callable[[], T]) -> T | None:
        """follow_all / pdf_links の子 1 本を取る。step に skip_errors: true があり、失敗が「ページが無い」
        （HTTP 404・410）なら、その 1 本だけ捨てて trace に残し、None を返す（群馬県・岐阜県: 一覧に
        消えた個別ページへのリンクが残り、1 本の 404 で slug 全体が落ちていた）。サーバーエラー・接続失敗は
        一時的なことが多く、黙って頭数を減らすより読めなかったと通知する方がよいので、従来どおり失敗にする。"""
        try:
            return fetch()
        except FetchError as e:
            if not step.get("skip_errors") or not page_gone(e):
                raise
            failed.append(f"{url}: {e}")
            self.trace.append(f"skip {url}: {e}")
            return None

    @staticmethod
    def _raise_if_all_failed(kind: str, tried: int, failed: list[str]) -> None:
        """skip_errors で捨てた結果、辿ろうとした子が全部失敗していたら従来どおり失敗にする（全部 404 の日を 0 頭扱いにしない）。"""
        if tried and len(failed) == tried:
            raise FetchError(f"{kind}: 辿った {tried} 本がすべて取得に失敗（{failed[0]}）")


def _json_values(obj: Any, path: str) -> list[Any]:
    """"hits.hits[]._id" のような簡単なパスで JSON から値を集める。obj が列なら各要素に適用して平らにする。"""
    toks = path.split(".")

    def walk(o: Any, ts: list[str]) -> list[Any]:
        if not ts:
            return [o]
        t = ts[0]
        if t.endswith("[]"):
            sub = o.get(t[:-2]) if isinstance(o, dict) else None
            return [x for item in (sub if isinstance(sub, list) else []) for x in walk(item, ts[1:])]
        if isinstance(o, dict) and t in o:
            return walk(o[t], ts[1:])
        return []

    if isinstance(obj, list):
        return [x for item in obj for x in walk(item, toks)]
    return walk(obj, toks)


# --- rows -------------------------------------------------------------------
def extract_rows(recipe: Recipe, doc: Doc) -> list[Row]:
    if doc.is_pdf:
        return _pdf_rows(recipe, doc)
    assert doc.soup is not None
    if recipe.transpose:
        rows = _transposed_rows(recipe, doc)
    elif recipe.row_until:
        rows = _grouped_rows(recipe, doc)
    else:
        rows = [Row(doc=doc, el=el) for el in doc.soup.select(recipe.rows)]
    return _filter_rows(recipe, rows)


def _transposed_rows(recipe: Recipe, doc: Doc) -> list[Row]:
    """1 列 = 1 頭の転置表（栃木県子犬・子猫）。

    表の中で「セルが N 個（N ≥ 2）の行」を個体別の行、「セルが 1 個の行」を全頭共通の注記
    （枠名や「5 月生まれ ワクチン接種済」）とみなし、列ごとに自分のセル＋共通セルを 1 つの要素に
    まとめて行にする。行の並び順は表ごとに違ってよい（fields は regex で取る）。
    全部の行が 1 セルの表（1 表 = 1 頭。栃木の子猫ページ）は表全体を 1 行にする。
    """
    import copy

    assert doc.soup is not None
    rows: list[Row] = []
    for table in doc.soup.select(recipe.transpose or ""):
        trs = [tr.find_all(["td", "th"], recursive=False) for tr in table.select("tr")]
        n = max((len(c) for c in trs), default=0)
        if n < 1:
            continue
        for i in range(n):
            holder = BeautifulSoup('<div class="transposed"></div>', "lxml").div
            assert holder is not None
            for cells in trs:
                if len(cells) == n:
                    holder.append(copy.copy(cells[i]))
                elif len(cells) == 1:
                    holder.append(copy.copy(cells[0]))
            rows.append(Row(doc=doc, el=holder))
    return rows


def _grouped_rows(recipe: Recipe, doc: Doc) -> list[Row]:
    """1 頭分がフラットな兄弟要素に分かれているページ（鹿児島市: h2 番号 → p 写真 → p 種類 …）。

    rows に当たった要素を 1 頭の始まりとし、後ろの兄弟要素を「次の始まり（またはそれを中に含む要素）」か
    「row_until に当たる要素」の手前までまとめ、複製を入れた div を行にする（_transposed_rows と同じ作り）。
    fields・image・row_filter はこの div の中を探す。元の位置は Row.anchor に持たせる。
    """
    import copy

    if doc.soup is None:
        return []
    starts = doc.soup.select(recipe.rows)
    start_ids = {id(s) for s in starts}
    rows: list[Row] = []
    for start in starts:
        holder = BeautifulSoup("", "lxml").new_tag("div", attrs={"class": "grouped"})
        holder.append(copy.copy(start))
        for sib in start.find_next_siblings():
            if not isinstance(sib, Tag):
                continue
            if id(sib) in start_ids or any(id(d) in start_ids for d in sib.find_all(True)):
                break      # 次の子の始まり（さいたま市: 2 頭目だけ div に包まれている）
            if sib.css.match(recipe.row_until or ""):
                break      # 区切り（大分市: 「お家がみつかりました」の h2、千葉市: 掲載日の h2）
            holder.append(copy.copy(sib))
        rows.append(Row(doc=doc, el=holder, anchor=start))
    return rows


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
    return visible_text(t) or None


_LABEL_PUNCT = " \t\r\n　:：・、。()（）[]［］【】「」<>＜＞*＊"


def _looks_like_heading(head: Tag, cand: Tag, label: str) -> bool:
    """label のセル head に対応する値の候補 cand が、値ではなく見出しに見えるか。

    見出しが横に並ぶ表（td「収容日」｜td「収容場所」の次の行が値）では、label「収容」の隣は別の見出しなので
    捨てて次の行を見る。この判定は以前「cand が label の文字を含めば捨てる」だったため、値が label を含むだけ
    （label「保健所」の値「菊池保健所」、熊本県動愛）でも捨てていた。今は次のときだけ見出しとみなす:
    - cand が th / dt（見出しのタグ）で label を含む
    - cand の文字が label そのもの（「性別：」のように記号・空白を除くと label と同じ）
    - cand の中に「label: …」と書かれている（値のセルの中に項目名つきで書く作り。従来どおり最後の読み取りに任せる）
    - head も cand も td で、cand が label で始まる（「収容日｜収容場所」のように見出しが並ぶ行）
    th → td、dt → dd の組は見出しと値がタグで分かれているので、label を含むだけの値は取る。
    """
    if label not in cand.get_text():
        return False
    text = cand.get_text("", strip=True)
    if cand.name in ("th", "dt"):
        return True
    if text.strip(_LABEL_PUNCT) == label:
        return True
    if re.search(re.escape(label) + r"\s*[:：]", text):
        return True     # セルの中に「備考: …」と書かれている（高知 kochi_apc）。最後の「label：値」の読み取りに任せる
    if head.name == "td":
        return text.startswith(label)
    return False


def _label_value(el: Tag, label: str) -> str | None:
    """「性別」と書かれたセルに対応する値。

    対応順: aria-label 属性 → th/dt の隣の td/dd → 見出し行の同じ列（次の tr）→ 表の先頭行が見出し
    → 「性別：メス」のようにテキスト内に書かれたもの。値が見出しに見えるとき（_looks_like_heading）は捨てて次を見る。
    """
    c = el.select_one(f'[aria-label*="{label}"]')
    if c is not None:
        return _text(c)
    for cell in el.find_all(["th", "td", "dt"]):
        t = visible_text(cell)
        if label not in t or len(t) > len(label) + 12:
            continue
        sib = cell.find_next_sibling(["td", "dd"])
        if sib is not None and not _looks_like_heading(cell, sib, label):
            return _text(sib)
        tr = cell.find_parent("tr")
        if tr is not None:
            kids = tr.find_all(["th", "td"], recursive=False)
            nxt = tr.find_next_sibling("tr")
            if cell in kids and nxt is not None:
                idx = kids.index(cell)
                cells = nxt.find_all(["th", "td"], recursive=False)
                if idx < len(cells) and not _looks_like_heading(cell, cells[idx], label):
                    return _text(cells[idx])
    if el.name == "tr":
        table = el.find_parent("table")
        head = table.find("tr") if table else None
        if head is not None and head is not el:
            heads = [visible_text(c) for c in head.find_all(["th", "td"])]
            for i, h in enumerate(heads):
                if label in h:
                    cells = el.find_all(["td", "th"])
                    if i < len(cells):
                        return _text(cells[i])
    m = re.search(re.escape(label) + r"\s*[:：]\s*([^\s　]+)", visible_text(el))
    return m.group(1) if m else None


def nearest_heading(el: Tag, selector: str) -> str | None:
    """行より前にある、selector に合う直近の要素（見出し）のテキスト。"""
    root = el
    while root.parent is not None and root.parent.name != "[document]":
        root = root.parent
    # 文書順は要素の同一性（id）で比べる。Tag の == は中身の比較なので、同じ文面の行が 2 つあると
    # 「後の見出し」を前の行にも当ててしまう（越谷の同日同所 2 頭で発覚）
    order = {id(t): i for i, t in enumerate(root.find_all(True))}
    pos = order.get(id(el))
    if pos is None:
        return None
    best = None
    for c in root.select(selector):
        if c is el or any(d is el for d in c.descendants):
            continue
        if order.get(id(c), -1) < pos:
            best = c
    return visible_text(best) if best is not None else None


def field_value(spec: Any, row: Row) -> str | None:
    if spec is None:
        return None
    if isinstance(spec, str):
        spec = {"selector": spec}
    val: str | None = None
    base_text = row.field_text()
    from_heading = spec.get("from") == "heading"   # 行より前の直近の見出しから取る（越谷の管理番号 h3、広島の整理番号 h2）
    if from_heading and row.origin is not None:
        val = nearest_heading(row.origin, spec.get("selector", "h2, h3, h4"))
    elif row.cells is not None:
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
        m = re.search(spec["regex"], val if val is not None and ("selector" in spec or "label" in spec or "header" in spec or from_heading) else base_text, re.S)
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

    def pick(root: Tag) -> tuple[str, str] | None:
        for el in root.select(sel):
            src = _attr(el, attr) or _attr(el, "data-src") or _attr(el, "data-original")
            if not src or src.startswith("data:"):
                continue
            if _JUNK_IMAGE.search(src) or any(p.search(src) for p in exclude):
                continue
            if spec.get("strip_query"):
                src = src.split("?", 1)[0]     # 取得ごとに変わるクエリ（キャッシュ避け）を外して ID を安定させる
            return _abs(recipe.base_url or row.doc.url, src), src
        return None

    scope = spec.get("scope")
    if scope in ("self_or_prev_siblings", "self_or_next_siblings"):
        # 行の中を先に探し、無ければ兄弟要素（岐阜県: 保健所によって写真が表の中だったり、表の直前の p だったりする）
        hit = pick(row.el)
        if hit:
            return hit
    root: Tag = row.el
    if scope in ("prev_siblings", "self_or_prev_siblings", "next_siblings", "self_or_next_siblings"):
        # 写真が行の外の兄弟要素にあるとき。prev は直前（広島市: h2 → p.imagecenter img → dl）、
        # next は直後（名古屋市 譲渡猫: h2 → p.imagecenter img）。次／前の行に当たるまで進み、文書順に並べて探す
        root = _sibling_holder(recipe, spec, row.origin or root, forward=scope.endswith("next_siblings"))
    return pick(root) or (None, None)


def _sibling_holder(recipe: Recipe, spec: dict[str, Any], base: Tag, forward: bool) -> Tag:
    """base の前（forward なら後ろ）の兄弟要素を、前／次の行に当たる手前まで集め、文書順に複製した div。

    既定は base と同じタグ名の兄弟で止める（広島市・明石・岐阜）。stop_at: row なら「rows に当たる要素」で止める
    （岩手県: 行も写真も p なので、同じタグ名で止めると写真の p で止まる）。
    まとめた行（row_until）では base は元の始まりの要素。
    """
    import copy

    holder = BeautifulSoup("", "lxml").new_tag("div", attrs={"class": "next-siblings" if forward else "prev-siblings"})
    sibs: list[Tag] = []
    stop_at_row = spec.get("stop_at") == "row" and isinstance(recipe.rows, str)
    walk = base.find_next_siblings() if forward else base.find_previous_siblings()
    for sib in walk:
        if not isinstance(sib, Tag):
            continue
        if stop_at_row:
            try:
                if sib.css.match(recipe.rows):
                    break
            except Exception:  # noqa: BLE001 — 解釈できないセレクタは既定の止め方に戻す
                if sib.name == base.name:
                    break
        elif sib.name == base.name:
            break
        sibs.append(sib)
    for sib in (sibs if forward else reversed(sibs)):
        holder.append(copy.copy(sib))
    return holder


def looks_like_date(s: str | None) -> bool:
    return bool(s and _DATE_RE.search(s))


def looks_like_mgmt(s: str | None) -> bool:
    return bool(s and _MGMT_RE.search(s))
