"""T518 ④: 四日市市の PDF の新しい様式（保護・収容犬の公示）を読む（ネットワークなし）。

t518_yokkaichi_hiraotyoinu.txt は 2026-10-05「平尾町（犬）」の PDF をエンジンと同じく pdfplumber で文字にしたもの。
変更前のレシピは「収容日：YYYY年…」を 1 頭の境目にしていて、新しい様式では行 0（failed）だった。
"""

from pathlib import Path

from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import Source, load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"


def _source(slug: str) -> Source:
    return next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == slug)


def _fixture(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _pick(a: dict, *keys: str) -> dict:
    return {k: a.get(k) for k in keys}


# --- 四日市市: PDF が「保護・収容犬の公示」の表に変わった（2026-10-05 夕方から）----------------------------------------
YOK_PDF = "https://www.city.yokkaichi.lg.jp/www/contents/1001000000924/simple/hiraotyoinu.pdf"


def _run_pdf(slug: str, text: str):
    src = _source(slug)
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    return build(src, recipe, [Doc(url=YOK_PDF, pdf_text=text, pdf_tables=[])])


def test_yokkaichi_reads_the_notice_table():
    res = _run_pdf("city_yokkaichi_pdf", _fixture("t518_yokkaichi_hiraotyoinu.txt"))
    assert len(res.animals) == 1
    a = res.animals[0]
    assert _pick(a, "species", "shelter_date", "breed", "color", "sex", "size", "age", "location", "source_url") == {
        "species": "dog", "shelter_date": "令和8年10月5日", "breed": "洋雑", "color": "茶", "sex": "オス", "size": "中",
        "age": "91日以上", "location": "平尾町",
        "source_url": "https://www.city.yokkaichi.lg.jp/www/contents/1001000000924/index.html"}


def test_yokkaichi_cat_notice_is_a_cat():
    text = _fixture("t518_yokkaichi_hiraotyoinu.txt").replace("収容犬の公示", "収容猫の公示").replace("した犬について", "した猫について")
    res = _run_pdf("city_yokkaichi_pdf", text)
    assert [a["species"] for a in res.animals] == ["cat"]
