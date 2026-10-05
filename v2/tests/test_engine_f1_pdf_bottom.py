"""10/5 監査 F1: PDF の表で、ページ最下行の下の横罫線が引かれていない（縦罫線だけが下まで伸びている）とき、
その行を落とさない。神奈川県 センター外保護猫（cat.pdf）1 ページ目の No.46 が表から漏れていた。ネットワークなし。"""

from collector.recipe import Recipe, _make_pdf_doc, extract_rows, field_value


def _table_pdf(bottom_line: bool, verticals_to: int = 290, frame: bool = False) -> bytes:
    """3 列の表（見出し + 2 行）を線と文字で組んだ 1 ページの PDF。bottom_line=False なら最下行の下の横罫線を引かない。"""
    xs = [50, 150, 250, 350]
    ys = [350, 330, 310] + ([290] if bottom_line else [])
    ops: list[bytes] = [b"0.5 w"]
    for y in ys:
        ops.append(f"{xs[0]} {y} m {xs[-1]} {y} l S".encode())
    for x in xs:
        ops.append(f"{x} 350 m {x} {verticals_to} l S".encode())
    if frame:
        ops.append(b"20 390 m 20 10 l S 580 390 m 580 10 l S")   # 表の外のページ枠（表の上から下まで伸びる縦線）
    cells = [(335, ["No", "Name", "Sex"]), (315, ["1", "A", "M"]), (295, ["2", "B", "F"])]
    for y, vals in cells:
        for x, v in zip(xs, vals):
            ops.append(f"BT /F1 10 Tf {x + 5} {y} Td ({v}) Tj ET".encode())
    ops.append(b"BT /F1 10 Tf 50 200 Td (note: footer) Tj ET")
    content = b"\n".join(ops)
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


RECIPE = Recipe.from_dict({
    "steps": [{"pdf_links": "a@href"}],
    "pdf": {"mode": "table", "header_row": 0},
    "fields": {"management_no": {"header": "No"}, "name": {"header": "Name"}, "sex": {"header": "Sex"}},
})


def _names(pdf: bytes) -> list[str | None]:
    doc = _make_pdf_doc("https://x.jp/a.pdf", pdf)
    return [field_value(RECIPE.fields["name"], r) for r in extract_rows(RECIPE, doc)]


def test_last_row_without_bottom_border_is_kept_when_verticals_reach_down():
    assert _names(_table_pdf(bottom_line=False)) == ["A", "B"]


def test_table_with_all_borders_is_unchanged():
    doc = _make_pdf_doc("https://x.jp/a.pdf", _table_pdf(bottom_line=True))
    assert doc.pdf_tables == [[["No", "Name", "Sex"], ["1", "A", "M"], ["2", "B", "F"]]]


def test_verticals_ending_at_last_border_add_nothing():
    # 最下行の横罫線より下に縦罫線が伸びていない（普通の表）なら補わない
    doc = _make_pdf_doc("https://x.jp/a.pdf", _table_pdf(bottom_line=False, verticals_to=310))
    assert doc.pdf_tables == [[["No", "Name", "Sex"], ["1", "A", "M"]]]


def test_page_frame_lines_do_not_close_the_table():
    # 表の外の縦線（ページ枠）は表の続きとみなさない。フッターの文字を行にしない
    doc = _make_pdf_doc("https://x.jp/a.pdf", _table_pdf(bottom_line=False, verticals_to=310, frame=True))
    assert all("footer" not in " ".join(c or "" for c in row) for t in doc.pdf_tables or [] for row in t)
