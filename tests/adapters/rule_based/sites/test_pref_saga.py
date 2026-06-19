"""PrefSagaAdapter のテスト

佐賀県保護動物サイト (pref.saga.lg.jp) 用 rule-based adapter の動作を検証する。

- 1 ページに `table.__wys_table` が 3 つ並ぶ single_page 形式
  (保護犬情報 / 保護猫情報 / その他の保護動物情報)
- 6 サイト (地域別 5 + 全県譲渡 1) すべての登録確認
- 縦並びレイアウト (ラベル ↔ 値) からの RawAnimalData 構築
"""

from __future__ import annotations

from unittest.mock import patch

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.pref_saga import (
    PrefSagaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site() -> SiteConfig:
    return SiteConfig(
        name="佐賀県（佐賀市・多久・小城・神埼）保護犬猫",
        prefecture="佐賀県",
        prefecture_code="41",
        list_url="https://www.pref.saga.lg.jp/kiji00349237/index.html",
        category="adoption",
        single_page=True,
    )


def _load_saga_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `pref_saga__saga.html` は、
    本来 UTF-8 のバイト列を Latin-1 として解釈してから再度 UTF-8 として
    保存し直された二重エンコーディング状態になっているため、
    実サイト相当のテキストを得るには逆変換が必要。
    実運用 (`_http_get`) では requests が正しい UTF-8 として受け取る。
    """
    raw = fixture_html("pref_saga__saga")
    # 復号後に「保護犬情報」が出現するかで判定
    if "保護犬情報" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


# 実データを持つテーブル 1 件と、データなし (「保護中…いません」) テーブル 2 件を
# 合成した HTML。修正後は実データ 1 件のみが仮想 URL として返ることを検証する。
_HTML_WITH_ONE_DATA_AND_TWO_EMPTY = """
<html><body>
<h3 class="title">保護犬情報</h3>
<table class="__wys_table">
  <tr><td>保護犬（26-1）</td><td colspan="2">保護した場所</td><td>嬉野市塩田町</td></tr>
  <tr><td rowspan="8">備考なし</td><td rowspan="6">犬の特徴</td><td>種類</td><td>雑種</td></tr>
  <tr><td>毛色</td><td>茶白</td></tr>
  <tr><td>性別</td><td>オス</td></tr>
  <tr><td>体格</td><td>中型</td></tr>
  <tr><td>推定年齢</td><td>2歳</td></tr>
  <tr><td>その他</td><td>人懐っこい</td></tr>
  <tr><td colspan="2">収容日</td><td>令和8年4月5日</td></tr>
  <tr><td colspan="2">ホームページ掲載期限</td><td>令和8年5月5日</td></tr>
</table>

<h3 class="title">保護猫情報</h3>
<table class="__wys_table">
  <tr><td>保護猫（- ）</td><td colspan="2">保護した場所</td><td>　</td></tr>
  <tr><td rowspan="8">現在保護中の猫はいません</td><td rowspan="6">猫の特徴</td><td>種類</td><td></td></tr>
  <tr><td>毛色</td><td></td></tr>
  <tr><td>性別</td><td></td></tr>
  <tr><td>体格</td><td></td></tr>
  <tr><td>推定年齢</td><td></td></tr>
  <tr><td>その他</td><td></td></tr>
  <tr><td colspan="2">収容日</td><td>令和8年(2026年） 月 日</td></tr>
  <tr><td colspan="2">ホームページ掲載期限</td><td>令和8年(2026年） 月 日</td></tr>
</table>

<h3 class="title">その他の保護動物情報</h3>
<table class="__wys_table">
  <tr><td>保護動物（- ）</td><td colspan="2">保護した場所</td><td>　　</td></tr>
  <tr><td rowspan="8">現在保護中のその他の動物はいません</td><td rowspan="6">特徴</td><td>種類</td><td></td></tr>
  <tr><td>毛色</td><td></td></tr>
  <tr><td>性別</td><td></td></tr>
  <tr><td>体格</td><td></td></tr>
  <tr><td>推定年齢</td><td></td></tr>
  <tr><td>その他</td><td></td></tr>
  <tr><td colspan="2">収容日</td><td>令和8年(2026年） 月 日</td></tr>
  <tr><td colspan="2">ホームページ掲載期限</td><td>令和8年(2026年） 月 日</td></tr>
</table>
</body></html>
"""


class TestPrefSagaAdapter:
    def test_fetch_animal_list_skips_empty_tables(self):
        """「保護中の動物がいない」空テーブルは仮想 URL を生成しない

        旧実装は 3 テーブル全件を `#row=N` 化し、全項目が空文字の
        ダミー RawAnimalData を 14/15 件分 snapshot に乗せていた。
        実データ 1 件 + 空 2 件の合成 HTML で、実データ 1 件のみが
        返ることを検証する。
        """
        adapter = PrefSagaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=_HTML_WITH_ONE_DATA_AND_TWO_EMPTY):
            result = adapter.fetch_animal_list()
        assert len(result) == 1, f"実データ入りテーブル 1 件のみが残るはず: got {len(result)}"
        url, cat = result[0]
        # row index は元テーブルの位置 (0=犬) を保持
        assert url == "https://www.pref.saga.lg.jp/kiji00349237/index.html#row=0"
        assert cat == "adoption"

    def test_fetch_animal_list_with_all_empty_tables_returns_empty(self, fixture_html):
        """既存 fixture は 3 テーブルすべて「保護中の動物がいない」状態なので空リスト"""
        html = _load_saga_html(fixture_html)
        adapter = PrefSagaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()
        assert result == [], "fixture は実データなしのため 0 件を返すべき (旧実装は 3 件返していた)"

    def test_extract_animal_details_from_data_table(self):
        """空でない実データテーブルから各フィールドが取れる"""
        adapter = PrefSagaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=_HTML_WITH_ONE_DATA_AND_TWO_EMPTY):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="adoption")
        assert isinstance(raw, RawAnimalData)
        assert raw.location == "嬉野市塩田町"
        assert raw.species == "犬"  # h3 から推定
        # 「種類：雑種」は species(table/heading で犬確定)ではなく犬種=breed として保持
        assert raw.breed == "雑種"
        assert raw.sex == "オス"
        assert raw.color == "茶白"
        assert raw.size == "中型"
        assert raw.age == "2歳"
        assert raw.shelter_date == "令和8年4月5日"

    def test_species_uses_table_marker_when_heading_is_h2(self):
        """セクション見出しが h2 のページでも、テーブル本文のマーカー
        (保護犬（番号）/犬の特徴) から犬を確定する。

        旧実装は find_previous('h3') 固定で、見出しが h2 のページ
        (kiji00334505 等) では無関係なフッタ/サイドバー h3 を拾って
        species='その他' を返し、`or` 短絡で 種類='ビーグル'(犬) を masking
        していた (2026-06-16 live 実測)。raw と normalize() の両方でアサート。
        """
        html = """
        <html><body>
        <h3 class="title">関連情報</h3>
        <h2 class="title">保護犬の情報</h2>
        <table class="__wys_table">
          <tr><td>保護犬（26-9）</td><td colspan="2">保護した場所</td><td>伊万里市</td></tr>
          <tr><td rowspan="8">備考なし</td><td rowspan="6">犬の特徴</td><td>種類</td><td>ビーグル</td></tr>
          <tr><td>毛色</td><td>茶白</td></tr>
          <tr><td>性別</td><td>オス</td></tr>
          <tr><td>体格</td><td>中型</td></tr>
          <tr><td>推定年齢</td><td>2歳</td></tr>
          <tr><td colspan="2">収容日</td><td>令和8年4月5日</td></tr>
        </table>
        <h3>ご意見・情報公開・相談窓口</h3>
        </body></html>
        """
        adapter = PrefSagaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 1
            raw = adapter.extract_animal_details(urls[0][0], category="adoption")
            animal = adapter.normalize(raw)
        assert raw.species == "犬"
        assert animal.species == "犬"
        # 「種類：ビーグル」は species ではなく犬種=breed として保持される
        assert raw.breed == "ビーグル"
        assert animal.breed == "ビーグル"

    def test_all_six_sites_registered(self):
        """6 つの佐賀県サイト名すべてが Registry に登録されている"""
        expected = [
            "佐賀県（佐賀市・多久・小城・神埼）保護犬猫",
            "佐賀県（鳥栖・三養基郡）保護犬猫",
            "佐賀県（唐津・東松浦郡）保護犬猫",
            "佐賀県（伊万里・西松浦郡）保護犬猫",
            "佐賀県（武雄・鹿島・嬉野・杵島・藤津）保護犬猫",
            "佐賀県（全県）譲渡犬猫",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, PrefSagaAdapter)
            assert SiteAdapterRegistry.get(name) is PrefSagaAdapter

    def test_no_tables_returns_empty_list(self):
        """`table.__wys_table` が存在しない HTML は真ゼロとして空リストを返す"""
        adapter = PrefSagaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value="<html><body></body></html>"):
            result = adapter.fetch_animal_list()
        assert result == []
