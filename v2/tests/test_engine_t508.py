"""T508 で足したエンジン機能のテスト: 転置表（1 列 = 1 頭）と PDF の 2 段組み。ネットワークなし。"""

from bs4 import BeautifulSoup
from collector.extract import build
from collector.recipe import Doc, Recipe, _make_pdf_doc, extract_rows, field_value
from collector.registry import Source


# --- 転置表（1 列 = 1 頭）---------------------------------------------------
def test_transpose_table_rows():
    html = """<table class="has-fixed-layout">
    <tr><td colspan="3">４枠</td></tr>
    <tr><td>番号：１</td><td>番号：２</td><td>番号：31 飼い主さん決まりました</td></tr>
    <tr><td>性別：メス</td><td>性別：オス</td><td>性別：メス</td></tr>
    <tr><td><img src="/2026/a.jpg"></td><td><img src="/2026/b.jpg"></td><td><img src="/2026/c.jpg"></td></tr>
    <tr><td colspan="3">５月生まれ　ワクチン2回接種済</td></tr>
    </table>"""
    recipe = Recipe.from_dict({
        "transpose": "table.has-fixed-layout",
        "row_filter": {"text_lacks": ["飼い主さん決まりました"]},
        "fields": {"management_no": {"regex": "番号[:：]\\s*(\\S+)"}, "sex": {"regex": "性別[:：]\\s*(\\S+)"},
                   "note": {"regex": "(\\S*月生まれ.*)$"}},
    })
    doc = Doc(url="https://x.jp/work/puppy/", html=html, soup=BeautifulSoup(html, "lxml"))
    rows = extract_rows(recipe, doc)
    assert len(rows) == 2                      # 3 列のうち「飼い主さん決まりました」の 1 列は捨てる
    assert [field_value(recipe.fields["sex"], r) for r in rows] == ["メス", "オス"]
    assert field_value(recipe.fields["note"], rows[0]) == "5月生まれ ワクチン2回接種済"   # 1 セルの共通行は全列に付く
    src = Source(slug="t", name="t", municipality="t", prefecture="栃木県", url=doc.url, kind="adoption", species="dog")
    res = build(src, recipe, [doc])
    assert [a["image_url"] for a in res.animals] == ["https://x.jp/2026/a.jpg", "https://x.jp/2026/b.jpg"]
    assert [a["management_no"] for a in res.animals] == ["1", "2"]


def test_transpose_single_cell_table_is_one_animal():
    """全行が 1 セルの表（栃木の子猫ページ）は表全体で 1 頭。見出しだけの表は写真も番号も無いので build で落ちる。"""
    html = """<table class="has-fixed-layout"><tr><td colspan="2">見出しだけ</td></tr></table>
    <table class="has-fixed-layout"><tr><td>ケージ A</td></tr><tr><td>番号：４</td></tr><tr><td><img src="/k.jpg"></td></tr><tr><td>性別：メス</td></tr></table>
    <table class="has-fixed-layout"><tr><td>番号：７</td><td>番号：８</td></tr><tr><td><img src="/a.jpg"></td><td><img src="/b.jpg"></td></tr></table>"""
    recipe = Recipe.from_dict({"transpose": "table.has-fixed-layout",
                               "fields": {"management_no": {"regex": "番号[:：]\\s*(\\S+)"}, "sex": {"regex": "性別[:：]\\s*(\\S+)"}}})
    doc = Doc(url="https://x.jp/", html=html, soup=BeautifulSoup(html, "lxml"))
    assert len(extract_rows(recipe, doc)) == 4
    src = Source(slug="t", name="t", municipality="t", prefecture="栃木県", url=doc.url, kind="adoption", species="cat")
    res = build(src, recipe, [doc])
    assert [a["management_no"] for a in res.animals] == ["4", "7", "8"]
    assert res.animals[0]["sex"] == "メス" and res.animals[0]["image_url"] == "https://x.jp/k.jpg"
    assert len(res.dropped) == 1


# --- 管理番号の判定 -----------------------------------------------------------
def test_mgmt_no_era_style_single_digits():
    from collector.recipe import looks_like_mgmt

    assert looks_like_mgmt("R8-6-5")          # 岩手県奥州保健所: 元号 + 1 桁区切り
    assert looks_like_mgmt("R8-12-10")
    assert looks_like_mgmt("2026-1-004D")     # 岩手県釜石保健所
    assert not looks_like_mgmt("R8")
    assert not looks_like_mgmt("1")


# --- PDF の 2 段組み ------------------------------------------------------------
def _two_column_pdf() -> bytes:
    """左右 2 列にテキストを置いた 1 ページの PDF を手で組む（xref も正しく書く）。"""
    content = b"\n".join([
        b"BT /F1 12 Tf 50 350 Td (L1 first) Tj ET",
        b"BT /F1 12 Tf 350 350 Td (R1 first) Tj ET",
        b"BT /F1 12 Tf 50 330 Td (L2 second) Tj ET",
        b"BT /F1 12 Tf 350 330 Td (R2 second) Tj ET",
    ])
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 400] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def test_pdf_columns_split_text():
    pdf = _two_column_pdf()
    whole = _make_pdf_doc("https://x.jp/a.pdf", pdf)
    assert "L1 first R1 first" in whole.text()          # 丸ごと読むと左右の行が混ざる
    two = _make_pdf_doc("https://x.jp/a.pdf", pdf, columns=2)
    lines = [ln for ln in two.text().splitlines() if ln.strip()]
    assert lines == ["L1 first", "L2 second", "R1 first", "R2 second"]   # 左列を全部読んでから右列
