"""T517 ①② のエンジン修正のテスト（ネットワークなし）。

1. empty_selector: 0 頭の日に文言が出ず、一覧の器（div / ul）が空になるだけのサイト用（豊橋市あいくる・福岡県動物愛護センター）。
   器があって中身が空なら empty。器が無い日（構造が変わった日）は empty にしない＝failed で通知される
2. follow_all / pdf_links の skip_errors: 子 1 本の取得失敗（404 等）でその 1 本だけ捨てて続ける（群馬県・岐阜県）。
   辿ろうとした子が全部失敗した日は従来どおり失敗
"""

import pytest
from bs4 import BeautifulSoup

from collector.extract import build
from collector.fetch import FakeFetcher, FetchError
from collector.recipe import Doc, Executor, Recipe
from collector.registry import Source


def _doc(html: str, url: str = "https://x.jp/a/") -> Doc:
    return Doc(url=url, html=html, soup=BeautifulSoup(html, "lxml"))


def _src(kind: str = "stray", species: str = "dog") -> Source:
    return Source(slug="t", name="t", municipality="t", prefecture="愛知県", url="https://x.jp/a/", kind=kind, species=species)


# --- 1. empty_selector -------------------------------------------------------------
# 豊橋市あいくる（2026-10-05 の実ページから抜粋）: 0 頭の日は div.dog-cat-list が空白だけになる
TOYOHASHI_EMPTY = """<div class="dog-cat-content">
<h2 class="dog-cat-heading"><span>保護犬/保護猫の情報</span></h2>
<p>現在、動物愛護センターで保護している犬/猫の情報は下記のとおりです。</p>
        <div class="dog-cat-list">
                    </div>
        <div class="section"><h3 class="dog-cat-heading mb"><span>保護犬/保護猫の返還について</span></h3></div>
</div>"""

TOYOHASHI_ONE = TOYOHASHI_EMPTY.replace(
    '<div class="dog-cat-list">\n                    </div>',
    '<div class="dog-cat-list"><div class="dog-cat-list__item"><div class="dog-cat-image"><img src="/up/d1.jpg">'
    '<span>保護日: 2026.10.05</span></div><dl><dt>管理番号</dt><dd>D-12</dd></dl></div></div>',
)

# 福岡県動物愛護センター（2026-10-05 の実ページから抜粋）: 0 頭の日は div.animals-list の ul が空になる
FUKUOKA_EMPTY = """<h3>＜詳細情報は写真をクリックしてください＞</h3>
<div  class="thumb-list list-4col animals-list ">
	<ul>
		<!-- 一覧 -->
			</ul>
</div>"""

TOYOHASHI = {"rows": "div.dog-cat-list__item", "image": "img@src",
             "fields": {"management_no": {"label": "管理番号"}}, "empty_selector": "div.dog-cat-list"}


def test_empty_selector_confirms_when_container_is_blank():
    res = build(_src(), Recipe.from_dict(TOYOHASHI), [_doc(TOYOHASHI_EMPTY)])
    assert res.animals == []
    assert res.empty_confirmed is True


def test_empty_selector_ignores_whitespace_and_comments():
    recipe = Recipe.from_dict({"rows": "div.animals-list li", "empty_selector": ["div.animals-list ul"]})
    res = build(_src(kind="sheltered"), recipe, [_doc(FUKUOKA_EMPTY)])
    assert res.empty_confirmed is True


def test_empty_selector_not_confirmed_when_container_is_missing():
    """構造が変わって器ごと無くなった日は「読めなかった」（failed で通知）のまま。"""
    html = TOYOHASHI_EMPTY.replace('class="dog-cat-list"', 'class="animal-grid"')
    res = build(_src(), Recipe.from_dict(TOYOHASHI), [_doc(html)])
    assert res.empty_confirmed is False


def test_empty_selector_not_confirmed_when_container_has_children():
    """器に中身があるのに行が取れない日（行のクラス名が変わった等）は empty にしない。"""
    html = TOYOHASHI_ONE.replace("dog-cat-list__item", "dog-cat-card")
    res = build(_src(), Recipe.from_dict(TOYOHASHI), [_doc(html)])
    assert res.animals == []
    assert res.empty_confirmed is False


def test_empty_selector_not_confirmed_when_container_has_only_text():
    html = TOYOHASHI_EMPTY.replace('<div class="dog-cat-list">\n                    </div>',
                                   '<div class="dog-cat-list">読み込み中です</div>')
    res = build(_src(), Recipe.from_dict(TOYOHASHI), [_doc(html)])
    assert res.empty_confirmed is False


def test_empty_selector_requires_every_match_to_be_blank():
    """同じセレクタに合う器が複数あり、1 つでも中身があれば empty にしない（取りこぼしを 0 頭に見せない）。"""
    html = TOYOHASHI_EMPTY + '<div class="dog-cat-list"><p>何か</p></div>'
    res = build(_src(), Recipe.from_dict(TOYOHASHI), [_doc(html)])
    assert res.empty_confirmed is False


def test_empty_selector_with_animals_reads_them_as_before():
    res = build(_src(), Recipe.from_dict(TOYOHASHI), [_doc(TOYOHASHI_ONE)])
    assert [a["management_no"] for a in res.animals] == ["D-12"]
    assert res.empty_confirmed is False


