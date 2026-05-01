"""LlmAdapter の統合テスト（モックLlmProvider使用）"""

from unittest.mock import MagicMock, patch

import pytest

from src.data_collector.domain.models import RawAnimalData
from src.data_collector.llm.adapter import CollectionStats, LlmAdapter, validate_extraction
from src.data_collector.llm.config import SiteConfig
from src.data_collector.llm.providers.base import (
    ExtractionResult,
    LlmProvider,
    MultiExtractionResult,
)


class MockProvider(LlmProvider):
    """テスト用モックプロバイダー"""

    def __init__(self):
        self.extract_calls = 0
        self.link_calls = 0
        self.multi_calls = 0

    def extract_animal_data(self, html_content, source_url, category):
        self.extract_calls += 1
        return ExtractionResult(
            fields={
                "species": "犬",
                "sex": "オス",
                "age": "約2歳",
                "color": "茶色",
                "size": "中型",
                "shelter_date": "2026-01-15",
                "location": "テスト県テスト市",
                "phone": "088-123-4567",
                "image_urls": ["https://example.com/dog.jpg"],
            },
            input_tokens=1000,
            output_tokens=200,
        )

    def extract_detail_links(self, html_content, base_url):
        self.link_calls += 1
        return [
            "https://example.com/detail/1",
            "https://example.com/detail/2",
        ]

    def extract_multiple_animals(self, content, source_url, category, hint_species=""):
        self.multi_calls += 1
        # 2頭分のデータを返す
        species = hint_species or "犬"
        return MultiExtractionResult(
            animals=[
                {
                    "species": species,
                    "sex": "オス",
                    "age": "R5.11.30",
                    "color": "茶白",
                    "size": "約16kg",
                    "shelter_date": "2026-03-22",
                    "location": "さぬき動物愛護センター",
                    "phone": "",
                    "image_urls": [],
                },
                {
                    "species": species,
                    "sex": "メス",
                    "age": "R6.5.1",
                    "color": "茶",
                    "size": "約14kg",
                    "shelter_date": "2026-03-22",
                    "location": "さぬき動物愛護センター",
                    "phone": "",
                    "image_urls": [],
                },
            ],
            input_tokens=2000,
            output_tokens=400,
        )


@pytest.fixture
def site_config():
    return SiteConfig(
        name="テストサイト",
        prefecture="テスト県",
        prefecture_code="99",
        list_url="https://example.com/list",
        list_link_pattern="a.detail-link",
        category="adoption",
        request_interval=1.0,
    )


@pytest.fixture
def site_config_no_selector():
    return SiteConfig(
        name="テストサイト（セレクターなし）",
        prefecture="テスト県",
        prefecture_code="99",
        list_url="https://example.com/list",
        category="adoption",
        request_interval=1.0,
    )


@pytest.fixture
def mock_provider():
    return MockProvider()


class TestLlmAdapterInit:
    def test_inherits_municipality_adapter(self, site_config, mock_provider):
        adapter = LlmAdapter(site_config=site_config, provider=mock_provider)
        assert adapter.prefecture_code == "99"
        assert adapter.municipality_name == "テストサイト"


