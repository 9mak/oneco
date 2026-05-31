"""函館どうなん動物愛護センター adapter テスト"""

from __future__ import annotations

from unittest.mock import patch

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.nyantomo import NyantomoAdapter
from data_collector.llm.config import SiteConfig


def _site() -> SiteConfig:
    return SiteConfig(
        name="函館どうなん動物愛護センター（里親募集）",
        prefecture="北海道",
        prefecture_code="01",
        list_url="https://nyantomo.jp/donanhakodate/",
        category="adoption",
        single_page=True,
    )


SAMPLE_HTML = """
<html><body>
  <div class="jet-listing-grid__item">
    <p class="elementor-heading-title">名前</p>
    <div class="jet-listing-dynamic-field__content">道南 ふわ</div>
    <p class="elementor-heading-title">年齢</p>
    <div class="jet-listing-dynamic-field__content">約6歳3ヵ月</div>
    <p class="elementor-heading-title">性別</p>
    <div class="jet-listing-dynamic-field__content">メス</div>
    <noscript>
      <img src="https://nyantomo.jp/wp-content/uploads/2026/01/cat1.jpg">
    </noscript>
  </div>
  <div class="jet-listing-grid__item">
    <p class="elementor-heading-title">名前</p>
    <div class="jet-listing-dynamic-field__content">函館 いろ</div>
    <p class="elementor-heading-title">年齢</p>
    <div class="jet-listing-dynamic-field__content">約2歳</div>
    <p class="elementor-heading-title">性別</p>
    <div class="jet-listing-dynamic-field__content">オス</div>
  </div>
</body></html>
"""


def test_fetch_returns_two_animals():
    adapter = NyantomoAdapter(_site())
    with patch.object(adapter, "_http_get", return_value=SAMPLE_HTML):
        result = adapter.fetch_animal_list()
    assert len(result) == 2
    for url, _ in result:
        assert url.startswith("https://nyantomo.jp/")


def test_fetch_returns_empty_for_no_cards():
    """募集 0 件 (cards 0) でも例外なし"""
    adapter = NyantomoAdapter(_site())
    with patch.object(adapter, "_http_get", return_value="<html><body></body></html>"):
        assert adapter.fetch_animal_list() == []


def test_extract_returns_raw_data():
    adapter = NyantomoAdapter(_site())
    with patch.object(adapter, "_http_get", return_value=SAMPLE_HTML):
        adapter.fetch_animal_list()
        raw = adapter.extract_animal_details(f"{adapter.site_config.list_url}#row=0")
    assert raw.species == "猫"  # サイト名から推定 or 固定
    assert raw.sex == "メス"
    assert raw.age == "約6歳3ヵ月"


def test_real_fixture_handles_gracefully(fixture_html):
    html = fixture_html("nyantomo_jp")
    adapter = NyantomoAdapter(_site())
    with patch.object(adapter, "_http_get", return_value=html):
        result = adapter.fetch_animal_list()
    assert isinstance(result, list)


def test_site_registered():
    name = "函館どうなん動物愛護センター（里親募集）"
    assert SiteAdapterRegistry.get(name) is NyantomoAdapter


# location ごとの電話番号マッピング検証用
_HTML_WITH_LOCATIONS = """
<html><body>
  <div class="jet-listing-grid__item">
    <div class="elementor-shortcode">
      <div class="centering">里親募集中<br/>函館市愛護センター</div>
    </div>
    <p class="elementor-heading-title">名前</p>
    <div class="jet-listing-dynamic-field__content">函館 いろ</div>
    <p class="elementor-heading-title">年齢</p>
    <div class="jet-listing-dynamic-field__content">約2歳</div>
    <p class="elementor-heading-title">性別</p>
    <div class="jet-listing-dynamic-field__content">オス</div>
  </div>
  <div class="jet-listing-grid__item">
    <div class="elementor-shortcode">
      <div class="centering">里親募集中<br/>道南愛護センター</div>
    </div>
    <p class="elementor-heading-title">名前</p>
    <div class="jet-listing-dynamic-field__content">道南 ふわ</div>
    <p class="elementor-heading-title">年齢</p>
    <div class="jet-listing-dynamic-field__content">約6歳3ヵ月</div>
    <p class="elementor-heading-title">性別</p>
    <div class="jet-listing-dynamic-field__content">メス</div>
  </div>
</body></html>
"""


def test_phone_mapped_by_location_hakodate():
    """函館市愛護センター → 0138-32-1524 (函館市保健所代表電話)

    2026-05 観測: nyantomo.jp は 3 つの電話番号 (本部 070-, 函館市 0138-32-,
    道南センター 0138-44-) を載せており、location 名で識別できる。
    """
    adapter = NyantomoAdapter(_site())
    with patch.object(adapter, "_http_get", return_value=_HTML_WITH_LOCATIONS):
        adapter.fetch_animal_list()
        raw = adapter.extract_animal_details(f"{adapter.site_config.list_url}#row=0")
    assert raw.location == "函館市愛護センター"
    assert raw.phone == "0138-32-1524"


def test_phone_mapped_by_location_donan():
    """道南愛護センター → 0138-44-2690"""
    adapter = NyantomoAdapter(_site())
    with patch.object(adapter, "_http_get", return_value=_HTML_WITH_LOCATIONS):
        adapter.fetch_animal_list()
        raw = adapter.extract_animal_details(f"{adapter.site_config.list_url}#row=1")
    assert raw.location == "道南愛護センター"
    assert raw.phone == "0138-44-2690"


def test_phone_empty_when_unknown_location():
    """マッピングに無い location は phone 空を維持 (フェイルセーフ)"""
    html_unknown = """
    <html><body>
      <div class="jet-listing-grid__item">
        <p class="elementor-heading-title">名前</p>
        <div class="jet-listing-dynamic-field__content">テスト</div>
      </div>
    </body></html>
    """
    adapter = NyantomoAdapter(_site())
    with patch.object(adapter, "_http_get", return_value=html_unknown):
        adapter.fetch_animal_list()
        raw = adapter.extract_animal_details(f"{adapter.site_config.list_url}#row=0")
    # 未知 location → phone 空
    assert raw.phone == ""