def test_empty_selector_checks_pages_visited_on_the_way():
    """empty_text と同じく、入口から辿った全文書（最終文書でない入口ページ）も見る。"""
    recipe = Recipe.from_dict({"steps": [{"follow_all": "a.detail@href"}], "rows": "body",
                               "empty_selector": "div.dog-cat-list"})
    ex = Executor(FakeFetcher({"https://x.test/": TOYOHASHI_EMPTY}), recipe)
    docs = ex.resolve("https://x.test/")
    res = build(_src(), recipe, docs, ex.visited)
    assert docs == [] and res.empty_confirmed is True


def test_empty_selector_and_empty_text_either_confirms():
    recipe = Recipe.from_dict({**TOYOHASHI, "empty_text": "現在いません"})
    assert build(_src(), recipe, [_doc(TOYOHASHI_EMPTY)]).empty_confirmed is True
    other = "<div class='x'></div><p>現在いません</p>"
    assert build(_src(), recipe, [_doc(other)]).empty_confirmed is True


# --- 2. skip_errors ----------------------------------------------------------------
GUNMA_LIST = """<div id="main_body"><div class="detail_free">
<p><a href="/page/775956.html">管理番号：26-095（北群馬郡吉岡町大久保）</a></p>
<p><a href="/page/776839.html">管理番号：26-097（北群馬郡吉岡町上野田）</a></p>
<p><a href="/page/777066.html">管理番号：26-098(北群馬郡榛東村長岡)</a></p>
</div></div>"""


def _dog(no: str) -> str:
    return f"<div id='main_body'><table><tr><th>管理番号</th><td>{no}</td></tr><tr><th>収容日</th><td>2026年9月28日</td></tr></table></div>"


GUNMA_PAGES = {"https://x.test/": GUNMA_LIST,
               "https://x.test/page/776839.html": _dog("26-097"),
               "https://x.test/page/777066.html": _dog("26-098")}   # 775956 は FakeFetcher に無い＝取得失敗


def _gunma(skip: bool) -> Recipe:
    step: dict = {"follow_all": "div.detail_free a[href*='/page/']"}
    if skip:
        step["skip_errors"] = True
    return Recipe.from_dict({"steps": [step], "rows": "body",
                             "fields": {"management_no": {"label": "管理番号"}, "shelter_date": {"label": "収容日"}}})


def test_follow_all_fails_whole_slug_on_one_child_error_by_default():
    ex = Executor(FakeFetcher(GUNMA_PAGES), _gunma(skip=False))
    with pytest.raises(FetchError):
        ex.resolve("https://x.test/")


def test_follow_all_skip_errors_drops_only_the_failed_child():
    recipe = _gunma(skip=True)
    ex = Executor(FakeFetcher(GUNMA_PAGES), recipe)
    docs = ex.resolve("https://x.test/")
    assert [d.url for d in docs] == ["https://x.test/page/776839.html", "https://x.test/page/777066.html"]
    assert any(t.startswith("skip https://x.test/page/775956.html: ") for t in ex.trace)
    res = build(_src(kind="sheltered"), recipe, docs, ex.visited)
    assert [a["management_no"] for a in res.animals] == ["26-097", "26-098"]


def test_follow_all_skip_errors_still_fails_when_every_child_fails():
    """全部 404 の日を 0 頭扱いにしない。"""
    ex = Executor(FakeFetcher({"https://x.test/": GUNMA_LIST}), _gunma(skip=True))
    with pytest.raises(FetchError):
        ex.resolve("https://x.test/")


def test_follow_all_skip_errors_with_no_links_is_not_an_error():
    """リンクが 1 本も無い日（本当に 0 頭）は今まで通り文書 0 で続ける（empty_text が判定する）。"""
    ex = Executor(FakeFetcher({"https://x.test/": "<div class='detail_free'></div>"}), _gunma(skip=True))
    assert ex.resolve("https://x.test/") == []


def _tiny_pdf(text: str) -> bytes:
    """1 ページに ASCII の文字列を 1 行だけ書いた最小の PDF。"""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{n:010d} 00000 n \n".encode() for n in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def test_pdf_links_skip_errors_drops_only_the_failed_pdf():
    recipe = Recipe.from_dict({"steps": [{"pdf_links": "a[href$='.pdf']", "skip_errors": True}],
                               "pdf": {"mode": "text"}, "rows_regex": r"^No.*$"})
    pages = {"https://x.test/": "<a href='old.pdf'>old</a><a href='new.pdf'>new</a>",
             "https://x.test/new.pdf": _tiny_pdf("No.26-001 dog")}
    ex = Executor(FakeFetcher(pages), recipe)
    docs = ex.resolve("https://x.test/")
    assert len(docs) == 1 and "No.26-001" in (docs[0].pdf_text or "")
    assert any(t.startswith("skip https://x.test/old.pdf: ") for t in ex.trace)


def test_pdf_links_fails_on_one_error_by_default():
    recipe = Recipe.from_dict({"steps": [{"pdf_links": "a[href$='.pdf']"}], "pdf": {"mode": "text"}})
    pages = {"https://x.test/": "<a href='old.pdf'>old</a><a href='new.pdf'>new</a>",
             "https://x.test/new.pdf": _tiny_pdf("No.26-001 dog")}
    with pytest.raises(FetchError):
        Executor(FakeFetcher(pages), recipe).resolve("https://x.test/")
