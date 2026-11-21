"""T656 直し 1 回目・項目 8（2026-11-20・ネットワークなし）: 前橋市 5 掲載元の所在地。

5 ページとも末尾の「この記事に関するお問い合わせ先」に「群馬県前橋市朝日町三丁目36番17号」があるのに、台帳の address が null だった（T640 ③）。
verify_registry の考え方（掲載元ページで確かめられた値だけ書く）に沿って、address と verified_address_url（その値が載っていたページ）を入れた。
2026-11-20 に `ops/verify_registry.py --only city_maebashi --dry-run` で 5 件とも電話・所在地が元ページと一致することを確かめた。
"""

from pathlib import Path

from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
SLUGS = ["city_maebashi", "city_maebashi-2", "city_maebashi-3", "city_maebashi-4", "city_maebashi-5"]
ADDRESS = "群馬県前橋市朝日町三丁目36番17号"


def test_all_five_have_address_and_the_page_it_was_confirmed_on():
    for slug in SLUGS:
        s = SOURCES[slug]
        assert s.address == ADDRESS, slug
        assert s.phone == "027-220-5777", slug
        # 値を確かめたページ = その掲載元のページ（verified_address_url は台帳の url と同じ）
        assert s.verified_address_url == s.url and s.verified_phone_url == s.url, slug
        assert s.verified_at, slug


def test_notes_do_not_say_the_address_is_missing():
    import yaml

    raw = yaml.safe_load((ROOT / "registry" / "sources.yaml").read_text(encoding="utf-8"))
    for r in raw["sources"]:
        if r["slug"] in SLUGS:
            n = r.get("note") or ""
            assert "所在地は無い" not in n and "所在地が無い" not in n and "住所は無い" not in n, r["slug"]


def test_any_entry_with_a_verified_address_url_has_an_address():
    # 値の無い entry に「確かめたページ」だけが残らない
    for s in SOURCES.values():
        if s.verified_address_url:
            assert s.address, s.slug
