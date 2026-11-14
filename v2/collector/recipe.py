"""レシピ（recipes/<slug>.yaml）の読み込みと実行。

流れ: 入口 URL → steps（follow / follow_text / follow_all / paginate / pdf_links / render / submit_form）→ 文書の列
→ 各文書に rows を適用 → 行 → fields で項目を取る。
"""

from __future__ import annotations

import io
import re
import unicodedata
import warnings
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import urljoin, urlsplit

import yaml
from bs4 import BeautifulSoup, CData, NavigableString, PageElement, Tag, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)   # RSS を HTML として読むレシピがある

from .errors import ErrorInfo
from .fetch import Fetcher, FetchError, page_gone

T = TypeVar("T")

_JUNK_IMAGE = re.compile(
    r"(icon|btn|button|logo|spacer|arrow|new_win|blank|banner|bnr|/common/|/design/|/img/parts|"
    r"header|footer|nav|menu|line\.|dot\.|bg_|_bg|pixel|1x1|tracking|counter|sns|facebook|twitter|"
    r"line_|instagram|youtube|\.svg$|loading|print|mail\.|tel\.|map\.|pdf\.|zoom|"
    r"search(?=[^/]*$)|"   # 検索ボタン。ファイル名にだけ効かせる（町田市は写真が search_cat.images/ 配下にある）
    r"noimage|no[-_]?image|no[-_]?photo|nophoto|no[-_]?gazou|placeholder|dummy|junbichu|準備中)",   # 「写真なし」のプレースホルダ（山梨 noimage01.jpg・千葉県 no_gazou.png 等）
    re.I,
)
# 日付らしさ: 2026年9月11日 / R8.9.11 / 2026/9/11 / 9月11日（年無し。神奈川・北九州の表に多い）
_DATE_RE = re.compile(r"(令和|平成|R|H)?\s*\d{1,4}\s*[年./\-]\s*\d{1,2}\s*[月./\-]\s*\d{1,2}\s*日?|\d{1,2}\s*月\s*\d{1,2}\s*日")
# 管理番号らしさ: 26-0123 / D250299 / 8中-D0155 / No.20049 / 第12号 / R8-6-5（岩手県奥州、元号＋1 桁区切り）/ 2 桁以上の数字
# （management_no は「受付番号」等の列を名指しで取った値なので、数字が 2 桁あれば番号とみなす）
_MGMT_RE = re.compile(r"[A-Za-z]?\d{1,4}[-‐\-–]\d{2,6}|[A-Za-z]\d{1,2}[-‐\-–]\d{1,3}[-‐\-–]\d{1,3}|[A-Za-z]{1,2}\d{3,}|No\.?\s*\d{2,}|第\s*\d+\s*号|\d{2,}")