class TestFetchAnimalList:
    @patch("src.data_collector.llm.fetcher.requests.get")
    @patch("src.data_collector.llm.adapter.time.sleep")
    def test_with_css_selector(self, mock_sleep, mock_get, site_config, mock_provider):
        mock_response = MagicMock()
        mock_response.text = """
        <html><body>
        <a class="detail-link" href="/detail/1">Dog 1</a>
        <a class="detail-link" href="/detail/2">Dog 2</a>
        <a href="/about">About</a>
        </body></html>
        """
        mock_response.apparent_encoding = "utf-8"
        mock_get.return_value = mock_response

        adapter = LlmAdapter(site_config=site_config, provider=mock_provider)
        result = adapter.fetch_animal_list()

        assert len(result) == 2
        assert result[0] == ("https://example.com/detail/1", "adoption")
        assert result[1] == ("https://example.com/detail/2", "adoption")
        assert mock_provider.link_calls == 0  # LLMは使わない

    @patch("src.data_collector.llm.fetcher.requests.get")
    @patch("src.data_collector.llm.adapter.time.sleep")
    def test_without_selector_uses_llm(
        self, mock_sleep, mock_get, site_config_no_selector, mock_provider
    ):
        mock_response = MagicMock()
        mock_response.text = "<html><body><a href='/detail/1'>Dog</a></body></html>"
        mock_response.apparent_encoding = "utf-8"
        mock_get.return_value = mock_response

        adapter = LlmAdapter(site_config=site_config_no_selector, provider=mock_provider)
        result = adapter.fetch_animal_list()

        assert len(result) == 2
        assert mock_provider.link_calls == 1

    @patch("src.data_collector.llm.fetcher.requests.get")
    @patch("src.data_collector.llm.adapter.time.sleep")
    def test_deduplicates_urls(self, mock_sleep, mock_get, site_config, mock_provider):
        mock_response = MagicMock()
        mock_response.text = """
        <html><body>
        <a class="detail-link" href="/detail/1">Dog 1</a>
        <a class="detail-link" href="/detail/1">Dog 1 again</a>
        </body></html>
        """
        mock_response.apparent_encoding = "utf-8"
        mock_get.return_value = mock_response

        adapter = LlmAdapter(site_config=site_config, provider=mock_provider)
        result = adapter.fetch_animal_list()

        assert len(result) == 1

    @patch("src.data_collector.llm.fetcher.requests.get")
    @patch("src.data_collector.llm.adapter.time.sleep")
    def test_max_pages_limit(self, mock_sleep, mock_get, mock_provider):
        config = SiteConfig(
            name="テスト",
            prefecture="テスト県",
            prefecture_code="99",
            list_url="https://example.com/list",
            list_link_pattern="a.link",
            max_pages=1,
        )
        mock_response = MagicMock()
        mock_response.text = """<html><body>
        <a class="link" href="/detail/1">Dog</a>
        <a href="/list?page=2">次へ</a>
        </body></html>"""
        mock_response.apparent_encoding = "utf-8"
        mock_get.return_value = mock_response

        adapter = LlmAdapter(site_config=config, provider=mock_provider)
        adapter.fetch_animal_list()

        assert mock_get.call_count == 1  # 1ページのみ


class TestExtractAnimalDetails:
    @patch("src.data_collector.llm.fetcher.requests.get")
    @patch("src.data_collector.llm.adapter.time.sleep")
    def test_extracts_and_returns_raw_data(self, mock_sleep, mock_get, site_config, mock_provider):
        mock_response = MagicMock()
        mock_response.text = "<html><body><p>Dog info</p></body></html>"
        mock_response.apparent_encoding = "utf-8"
        mock_get.return_value = mock_response

        adapter = LlmAdapter(site_config=site_config, provider=mock_provider)
        result = adapter.extract_animal_details("https://example.com/detail/1", "adoption")

        assert isinstance(result, RawAnimalData)
        assert result.species == "犬"
        assert result.source_url == "https://example.com/detail/1"
        assert result.category == "adoption"
        assert mock_provider.extract_calls == 1

    @patch("src.data_collector.llm.fetcher.requests.get")
    @patch("src.data_collector.llm.adapter.time.sleep")
    def test_tracks_stats(self, mock_sleep, mock_get, site_config, mock_provider):
        mock_response = MagicMock()
        mock_response.text = "<html><body><p>Dog</p></body></html>"
        mock_response.apparent_encoding = "utf-8"
        mock_get.return_value = mock_response

        adapter = LlmAdapter(site_config=site_config, provider=mock_provider)
        adapter.extract_animal_details("https://example.com/detail/1", "adoption")

        assert adapter.stats.api_calls == 1
        assert adapter.stats.total_input_tokens == 1000
        assert adapter.stats.total_output_tokens == 200


class TestNormalize:
    def test_delegates_to_data_normalizer(self, site_config, mock_provider):
        adapter = LlmAdapter(site_config=site_config, provider=mock_provider)
        raw = RawAnimalData(
            species="犬",
            sex="オス",
            age="2歳",
            color="茶色",
            size="中型",
            shelter_date="2026-01-15",
            location="テスト県テスト市",
            phone="0881234567",
            image_urls=[],
            source_url="https://example.com/detail/1",
            category="adoption",
        )
        result = adapter.normalize(raw)
        assert result.species == "犬"
        assert result.sex == "男の子"


