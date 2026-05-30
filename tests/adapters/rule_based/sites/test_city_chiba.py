"""CityChibaAdapter のテスト

千葉市動物保護指導センター (city.chiba.jp/.../dobutsuhogo/) 用
rule-based adapter の動作を検証する。

- `<h4>` を起点とした animal block が並ぶ single_page 形式
- 6 サイト (迷子/市民保護 × 犬/猫/その他) すべての登録確認
"""

from __future__ import annotations

from unittest.mock import patch

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


# 実 HTML を再現した合成 HTML。先頭の注意書き <h4> と、ラベルが
# 「保護日：」「保護場所：」「体格：生後1か月前後」のケースを含む。
_HTML_REAL_LABELS = """
<html><body>
<div id="contents_editable">
  <h4>猫は逃がさないように飼いましょう。
いなくなってしまったときは、責任を持ってすぐに探して下さい。</h4>
  <p>注意書きの段落 (動物データではない)</p>

  <h4>A-6002</h4>
  <p><img alt="A-6002" src="/cmsfiles/images/a6002.jpg"></p>
  <p>保護日：令和８年４月８日<br>
保護場所：美浜区真砂<br>
種類：雑種<br>
毛色：三毛（茶黒白）<br>
性別：不明<br>
体格：中<br>
特徴：真っすぐな尾長、長毛、人なれしている</p>

  <h4>A-5073</h4>
  <p><img alt="A-5073" src="/cmsfiles/images/a5073.jpg"></p>
  <p>保護日：令和7年11月9日<br>
保護場所：村田町付近<br>
種類：雑種<br>
毛色：キジトラ<br>
性別：メス<br>
体格：生後1か月前後<br>
特徴：</p>
</div>
</body></html>
"""


def _site_cat() -> SiteConfig:
    return SiteConfig(
        name="千葉市（市民保護猫）",
        prefecture="千葉県",
        prefecture_code="12",
        list_url=(
            "https://www.city.chiba.jp/hokenfukushi/iryoeisei/"
            "seikatsueisei/dobutsuhogo/hogo_cat.html"
        ),
        category="sheltered",
        single_page=True,
    )


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

    def test_fetch_animal_list_skips_notice_h4(self):
        """注意書きの h4 (「猫は逃がさないように…」) は動物ブロックではないのでスキップする"""
        adapter = CityChibaAdapter(_site_cat())
        with patch.object(adapter, "_http_get", return_value=_HTML_REAL_LABELS):
            result = adapter.fetch_animal_list()
        # 注意書き 1 件 + 動物 2 件 → 動物 2 件のみ
        assert len(result) == 2
        # row index は元 h4 リストでの位置を保持 (1, 2)
        urls = [u for u, _c in result]
        assert urls[0].endswith("#row=1")
        assert urls[1].endswith("#row=2")

    def test_extract_supports_保護日_保護場所_labels(self):
        """実 HTML の「保護日：」「保護場所：」ラベルが shelter_date / location に流れる

        旧実装は「収容日：」「収容場所：」のみ対応で、現サイトのラベル変更
        (「保護日」「保護場所」) で全件 location 取得できていなかった。
        """
        adapter = CityChibaAdapter(_site_cat())
        with patch.object(adapter, "_http_get", return_value=_HTML_REAL_LABELS):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")
        assert raw.location == "美浜区真砂"
        assert "令和８年４月８日" == raw.shelter_date

    def test_extract_drops_non_standard_size_value(self):
        """size に標準値以外 (「生後1か月前後」) が入っていれば空文字にする

        ソース側で体格欄に年齢相当テキストを書き込んだケースを adapter で
        防御する。標準値は 小/中/大/小型/中型/大型/その他 のみ。
        """
        adapter = CityChibaAdapter(_site_cat())
        with patch.object(adapter, "_http_get", return_value=_HTML_REAL_LABELS):
            urls = adapter.fetch_animal_list()
            # 2 件目 (A-5073) が「体格：生後1か月前後」
            raw = adapter.extract_animal_details(urls[1][0], category="sheltered")
        assert raw.size == "", f"非標準値 '生後1か月前後' は除外されるべき: got {raw.size!r}"
        # location は引き続き取れる (副作用なし)
        assert raw.location == "村田町付近"

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

    def test_no_blocks_returns_empty_list(self):
        """動物ブロックが見当たらない HTML は真ゼロとして空リストを返す"""
        adapter = CityChibaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value="<html><body></body></html>"):
            result = adapter.fetch_animal_list()
        assert result == []