class RecipeError(Exception):
    """レシピの定義・実行の失敗。info.kind は recipe（判定用）。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.info = ErrorInfo("recipe", phase="parse")


@dataclass
class Recipe:
    steps: list[dict[str, Any]] = field(default_factory=list)
    rows: str = "body"
    row_filter: dict[str, Any] = field(default_factory=dict)
    image: str | dict[str, Any] = "img@src"
    fields: dict[str, Any] = field(default_factory=dict)
    species: dict[str, Any] = field(default_factory=dict)
    empty_text: list[str] = field(default_factory=list)
    empty_text_each: list[str] = field(default_factory=list)   # rows を当てる文書の「全部」が、この文のどれかを出したときだけ 0 頭（保健所・PDF ごとに 0 頭の文を出すサイト。W006 T631）。extract.build で照合
    empty_text_entries: list[str] = field(default_factory=list)   # 入口の文書（steps で辿る前の ?animal-type=… 等の一覧）の「全部」が、この文のどれかを出したときだけ 0 頭（入口を複数にした一覧の 1 本が空の文を出すのは子がいる日も同じなので、empty_text にできない。W006 監査 B 班）。extract.empty_hits で照合
    empty_text_all: list[str] = field(default_factory=list)   # 列挙した 0 頭の文が全部出たときだけ 0 頭（複数の節があるページ。W006 T631）。extract.build で照合
    empty_selector: list[str] = field(default_factory=list)   # 0 頭の日に空になる一覧の器（文言が出ないサイト用）。extract.build で照合
    empty_absent: dict[str, str] = field(default_factory=dict)   # {page, none}: 0 頭の日に器ごと消えるサイト用。extract.build で照合
    empty_container: str | None = None   # rows が単一段のとき、全行除外の 0 頭を確定する根拠にする一覧の器（W006 T605）。extract.build で照合
    encoding: str | None = None
    max_pages: int = 20
    base_url: str | None = None
    pdf: dict[str, Any] = field(default_factory=dict)
    rows_regex: str | None = None
    notes: str | None = None
    url: str | None = None          # 台帳の URL の代わりに開く入口（省略時は台帳の URL）
    urls: list[str] = field(default_factory=list)   # 入口を複数にする（url の代わりに全部開き、steps は全部の入口に適用）。長崎犬猫ネット: 一覧の ?animal-type=dog|cat|others
    transpose: str | None = None    # 転置表（1 列 = 1 頭）の table セレクタ。指定時は rows の代わりに列を行にする
    row_until: str | None = None    # 指定時は rows の要素を 1 頭の始まりとし、後ろの兄弟要素を次の始まりかこの要素の手前までまとめて 1 行にする
    id_by_management_no: list[str] = field(default_factory=list)   # 同じ写真を共有する子のうち、この管理番号（前方一致）の行は写真でなく管理番号から ID を作る。先に載った子が消えても残った子の ID が写真由来（消えた子の ID）に移らないよう、先頭の子以外を固定する
    unique_management_no: bool = False   # 同じ管理番号の行が 2 つ以上あるとき、先の行だけ採る（上が最新で下に古い掲載が残るページ。鹿児島市 保護犬）。写真の有無で ID が別になるので「同じ ID」の判定では重なりを捨てられない
    source_url: str | None = None   # PDF の子の元ページリンク。既定は入口ページ（日次で差し替わる PDF は翌日 404 になる）。"doc" で PDF そのもの

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Recipe:
        known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
        for key in ("empty_text", "empty_text_each", "empty_text_entries", "empty_selector"):
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
    parent_url: str | None = None   # follow / follow_all で辿ってきた元の文書の URL（species.from: parent_url 用。入口は None）

    @property
    def is_pdf(self) -> bool:
        return self.pdf_text is not None

    def text(self) -> str:
        if self.is_pdf:
            return self.pdf_text or ""
        return self.soup.get_text(" ", strip=True) if self.soup else ""


def _make_doc(url: str, html: str) -> Doc:
    return Doc(url=url, html=html, soup=BeautifulSoup(html, "lxml"))


def _make_pdf_doc(url: str, content: bytes, columns: int = 1, join_ja: bool = False) -> Doc:
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
                for t in _page_tables(part):
                    tables.append([[_pdf_cell(c, join_ja) for c in row] for row in t])
    return Doc(url=url, pdf_tables=tables, pdf_text="\n".join(texts))


# 和文の文字（かな・カナ・漢字・長音・々・〜）。「・」「※」「。」は入れない（箇条書きの頭と文の終わりの改行は空白にする）
_JA = "ぁ-んァ-ヶー一-龠々〆〜"
_JA_BREAK = re.compile(rf"(?<=[{_JA}])\n(?=[{_JA}])")


def _pdf_cell(c: str | None, join_ja: bool = False) -> str:
    """PDF の表のセル。改行は空白にする。join_ja（レシピの pdf.join_ja_lines）なら、セル幅で折り返した和文の途中の改行は詰める
    （香川 さぬき「スクスク成 長しています」。2026-11-13 Codex #28）。神奈川県のように改行で句を区切る PDF もあるので既定では詰めない。"""
    s = _JA_BREAK.sub("", c or "") if join_ja else (c or "")
    return s.replace("\n", " ").strip()


_CIRCLED = re.compile("[①-⑳]")   # ①〜⑳


def _norm_text(val: str) -> str | None:
    """項目の値の正規化（NFKC・空白を 1 つに）。丸数字は NFKC で数字に潰れて「メス:4匹①②③⑤」が「メス:4匹1235」に
    なるので残す（福井県動物愛護センター。2026-11-13 Codex #5）。"""
    marks = _CIRCLED.findall(val)
    parts = [unicodedata.normalize("NFKC", p) for p in _CIRCLED.split(val)]
    joined = "".join(p + (marks[i] if i < len(marks) else "") for i, p in enumerate(parts))
    return re.sub(r"\s+", " ", joined).strip() or None


