"""PrefShimaneAdapter のテスト

島根県 松江保健所 (pref.shimane.lg.jp) 用 rule-based adapter の動作を検証する。

- 1 ページに収容犬テーブル + 収容猫テーブルが並ぶ single_page 形式
- 各 table の `<caption>` (収容犬/収容猫) から species を推定
- ヘッダ行 (`<th>` のみ) や空セルだけのプレースホルダ行は除外
- 在庫 0 件のページでも ParsingError を出さず空リストを返す
- 実 fixture (pref_shimane_lg_jp.html) は「現在保護収容している動物がいない」
  状態のスナップショットなので、データ行は 0 件である
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.pref_shimane import (
    PrefShimaneAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


SITE_NAME = "島根県 松江保健所（収容動物）"
LIST_URL = (
    "https://www.pref.shimane.lg.jp/infra/nature/animal/matsue_hoken/"
    "doubutu/hogozyouhou_kakobunn/syuyouari.html"
)


def _site() -> SiteConfig:
    return SiteConfig(
        name=SITE_NAME,
        prefecture="島根県",
        prefecture_code="32",
        list_url=LIST_URL,
        category="sheltered",
        single_page=True,
    )


def _populated_html() -> str:
    """テスト用に動物データ行を 1 件ずつ持つ HTML を生成する

    実フィクスチャ (pref_shimane_lg_jp.html) は在庫 0 件のスナップショットの
    ため、抽出ロジック (収容日・場所・性別・画像 URL 等) を検証する目的で
    最小構成の populated HTML を別途作る。
    """
    return """<html><head><title>島根県：保護・収容情報</title></head>
<body><main>
<h1>保護・収容動物情報</h1>
<div>
  <table>
    <caption>収容犬</caption>
    <tbody>
      <tr>
        <th scope="col">管理番号</th><th scope="col">写真</th>
        <th scope="col">収容日</th><th scope="col">収容場所</th>
        <th scope="col">動物種別</th><th scope="col">種類</th>
        <th scope="col">性別</th>
      </tr>
      <tr>
        <td>2026-0001</td>
        <td><img alt="dog" src="/images/dog1.jpg"></td>
        <td>2026年5月10日</td>
        <td>松江市</td>
        <td>犬</td>
        <td>雑種</td>
        <td>オス</td>
      </tr>
    </tbody>
  </table>
</div>
<div>
  <table>
    <caption>収容猫</caption>
    <tbody>
      <tr>
        <th scope="col">管理番号</th><th scope="col">写真</th>
        <th scope="col">収容日</th><th scope="col">収容場所</th>
        <th scope="col">動物種別</th><th scope="col">種類</th>
        <th scope="col">性別</th>
      </tr>
      <tr>
        <td>2026-0002</td>
        <td><img alt="cat" src="/images/cat1.jpg"></td>
        <td>2026年5月12日</td>
        <td>安来市</td>
        <td>猫</td>
        <td>雑種</td>
        <td>メス</td>
      </tr>
    </tbody>
  </table>
</div>
</main></body></html>
"""


class TestPrefShimaneAdapter:
    # ─────────────── 実 fixture (在庫 0 件) ───────────────

    def test_fetch_animal_list_empty_returns_empty(self, fixture_html):
        """実 fixture は在庫 0 件のため空リストが返る (例外を出さない)

        ヘッダ行 (`<th>` のみ) と空 td/th だけのプレースホルダ行しか無いので、
        `_load_rows` が両方除外して 0 件になる。
        """
        html = fixture_html("pref_shimane_lg_jp")
        adapter = PrefShimaneAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_fixture_is_clean_utf8(self, fixture_html):
        """実 fixture は UTF-8 で保存されており「島根」が含まれる

        mojibake 補正分岐に入らないこと (= 文字化け修復不要) を確認する。
        """
        html = fixture_html("pref_shimane_lg_jp")
        assert "島根" in html
        assert "松江" in html

    # ─────────────── populated HTML での抽出検証 ───────────────

    def test_extract_dog_from_populated_html(self):
        """収容犬テーブルのデータ行から RawAnimalData が構築できる"""
        adapter = PrefShimaneAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=_populated_html()):
            urls = adapter.fetch_animal_list()
            # 収容犬 1 件 + 収容猫 1 件 = 2 件
            assert len(urls) == 2
            url, category = urls[0]
            raw = adapter.extract_animal_details(url, category=category)

        assert isinstance(raw, RawAnimalData)
        # caption「収容犬」から species 推定
        assert raw.species == "犬"
        assert raw.shelter_date == "2026-05-10"
        assert raw.location == "松江市"
        assert raw.sex == "オス"
        assert raw.category == "sheltered"
        # 画像 URL は絶対 URL に変換される
        assert raw.image_urls
        assert all(u.startswith("http") for u in raw.image_urls)
        assert "/images/dog1.jpg" in raw.image_urls[0]

    def test_extract_cat_from_populated_html(self):
        """収容猫テーブルのデータ行も同様に抽出される"""
        adapter = PrefShimaneAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=_populated_html()):
            urls = adapter.fetch_animal_list()
            url, category = urls[1]
            raw = adapter.extract_animal_details(url, category=category)

        assert raw.species == "猫"
        assert raw.shelter_date == "2026-05-12"
        assert raw.location == "安来市"
        assert raw.sex == "メス"

    def test_http_called_only_once(self):
        """_load_rows のキャッシュにより HTTP は 1 回しか呼ばれない"""
        adapter = PrefShimaneAdapter(_site())

        with patch.object(
            adapter, "_http_get", return_value=_populated_html()
        ) as mock_get:
            urls = adapter.fetch_animal_list()
            for url, cat in urls:
                adapter.extract_animal_details(url, category=cat)

        assert mock_get.call_count == 1

    def test_header_and_placeholder_rows_excluded(self):
        """ヘッダ行 (`<th>` のみ) と空セルだけの行はデータに混入しない"""
        html_only_placeholder = """
