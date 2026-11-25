"""W006 T630（写真表示のお伺いへの返事 2026-11-24）と札幌市の公式ホームページのリニューアルによる URL の移転（2026-11-25）。

札幌市保健所 動物愛護管理センター（11/24 19:59）: 11/18 にお伺いした 4 ページ（迷子犬・迷子猫・譲渡可能犬・譲渡可能猫）について
「複製・転用について、写真も含め表示することについては、特に問題ありません。」条件は付いていない。写真を出す。
同じ返事の「11月24日以降はURLが変更となります」のとおり、4 ページとも 301 で s049/ の下へ移った。電話・所在地は移転先のページで確かめた。
"""

from pathlib import Path

import pytest
import yaml
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
RAW = yaml.safe_load((ROOT / "registry" / "sources.yaml").read_text(encoding="utf-8"))["sources"]
NOTES = {d["slug"]: d.get("note") or "" for d in RAW}

NEW_URL = {
    "city_sapporo-1": "https://www.city.sapporo.jp/s049/68135.html",
    "city_sapporo-2": "https://www.city.sapporo.jp/s049/68127.html",
    "city_sapporo-3": "https://www.city.sapporo.jp/s049/30069.html",
    "city_sapporo-4": "https://www.city.sapporo.jp/s049/99397.html",
}


@pytest.mark.parametrize("slug", list(NEW_URL))
def test_sapporo_pages_show_photos_after_the_city_said_yes(slug: str) -> None:
    s = SOURCES[slug]
    assert (s.mode, s.enabled, s.photo) == ("recipe", True, "ok")
    assert NOTES[slug].startswith("2026-11-24 札幌市保健所 動物愛護管理センターから")
    assert "特に問題ありません" in NOTES[slug]
    assert "写真は pending" not in NOTES[slug]


@pytest.mark.parametrize("slug", list(NEW_URL))
def test_sapporo_url_and_contacts_follow_the_new_site(slug: str) -> None:
    s = SOURCES[slug]
    assert s.url == NEW_URL[slug]
    assert s.verified_at == "2026-11-25"
    # 電話・所在地は同じ掲載元のページ自身で確かめた（4 ページとも本文に載っている）
    assert s.verified_phone_url == NEW_URL[slug]
    assert s.verified_address_url == NEW_URL[slug]
    assert s.phone == "011-736-6134"
    assert s.address == "〒060-0022 札幌市中央区北22条西15丁目3-6"


def test_no_old_sapporo_url_left_in_the_registry() -> None:
    text = (ROOT / "registry" / "sources.yaml").read_text(encoding="utf-8")
    for old in ("maigoinu.html", "maigoneko2.html", "houkiken.html", "jotoneko.html"):
        assert old not in text