def _page_tables(page: Any) -> list[list[list[str | None]]]:
    """ページの表。最下行の下の横罫線が引かれていない表は、縦罫線の下端に横罫線を補って最下行も取る。

    神奈川県 センター外保護猫（cat.pdf）は 1 ページ目の最下行だけ下の横罫線が無く（縦罫線は下まで伸びている）、
    pdfplumber が表をその上の横罫線で閉じて最下行（No.46）を落としていた。補うのは次をすべて満たすときだけ:
    - 表の中から始まる縦罫線が、表の下端より下まで伸びている（表の列の境目の半分以上、かつ 2 本以上）
    - 伸びた先に、表の幅の横罫線がまだ無い
    - 伸びた長さが表の行の高さの 3 倍以内（ページ枠のような長い線で本文やフッターを表にしない）
    """
    found = page.find_tables()
    tol = 3.0
    h_edges = [e for e in page.edges if e["orientation"] == "h" and e["x1"] - e["x0"] >= tol]
    extra: list[float] = []
    for t in found:
        x0, top, x1, bottom = t.bbox
        inside = [e for e in page.edges if e["orientation"] == "v" and x0 - tol <= e["x0"] <= x1 + tol
                  and e["top"] >= top - tol and e["top"] <= bottom - tol]
        longer = [e for e in inside if e["bottom"] > bottom + tol]
        cols = {round(e["x0"]) for e in inside}
        long_cols = {round(e["x0"]) for e in longer}
        if len(long_cols) < 2 or len(long_cols) * 2 < len(cols):
            continue
        y = max(e["bottom"] for e in longer)
        row_h = max((r.bbox[3] - r.bbox[1] for r in t.rows), default=0.0)
        if row_h <= 0 or y - bottom > row_h * 3:
            continue
        if any(abs(h["top"] - y) <= tol and h["x0"] <= x0 + tol and h["x1"] >= x1 - tol for h in h_edges):
            continue
        extra.append(y)
    if not extra:
        return [t.extract() for t in found]
    return page.extract_tables({"explicit_horizontal_lines": extra}) or []


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
    # 再帰でなく明示のスタックで回す（閉じ忘れの strong が数百段重なるページで RecursionError にしない。千葉県で 52 段の実例）。
    # 要素は (子の反復子, ブロック要素か)。ブロック要素に入るときと出るときに空白を入れる
    stack: list[tuple[Iterator[PageElement], bool]] = [(iter(el.children), False)]
    while stack:
        it, block = stack[-1]
        c = next(it, None)
        if c is None:
            stack.pop()
            if block:
                gap = True
            continue
        if isinstance(c, Tag):
            inline = c.name in _INLINE_TAGS
            if not inline:
                gap = True
            stack.append((iter(c.children), not inline))
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


def _script_urls(doc: Doc, pattern: str, base: str) -> list[str]:
    """follow_all の script_url: 文書のインラインの script（src の無いもの）から pattern に合う URL を拾う。
    グループがあれば 1 番目、無ければ全体。辿るときと同じ base で解決し、http(s) で文書と同じホストの URL だけ拾う
    （解析用のタグ等を辿らない）。熊本市の一覧は記事が 1 件の日だけ一覧を出さず location.href='…detail.aspx?…' で
    その記事へ飛ばす（W006 2026-11-13）。"""
    if doc.soup is None:
        return []
    host = urlsplit(doc.url).hostname
    out: list[str] = []
    for s in doc.soup.find_all("script"):
        if s.get("src"):
            continue
        for m in re.finditer(pattern, s.get_text()):
            href = (m.group(1) if m.groups() else m.group(0)).strip()
            if not href:
                continue
            u = urlsplit(_abs(base, href))
            if u.scheme in ("http", "https") and u.hostname == host:
                out.append(href)
    return out


# --- form（steps の submit_form）---------------------------------------------
_NO_SUBMIT_INPUT = frozenset({"submit", "button", "image", "reset", "file"})


