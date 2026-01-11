"""
KochiAdapter のユニットテスト

高知県自治体サイト向けスクレイピングアダプターのテストです。
モック HTML を使用してスクレイピングロジックを検証します。
"""
import pytest
from unittest.mock import patch, Mock
from bs4 import BeautifulSoup

from src.data_collector.adapters.kochi_adapter import KochiAdapter
from src.data_collector.adapters.municipality_adapter import (
    MunicipalityAdapter,
    NetworkError,
    ParsingError,
)
from src.data_collector.domain.models import RawAnimalData, AnimalData


# モック HTML データ
MOCK_LIST_PAGE_HTML = """
<!DOCTYPE html>
<html>
<head><title>保護動物一覧</title></head>
<body>
    <div class="animal-list">
        <div class="animal-item">
            <a href="/animals/detail/001">個体1</a>
        </div>
        <div class="animal-item">
            <a href="/animals/detail/002">個体2</a>
        </div>
        <div class="animal-item">
            <a href="/animals/detail/003">個体3</a>
        </div>
    </div>
</body>
</html>
"""

MOCK_DETAIL_PAGE_HTML = """
<!DOCTYPE html>
<html>
<head><title>個体詳細</title></head>
<body>
    <div class="animal-detail">
        <table class="info-table">
            <tr><th>動物種別</th><td class="species">犬</td></tr>
            <tr><th>性別</th><td class="sex">オス</td></tr>
            <tr><th>推定年齢</th><td class="age">2歳</td></tr>
            <tr><th>毛色</th><td class="color">茶色</td></tr>
            <tr><th>体格</th><td class="size">中型</td></tr>
            <tr><th>収容日</th><td class="shelter-date">令和8年1月5日</td></tr>
            <tr><th>収容場所</th><td class="location">高知県動物愛護センター</td></tr>
            <tr><th>問い合わせ先</th><td class="phone">088-123-4567</td></tr>
        </table>
        <div class="images">
            <img src="/images/animal001_1.jpg" alt="画像1">
            <img src="/images/animal001_2.jpg" alt="画像2">
        </div>
    </div>
</body>
</html>
"""

MOCK_INVALID_STRUCTURE_HTML = """
<!DOCTYPE html>
<html>
<head><title>不正なページ</title></head>
<body>
    <p>ページ構造が変更されました</p>
</body>
</html>
"""


class TestKochiAdapterInitialization:
    """KochiAdapter 初期化のテスト"""

    def test_kochi_adapter_inherits_municipality_adapter(self):
        """KochiAdapter は MunicipalityAdapter を継承すること"""
        assert issubclass(KochiAdapter, MunicipalityAdapter)

    def test_kochi_adapter_initialization(self):
        """KochiAdapter が正しく初期化されること"""
        adapter = KochiAdapter()
        assert adapter.prefecture_code == "39"
        assert adapter.municipality_name == "高知県"

    def test_kochi_adapter_has_base_url(self):
        """KochiAdapter は BASE_URL を持つこと"""
        assert hasattr(KochiAdapter, "BASE_URL")
        assert KochiAdapter.BASE_URL is not None


class TestKochiAdapterPageValidation:
    """ページ構造検証のテスト"""

    def test_validate_page_structure_valid(self):
        """有効なページ構造を検証できること"""
        adapter = KochiAdapter()
        soup = BeautifulSoup(MOCK_LIST_PAGE_HTML, "html.parser")
        expected_selectors = [".animal-list", ".animal-item"]

        result = adapter._validate_page_structure(soup, expected_selectors)
        assert result is True

    def test_validate_page_structure_invalid(self):
        """無効なページ構造を検出できること"""
        adapter = KochiAdapter()
        soup = BeautifulSoup(MOCK_INVALID_STRUCTURE_HTML, "html.parser")
        expected_selectors = [".animal-list", ".animal-item"]

        result = adapter._validate_page_structure(soup, expected_selectors)
        assert result is False

    def test_validate_page_structure_partial_match(self):
        """一部のセレクターのみマッチする場合は False を返すこと"""
        adapter = KochiAdapter()
        soup = BeautifulSoup(MOCK_LIST_PAGE_HTML, "html.parser")
        # .non-existent は存在しない
        expected_selectors = [".animal-list", ".non-existent"]

        result = adapter._validate_page_structure(soup, expected_selectors)
        assert result is False


class TestKochiAdapterFetchAnimalList:
    """一覧ページスクレイピングのテスト"""

    @patch("src.data_collector.adapters.kochi_adapter.requests.get")
    def test_fetch_animal_list_success(self, mock_get):
        """一覧ページから URL リストを取得できること"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = MOCK_LIST_PAGE_HTML
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        adapter = KochiAdapter()
        urls = adapter.fetch_animal_list()

        assert len(urls) == 3
        # 相対パスが絶対 URL に変換されていること
        assert all(url.startswith("http") for url in urls)

    @patch("src.data_collector.adapters.kochi_adapter.requests.get")
    def test_fetch_animal_list_network_error(self, mock_get):
        """ネットワークエラー時に NetworkError をスローすること"""
        import requests

        mock_get.side_effect = requests.exceptions.RequestException("接続エラー")

        adapter = KochiAdapter()
        with pytest.raises(NetworkError) as exc_info:
            adapter.fetch_animal_list()
        assert "接続エラー" in str(exc_info.value) or exc_info.value.url is not None

    @patch("src.data_collector.adapters.kochi_adapter.requests.get")
    def test_fetch_animal_list_http_error(self, mock_get):
        """HTTP エラー時に NetworkError をスローすること"""
        import requests

        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "500 Server Error"
        )
        mock_get.return_value = mock_response

        adapter = KochiAdapter()
        with pytest.raises(NetworkError) as exc_info:
            adapter.fetch_animal_list()
        assert exc_info.value.status_code == 500

    @patch("src.data_collector.adapters.kochi_adapter.requests.get")
    def test_fetch_animal_list_parsing_error(self, mock_get):
        """ページ構造が変更された場合に ParsingError をスローすること"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = MOCK_INVALID_STRUCTURE_HTML
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        adapter = KochiAdapter()
        with pytest.raises(ParsingError):
            adapter.fetch_animal_list()


