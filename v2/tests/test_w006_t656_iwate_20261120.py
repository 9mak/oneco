"""T656 直し 1 回目・項目 6・7（2026-11-20・ネットワークなし）: 岩手県 久慈・奥州の「決定しました」の見出しの下の子。

久慈は見出し h2「【譲渡】新しい飼い主さんが決定しました」の下の 3 頭（さら・我愛羅(ガーラ)・グリード）、
奥州は「【決定】譲渡が決まりました！」の下の 2 頭（R8-9-4 ソラくん・R8-9-5 リクちゃん）が載っていた。決まった子は載せない。
見出しで決まった子かを決める（宮古 pref_iwate_miyako の「【御報告】」と同じ読み方。行の文では決まった子の備考に「決定」とは書かれない）。
"""

from pathlib import Path

from collector.fetch import FakeFetcher
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
KUJI = "w006_pref_iwate_kuji_20261120.html"
OSHU = "w006_pref_iwate_oshu_20261120.html"


def _run(slug: str, fixture: str, mutate=None) -> Collected:
    html = (FIX / fixture).read_text(encoding="utf-8")
    if mutate:
        html = mutate(html)
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


def _names(c: Collected, key: str) -> list[str | None]:
    return [a[key] for a in c.result.animals]


def test_kuji_decided_cats_are_not_listed():
    h = (FIX / KUJI).read_text(encoding="utf-8")
    assert h.count("【譲渡】新しい飼い主さんが決定しました") == 3 and h.count("【譲渡】新しい飼い主さんを募集しています") == 9
    c = _run("pref_iwate_kuji", KUJI)
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 9
    assert all(a["image_url"] and a["species"] == "cat" and a["kind"] == "adoption" for a in c.result.animals)
    # 決まった子の写真は 2026092505・2026092502・2026092510（前の実行で 3 頭が写真だけで載っていた）
    imgs = " ".join(a["image_url"] for a in c.result.animals)
    for decided in ("2026092505", "2026092502", "2026092510"):
        assert decided not in imgs
    assert len({a["id"] for a in c.result.animals}) == 9


def test_oshu_decided_cats_are_not_listed():
    h = (FIX / OSHU).read_text(encoding="utf-8")
    assert h.count("【決定】譲渡が決まりました！") == 2
    c = _run("pref_iwate_oshu", OSHU)
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 6    # 募集中 4 + 譲渡調整中 2（受付一時停止だが募集中の見出し）
    nos = _names(c, "management_no")
    assert not any(n and (n.startswith("R8-9-4") or n.startswith("R8-9-5")) for n in nos)
    assert any(n and n.startswith("R8-9-2") for n in nos) and any(n and n.startswith("R8-9-3") for n in nos)


def test_oshu_photos_stay_with_their_cats_after_the_decided_rows_are_dropped():
    # 行を外す前に写真を決めている（遡りは決まった子の行でも止まる）ので、残った子の写真は自分の写真
    c = _run("pref_iwate_oshu", OSHU)
    imgs = {a["management_no"].split("(")[0]: a["image_url"].rsplit("/", 1)[1] for a in c.result.animals}
    assert imgs == {"R8-10-1": "081001.jpg", "R8-6-5": "080605.png", "R8-6-2": "azuki01.jpg", "R7-8-5": "0303.jpg",
                    "R8-9-2": "yoruhoshi01.jpg", "R8-9-3": "yoruhoshi01.jpg"}   # R8-9-2 と R8-9-3 は元から同じ写真（既知）


def test_page_with_only_decided_cats_is_zero_by_the_heading_evidence():
    # 決まった子しかいない日は 0 頭（全行が見出しで除外され、一覧の器が残っている。宮古と同じ読み方）。通知を止めない
    def all_decided(h: str) -> str:
        return h.replace("【譲渡】新しい飼い主さんを募集しています", "【譲渡】新しい飼い主さんが決定しました")

    c = _run("pref_iwate_kuji", KUJI, all_decided)
    assert c.status == "empty"
    assert c.result.animals == []


def test_other_iwate_recipes_exclude_decided_sections_by_heading():
    # 久慈と同じ「h2 【譲渡】の直後」で行を取る中部（花巻）も、決定の見出しの下は載せない
    import yaml

    for slug in ("pref_iwate_kuji", "pref_iwate_oshu", "pref_iwate_chubu"):
        raw = yaml.safe_load((ROOT / "recipes" / f"{slug}.yaml").read_text(encoding="utf-8"))
        lacks = raw["row_filter"]["field_lacks"]["section"]
        assert "決定" in lacks or "決まりました" in lacks, slug