class TestCollectionStats:
    def test_initial_values(self):
        stats = CollectionStats()
        assert stats.api_calls == 0
        assert stats.estimated_cost_usd == 0.0

    def test_record_extraction(self):
        stats = CollectionStats()
        result = ExtractionResult(fields={}, input_tokens=1000, output_tokens=500)
        stats.record_extraction(result)
        assert stats.api_calls == 1
        assert stats.total_input_tokens == 1000
        assert stats.total_output_tokens == 500
        assert stats.estimated_cost_usd > 0

    def test_cost_calculation(self):
        stats = CollectionStats()
        stats.total_input_tokens = 1_000_000
        stats.total_output_tokens = 1_000_000
        # Haiku: $0.25/MTok in + $1.25/MTok out = $1.50
        assert abs(stats.estimated_cost_usd - 1.50) < 0.01


class TestPdfMultiAnimal:
    """pdf_multi_animal フラグによる複数動物抽出テスト"""

    @pytest.fixture
    def multi_site_config(self):
        return SiteConfig(
            name="さぬきテスト",
            prefecture="香川県",
            prefecture_code="37",
            list_url="https://example.com/list",
            pdf_link_pattern="a[href$='.pdf']",
            category="adoption",
            request_interval=1.0,
            pdf_multi_animal=True,
        )

    def _make_mock_fetcher(self, list_html: str, pdf_content: str) -> MagicMock:
        """一覧ページとPDFを返すモックフェッチャーを生成"""
        mock_fetcher = MagicMock()
        mock_fetcher.fetch.side_effect = [list_html, pdf_content]
        return mock_fetcher

    def test_fetch_animal_list_returns_virtual_urls(self, multi_site_config):
        """pdf_multi_animal モードでは仮想URL(#index)のリストを返すこと"""
        list_html = """<html><body>
        <a href="https://example.com/0322dog.pdf">犬PDF</a>
        </body></html>"""
        pdf_text = "<pre>犬一覧表テキスト</pre>"

        mock_fetcher = MagicMock()
        mock_fetcher.fetch.side_effect = [list_html, pdf_text]

        mock_provider = MockProvider()

        with patch("src.data_collector.llm.adapter.time.sleep"):
            adapter = LlmAdapter(
                site_config=multi_site_config,
                provider=mock_provider,
                fetcher=mock_fetcher,
            )
            result = adapter.fetch_animal_list()

        # 2頭分の仮想URLが返ること
        assert len(result) == 2
        assert result[0] == ("https://example.com/0322dog.pdf#0", "adoption")
        assert result[1] == ("https://example.com/0322dog.pdf#1", "adoption")
        # extract_multiple_animals が1回呼ばれること
        assert mock_provider.multi_calls == 1

    def test_species_hint_from_dog_url(self, multi_site_config):
        """dog を含むURLでは hint_species='犬' が渡されること"""
        list_html = """<html><body>
        <a href="https://example.com/0322dog.pdf">犬PDF</a>
        </body></html>"""
        pdf_text = "<pre>dog pdf</pre>"

        mock_fetcher = MagicMock()
        mock_fetcher.fetch.side_effect = [list_html, pdf_text]

        captured = {}

        class CapturingProvider(MockProvider):
            def extract_multiple_animals(self, content, source_url, category, hint_species=""):
                captured["hint_species"] = hint_species
                return super().extract_multiple_animals(content, source_url, category, hint_species)

        with patch("src.data_collector.llm.adapter.time.sleep"):
            adapter = LlmAdapter(
                site_config=multi_site_config,
                provider=CapturingProvider(),
                fetcher=mock_fetcher,
            )
            adapter.fetch_animal_list()

        assert captured["hint_species"] == "犬"

    def test_species_hint_from_cat_url(self, multi_site_config):
        """cat を含むURLでは hint_species='猫' が渡されること"""
        list_html = """<html><body>
        <a href="https://example.com/0322cat.pdf">猫PDF</a>
        </body></html>"""
        pdf_text = "<pre>cat pdf</pre>"

        mock_fetcher = MagicMock()
        mock_fetcher.fetch.side_effect = [list_html, pdf_text]

        captured = {}

        class CapturingProvider(MockProvider):
            def extract_multiple_animals(self, content, source_url, category, hint_species=""):
                captured["hint_species"] = hint_species
                return super().extract_multiple_animals(content, source_url, category, hint_species)

        with patch("src.data_collector.llm.adapter.time.sleep"):
            adapter = LlmAdapter(
                site_config=multi_site_config,
                provider=CapturingProvider(),
                fetcher=mock_fetcher,
            )
            adapter.fetch_animal_list()

        assert captured["hint_species"] == "猫"

    def test_extract_animal_details_from_cache(self, multi_site_config):
        """仮想URLから extract_animal_details でキャッシュ済みデータが返ること"""
        list_html = """<html><body>
        <a href="https://example.com/0322dog.pdf">犬PDF</a>
        </body></html>"""
        pdf_text = "<pre>dog pdf</pre>"

        mock_fetcher = MagicMock()
        mock_fetcher.fetch.side_effect = [list_html, pdf_text]

        mock_provider = MockProvider()

        with patch("src.data_collector.llm.adapter.time.sleep"):
            adapter = LlmAdapter(
                site_config=multi_site_config,
                provider=mock_provider,
                fetcher=mock_fetcher,
            )
            # fetch_animal_list でキャッシュが作られる
            urls = adapter.fetch_animal_list()

            # 仮想URLから個別データを取得
            raw0 = adapter.extract_animal_details(urls[0][0], "adoption")
            raw1 = adapter.extract_animal_details(urls[1][0], "adoption")

        assert isinstance(raw0, RawAnimalData)
        assert isinstance(raw1, RawAnimalData)
        assert raw0.sex == "オス"
        assert raw1.sex == "メス"
        assert raw0.species == "犬"
        assert raw1.species == "犬"
        # キャッシュヒットのため extract_multiple_animals は1回だけ呼ばれること
        assert mock_provider.multi_calls == 1

    def test_pdf_not_refetched_for_second_animal(self, multi_site_config):
        """同じPDFから2頭目を取得する際にPDFを再ダウンロードしないこと"""
        list_html = """<html><body>
        <a href="https://example.com/0322dog.pdf">犬PDF</a>
        </body></html>"""
        pdf_text = "<pre>dog pdf</pre>"

        mock_fetcher = MagicMock()
        mock_fetcher.fetch.side_effect = [list_html, pdf_text]

        with patch("src.data_collector.llm.adapter.time.sleep"):
            adapter = LlmAdapter(
                site_config=multi_site_config,
                provider=MockProvider(),
                fetcher=mock_fetcher,
            )
            urls = adapter.fetch_animal_list()
            adapter.extract_animal_details(urls[0][0], "adoption")
            adapter.extract_animal_details(urls[1][0], "adoption")

        # fetch は一覧ページ1回 + PDF1回 = 合計2回のみ
        assert mock_fetcher.fetch.call_count == 2

    def test_stats_updated_after_multi_extraction(self, multi_site_config):
        """複数動物抽出後にstatsが正しく更新されること"""
        list_html = """<html><body>
        <a href="https://example.com/0322dog.pdf">犬PDF</a>
        </body></html>"""
        pdf_text = "<pre>dog pdf</pre>"

        mock_fetcher = MagicMock()
        mock_fetcher.fetch.side_effect = [list_html, pdf_text]

        with patch("src.data_collector.llm.adapter.time.sleep"):
            adapter = LlmAdapter(
                site_config=multi_site_config,
                provider=MockProvider(),
                fetcher=mock_fetcher,
            )
            adapter.fetch_animal_list()

        assert adapter.stats.api_calls == 1
        assert adapter.stats.total_input_tokens == 2000
        assert adapter.stats.total_output_tokens == 400


class TestValidateExtraction:
    def test_valid_fields(self):
        fields = {"species": "犬", "shelter_date": "2026-01-15"}
        errors = validate_extraction(fields)
        assert errors == []

    def test_missing_species(self):
        fields = {"species": "", "shelter_date": "2026-01-15"}
        errors = validate_extraction(fields)
        assert "species" in errors[0]

    def test_missing_shelter_date(self):
        fields = {"species": "犬", "shelter_date": ""}
        errors = validate_extraction(fields)
        assert "shelter_date" in errors[0]

    def test_missing_both(self):
        fields = {}
        errors = validate_extraction(fields)
        assert len(errors) == 2
