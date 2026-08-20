"""ワンニャピアあきた adapter テスト

かつて JS 必須サイトとして常に空リストを返す実装だったが、現行サイトは
静的 HTML に一覧リンク・詳細フィールドを出力している (2026-08-19 T046 で確認)。
実サイト取得の fixture (一覧・詳細) で通常抽出フローを検証し、
旧 JS シェル時代の fixture では安全に 0 件へ落ちることも保証する。
"""

from __future__ import annotations

from unittest.mock import patch

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.wannyapia_akita import (
    WannyapiaAkitaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site(species: str = "犬") -> SiteConfig:
    return SiteConfig(
        name=f"ワンニャピアあきた（譲渡{species}）",
        prefecture="秋田県",
        prefecture_code="05",
        list_url=f"https://wannyapia.akita.jp/pages/protective-{'dogs' if species == '犬' else 'cats'}",
        list_link_pattern="a[href*='/pages/animals/']",
        category="adoption",
    )


class TestFetchAnimalList:
    def test_extracts_detail_urls_from_live_fixture(self, fixture_html):
        """実サイト取得の一覧 fixture から 9 件の詳細 URL を抽出する"""
        adapter = WannyapiaAkitaAdapter(_site("猫"))
        html = fixture_html("wannyapia_akita__cats_list")
        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        urls = [u for u, _cat in result]
        assert len(urls) == 9
        assert "https://wannyapia.akita.jp/pages/animals/p2085" in urls
        assert all(cat == "adoption" for _u, cat in result)

    def test_js_shell_era_fixture_falls_back_to_empty(self, fixture_html):
        """旧 JS シェル時代の fixture (リンク無し) では安全に 0 件を返す"""
        adapter = WannyapiaAkitaAdapter(_site("犬"))
        html = fixture_html("wannyapia_akita")
        with patch.object(adapter, "_http_get", return_value=html):
            assert adapter.fetch_animal_list() == []


class TestExtractAnimalDetails:
    def test_extracts_fields_from_live_fixture(self, fixture_html, assert_raw_animal):
        """実サイト取得の詳細 fixture (むつ・26-131) からフィールドを抽出する"""
        adapter = WannyapiaAkitaAdapter(_site("猫"))
        html = fixture_html("wannyapia_akita__detail")
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(
                "https://wannyapia.akita.jp/pages/animals/p2085",
                category="adoption",
            )

        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            # 「種類: 雑種（ミックス）」では犬猫判定できないため list_url から補完
            species="猫",
            sex="メス",
            age="2歳～5歳",
            color="バイカラー",
            # 体格フィールドは無く「体重: 約2.7㎏」のみ。_cap_size は体格語の
            # 無い体重表記を None に捨てるため adapter 側で体格語へ変換する
            size="小型",
            # 収容日フィールドは存在しない
            shelter_date="",
            # 収容場所フィールドが無いためセンター名を注入
            location="秋田県動物愛護センター",
            # 「連絡先」は施設名のみのため代表電話を注入
            phone="018-827-5051",
            source_url="https://wannyapia.akita.jp/pages/animals/p2085",
            category="adoption",
        )
        assert raw.name == "むつ"
        assert raw.management_number == "26-131"
        assert raw.breed == "雑種（ミックス）"

    def test_images_are_animal_uploads_only(self, fixture_html):
        """動物写真 (/uploads/contents/animals_...) のみ拾い、装飾画像は混ぜない"""
        adapter = WannyapiaAkitaAdapter(_site("猫"))
        html = fixture_html("wannyapia_akita__detail")
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details("https://wannyapia.akita.jp/pages/animals/p2085")
        assert len(raw.image_urls) >= 1
        assert all("/uploads/contents/animals" in u for u in raw.image_urls)

    def test_personal_phone_kept_when_number_present(self):
        """「連絡先」に電話番号が含まれるときは代表電話で上書きしない"""
        html = """
        <html><body>
          <div class="page-header"><h1>テスト</h1></div>
          <table>
            <tr><th>種類</th><td>雑種</td><th>性別</th><td>オス</td></tr>
            <tr><th>連絡先</th><td>018-000-1234</td></tr>
          </table>
        </body></html>
        """
        adapter = WannyapiaAkitaAdapter(_site("犬"))
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details("https://wannyapia.akita.jp/pages/animals/p9999")
        assert raw.phone == "018-000-1234"


class TestWeightToSize:
    """体重表記 → 体格語変換 (reviewer F-01 対応)

    DataNormalizer._cap_size は体格語の無い純粋な体重表記を None に捨てるため、
    adapter 側で oita_aigo / city_kashiwa と同じ 5kg/15kg 境界で変換する。
    """

    def test_boundaries(self):
        assert WannyapiaAkitaAdapter._weight_to_size("約2.7㎏") == "小型"
        assert WannyapiaAkitaAdapter._weight_to_size("4.9kg") == "小型"
        assert WannyapiaAkitaAdapter._weight_to_size("5kg") == "中型"
        assert WannyapiaAkitaAdapter._weight_to_size("14.9kg") == "中型"
        assert WannyapiaAkitaAdapter._weight_to_size("15kg") == "大型"
        assert WannyapiaAkitaAdapter._weight_to_size("") == ""
        assert WannyapiaAkitaAdapter._weight_to_size("不明") == ""
        # 既に体格語を含む表記は温存
        assert WannyapiaAkitaAdapter._weight_to_size("中型（10kg）") == "中型（10kg）"

    def test_size_survives_normalizer(self, fixture_html):
        """adapter.normalize まで通した後も size が捨てられないこと (正規化後検証)"""
        adapter = WannyapiaAkitaAdapter(_site("猫"))
        html = fixture_html("wannyapia_akita__detail")
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(
                "https://wannyapia.akita.jp/pages/animals/p2085",
                category="adoption",
            )
        animal = adapter.normalize(raw)
        assert animal.size == "小型"


class TestRegistry:
    def test_two_sites_registered(self):
        assert SiteAdapterRegistry.get("ワンニャピアあきた（譲渡犬）") is WannyapiaAkitaAdapter
        assert SiteAdapterRegistry.get("ワンニャピアあきた（譲渡猫）") is WannyapiaAkitaAdapter
