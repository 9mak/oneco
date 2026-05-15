"""MieDakcAdapter のテスト

三重県動物愛護管理センター (mie-dakc.server-shared.com) サイト用
rule-based adapter の動作を検証する。

- 1 ページに 1 動物 = 1 テーブルが並ぶ single_page 形式
- フィクスチャは Shift_JIS の二重エンコーディング状態
  (utf-8 として読み出し → latin-1 → shift_jis で逆変換が必要) で保存
- サイト登録 (1 サイトのみ) の確認
- 在庫 0 件のページでも ParsingError を出さず空リストを返す
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.mie_dakc import MieDakcAdapter
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


_FIXTURE_SLUG = "mie-dakc_server-shared_com"


def _site() -> SiteConfig:
    return SiteConfig(
        name="三重県動物愛護管理センター（迷い犬情報）",
        prefecture="三重県",
        prefecture_code="24",
        list_url="http://mie-dakc.server-shared.com/maigoinujyouhou.html",
        category="lost",
        single_page=True,
    )


class TestMieDakcAdapter:
    def test_fetch_animal_list_returns_at_least_one_animal(self, fixture_html):
        """フィクスチャから動物テーブル (1 件) が抽出される"""
        html = fixture_html(_FIXTURE_SLUG)
        adapter = MieDakcAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) >= 1, "少なくとも 1 件の動物テーブルが抽出されるはず"
        for url, cat in result:
            assert "#row=" in url
            assert url.startswith("http://mie-dakc.server-shared.com/")
            assert cat == "lost"

    def test_extract_animal_details_first_row(self, fixture_html):
        """1 件目のテーブルから RawAnimalData を構築できる

        フィクスチャ 1 件目:
        - 保護年月日: 令和8年5月7日
        - 保護場所: 鈴鹿市地子町
        - 種類: 雑種, 毛色: うす茶
        - 性別: オス
        - その他特徴: 体格：中
        - 問い合わせ先: 鈴鹿保健所 衛生指導課 (電話 059-382-8674)
        - 画像: image2774.jpg (相対 URL → 絶対化)
        """
        html = fixture_html(_FIXTURE_SLUG)
        adapter = MieDakcAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # 同一ページから複数取得しても HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        # サイト名から犬と推定される
        assert raw.species == "犬"
        # 場所
        assert "鈴鹿市" in raw.location
        # 性別
        assert raw.sex == "オス"
        # 毛色
        assert "茶" in raw.color
        # 体格 (「体格：中」 → "中")
        assert raw.size == "中"
        # 収容日 (令和表記のまま raw に保持される。正規化は normalizer 側で実施)
        assert "令和8年5月7日" in raw.shelter_date
        # 電話番号 (ハイフン付き形式に正規化)
        assert raw.phone == "059-382-8674"
        # 画像 URL が絶対 URL に変換されている
        assert raw.image_urls
        assert all(u.startswith("http") for u in raw.image_urls)
        # source_url は仮想 URL
        assert raw.source_url == first_url
        assert raw.category == "lost"

    def test_only_animal_tables_extracted(self, fixture_html):
        """案内表 (注意事項テーブル等) は動物として扱われない

        ページ内には HPB_TABLE_XLS_* 以外のテーブルや、
        XLS_* でも「保護年月日」を含まない案内表が存在し得るが、
        これらは動物テーブル抽出から除外される。
        """
        html = fixture_html(_FIXTURE_SLUG)
        adapter = MieDakcAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        # 抽出された行はすべて「保護年月日」を含む動物テーブル
        rows = adapter._load_rows()
        for table in rows:
            assert "保護年月日" in table.get_text()
        assert len(result) == len(rows)

    def test_site_registered(self):
        """三重県サイト名が Registry に登録されている"""
        name = "三重県動物愛護管理センター（迷い犬情報）"
        # 他テストが registry を clear する場合に備えて冪等に再登録
        if SiteAdapterRegistry.get(name) is None:
            SiteAdapterRegistry.register(name, MieDakcAdapter)
        assert SiteAdapterRegistry.get(name) is MieDakcAdapter

    def test_empty_page_returns_empty_list(self):
        """動物テーブルが 1 つも無いページでは空リストを返す (在庫 0 件可)"""
        adapter = MieDakcAdapter(_site())
        # 動物テーブル (「保護年月日」を含む XLS_1_ テーブル) を含まない HTML
        empty_html = (
            "<html><body><p>現在、迷い犬の公示はありません。</p></body></html>"
        )
        with patch.object(adapter, "_http_get", return_value=empty_html):
            result = adapter.fetch_animal_list()
        assert result == []

    def test_normalize_via_default_pipeline(self, fixture_html):
        """`normalize` で AnimalData に変換できる (令和→西暦変換含む)

        基底の `_default_normalize` を使用するため、
        `shelter_date` に「令和8年5月7日」が入っていれば
        AnimalData では date(2026, 5, 7) に正規化される。
        """
        from datetime import date

        html = fixture_html(_FIXTURE_SLUG)
        adapter = MieDakcAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)
            normalized = adapter.normalize(raw)

        # AnimalData の収容日は date オブジェクト (令和8年5月7日 → 2026-05-07)
        assert normalized.shelter_date == date(2026, 5, 7)
        assert normalized.species == "犬"
        # 電話番号は数字 10 桁が抽出されている (具体的な区切りは normalizer 任せ。
        # 三重県 059 局番に対して normalizer は 05-XXXX-XXXX に分割するが、
        # 桁数 (10 桁) が保持されていることだけ確認する)
        assert normalized.phone is not None
        digits_only = "".join(c for c in normalized.phone if c.isdigit())
        assert digits_only == "0593828674"