def form_data(form: Tag) -> dict[str, str | list[str]]:
    """ブラウザが form を送るときの値の集め方（input・select・textarea）。ボタン類・無効な項目・チェックの無い
    checkbox / radio は送らない。select multiple は選んだ全部を list で持つ。"""
    data: dict[str, str | list[str]] = {}

    def put(name: str, value: str) -> None:
        cur = data.get(name)
        if cur is None:
            data[name] = value
        elif isinstance(cur, list):
            cur.append(value)
        else:
            data[name] = [cur, value]

    for el in form.select("input, select, textarea"):
        name = el.get("name")
        if not isinstance(name, str) or not name or el.has_attr("disabled"):
            continue
        if el.name == "input":
            typ = str(el.get("type") or "text").lower()
            if typ in _NO_SUBMIT_INPUT:
                continue
            if typ in ("checkbox", "radio"):
                if el.has_attr("checked"):
                    put(name, str(el.get("value") if el.get("value") is not None else "on"))
                continue
            put(name, str(el.get("value") or ""))
        elif el.name == "textarea":
            put(name, el.get_text())
        else:
            options = el.select("option")
            chosen = [o for o in options if o.has_attr("selected")]
            if not chosen and options and not el.has_attr("multiple"):
                chosen = options[:1]
            for o in chosen:
                put(name, str(o.get("value") if o.get("value") is not None else o.get_text(strip=True)))
    return data


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
            return _make_pdf_doc(page.final_url, page.content, columns=self._pdf_columns(), **self._pdf_opts())
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

    def _pdf_opts(self) -> dict[str, bool]:
        """_make_pdf_doc に足す引数。指定のあるレシピだけ渡す（試験で _make_pdf_doc を差し替えているものを壊さない）。"""
        return {"join_ja": True} if (self.recipe.pdf or {}).get("join_ja_lines") is True else {}

    def resolve(self, entry_url: str) -> list[Doc]:
        """入口 URL から steps を辿り、rows を適用する文書の列を返す。

        recipe.url があれば台帳の URL より優先する（iframe の中身を直接指す等）。
        途中で通った文書は self.visited に残し、empty_text の照合に使う（PDF が 0 本の日など、
        最終文書が無くても入口ページの「現在いません」を拾えるように）。
        """
        entry_urls = self.recipe.urls or [self.recipe.url or entry_url]
        rj = next((s["render_json"] for s in self.recipe.steps if "render_json" in s), None)
        render_first = any(s.get("render") for s in self.recipe.steps) or rj is not None
        docs = []
        for u in entry_urls:
            docs.append(self._get(u, render=render_first, capture=rj.get("match") if rj else None))
            self.trace.append(f"entry {u}")
        self.visited: list[Doc] = list(docs)
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
                child = self._get(url, render=step.get("rendered", False))
                child.parent_url = d.url
                out.append(child)
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
                hrefs = [_attr(el, attr) for el in (d.soup.select(sel) if d.soup else [])]
                if step.get("script_url"):
                    hrefs += _script_urls(d, str(step["script_url"]), self.recipe.base_url or d.url)
                for href in hrefs:
                    if not href:
                        continue
                    url = _abs(self.recipe.base_url or d.url, href)
                    if url in seen or len(seen) >= limit:
                        continue
                    seen.add(url)
                    tried += 1
                    doc = self._child(step, url, failed, lambda u=url: self._get(u, render=step.get("rendered", False)))
                    if doc is not None:
                        doc.parent_url = d.url
                        out.append(doc)
                self.trace.append(f"follow_all → {len(seen)} 件 ({d.url})")
                if self.recipe.urls and d.parent_url is None and not seen:
                    # 入口を複数にしたレシピで、子のリンクが 0 本なのに自分の 0 頭の文も出していない入口は、作りが変わったのであって
                    # 空ではない。他の入口に子がいても成功にすると、その入口の子が黙って全部消える（W006 監査 B 班 F-01）
                    ents = self.recipe.empty_text_entries
                    if not (d.soup is not None and any(t in d.text() for t in ents)):
                        raise RecipeError(f"follow_all: 入口 {d.url} に子のリンクが無く、empty_text_entries の文も無い（一覧の作りが変わった）")
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
                        out.append(_make_pdf_doc(page.final_url, page.content, columns=self._pdf_columns(), **self._pdf_opts()))
                self.trace.append(f"pdf_links → {len(seen)} 件")
            self._raise_if_all_failed("pdf_links", tried, failed)
        elif "submit_form" in step:
            for d in docs:
                out.extend(self._submit_form(step["submit_form"], d))
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

    def _submit_form(self, spec: dict[str, Any], d: Doc) -> list[Doc]:
        """文書 d の form を POST して結果の文書を返す（W006 鹿児島県。画像ボタンの JavaScript が hidden と anti-forgery
        トークン付きの form を POST して一覧を出すサイト用）。hidden など form の値を集め、`set` の値で上書き・追加して送る。

        - 宛先は form の action だけ（レシピに URL を書かせない）。文書と別のホスト・POST でない form は拒否する
        - `require` の名前の値が form に無い・空なら送らず失敗（トークンが取れない日を 0 頭にしない）
        - 結果の文書の URL は入口のページの URL のまま（source_url が POST 専用の URL にならないように）
        - 返ってきた URL の path が action と違えば失敗（token 不正・セッション切れは /Shared/Error へ転送される）
        - `repeat_while`（セレクタ）があれば paginate と同じ形: d を残し、その要素が結果にある間、結果の同じ form を送って次を得る。
          max（既定 recipe.max_pages）ページで終わらず次がまだあれば、黙って切らず失敗にする"""
        form_sel = spec["form"]
        repeat = spec.get("repeat_while")
        limit = int(spec.get("max", self.recipe.max_pages))
        out: list[Doc] = []
        cur = d
        sent = 0
        if repeat:
            out.append(d)
        while True:
            if repeat and not (cur.soup and cur.soup.select_one(repeat)):
                break
            if sent >= limit and repeat:
                raise RecipeError(f"submit_form: {limit}（max）ページ送っても '{repeat}' が続く ({cur.url})")
            form = cur.soup.select_one(form_sel) if cur.soup else None
            if form is None:
                raise RecipeError(f"submit_form: form '{form_sel}' が見つからない ({cur.url})")
            data = form_data(form)
            for name in spec.get("require", []):
                if not data.get(name):
                    raise RecipeError(f"submit_form: form '{form_sel}' に '{name}' が無い・空 ({cur.url})")
            if str(form.get("method") or "get").lower() != "post":
                raise RecipeError(f"submit_form: form '{form_sel}' は POST でない ({cur.url})")
            data.update(spec.get("set", {}))
            action = _abs(self.recipe.base_url or cur.url, str(form.get("action") or cur.url))
            if (urlsplit(action).hostname or "").lower() != (urlsplit(cur.url).hostname or "").lower():
                raise RecipeError(f"submit_form: 別のホストへの form は送らない ({action})")
            page = self.fetcher.post(action, data, referer=cur.url, encoding=self.recipe.encoding)
            if urlsplit(page.final_url).path.lower() != urlsplit(action).path.lower():
                raise RecipeError(f"submit_form: 結果が {action} でなく {page.final_url} だった（トークン不正・セッション切れ）")
            # 結果の文書の URL は、人が開ける form のあるページ（入口）にする。POST 専用の URL は GET だとエラーページで、
            # 個体の「自治体のページで詳細を見る」（source_url）にできない
            cur = _make_doc(cur.url, page.html or "")
            out.append(cur)
            sent += 1
            self.trace.append(f"submit_form → {action}（{sent} 回目）")
            if not repeat:
                break
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
            raise FetchError(f"{kind}: 辿った {tried} 本がすべて取得に失敗（{failed[0]}）",
                             getattr(failed[0], "info", None) if failed and isinstance(failed[0], FetchError) else None)


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
        cur: Tag = start
        while True:
            added = False
            stopped = False
            for sib in cur.next_siblings:
                if not isinstance(sib, Tag):
                    if type(sib) is NavigableString:
                        holder.append(NavigableString(str(sib)))   # 始まりの間の裸の文字（「<h3>No.1</h3>種類：柴<br>…」）
                    continue
                if id(sib) in start_ids:
                    stopped = True
                    break
                if any(id(d) in start_ids for d in sib.find_all(True)):
                    # 次の子の始まりを中に含む要素（さいたま市: 2 頭目だけ div に包まれている）。多くは始まりが先頭で何も残らないが、
                    # 前の子の写真・属性が同じ入れ物の手前側に入っていることがある（R08-58: 写真・ul は次の子の div の前半）。その手前までを足す
                    part = _before_cut(sib, start_ids, recipe.row_until or "")
                    if part is not None:
                        holder.append(part)
                        added = True
                    stopped = True
                    break
                if sib.css.match(recipe.row_until or "") or sib.select_one(recipe.row_until or "") is not None:
                    stopped = True
                    break      # 区切り（大分市: 「お家がみつかりました」の h2、千葉市: 掲載日の h2）。兄弟の中にあっても止める
                holder.append(copy.copy(sib))
                added = True
            parent = cur.parent
            # 始まりが「それだけを包む div」の中にあり、後ろの兄弟が無いときは、包みの外の兄弟を続きとして読む
            # （さいたま市 R08-58: 管理番号の p だけが div に包まれ、写真・属性は包みの次の兄弟）
            if stopped or added or not isinstance(parent, Tag) or parent.name in ("body", "html", "[document]"):
                break
            if parent.get_text(strip=True) != start.get_text(strip=True) or parent.find("img") is not None:
                break
            cur = parent
        rows.append(Row(doc=doc, el=holder, anchor=start))
    return rows


