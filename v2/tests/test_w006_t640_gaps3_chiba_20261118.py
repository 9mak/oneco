"""W006 T640 掲載漏れ 3 回目 A: 千葉市の育成中の子猫（koneko-jyouto.html。2026-11-18・ネットワークなし）。

- h4 の管理番号 → 写真 → 種類・毛色・性別・生年月日（推定）・コメント。既存の transfercats.html（city_chiba-8）に同じ子はいない。
- 0 頭の日（お見合い会の無い期間。Wayback 2025-02・2026-03）は h4 が &nbsp;・欄が空の雛形が 1 つ残る。
"""


from pathlib import Path

from collector.fetch import FakeFetcher
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _run(slug: str, html: str) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


def _zero(c: Collected) -> bool:
    return c.status == "empty" and c.result is not None and c.result.animals == []


# --- 千葉市 育成中の子猫 ---------------------------------------------------
CHIBA = "city_chiba-9"
CHIBA_URL = "https://www.city.chiba.jp/hokenfukushi/iryoeisei/seikatsueisei/dobutsuhogo/koneko-jyouto.html"
CHIBA_FX = "w006_city_chiba-9_20261118.html"
CHIBA_IMG = "https://www.city.chiba.jp/hokenfukushi/iryoeisei/seikatsueisei/dobutsuhogo/images/"


def test_chiba_registry():
    s = SOURCES[CHIBA]
    assert (s.url, s.kind, s.species, s.mode, s.enabled) == (CHIBA_URL, "adoption", "cat", "recipe", True)
    assert (s.municipality, s.prefecture, s.phone) == ("千葉市", "千葉県", "043-258-7817")
    assert s.photo == "pending" and s.recipe_path.exists()   # 無断転載禁止のみ（2026-11-22 方針 1・2: 可の返事も規約の可も無いので、確認が取れるまで出さない）


def test_chiba_today_reads_2_kittens_and_none_is_on_the_transfercats_page():
    c = _run(CHIBA, _fx(CHIBA_FX))
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert [(a["management_no"], a["breed"], a["color"], a["sex"]) for a in animals] == [
        ("26102201", "雑種", "黒白", "メス"), ("26092501", "雑種", "キジ白", "メス")]
    assert all(a["species"] == "cat" for a in animals) and len({a["id"] for a in animals}) == 2
    assert [a["image_url"] for a in animals] == [CHIBA_IMG + "26102201.jpg", CHIBA_IMG + "20261030.jpg"]
    assert animals[0]["age"] == "令和8年10 月1 日" and "白ソックス" in animals[0]["note"] and "甘えん坊" in animals[1]["note"]
    # 既存の譲渡猫の一覧（transfercats.html。city_chiba-8。2026-11-17 の保存ページ）に同じ子（管理番号・写真）はいない。2026-11-18 の実ページも同じ（18 頭に無い）
    other = _run("city_chiba-8", _fx("w006_city_chiba-8_20261117.html"))
    assert other.status == "ok" and len(other.result.animals) >= 10
    assert not ({a["management_no"] for a in animals} & {a["management_no"] for a in other.result.animals})
    assert not ({a["image_url"] for a in animals} & {a["image_url"] for a in other.result.animals})


def test_chiba_zero_days_in_wayback_keep_an_empty_template_kitten():
    # お見合い会の無い期間（2025-02・2026-03）は h2「対象の子猫」の下に、見出しが &nbsp;・欄が全部空（種類：毛色：性別：…）の雛形が 1 つ残る。0 頭
    for name in ("w006_city_chiba-9_wb20250207.html", "w006_city_chiba-9_wb20260309.html"):
        html = _fx(name)
        assert "<h4>&nbsp;</h4>" in html and "種類：<br>" in html
        c = _run(CHIBA, html)
        assert _zero(c), (name, c.status, c.error)


def test_chiba_day_with_a_kitten_whose_matching_is_decided_in_wayback():
    # 2024-07: 見出しが「24060603　お見合いが決まりました！」（写真は無い）。お見合いが決まった子は載せて note に出す（city_chiba-7・-8 と同じ。譲渡が決まったのとは別）
    html = _fx("w006_city_chiba-9_wb20240717.html")
    c = _run(CHIBA, html)
    assert c.status == "ok", c.error
    a = c.result.animals[0]
    assert len(c.result.animals) == 1 and (a["management_no"], a["breed"], a["color"], a["sex"], a["age"]) == ("24060603", "雑種", "白黒", "めす", "令和6年6月3日")
    assert a["note"].startswith("お見合いが決まりました!")   # 「！」は半角にそろえる（エンジンの正規化） and "おしゃべり好き" in a["note"]
    assert not a["image_url"]
    # 子のいる日に 0 頭の根拠は成り立たない（audit_empty が毎日通知しない）
    assert _run(CHIBA, html).result.empty_confirmed is False


def test_chiba_zero_is_not_claimed_when_the_template_is_filled_or_the_frame_changes():
    zero = _fx("w006_city_chiba-9_wb20260309.html")
    # 雛形の h4 に管理番号が入った日（欄はまだ空）・写真が入った日は 0 頭にしない
    assert not _zero(_run(CHIBA, zero.replace("<h4>&nbsp;</h4>", "<h4>27010101</h4>")))
    assert not _zero(_run(CHIBA, zero.replace("<h4>&nbsp;</h4>", '<h4>&nbsp;</h4><p><img alt="" src="/hokenfukushi/x/images/a.jpg"></p>')))
    # 枠の見出しが変わった日・欄の名前が変わった日は 0 頭にしない（今日の子猫が載る日の保存ページで）
    assert not _zero(_run(CHIBA, zero.replace("対象の子猫", "子猫の一覧")))
    assert not _zero(_run(CHIBA, _fx(CHIBA_FX).replace("種類：", "品種：")))