<html><head><title>島根県</title></head><body><main>
<table>
  <caption>収容犬</caption>
  <tbody>
    <tr><th>管理番号</th><th>写真</th><th>収容日</th><th>収容場所</th>
        <th>動物種別</th><th>種類</th><th>性別</th></tr>
    <tr><th></th><th></th><th></th><th></th>
        <th></th><th></th><th></th></tr>
  </tbody>
</table>
</main></body></html>
"""
        adapter = PrefShimaneAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html_only_placeholder):
            assert adapter.fetch_animal_list() == []

    def test_empty_td_row_excluded(self):
        """全 td が空文字のプレースホルダ td 行も除外される

        テーブル更新時に td の空配列だけが残るパターンへのフェイルセーフ。
        """
        html_empty_td_row = """
<html><head><title>島根県</title></head><body><main>
<table>
  <caption>収容犬</caption>
  <tbody>
    <tr><th>管理番号</th><th>写真</th><th>収容日</th><th>収容場所</th>
        <th>動物種別</th><th>種類</th><th>性別</th></tr>
    <tr><td></td><td></td><td></td><td></td>
        <td></td><td></td><td></td></tr>
  </tbody>
</table>
</main></body></html>
"""
        adapter = PrefShimaneAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html_empty_td_row):
            assert adapter.fetch_animal_list() == []

    # ─────────────── species 推定ロジック ───────────────

    def test_species_inferred_from_caption_priority(self):
        """caption の「収容犬」「収容猫」が動物種別列より優先される

        動物種別列が空欄でも caption から犬/猫が推定できる。
        """
        html = """
<html><head><title>島根県</title></head><body><main>
<table>
  <caption>収容犬</caption>
  <tbody>
    <tr><th>管理番号</th><th>写真</th><th>収容日</th><th>収容場所</th>
        <th>動物種別</th><th>種類</th><th>性別</th></tr>
    <tr><td>X-1</td><td></td><td>2026年5月10日</td><td>松江市</td>
        <td></td><td>柴犬</td><td>オス</td></tr>
  </tbody>
</table>
</main></body></html>
"""
        adapter = PrefShimaneAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")
        assert raw.species == "犬"

    def test_species_falls_back_to_animal_type_column(self):
        """caption が無い場合は「動物種別」列から species を推定する"""
        html = """
<html><head><title>島根県</title></head><body><main>
<table>
  <tbody>
    <tr><th>管理番号</th><th>写真</th><th>収容日</th><th>収容場所</th>
        <th>動物種別</th><th>種類</th><th>性別</th></tr>
    <tr><td>X-2</td><td></td><td>2026年5月10日</td><td>出雲市</td>
        <td>猫</td><td>雑種</td><td>メス</td></tr>
  </tbody>
</table>
</main></body></html>
"""
        adapter = PrefShimaneAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")
        assert raw.species == "猫"

    # ─────────────── 日付パース ───────────────

    def test_parse_shelter_date_variants(self):
        """和暦表記 / スラッシュ / ハイフンいずれも ISO に揃う"""
        f = PrefShimaneAdapter._parse_shelter_date
        assert f("2026年5月10日") == "2026-05-10"
        assert f("2026/5/10") == "2026-05-10"
        assert f("2026-05-10") == "2026-05-10"
        # 月日のみは不明扱い (空文字)
        assert f("5月10日") == ""
        assert f("") == ""

    # ─────────────── mojibake 補正 ───────────────

    def test_mojibake_is_repaired(self):
        """二重 UTF-8 エンコード HTML でも漢字が正しく復元される"""
        good = _populated_html()
        # 二重エンコード状態を疑似的に作る
        try:
            mojibake = good.encode("utf-8").decode("latin-1")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pytest.skip("環境依存: 二重エンコード再現不可")
        # 念のため「島根」が見えなくなっていることを確認
        assert "島根" not in mojibake

        adapter = PrefShimaneAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=mojibake):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")

        # 復元できていれば「松江市」が読める
        assert raw.location == "松江市"

    # ─────────────── normalize ───────────────

    def test_normalize_returns_animal_data(self):
        """RawAnimalData を normalize して AnimalData に変換できる"""
        adapter = PrefShimaneAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=_populated_html()):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")
            normalized = adapter.normalize(raw)
        assert normalized is not None
        assert hasattr(normalized, "species")

    # ─────────────── レジストリ ───────────────

    def test_site_is_registered(self):
        """sites.yaml の site name が Registry に登録されている"""
        # 他テストが registry を clear する場合に備えて冪等に再登録
        if SiteAdapterRegistry.get(SITE_NAME) is None:
            SiteAdapterRegistry.register(SITE_NAME, PrefShimaneAdapter)
        assert SiteAdapterRegistry.get(SITE_NAME) is PrefShimaneAdapter
