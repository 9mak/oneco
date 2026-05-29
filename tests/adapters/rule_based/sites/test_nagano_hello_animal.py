"""NaganoHelloAnimalAdapter のテスト

長野県動物愛護センター（ハローアニマル）譲渡情報サイト用 rule-based adapter
の動作を検証する。

実構造: single_page。「飼い主募集中の犬／猫の情報」h2 配下の
`<div class="section">` を 1 動物として抽出。
「県内保健所…」h2 以降は別セクションなので除外。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.nagano_hello_animal import (
    NaganoHelloAnimalAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

# 実構造を模した合成 HTML: 飼い主募集中 2 件 + 県内保健所セクション (除外)
ACTIVE_AND_OTHER_HTML = """
<html><body>
<div id="tmp_contents">
  <h1>犬の譲渡</h1>
  <h2>飼い主募集中の犬の情報</h2>
  <div class="section">
    <h3>やまと</h3>
    <p>種類：ミックス（薄茶）</p>
    <p>性別：オス（去勢済み）</p>
    <p>生年月：2021年5月頃生まれ</p>
    <p>備考：デモンストレーション犬を引退。体重16kg前後で中型犬です。</p>
  </div>
  <div class="section">
    <h3>はな</h3>
    <p>種類：柴系雑種（茶白）</p>
    <p>性別：メス（避妊済み）</p>
    <p>生年月：2019年10月頃生まれ</p>
    <p>備考：小型犬。室内飼育向き。</p>
  </div>
  <h2>県内保健所（保健福祉事務所）の情報</h2>
  <div class="section">
    <p>北信保健福祉事務所はこちら</p>
  </div>
</div>
</body></html>
"""

# 飼い主募集中セクションが無い (在庫 0 件) HTML
EMPTY_HTML = """
<html><body>
<div id="tmp_contents">
  <h1>犬の譲渡</h1>
  <h2>県内保健所（保健福祉事務所）の情報</h2>
  <div class="section"><p>各保健所へのリンク</p></div>
</div>
</body></html>
"""


def _site(name: str = "長野県動物愛護センター（譲渡犬）") -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="長野県",
        prefecture_code="20",
        list_url="https://www.pref.nagano.lg.jp/dobutsuaigo/joto/inu-neko/inu.html",
        category="adoption",
        single_page=True,
    )


class TestNaganoFetchList:
    def test_extracts_only_active_blocks(self):
        """「飼い主募集中」配下のみ抽出、「県内保健所」配下は除外"""
        adapter = NaganoHelloAnimalAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=ACTIVE_AND_OTHER_HTML):
            urls = adapter.fetch_animal_list()
        assert len(urls) == 2
        for u, cat in urls:
            assert "#row=" in u
            assert u.startswith("https://www.pref.nagano.lg.jp/")
            assert cat == "adoption"

    def test_empty_when_no_active_section(self):
        adapter = NaganoHelloAnimalAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=EMPTY_HTML):
            urls = adapter.fetch_animal_list()
        assert urls == []

    def test_caches_html(self):
        """fetch + extract で HTTP は 1 回だけ"""
        adapter = NaganoHelloAnimalAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=ACTIVE_AND_OTHER_HTML) as mock_get:
            urls = adapter.fetch_animal_list()
            for u, c in urls:
                adapter.extract_animal_details(u, c)
        assert mock_get.call_count == 1


class TestNaganoExtract:
    def test_first_block(self):
        """1匹目: やまと/オス/中型犬/薄茶"""
        adapter = NaganoHelloAnimalAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=ACTIVE_AND_OTHER_HTML):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], "adoption")
        assert isinstance(raw, RawAnimalData)
        assert raw.species == "犬"  # サイト名 (譲渡犬) から確定
        assert "オス" in raw.sex
        assert "薄茶" in raw.color  # 種類：ミックス（薄茶）の括弧内
        assert "中型犬" in raw.size  # 備考から「中型犬」を拾う
        assert "2021年5月" in raw.age  # 生年月 → DataNormalizer が月数化
        # location は施設名で固定 (location 不明回避)
        assert "ハローアニマル" in raw.location
        assert raw.category == "adoption"

    def test_second_block(self):
        """2匹目: はな/メス/小型犬/茶白"""
        adapter = NaganoHelloAnimalAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=ACTIVE_AND_OTHER_HTML):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[1][0], "adoption")
        assert "メス" in raw.sex
        assert "茶白" in raw.color
        assert "小型犬" in raw.size

    def test_cat_site_species_inference(self):
        """猫サイトでは species が「猫」に推定される"""
        cat_site = _site(name="長野県動物愛護センター（譲渡猫）")
        adapter = NaganoHelloAnimalAdapter(cat_site)
        cat_html = ACTIVE_AND_OTHER_HTML.replace("飼い主募集中の犬の情報", "飼い主募集中の猫の情報")
        with patch.object(adapter, "_http_get", return_value=cat_html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], "adoption")
        assert raw.species == "猫"


class TestNaganoSpeciesInference:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("長野県動物愛護センター（譲渡犬）", "犬"),
            ("長野県動物愛護センター（譲渡猫）", "猫"),
            ("長野県動物愛護センター（譲渡犬猫）", "その他"),
            ("どこかのサイト", ""),
        ],
    )
    def test_infer_species_from_site_name(self, name, expected):
        assert NaganoHelloAnimalAdapter._infer_species_from_site_name(name) == expected


class TestNaganoRegistry:
    @pytest.mark.parametrize(
        "site_name",
        [
            "長野県動物愛護センター（譲渡犬）",
            "長野県動物愛護センター（譲渡猫）",
        ],
    )
    def test_site_registered(self, site_name):
        if SiteAdapterRegistry.get(site_name) is None:
            SiteAdapterRegistry.register(site_name, NaganoHelloAnimalAdapter)
        cls = SiteAdapterRegistry.get(site_name)
        assert cls is NaganoHelloAnimalAdapter
