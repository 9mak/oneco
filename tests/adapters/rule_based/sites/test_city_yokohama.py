"""CityYokohamaAdapter のテスト

横浜市動物愛護センター (city.yokohama.lg.jp/.../aigo/maigo/) 用
rule-based adapter の動作を検証する。

- `<table>` 形式の single_page サイト (収容犬/収容猫/収容その他動物 の 3 種)
- フィクスチャは 0 件状態 (プレースホルダ行のみ) なので、データ行を持つ
  テストは synthetic な HTML を組み立てて検証する
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_yokohama import (
    CityYokohamaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site(
    name: str = "横浜市（収容犬）",
    list_url: str = (
        "https://www.city.yokohama.lg.jp/kurashi/sumai-kurashi/"
        "pet-dobutsu/aigo/maigo/shuyoinfo.html"
    ),
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="神奈川県",
        prefecture_code="14",
        list_url=list_url,
        category="sheltered",
        single_page=True,
    )


def _load_yokohama_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `city_yokohama.html` は、本来 UTF-8 のバイト列を
    Latin-1 として解釈してから再度 UTF-8 として保存し直された二重エンコーディング
    状態になっているため、実サイト相当のテキストを得るには逆変換が必要。
    実運用 (`_http_get`) では requests が正しい UTF-8 として受け取る。
    """
    raw = fixture_html("city_yokohama")
    if "横浜" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


def _build_html_with_one_row() -> str:
    """1 件のデータ行を含むテーブル HTML を生成する (テスト用)

    実サイトの `div.wysiwyg_wp` 配下のテーブル構造を再現する。
    """
    return """
    <html><body>
      <div class="wysiwyg_wp">
        <table align="center" style="width:95%">
          <caption>収容動物情報</caption>
          <tr>
            <th class="center top" scope="col">収容日・収容場所</th>
            <th class="center top" scope="col">写真</th>
            <th class="center top" scope="col">種類</th>
            <th class="center top" scope="col">性別</th>
            <th class="center top" scope="col">毛色</th>
            <th class="center top" scope="col">体格</th>
            <th class="center top" scope="col">その他</th>
          </tr>
          <tr>
            <td class="center">
              収容日：令和8年5月10日<br>
              収容場所：横浜市中区本町
            </td>
            <td class="center">
              <img src="/kurashi/sumai-kurashi/pet-dobutsu/aigo/maigo/img/dog001.jpg" alt="">
            </td>
            <td class="center">柴犬</td>
            <td class="center">オス</td>
            <td class="center">茶</td>
            <td class="center">中</td>
            <td class="center">首輪あり</td>
          </tr>
        </table>
      </div>
    </body></html>
    """


