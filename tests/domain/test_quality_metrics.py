"""quality_metrics の純関数テスト"""

from __future__ import annotations

from datetime import date

from src.data_collector.domain.models import AnimalData
from src.data_collector.domain.quality_metrics import (
    MONITORED_FIELDS,
    compute_missing_rates,
    group_animals_by_site,
    is_missing,
)


def _make(
    *,
    location: str = "練馬区",
    age_months: int | None = 24,
    size: str | None = "中型",
    sex: str = "男の子",
    phone: str | None = "03-1234-5678",
    image_urls: list[str] | None = None,
    source_url: str = "https://example.lg.jp/animals/detail/1",
) -> AnimalData:
    # 空リストとデフォルト指定を区別するため `is not None` 判定
    imgs = image_urls if image_urls is not None else ["https://example.lg.jp/img/1.jpg"]
    return AnimalData(
        species="犬",
        shelter_date=date(2026, 5, 1),
        location=location,
        sex=sex,
        age_months=age_months,
        color="茶",
        size=size,
        phone=phone,
        image_urls=imgs,
        source_url=source_url,
        category="sheltered",
    )


class TestIsMissing:
    def test_none_is_missing(self):
        assert is_missing(_make(age_months=None), "age_months") is True
        assert is_missing(_make(size=None), "size") is True
        assert is_missing(_make(phone=None), "phone") is True

    def test_empty_string_is_missing(self):
        # location は str required だが空相当 ("不明"/"-") を missing と扱う
        assert is_missing(_make(location="不明"), "location") is True
        assert is_missing(_make(location="-"), "location") is True

    def test_sex_unknown_is_missing(self):
        assert is_missing(_make(sex="不明"), "sex") is True

    def test_image_urls_empty_is_missing(self):
        assert is_missing(_make(image_urls=[]), "image_urls") is True

    def test_present_values_are_not_missing(self):
        a = _make()
        assert is_missing(a, "location") is False
        assert is_missing(a, "age_months") is False
        assert is_missing(a, "size") is False
        assert is_missing(a, "sex") is False
        assert is_missing(a, "phone") is False
        assert is_missing(a, "image_urls") is False


class TestComputeMissingRates:
    def test_all_present(self):
        animals = [_make() for _ in range(3)]
        rates = compute_missing_rates(animals)
        for f in MONITORED_FIELDS:
            assert rates[f] == 0.0

    def test_all_missing(self):
        animals = [
            _make(
                location="不明", age_months=None, size=None, sex="不明", phone=None, image_urls=[]
            )
            for _ in range(2)
        ]
        rates = compute_missing_rates(animals)
        for f in MONITORED_FIELDS:
            assert rates[f] == 1.0

    def test_partial_missing(self):
        animals = [
            _make(age_months=24),
            _make(age_months=None),
            _make(age_months=None),
            _make(age_months=12),
        ]
        rates = compute_missing_rates(animals)
        assert rates["age_months"] == 0.5  # 2/4 が missing

    def test_empty_animals_returns_zero_rates(self):
        rates = compute_missing_rates([])
        for f in MONITORED_FIELDS:
            assert rates[f] == 0.0

    def test_only_specified_fields(self):
        animals = [_make(age_months=None, size=None)]
        rates = compute_missing_rates(animals, fields=("age_months",))
        assert rates == {"age_months": 1.0}
        assert "size" not in rates


class TestGroupAnimalsBySite:
    """収集時に判明した source_url の対応でグルーピングする

    従来は `{site_name: list_url}` を渡し `source_url.startswith(list_url)` で
    振り分けていたが、1 頭ごとに独立した詳細ページ URL を持つサイトでは
    前方一致が成立せず、実測で 211 サイト中 70 サイトが「実データがあるのに
    品質監視の対象外」になっていた (2026-08-03)。
    さらに同一ドメインに複数サイトを持つ自治体 (旭川市 8 / 福岡県 8 など) は
    source_url だけでは原理的に site を特定できない。
    そのため収集時に得た `{site_name: [source_url, ...]}` を正とする。
    """

    def test_groups_by_collected_source_urls(self):
        animals = [
            _make(source_url="https://a.example.com/animals/1"),
            _make(source_url="https://a.example.com/animals/2"),
            _make(source_url="https://b.example.com/list/3"),
        ]
        groups = group_animals_by_site(
            animals,
            {
                "サイトA": [
                    "https://a.example.com/animals/1",
                    "https://a.example.com/animals/2",
                ],
                "サイトB": ["https://b.example.com/list/3"],
            },
        )
        assert len(groups["サイトA"]) == 2
        assert len(groups["サイトB"]) == 1

    def test_detail_url_unrelated_to_list_url_is_grouped(self):
        """詳細 URL が list_url と無関係でもグルーピングできる (43% 漏れの回帰)"""
        animals = [
            _make(source_url="https://animal-net.pref.nagasaki.jp/animal/no-19847/"),
            _make(source_url="https://animal-net.pref.nagasaki.jp/animal/no-19823/"),
        ]
        groups = group_animals_by_site(
            animals,
            {
                "長崎犬猫ネット（保健所収容）": [
                    "https://animal-net.pref.nagasaki.jp/animal/no-19847/",
                    "https://animal-net.pref.nagasaki.jp/animal/no-19823/",
                ]
            },
        )
        assert len(groups["長崎犬猫ネット（保健所収容）"]) == 2

    def test_same_domain_multiple_sites_are_separated(self):
        """同一ドメインの複数サイトを取り違えない (旭川市 douaicenter.jp 型)"""
        animals = [
            _make(source_url="https://www.douaicenter.jp/animal/15259"),
            _make(source_url="https://www.douaicenter.jp/animal/14950"),
        ]
        groups = group_animals_by_site(
            animals,
            {
                "旭川市あにまある（譲渡犬）": ["https://www.douaicenter.jp/animal/15259"],
                "旭川市あにまある（譲渡猫）": ["https://www.douaicenter.jp/animal/14950"],
            },
        )
        assert [str(a.source_url) for a in groups["旭川市あにまある（譲渡犬）"]] == [
            "https://www.douaicenter.jp/animal/15259"
        ]
        assert [str(a.source_url) for a in groups["旭川市あにまある（譲渡猫）"]] == [
            "https://www.douaicenter.jp/animal/14950"
        ]

    def test_unmatched_url_not_in_any_group(self):
        animals = [_make(source_url="https://other.example.com/foo")]
        groups = group_animals_by_site(animals, {"サイトA": ["https://a.example.com/1"]})
        assert "サイトA" not in groups or len(groups["サイトA"]) == 0

    def test_site_with_no_collected_animals_is_omitted(self):
        """1 件も取れなかったサイトはキーごと落とす (空配列を返さない)"""
        animals = [_make(source_url="https://a.example.com/1")]
        groups = group_animals_by_site(
            animals,
            {"サイトA": ["https://a.example.com/1"], "サイトB": []},
        )
        assert "サイトB" not in groups

    def test_empty_inputs(self):
        assert group_animals_by_site([], {"サイトA": ["https://a.example.com/1"]}) == {}
        assert group_animals_by_site([_make()], {}) == {}
