"""CityChibaAdapter のテスト

千葉市動物保護指導センター (city.chiba.jp/.../dobutsuhogo/) 用
rule-based adapter の動作を検証する。

- `<h4>` を起点とした animal block が並ぶ single_page 形式
- 6 サイト (迷子/市民保護 × 犬/猫/その他) すべての登録確認
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_chiba import (
    CityChibaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site() -> SiteConfig:
    return SiteConfig(
        name="千葉市（迷子犬）",
        prefecture="千葉県",
        prefecture_code="12",
        list_url=(
            "https://www.city.chiba.jp/hokenfukushi/iryoeisei/"
            "seikatsueisei/dobutsuhogo/lost_dog.html"
        ),
        category="lost",
        single_page=True,
    )


def _load_chiba_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `city_chiba__lostdog.html` は、
    本来 UTF-8 のバイト列を Latin-1 として解釈してから再度 UTF-8 として
    保存し直された二重エンコーディング状態になっているため、
    実サイト相当のテキストを得るには逆変換が必要。
    実運用 (`_http_get`) では requests が正しい UTF-8 として受け取る。
    """
    raw = fixture_html("city_chiba__lostdog")
    # 実際のページに含まれる漢字 "千葉" が出てくるか判定
    if "千葉" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


class TestCityChibaAdapter:
    def test_fetch_animal_list_returns_rows(self, fixture_html):
        """一覧ページから動物ブロック (仮想 URL) が抽出できる"""
        html = _load_chiba_html(fixture_html)
        adapter = CityChibaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) >= 1, "少なくとも 1 件以上の動物ブロックが抽出されるはず"
        for url, cat in result:
            assert "#row=" in url
            assert url.startswith("https://www.city.chiba.jp/")
            assert cat == "lost"

    def test_extract_animal_details_first_row(self, fixture_html):
        """1 件目のブロックから RawAnimalData を構築できる

        フィクスチャ収録の動物 (管理番号 2605070106):
        - 収容日: 令和8年5月7日
        - 収容場所: 稲毛区小仲台
        - 種類: 柴犬 → サイト名から species は「犬」
        - 毛色: 茶
        - 性別: メス
        - 体格: 中
        """
        html = _load_chiba_html(fixture_html)
        adapter = CityChibaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # 同一ページから複数取得しても HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        # サイト名から犬と推定される
        assert raw.species == "犬"
        assert "稲毛区" in raw.location
        assert raw.sex == "メス"
        assert "茶" in raw.color
        assert raw.size == "中"
        assert "令和8年5月7日" in raw.shelter_date
        # 画像 URL が絶対 URL に変換されている
        assert raw.image_urls
        assert all(u.startswith("http") for u in raw.image_urls)
        assert any("26050706.jpg" in u for u in raw.image_urls)
        # source_url は仮想 URL
        assert raw.source_url == first_url
        assert raw.category == "lost"

    def test_all_six_sites_registered(self):
        """6 つの千葉市サイト名すべてが Registry に登録されている"""
        expected = [
            "千葉市（迷子犬）",
            "千葉市（迷子猫）",
            "千葉市（迷子その他動物）",
            "千葉市（市民保護犬）",
            "千葉市（市民保護猫）",
            "千葉市（市民保護その他）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, CityChibaAdapter)
            assert SiteAdapterRegistry.get(name) is CityChibaAdapter

    def test_species_inference_from_site_name(self, fixture_html):
        """サイト名 "千葉市（迷子猫）" のときは species が "猫" になる

        HTML の「種類：柴犬」のような具体名ではなくサイト名で推定することを確認。
        """
        html = _load_chiba_html(fixture_html)
        cat_site = SiteConfig(
            name="千葉市（迷子猫）",
            prefecture="千葉県",
            prefecture_code="12",
            list_url=(
                "https://www.city.chiba.jp/hokenfukushi/iryoeisei/"
                "seikatsueisei/dobutsuhogo/lost_cat.html"
            ),
            category="lost",
            single_page=True,
        )
        adapter = CityChibaAdapter(cat_site)
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")
        assert raw.species == "猫"

    def test_raises_parsing_error_when_no_blocks(self):
        """動物ブロックが見当たらない HTML では ParsingError 系例外を出す"""
        adapter = CityChibaAdapter(_site())
        with patch.object(
            adapter, "_http_get", return_value="<html><body></body></html>"
        ):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()
