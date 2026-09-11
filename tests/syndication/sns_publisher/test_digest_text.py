"""digest_text.py: 定型文組み立て TDD (T160)"""

from __future__ import annotations

from datetime import date

from syndication_service.sns_publisher.digest import DigestStats
from syndication_service.sns_publisher.digest_text import build_digest_text

_SITE_URL = "https://oneco.example"


class TestBuildDigestText:
    def test_basic_text_within_180_chars(self):
        stats = DigestStats(
            target_date=date(2026, 9, 10),
            total=5,
            dog=3,
            cat=2,
            other=0,
            prefecture_counts=[("高知県", 3), ("東京都", 2)],
        )
        text = build_digest_text(stats, site_url=_SITE_URL)
        assert len(text) <= 180
        assert "9/10" in text
        assert "5 頭" in text
        assert "犬 3・猫 2" in text
        assert "高知県 3・東京都 2" in text
        assert "詳細と問い合わせは各自治体の公式ページへ。" in text
        assert _SITE_URL in text
        assert text.endswith("#保護犬 #保護猫")

    def test_other_part_included_when_present(self):
        stats = DigestStats(
            target_date=date(2026, 9, 10),
            total=6,
            dog=3,
            cat=2,
            other=1,
            prefecture_counts=[("高知県", 6)],
        )
        text = build_digest_text(stats, site_url=_SITE_URL)
        assert "犬 3・猫 2・その他 1" in text

    def test_other_part_omitted_when_zero(self):
        stats = DigestStats(
            target_date=date(2026, 9, 10),
            total=5,
            dog=3,
            cat=2,
            other=0,
            prefecture_counts=[("高知県", 5)],
        )
        text = build_digest_text(stats, site_url=_SITE_URL)
        assert "その他" not in text

    def test_three_or_fewer_prefectures_no_rest_part(self):
        stats = DigestStats(
            target_date=date(2026, 9, 10),
            total=3,
            dog=2,
            cat=1,
            other=0,
            prefecture_counts=[("高知県", 1), ("東京都", 1), ("大阪府", 1)],
        )
        text = build_digest_text(stats, site_url=_SITE_URL)
        assert "内訳: 高知県 1・東京都 1・大阪府 1。" in text
        assert "都道府県" not in text  # 「他 N 都道府県」の畳みが無い

    def test_four_or_more_prefectures_folds_rest(self):
        stats = DigestStats(
            target_date=date(2026, 9, 10),
            total=10,
            dog=6,
            cat=4,
            other=0,
            prefecture_counts=[
                ("高知県", 4),
                ("東京都", 3),
                ("大阪府", 2),
                ("福岡県", 1),
            ],
        )
        text = build_digest_text(stats, site_url=_SITE_URL)
        assert "内訳: 高知県 4・東京都 3・大阪府 2・他 1 都道府県 1 頭。" in text

    def test_many_prefectures_still_within_180_chars_by_folding_more(self):
        """都道府県が多い場合、180字を超えるなら明記数を3->2->1と減らして収める"""
        prefecture_counts = [(f"都道府県{i:02d}", 50 - i) for i in range(20)]
        stats = DigestStats(
            target_date=date(2026, 9, 10),
            total=sum(n for _p, n in prefecture_counts),
            dog=500,
            cat=400,
            other=0,
            prefecture_counts=prefecture_counts,
        )
        text = build_digest_text(stats, site_url=_SITE_URL)
        assert len(text) <= 180

    def test_unknown_prefecture_included_as_is(self):
        stats = DigestStats(
            target_date=date(2026, 9, 10),
            total=2,
            dog=1,
            cat=1,
            other=0,
            prefecture_counts=[("高知県", 1), ("不明", 1)],
        )
        text = build_digest_text(stats, site_url=_SITE_URL)
        assert "不明 1" in text

    def test_single_digit_date_no_zero_padding(self):
        stats = DigestStats(
            target_date=date(2026, 9, 1),
            total=1,
            dog=1,
            cat=0,
            other=0,
            prefecture_counts=[("高知県", 1)],
        )
        text = build_digest_text(stats, site_url=_SITE_URL)
        assert text.startswith("9/1 ")