def _before_cut(sib: Tag, start_ids: set[int], row_until: str) -> Tag | None:
    """sib の複製のうち、最初の「次の始まり（または row_until に当たる要素）」より前だけを返す。文字も写真も無ければ None。"""
    import copy

    originals = sib.find_all(True)
    cut_index = next(
        (i for i, d in enumerate(originals) if id(d) in start_ids or (row_until and d.css.match(row_until))), None)
    if cut_index is None:
        return None
    clone = copy.copy(sib)
    cut = clone.find_all(True)[cut_index]
    node: Tag | None = cut
    while node is not None and node is not clone:
        for after in list(node.next_siblings):
            after.extract()
        parent = node.parent
        if node is cut:
            node.extract()
        node = parent if isinstance(parent, Tag) else None
    if not clone.get_text(strip=True) and clone.find("img") is None:
        return None
    return clone


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


FOLDED_CELL = "続き"   # pdf.fold_blank_key で畳んだ行の文字を入れるセル名（fields の header: "続き" で引く）


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
    fold_key = (recipe.pdf or {}).get("fold_blank_key")   # この見出しの語の列が空の行は、直前の行の「続き」セルに畳む
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
        last: Row | None = None   # この表で直前に読んだ、キーのある行（fold_blank_key 用）
        for raw in table[hr + 1:]:
            cells: dict[str, str] = {}
            for i, v in enumerate(raw):
                cells[str(i)] = v
                h = (header[i] if i < len(header) else "").replace("\n", "").replace(" ", "")
                if h:
                    cells[h] = v
            if not any(v for k, v in cells.items()):
                continue
            keyed = True
            if fold_key:
                key_val = next((v for k, v in cells.items() if fold_key in k and not k.isdigit()), None)
                keyed = bool((key_val or "").strip())
                if not keyed and last is not None and last.cells is not None:
                    # 重ね書きの文字が表の続きの行に割れて出る（香川 しっぽの森）。その行を直前の行の「続き」セルに畳む。
                    # 続きの行は管理番号が無く、元の行の既存のセルには混ぜない
                    extra = " ".join(v for k, v in cells.items() if k.isdigit() and v)
                    last.cells[FOLDED_CELL] = f"{last.cells.get(FOLDED_CELL, '')} {extra}".strip()
                    continue
            row = Row(doc=doc, cells=cells)
            rows.append(row)
            if keyed:
                last = row
    return _filter_rows(recipe, rows)


