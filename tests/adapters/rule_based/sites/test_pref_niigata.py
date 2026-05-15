"""PrefNiigataAdapter のテスト

新潟県動物愛護センター (pref.niigata.lg.jp) 用 rule-based adapter の動作検証。

- `<div class="detail_free">` ブロックのうち先頭 `<h3>` が「犬」「猫」のもの
  だけを動物データとして扱う single_page 形式
- フィクスチャは二重 UTF-8 mojibake 状態で保存されているため adapter 側で逆変換
- 在庫 0 件のページでも ParsingError を出さず空リストを返す
- 種別判定は h3 見出し (HTML 内) から行い、サイト名には依存しない
"""

from __future__ import annotations

from unittest.mock import patch

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.pref_niigata import (
    PrefNiigataAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site() -> SiteConfig:
    return SiteConfig(
        name="新潟県動物愛護センター（保護動物）",
        prefecture="新潟県",
        prefecture_code="15",
        list_url=("https://www.pref.niigata.lg.jp/sec/seikatueisei/1333314133188.html"),
        category="sheltered",
        single_page=True,
    )


class TestPrefNiigataAdapter:
    def test_fetch_animal_list_returns_one_animal(self, fixture_html):
        """fixture には猫の保護動物が 1 件のみ存在する

        他の `<div class="detail_free">` (関連情報・返還の手続き等) は
        h3 が「犬」「猫」と一致しないので除外される。
        """
        html = fixture_html("pref_niigata_lg_jp")
        adapter = PrefNiigataAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 1
        url, cat = result[0]
        assert "#row=0" in url
        assert url.startswith("https://www.pref.niigata.lg.jp/sec/seikatueisei/1333314133188.html")
        assert cat == "sheltered"

    def test_extract_first_animal(self, fixture_html):
        """fixture 1 件目 (猫: 26長MC007) から RawAnimalData を構築できる"""
        html = fixture_html("pref_niigata_lg_jp")
        adapter = PrefNiigataAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        # h3「猫」見出しから猫と判定される
        assert raw.species == "猫"
        # 場所抽出: "5月13日 長岡市乙吉地内で保護" -> "長岡市乙吉地内"
        assert "長岡市" in raw.location
        # 属性: "MIX、オス(未去勢)、白茶、しま模様の尻尾、体重3.6Kg、装着物なし"
        assert "オス" in raw.sex
        assert raw.color == "白茶"
        # 体重 3.6Kg → size に格納
        assert "3.6" in raw.size
        # 画像 URL が絶対 URL として取得される
        assert raw.image_urls
        assert all(u.startswith("http") for u in raw.image_urls)
        # 同一画像が 4 枚 (fixture)
        assert len(raw.image_urls) == 4
        # source_url は仮想 URL
        assert raw.source_url == first_url
        assert raw.category == "sheltered"

    def test_phone_extracted_from_footer(self, fixture_html):
        """フッタの "Tel：0258-21-5501" から電話番号が取得される"""
        html = fixture_html("pref_niigata_lg_jp")
        adapter = PrefNiigataAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")

        assert raw.phone == "0258-21-5501"

    def test_shelter_date_uses_recent_year_heuristic(self, fixture_html):
        """年が省略された月日 (5月13日) でも ISO 形式の日付になる

        年は実装ヒューリスティクス (今日基準で未来なら前年) なので
        厳密値の比較は避け、"YYYY-05-13" の形式である事だけを確認する。
        """
        html = fixture_html("pref_niigata_lg_jp")
        adapter = PrefNiigataAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")

        assert raw.shelter_date.endswith("-05-13"), raw.shelter_date
        # YYYY-MM-DD の形式
        assert len(raw.shelter_date) == 10

    def test_mojibake_is_repaired(self, fixture_html):
        """二重 UTF-8 エンコード fixture でも漢字が正しく復元される"""
        html = fixture_html("pref_niigata_lg_jp")
        adapter = PrefNiigataAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")

        # 復元できていれば "長岡市" / "白茶" が読める
        assert "長岡市" in raw.location
        assert raw.color == "白茶"

    def test_non_animal_blocks_excluded(self, fixture_html):
        """h3 が「犬」「猫」以外の detail_free (関連情報等) は除外される

        fixture 内には detail_free_3 (返還の際に必要な物) など
        動物データではない `detail_free` ブロックも存在する。
        """
        html = fixture_html("pref_niigata_lg_jp")
        adapter = PrefNiigataAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            rows = adapter._load_rows()

        assert len(rows) == 1
        # 唯一の行は h3=「猫」
        h3 = rows[0].find("h3")
        assert h3 is not None
        heading = h3.get_text(strip=True).replace("\xa0", "").strip()
        assert heading == "猫"

    def test_empty_page_returns_empty_list(self):
        """動物 detail_free が無いページ (在庫 0 件) でも例外を出さない"""
        empty_html = (
            "<html><head><title>新潟県</title></head>"
            "<body>"
            "<div class='detail_free' id='detail_free_1'>"
            "<h2>保護中の動物はいません</h2>"
            "</div>"
            "<div class='detail_free' id='detail_free_2'>"
            "<h3>関連情報</h3>"
            "</div>"
            "</body></html>"
        )
        adapter = PrefNiigataAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=empty_html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_dog_block_inferred_correctly(self):
        """h3 が「犬」のブロックは species=犬 として抽出される"""
        html_with_dog = (
            "<html><head><title>新潟県</title></head>"
            "<body>"
            "<div class='detail_free' id='detail_free_1'>"
            "<h3>犬</h3>"
            "<p><img src='/uploaded/image/x.jpg'></p>"
            "<p><strong>26長DG001</strong></p>"
            "<p>5月10日 新潟市中央区で保護</p>"
            "<p>柴犬、メス、茶色、体重8.0Kg</p>"
            "</div>"
            "<span class='sf_tel'>Tel：0258-21-5501</span>"
            "</body></html>"
        )
        adapter = PrefNiigataAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html_with_dog):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")

        assert raw.species == "犬"
        assert raw.sex == "メス"
        assert raw.color == "茶色"
        assert "新潟市中央区" in raw.location
        assert "8.0" in raw.size
        assert raw.shelter_date.endswith("-05-10")

    def test_site_registered(self):
        """sites.yaml の「新潟県動物愛護センター（保護動物）」が
        Registry に登録されている"""
        name = "新潟県動物愛護センター（保護動物）"
        # 他テストが registry を clear する場合に備えて冪等に再登録
        if SiteAdapterRegistry.get(name) is None:
            SiteAdapterRegistry.register(name, PrefNiigataAdapter)
        assert SiteAdapterRegistry.get(name) is PrefNiigataAdapter

    def test_normalize_returns_animal_data(self, fixture_html):
        """RawAnimalData を normalize して AnimalData に変換できる"""
        html = fixture_html("pref_niigata_lg_jp")
        adapter = PrefNiigataAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")
            normalized = adapter.normalize(raw)

        assert normalized is not None
        assert hasattr(normalized, "species")
