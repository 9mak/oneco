"""RuleBasedAdapter 基底クラスのテスト

Phase A2 Task 1.1: 共通基底クラスの helper の動作を検証する。
abstract メソッド群はサブクラステストで担保。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
import requests
from requests.utils import get_encoding_from_headers

from data_collector.adapters.municipality_adapter import (
    MunicipalityAdapter,
    NetworkError,
)
from data_collector.adapters.rule_based.base import RuleBasedAdapter
from data_collector.domain.models import AnimalData, RawAnimalData
from data_collector.llm.config import SiteConfig

# ─────────────────────────── Test fixtures ───────────────────────────


def _site() -> SiteConfig:
    """テスト用最小限の SiteConfig"""
    return SiteConfig(
        name="テストサイト",
        prefecture="高知県",
        prefecture_code="39",
        list_url="https://example.com/list/",
    )


class _ConcreteAdapter(RuleBasedAdapter):
    """abstract method を実装したテスト用具象クラス"""

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        return []

    def extract_animal_details(self, detail_url: str, category: str = "adoption") -> RawAnimalData:
        raise NotImplementedError

    def normalize(self, raw_data: RawAnimalData) -> AnimalData:
        return super()._default_normalize(raw_data)


# ─────────────────────────── Tests ───────────────────────────


class TestRuleBasedAdapterInheritance:
    def test_inherits_from_municipality_adapter(self):
        """MunicipalityAdapter を継承していること"""
        assert issubclass(RuleBasedAdapter, MunicipalityAdapter)

    def test_concrete_subclass_passes_prefecture_to_super(self):
        """具象サブクラスが super().__init__ に正しく値を渡すこと"""
        adapter = _ConcreteAdapter(_site())
        assert adapter.prefecture_code == "39"
        assert adapter.municipality_name == "テストサイト"

    def test_site_config_stored(self):
        """site_config がインスタンスに保持されていること"""
        site = _site()
        adapter = _ConcreteAdapter(site)
        assert adapter.site_config is site


class TestAbsoluteUrl:
    def test_absolute_url_returns_unchanged_when_already_absolute(self):
        adapter = _ConcreteAdapter(_site())
        result = adapter._absolute_url("https://example.com/page", base="https://other.com/")
        assert result == "https://example.com/page"

    def test_absolute_url_resolves_relative_against_base(self):
        adapter = _ConcreteAdapter(_site())
        result = adapter._absolute_url("/sub/page", base="https://example.com/list/")
        assert result == "https://example.com/sub/page"

    def test_absolute_url_uses_site_list_url_when_base_omitted(self):
        adapter = _ConcreteAdapter(_site())
        result = adapter._absolute_url("detail/1")
        assert result == "https://example.com/list/detail/1"


class TestNormalizePhone:
    def test_extract_hyphenated_phone(self):
        adapter = _ConcreteAdapter(_site())
        assert adapter._normalize_phone("お問い合わせ: 088-826-2364 まで") == "088-826-2364"

    def test_extract_phone_without_hyphens(self):
        adapter = _ConcreteAdapter(_site())
        assert adapter._normalize_phone("0888262364") == "088-826-2364"

    def test_returns_empty_when_no_phone_in_text(self):
        adapter = _ConcreteAdapter(_site())
        assert adapter._normalize_phone("電話番号は不明です") == ""

    def test_handles_empty_input(self):
        adapter = _ConcreteAdapter(_site())
        assert adapter._normalize_phone("") == ""


class TestFilterImageUrls:
    def test_filters_template_paths(self):
        """サイトテンプレート画像 (themes 配下) は除外される"""
        adapter = _ConcreteAdapter(_site())
        urls = [
            "https://example.com/wp-content/themes/foo/logo.png",
            "https://example.com/wp-content/uploads/2026/animal1.jpg",
            "https://example.com/wp-content/uploads/2026/animal2.jpg",
        ]
        result = adapter._filter_image_urls(urls, base_url="https://example.com/")
        assert len(result) == 2
        assert all("/uploads/" in u for u in result)

    def test_returns_originals_when_no_uploads_path(self):
        """uploads 画像が無い場合は元リストを返す（データ消失防止）"""
        adapter = _ConcreteAdapter(_site())
        urls = ["https://example.com/img/animal.jpg"]
        result = adapter._filter_image_urls(urls, base_url="https://example.com/")
        assert result == urls


class TestHttpGet:
    def test_returns_text_on_success(self):
        adapter = _ConcreteAdapter(_site())

        class _MockResp:
            text = "<html>ok</html>"
            status_code = 200
            headers = {"Content-Type": "text/html; charset=utf-8"}

            def raise_for_status(self):
                pass

        with patch("requests.get", return_value=_MockResp()) as mock_get:
            result = adapter._http_get("https://example.com/")
            assert result == "<html>ok</html>"
            mock_get.assert_called_once()

    def test_raises_network_error_on_http_error(self):
        adapter = _ConcreteAdapter(_site())

        with patch(
            "requests.get",
            side_effect=requests.exceptions.HTTPError("500 Server Error"),
        ):
            with pytest.raises(NetworkError):
                adapter._http_get("https://example.com/")

    def test_passes_user_agent_header(self):
        adapter = _ConcreteAdapter(_site())

        class _MockResp:
            text = ""
            status_code = 200
            headers = {"Content-Type": "text/html; charset=utf-8"}

            def raise_for_status(self):
                pass

        with patch("requests.get", return_value=_MockResp()) as mock_get:
            adapter._http_get("https://example.com/")
            kwargs = mock_get.call_args.kwargs
            assert "headers" in kwargs
            assert "User-Agent" in kwargs["headers"]

    def test_warns_when_html_size_below_min_threshold(self, caplog):
        """HTTP 200 でも本文が極端に短ければ構造崩壊警告を出す (Task #13)"""
        import logging

        adapter = _ConcreteAdapter(_site())

        class _MockResp:
            text = "x"  # 1 byte
            status_code = 200
            headers = {"Content-Type": "text/html; charset=utf-8"}

            def raise_for_status(self):
                pass

        with patch("requests.get", return_value=_MockResp()):
            with caplog.at_level(logging.WARNING, logger="data_collector.adapters.rule_based.base"):
                adapter._http_get("https://example.com/")
        # 警告ログに "HTML 取得サイズが小さい" が含まれること
        assert any("HTML 取得サイズが小さい" in r.message for r in caplog.records), (
            f"短い HTML で構造崩壊警告が出るべき: {[r.message for r in caplog.records]}"
        )

    def test_no_warning_for_normal_sized_html(self, caplog):
        """通常サイズの HTML では警告が出ない"""
        import logging

        adapter = _ConcreteAdapter(_site())

        class _MockResp:
            text = "<html>" + "x" * 1000 + "</html>"
            status_code = 200
            headers = {"Content-Type": "text/html; charset=utf-8"}

            def raise_for_status(self):
                pass

        with patch("requests.get", return_value=_MockResp()):
            with caplog.at_level(logging.WARNING, logger="data_collector.adapters.rule_based.base"):
                adapter._http_get("https://example.com/")
        assert not any("HTML 取得サイズが小さい" in r.message for r in caplog.records)


class TestHttpGetEncoding:
    """Content-Type ヘッダに charset が無い応答のデコードを検証する。

    requests は charset 未指定の text/* に対し ISO-8859-1 を仮定する
    (RFC 2616 §3.7.1)。<meta charset=...> でしか文字コードを宣言しない
    自治体サイトで日本語が文字化けする回帰を防ぐ。
    """

    @staticmethod
    def _response(body: str, *, source_encoding: str, content_type: str) -> requests.Response:
        resp = requests.Response()
        resp.status_code = 200
        resp._content = body.encode(source_encoding)
        resp.headers["Content-Type"] = content_type
        # requests.get() がヘッダから解決するのと同じ encoding を再現する。
        # charset 未指定の text/* では "ISO-8859-1" が入り、未指定時に
        # encoding=None で apparent_encoding に自動フォールバックする
        # 偽の成功を避ける (実バグを正しく再現する)。
        resp.encoding = get_encoding_from_headers(resp.headers)
        return resp

    def test_decodes_utf8_body_when_header_lacks_charset(self):
        """charset 未指定の UTF-8 本文を文字化けさせず読む (山梨県の実例)"""
        adapter = _ConcreteAdapter(_site())
        body = "<html><body>" + "北杜市高根町清里 メス（避妊） 白、黒、茶 " * 8 + "</body></html>"
        resp = self._response(body, source_encoding="utf-8", content_type="text/html")

        with patch("requests.get", return_value=resp):
            result = adapter._http_get("https://example.com/")

        assert "北杜市高根町清里" in result
        assert "ç" not in result  # ISO-8859-1 誤デコードの痕跡が無いこと

    def test_decodes_shift_jis_body_when_header_lacks_charset(self):
        """charset 未指定の Shift_JIS 本文も byte 検出で正しく読む"""
        adapter = _ConcreteAdapter(_site())
        body = (
            "<html><body>"
            + "保護されている犬猫の収容情報をお知らせします。譲渡をご希望の方はセンターまでご連絡ください。"
            * 6
            + "</body></html>"
        )
        resp = self._response(body, source_encoding="shift_jis", content_type="text/html")

        with patch("requests.get", return_value=resp):
            result = adapter._http_get("https://example.com/")

        assert "保護されている犬猫の収容情報" in result

    def test_respects_explicit_charset_in_header(self):
        """ヘッダに charset 明示がある場合はそれを尊重する (回帰防止)"""
        adapter = _ConcreteAdapter(_site())
        body = "<html><body>" + "犬猫の里親募集中です。" * 8 + "</body></html>"
        resp = self._response(
            body, source_encoding="utf-8", content_type="text/html; charset=utf-8"
        )

        with patch("requests.get", return_value=resp):
            result = adapter._http_get("https://example.com/")

        assert "犬猫の里親募集中です。" in result


class TestDefaultNormalize:
    def test_delegates_to_data_normalizer(self):
        """_default_normalize は DataNormalizer.normalize に委譲する"""
        adapter = _ConcreteAdapter(_site())
        raw = RawAnimalData(
            species="犬",
            sex="オス",
            age="3歳",
            color="茶",
            size="中型",
            shelter_date="2026-04-01",
            location="高知県",
            phone="088-826-2364",
            image_urls=["https://example.com/img.jpg"],
            source_url="https://example.com/detail/1",
            category="adoption",
        )
        result = adapter.normalize(raw)
        assert isinstance(result, AnimalData)
        assert result.species == "犬"