# --- fields -----------------------------------------------------------------
def _text(t: Tag) -> str | None:
    return visible_text(t) or None


# 「性別：」のような項目名＋コロン（_label_value の最後の読み取り用）。数字（18:30）・英字（TEL:・https://）で始まるものは値
_NEXT_LABEL = re.compile(r"(?![A-Za-zＡ-Ｚａ-ｚ])[^\s\d:：]{1,8}[:：]")
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
    - head も cand も td で、どちらも label で終わり cand が短い（label「場所」の「保護場所｜収容場所」）
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
        # 見出しが td で横に並ぶ行。候補が label で始まる（「収容日｜収容場所」）なら見出し。
        # 見出しセルも候補も label で終わり（label「場所」に「保護場所」「収容場所」）、候補が短いときも見出し。
        # 見出しセルが label そのもの（「保健所｜水俣保健所」）や、label が見出しの途中にある（岐阜「毛 色｜虎毛」の label「毛」）
        # なら候補は値。捨てても次の行の同じ列を見るので、旧挙動より悪くはならない
        if text.startswith(label):
            return True
        head_text = head.get_text("", strip=True).strip(_LABEL_PUNCT)
        cand_text = text.strip(_LABEL_PUNCT)
        return (head_text != label and head_text.endswith(label) and cand_text.endswith(label)
                and len(cand_text) <= len(label) + 4)
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
    if m is None:
        return None
    # 値が空欄の項目（「毛色：」の次の行が「性別：不明」）では、次の項目を値として拾ってしまう。
    # 別の項目名＋「：」に見える値は取らない（数字で始まる「18:30」は項目名ではないので取る）
    return None if _NEXT_LABEL.match(m.group(1)) else m.group(1)


