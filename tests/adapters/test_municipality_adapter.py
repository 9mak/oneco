"""
MunicipalityAdapter 抽象基底クラスのユニットテスト

アダプターの抽象インターフェースとカスタム例外クラスをテストします。
"""
import pytest
from abc import ABC

from src.data_collector.adapters.municipality_adapter import (
    MunicipalityAdapter,
    NetworkError,
    ParsingError,
)
from src.data_collector.domain.models import RawAnimalData, AnimalData


class TestMunicipalityAdapterInterface:
    """MunicipalityAdapter 抽象基底クラスのテスト"""

    def test_municipality_adapter_is_abstract(self):
        """MunicipalityAdapter は抽象クラスであること"""
        assert issubclass(MunicipalityAdapter, ABC)

    def test_municipality_adapter_cannot_be_instantiated(self):
        """MunicipalityAdapter は直接インスタンス化できないこと"""
        with pytest.raises(TypeError):
            MunicipalityAdapter("39", "高知県")

    def test_municipality_adapter_has_abstract_methods(self):
        """MunicipalityAdapter は抽象メソッドを持つこと"""
        # fetch_animal_list, extract_animal_details, normalize が抽象メソッド
        assert hasattr(MunicipalityAdapter, "fetch_animal_list")
        assert hasattr(MunicipalityAdapter, "extract_animal_details")
        assert hasattr(MunicipalityAdapter, "normalize")


class TestConcreteAdapter:
    """具象アダプター実装のテスト"""

    def test_concrete_adapter_initialization(self):
        """具象アダプターが正しく初期化されること"""

        class TestAdapter(MunicipalityAdapter):
            def fetch_animal_list(self):
                return []

            def extract_animal_details(self, detail_url: str):
                return RawAnimalData(
                    species="犬",
                    sex="オス",
                    age="2歳",
                    color="茶色",
                    size="中型",
                    shelter_date="2026-01-05",
                    location="センター",
                    phone="088-123-4567",
                    image_urls=[],
                    source_url=detail_url,
                )

            def normalize(self, raw_data: RawAnimalData):
                from src.data_collector.domain.normalizer import DataNormalizer

                return DataNormalizer.normalize(raw_data)

        adapter = TestAdapter("39", "高知県")
        assert adapter.prefecture_code == "39"
        assert adapter.municipality_name == "高知県"

    def test_concrete_adapter_fetch_animal_list(self):
        """具象アダプターの fetch_animal_list が呼び出せること"""

        class TestAdapter(MunicipalityAdapter):
            def fetch_animal_list(self):
                return ["https://example.com/1", "https://example.com/2"]

            def extract_animal_details(self, detail_url: str):
                return RawAnimalData(
                    species="犬",
                    sex="オス",
                    age="2歳",
                    color="茶色",
                    size="中型",
                    shelter_date="2026-01-05",
                    location="センター",
                    phone="088-123-4567",
                    image_urls=[],
                    source_url=detail_url,
                )

            def normalize(self, raw_data: RawAnimalData):
                from src.data_collector.domain.normalizer import DataNormalizer

                return DataNormalizer.normalize(raw_data)

        adapter = TestAdapter("39", "高知県")
        urls = adapter.fetch_animal_list()
        assert len(urls) == 2
        assert urls[0] == "https://example.com/1"


class TestNetworkError:
    """NetworkError カスタム例外のテスト"""

    def test_network_error_inheritance(self):
        """NetworkError は Exception を継承すること"""
        assert issubclass(NetworkError, Exception)

    def test_network_error_with_message(self):
        """NetworkError はメッセージを持てること"""
        error = NetworkError("HTTP 500 エラー")
        assert str(error) == "HTTP 500 エラー"

    def test_network_error_with_url_and_status_code(self):
        """NetworkError は URL とステータスコードを保持できること"""
        error = NetworkError("HTTP エラー", url="https://example.com", status_code=503)
        assert error.url == "https://example.com"
        assert error.status_code == 503

    def test_network_error_raise_and_catch(self):
        """NetworkError を raise して catch できること"""
        with pytest.raises(NetworkError) as exc_info:
            raise NetworkError("接続タイムアウト", url="https://example.com")
        assert "接続タイムアウト" in str(exc_info.value)


class TestParsingError:
    """ParsingError カスタム例外のテスト"""

    def test_parsing_error_inheritance(self):
        """ParsingError は Exception を継承すること"""
        assert issubclass(ParsingError, Exception)

    def test_parsing_error_with_message(self):
        """ParsingError はメッセージを持てること"""
        error = ParsingError("HTML 構造が変更されました")
        assert str(error) == "HTML 構造が変更されました"

    def test_parsing_error_with_selector(self):
        """ParsingError はセレクター情報を保持できること"""
        error = ParsingError(
            "セレクターが見つかりません",
            selector=".animal-list",
            url="https://example.com/animals",
        )
        assert error.selector == ".animal-list"
        assert error.url == "https://example.com/animals"

    def test_parsing_error_raise_and_catch(self):
        """ParsingError を raise して catch できること"""
        with pytest.raises(ParsingError) as exc_info:
            raise ParsingError("期待されるセレクターが存在しません", selector=".detail")
        assert "期待されるセレクター" in str(exc_info.value)