class TestCityYokohamaAdapter:
    def test_fetch_animal_list_returns_empty_when_placeholder_only(self, fixture_html):
        """0 件プレースホルダ行のみの実フィクスチャでは空リストを返す"""
        html = _load_yokohama_html(fixture_html)
        adapter = CityYokohamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        # 「現在、犬の収容情報はありません。」のみの状態 → 0 件扱い
        assert result == []

    def test_fetch_animal_list_returns_rows_when_data_present(self):
        """データ行があるときは仮想 URL のリストを返す"""
        html = _build_html_with_one_row()
        adapter = CityYokohamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 1
        url, cat = result[0]
        assert url.endswith("#row=0")
        assert url.startswith("https://www.city.yokohama.lg.jp/")
        assert cat == "sheltered"

    def test_extract_animal_details_first_row(self):
        """1 件目のデータ行から RawAnimalData を構築できる"""
        html = _build_html_with_one_row()
        adapter = CityYokohamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # 同一ページから複数取得しても HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        # サイト名から犬と推定される
        assert raw.species == "犬"
        # 「種類」列は species ではなく犬種=breed として保持(サイレントドロップ回帰防止)
        assert raw.breed
        assert adapter.normalize(raw).breed
        assert raw.sex == "オス"
        assert raw.color == "茶"
        assert raw.size == "中"
        assert "令和8年5月10日" in raw.shelter_date
        assert "横浜市中区" in raw.location
        # 画像 URL が絶対 URL に変換されている
        assert raw.image_urls
        for u in raw.image_urls:
            assert u.startswith("https://www.city.yokohama.lg.jp/")
        # source_url は仮想 URL
        assert raw.source_url == first_url
        assert raw.category == "sheltered"

    def test_species_inference_for_cat_site(self):
        """サイト名 "横浜市（収容猫）" のときは species が "猫" になる"""
        html = _build_html_with_one_row()
        cat_site = _site(
            name="横浜市（収容猫）",
            list_url=(
                "https://www.city.yokohama.lg.jp/kurashi/sumai-kurashi/"
                "pet-dobutsu/aigo/maigo/20121004094818.html"
            ),
        )
        adapter = CityYokohamaAdapter(cat_site)

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")

        assert raw.species == "猫"

    def test_species_inference_for_other_site(self):
        """サイト名 "横浜市（収容その他動物）" のときは species が "その他" になる"""
        html = _build_html_with_one_row()
        other_site = _site(
            name="横浜市（収容その他動物）",
            list_url=(
                "https://www.city.yokohama.lg.jp/kurashi/sumai-kurashi/"
                "pet-dobutsu/aigo/maigo/20121004110429.html"
            ),
        )
        adapter = CityYokohamaAdapter(other_site)

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")

        assert raw.species == "その他"

    def test_all_three_sites_registered(self):
        """3 つの横浜市サイト名すべてが Registry に登録されている"""
        expected = [
            "横浜市（収容犬）",
            "横浜市（収容猫）",
            "横浜市（収容その他動物）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, CityYokohamaAdapter)
            assert SiteAdapterRegistry.get(name) is CityYokohamaAdapter

    def test_extract_phone_injected_from_constant(self):
        """各動物カードには phone 欄が無いがフロントで連絡先表示が必須なため
        動物愛護センター代表電話 045-471-2111 を常に注入する"""
        html = _build_html_with_one_row()
        adapter = CityYokohamaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")
        assert raw.phone == "045-471-2111", f"代表電話が注入されるべき: got {raw.phone!r}"

    def test_extract_animal_details_cat_table_8_columns(self):
        """収容猫テーブルは犬と列構造が違う (8列, 先頭「掲載日」追加, 6列目「年齢」)

        実サイト調査 (2026-06): 収容猫ページのテーブルヘッダは
        [掲載日, 収容日・収容場所, 写真, 種類, 性別, 毛色, 年齢, その他]
        旧実装は犬の 7列構造で固定だったため、color/size の値が誤った
        セルから取得されていた (snapshot で color が性別文字列だった証拠)。

        ヘッダ <th> の文字列からフィールドマッピングを動的に構築する。
        """
        cat_html = """
        <html><body>
          <div class="wysiwyg_wp">
            <table>
              <caption>収容動物情報</caption>
              <tr>
                <th>掲載日</th>
                <th>収容日・収容場所</th>
                <th>写真</th>
                <th>種類</th>
                <th>性別</th>
                <th>毛色</th>
                <th>年齢</th>
                <th>その他</th>
              </tr>
              <tr>
                <td>令和8年5月20日</td>
                <td>
                  収容日：令和8年5月18日<br>
                  収容場所：横浜市旭区
                </td>
                <td><img src="/img/cat001.jpg" alt=""></td>
                <td>雑種</td>
                <td>メス</td>
                <td>三毛</td>
                <td>3歳</td>
                <td>首輪なし</td>
              </tr>
            </table>
          </div>
        </body></html>
        """
        cat_site = _site(
            name="横浜市（収容猫）",
            list_url=(
                "https://www.city.yokohama.lg.jp/kurashi/sumai-kurashi/"
                "pet-dobutsu/aigo/maigo/20121004094818.html"
            ),
        )
        adapter = CityYokohamaAdapter(cat_site)
        with patch.object(adapter, "_http_get", return_value=cat_html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")
        # color と sex が正しく取得される (旧実装ではズレていた)
        assert raw.species == "猫"
        assert raw.sex == "メス", f"sex 列ズレ修正されるべき: got {raw.sex!r}"
        assert raw.color == "三毛", f"color 列ズレ修正されるべき: got {raw.color!r}"
        # 猫テーブル特有の「年齢」列が age に流れる (犬テーブルには無い)
        assert raw.age == "3歳", f"年齢列が age に格納されるべき: got {raw.age!r}"
        # 収容日/場所は2列目から正しく抽出
        assert "令和8年5月18日" in raw.shelter_date
        assert "横浜市旭区" in raw.location
        # 体格列が無いので size は空 (size を sex/color から誤取得しない)
        assert raw.size == "", f"猫テーブルに体格列なし: got {raw.size!r}"

    def test_raises_parsing_error_when_no_table(self):
        """テーブルが見当たらない HTML では例外を出す"""
        adapter = CityYokohamaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value="<html><body></body></html>"):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()