def _labels(spec: dict[str, Any]) -> list[str]:
    """label は 1 語か、候補の並び（["収容日", "収容期日"]。前から順に試し、最初に取れた値を使う）。"""
    lb = spec["label"]
    return [str(x) for x in lb] if isinstance(lb, list) else [str(lb)]


def _header_row_value(el: Tag, label: str) -> str | None:
    """header_row: true の label。見出し行（表の 1 行に項目名が並ぶ）にある label の列を、同じ表の次の行から読む。

    次の行は thead と tbody をまたいで探す（見出しが thead の th、値が tbody の td の表）。見出しの語と一致するセル
    （記号・空白を除いて label と同じ）だけを見出しとみなし、隣のセルは見ない（見出し行を td で書いた表で、隣の見出し
    「収容期限」を値に取らない）。越谷市（2026-10-05 T521。表の作りが日によって 3 通りある）。
    """
    for cell in el.find_all(["th", "td"]):
        if visible_text(cell).strip(_LABEL_PUNCT) != label:
            continue
        tr = cell.find_parent("tr")
        table = tr.find_parent("table") if tr is not None else None
        if table is None:
            continue
        kids = tr.find_all(["th", "td"], recursive=False)
        idx = next((i for i, c in enumerate(kids) if c is cell), None)
        trs = [t for t in table.find_all("tr") if t.find_parent("table") is table]
        pos = next((i for i, t in enumerate(trs) if t is tr), None)
        if idx is None or pos is None or pos + 1 >= len(trs):
            continue
        cells = trs[pos + 1].find_all(["th", "td"], recursive=False)
        if idx < len(cells):
            return _text(cells[idx])
    return None


def _table_has_header(el: Tag | None, word: str) -> bool:
    """行（tr）を含む表に、記号・空白を除いて word と同じ見出しセル（th）があるか。表の中に入れ子の表があっても自分の表の th だけを見る。"""
    table = el.find_parent("table") if el is not None else None
    if table is None:
        return False
    for th in table.find_all("th"):
        if th.find_parent("table") is table and visible_text(th).strip(_LABEL_PUNCT) == word:
            return True
    return False


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
    if "if_header" in spec or "unless_header" in spec:
        # 表の見出し（th）に応じて列の意味が変わる表（船橋市 譲渡可能犬猫: 猫の表は見出し「毛色」、犬の表は見出し行が無く 2 列目が種類）
        has = _table_has_header(row.el, str(spec.get("if_header") or spec.get("unless_header")))
        if ("if_header" in spec and not has) or ("unless_header" in spec and has):
            return None
    if "join" in spec:
        # 複数の指定で取った値を sep でつなぐ（取れなかったものと、前と同じ値は飛ばす）。明石 飼い主募集の猫の
        # 「トライアル中」の印と性格（2026-10-07 T521）
        parts: list[str] = []
        for sub in spec["join"]:
            v = field_value(sub, row)
            if v and v not in parts:
                parts.append(v)
        return str(spec.get("sep", " ")).join(parts) or None
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
            val = next((v for lb in _labels(spec) for k, v in row.cells.items() if lb in k), None)
    elif row.el is not None:
        if "selector" in spec:
            el = row.el.select_one(spec["selector"]) if spec["selector"] not in (".", "self") else row.el
            if el is not None:
                val = _attr(el, spec.get("attr", "text"))
        elif "label" in spec:
            read = _header_row_value if spec.get("header_row") else _label_value
            val = next((v for v in (read(row.el, lb) for lb in _labels(spec)) if v is not None), None)
        elif "attr" in spec:
            val = _attr(row.el, spec["attr"])
    if "regex" in spec:
        m = re.search(spec["regex"], val if val is not None and ("selector" in spec or "label" in spec or "header" in spec or from_heading) else base_text, re.S)
        val = (m.group(1) if m.groups() else m.group(0)).strip() if m else None
    if val is None and "default" in spec:
        val = spec["default"]
    if isinstance(val, str):
        val = _norm_text(val)
    if val and "prefix" in spec:
        val = f"{spec['prefix']}{val}"   # 取れた値の頭に足す（高崎「毛色・首輪」の首輪を備考で「首輪：無」。2026-11-13）
    return val