class TestKochiAdapterExtractAnimalDetails:
    """詳細ページスクレイピングのテスト"""

    @patch("src.data_collector.adapters.kochi_adapter.requests.get")
    def test_extract_animal_details_success(self, mock_get):
        """詳細ページから動物情報を抽出できること"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = MOCK_DETAIL_PAGE_HTML
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        adapter = KochiAdapter()
        raw_data = adapter.extract_animal_details("https://example.com/animals/detail/001")

        assert isinstance(raw_data, RawAnimalData)
        assert raw_data.species == "犬"
        assert raw_data.sex == "オス"
        assert raw_data.age == "2歳"
        assert raw_data.color == "茶色"
        assert raw_data.size == "中型"
        assert raw_data.shelter_date == "令和8年1月5日"
        assert raw_data.location == "高知県動物愛護センター"
        assert raw_data.phone == "088-123-4567"
        assert len(raw_data.image_urls) == 2
        assert raw_data.source_url == "https://example.com/animals/detail/001"

    @patch("src.data_collector.adapters.kochi_adapter.requests.get")
    def test_extract_animal_details_network_error(self, mock_get):
        """ネットワークエラー時に NetworkError をスローすること"""
        import requests

        mock_get.side_effect = requests.exceptions.RequestException("接続エラー")

        adapter = KochiAdapter()
        with pytest.raises(NetworkError):
            adapter.extract_animal_details("https://example.com/animals/detail/001")

    @patch("src.data_collector.adapters.kochi_adapter.requests.get")
    def test_extract_animal_details_parsing_error(self, mock_get):
        """ページ構造が変更された場合に ParsingError をスローすること"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = MOCK_INVALID_STRUCTURE_HTML
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        adapter = KochiAdapter()
        with pytest.raises(ParsingError):
            adapter.extract_animal_details("https://example.com/animals/detail/001")

    @patch("src.data_collector.adapters.kochi_adapter.requests.get")
    def test_extract_animal_details_image_url_conversion(self, mock_get):
        """画像の相対 URL が絶対 URL に変換されること"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = MOCK_DETAIL_PAGE_HTML
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        adapter = KochiAdapter()
        raw_data = adapter.extract_animal_details("https://example.com/animals/detail/001")

        # 相対パスが絶対 URL に変換されていること
        for url in raw_data.image_urls:
            assert url.startswith("http")

    @patch("src.data_collector.adapters.kochi_adapter.requests.get")
    def test_extract_animal_details_no_images(self, mock_get):
        """画像がない場合は空配列を返すこと"""
        html_no_images = """
        <!DOCTYPE html>
        <html>
        <body>
            <div class="animal-detail">
                <table class="info-table">
                    <tr><th>動物種別</th><td class="species">猫</td></tr>
                    <tr><th>性別</th><td class="sex">メス</td></tr>
                    <tr><th>推定年齢</th><td class="age">1歳</td></tr>
                    <tr><th>毛色</th><td class="color">白</td></tr>
                    <tr><th>体格</th><td class="size">小型</td></tr>
                    <tr><th>収容日</th><td class="shelter-date">2026/01/10</td></tr>
                    <tr><th>収容場所</th><td class="location">センター</td></tr>
                    <tr><th>問い合わせ先</th><td class="phone">088-111-2222</td></tr>
                </table>
                <div class="images">
                </div>
            </div>
        </body>
        </html>
        """
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = html_no_images
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        adapter = KochiAdapter()
        raw_data = adapter.extract_animal_details("https://example.com/animals/detail/002")

        assert raw_data.image_urls == []


class TestKochiAdapterNormalize:
    """正規化統合のテスト"""

    def test_normalize_raw_data(self):
        """RawAnimalData を AnimalData に正規化できること"""
        adapter = KochiAdapter()
        raw_data = RawAnimalData(
            species="犬",
            sex="オス",
            age="2歳",
            color="茶色",
            size="中型",
            shelter_date="令和8年1月5日",
            location="高知県動物愛護センター",
            phone="0881234567",
            image_urls=["https://example.com/image1.jpg"],
            source_url="https://example.com/animals/001",
        )

        animal_data = adapter.normalize(raw_data)

        assert isinstance(animal_data, AnimalData)
        assert animal_data.species == "犬"
        assert animal_data.sex == "男の子"
        assert animal_data.age_months == 24


class TestKochiAdapterIntegration:
    """KochiAdapter 統合テスト"""

    @patch("src.data_collector.adapters.kochi_adapter.requests.get")
    def test_full_scraping_flow(self, mock_get):
        """一覧取得→詳細取得→正規化の完全フローをテスト"""

        def mock_response(url, **kwargs):
            response = Mock()
            response.status_code = 200
            response.raise_for_status = Mock()

            if "detail" in url:
                response.text = MOCK_DETAIL_PAGE_HTML
            else:
                response.text = MOCK_LIST_PAGE_HTML
            return response

        mock_get.side_effect = mock_response

        adapter = KochiAdapter()

        # 一覧取得
        urls = adapter.fetch_animal_list()
        assert len(urls) == 3

        # 詳細取得と正規化
        for url in urls:
            raw_data = adapter.extract_animal_details(url)
            animal_data = adapter.normalize(raw_data)
            assert isinstance(animal_data, AnimalData)