def image_url(recipe: Recipe, row: Row, fields: dict[str, str | None] | None = None) -> tuple[str | None, str | None]:
    """(絶対 URL, 生の src)。ゴミ画像は除く。fields は image.match_field で使う、この行で取った項目。"""
    if row.el is None:
        return None, None
    spec = recipe.image
    if isinstance(spec, str):
        spec = {"selector": spec}
    sel, attr = parse_sel(spec.get("selector", "img@src"))
    if attr == "href" and sel.startswith("img"):
        attr = "src"
    exclude = [re.compile(x, re.I) for x in spec.get("exclude", [])]
    # match_field: 写真が本体と別の表にあるページ（仙台市 譲渡猫: 「管理番号/写真1/写真2」の表）。
    # 行で取った項目（管理番号）の値を src か alt に含む画像を文書全体から探す。前後が英数字の位置は
    # 別の番号の一部とみなして当てない（C2509 を c25093-3.jpg に当てない）。値が無い行には写真を付けない。
    # 後ろの 1 文字の英字の枝番（c22068b.jpg・alt「C22068B」）は同じ子とみなす（仙台市 Wayback 2023-03。T521 ゲート）
    match_field = spec.get("match_field")
    want: re.Pattern[str] | None = None
    if match_field:
        value = (fields or {}).get(str(match_field))
        if not value or row.doc.soup is None:
            return None, None
        want = re.compile(r"(?<![A-Za-z0-9])" + re.escape(value) + r"(?![0-9])(?![A-Za-z][A-Za-z0-9])", re.I)

    def pick(root: Tag) -> tuple[str, str] | None:
        for el in root.select(sel):
            src = _attr(el, attr) or _attr(el, "data-src") or _attr(el, "data-original")
            if not src or src.startswith("data:"):
                continue
            if _JUNK_IMAGE.search(src) or any(p.search(src) for p in exclude):
                continue
            if want is not None and not (want.search(src) or want.search(unicodedata.normalize("NFKC", str(el.get("alt") or "")))):
                continue
            if spec.get("strip_query"):
                src = src.split("?", 1)[0]     # 取得ごとに変わるクエリ（キャッシュ避け）を外して ID を安定させる
            return _abs(recipe.base_url or row.doc.url, src), src
        return None

    if want is not None and row.doc.soup is not None:
        return pick(row.doc.soup) or (None, None)   # 文書全体（元の文書。まとめた行・転置表の複製でなく）
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
    stop_at = str(spec.get("stop_at") or "")
    # "row, h2" は「rows に当たる要素」に加えて h2 の手前でも止める（岩手県 県央: 迷子の節の写真 p が、譲渡の最初の子まで遡って届くのを防ぐ）
    stop_extra = stop_at[len("row,"):].strip() if stop_at.startswith("row,") else ""
    stop_at_row = (stop_at == "row" or bool(stop_extra)) and isinstance(recipe.rows, str)
    walk = base.find_next_siblings() if forward else base.find_previous_siblings()
    for sib in walk:
        if not isinstance(sib, Tag):
            continue
        if stop_extra:
            try:
                if sib.css.match(stop_extra):
                    break
            except Exception:
                pass
        if stop_at_row:
            try:
                if sib.css.match(recipe.rows):
                    break
            except Exception:
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
    # 丸数字（「No.8F-9-1③」）は値には残すが、管理番号らしさは数字として見る（#124 reviewer F-02）
    return bool(s and _MGMT_RE.search(unicodedata.normalize("NFKC", s)))
