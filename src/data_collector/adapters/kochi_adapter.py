"""
高知県アダプター

高知県自治体サイトから保護動物情報をスクレイピングするアダプターです。
"""

from typing import List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .municipality_adapter import MunicipalityAdapter, NetworkError, ParsingError
from ..domain.models import RawAnimalData, AnimalData
from ..domain.normalizer import DataNormalizer


class KochiAdapter(MunicipalityAdapter):
    """
    高知県自治体サイト向けスクレイピング実装

    高知県の保護動物情報サイトから犬猫の情報を収集し、
    統一スキーマに変換します。
    """

    # 高知県の保護動物情報ページ（実際の URL に置換が必要）
    BASE_URL = "https://example-kochi-prefecture.jp/animals"

    # HTTP リクエストヘッダー
    HEADERS = {
        "User-Agent": "PetRescueApp/1.0 (+https://example.com/about)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en;q=0.5",
    }

    # リクエストタイムアウト（秒）
    TIMEOUT = 30

    # 一覧ページの期待されるセレクター
    LIST_PAGE_SELECTORS = [".animal-list", ".animal-item"]

    # 詳細ページの期待されるセレクター
    DETAIL_PAGE_SELECTORS = [".animal-detail", ".info-table"]

    def __init__(self):
        """高知県アダプターを初期化"""
        super().__init__(prefecture_code="39", municipality_name="高知県")

    def fetch_animal_list(self) -> List[str]:
        """
        高知県の一覧ページから個体詳細 URL リストを抽出

        Returns:
            List[str]: 個体詳細ページの絶対 URL リスト

        Raises:
            NetworkError: HTTP エラー発生時
            ParsingError: HTML 構造が想定と異なる時
        """
        try:
            response = requests.get(
                self.BASE_URL,
                headers=self.HEADERS,
                timeout=self.TIMEOUT,
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise NetworkError(
                f"HTTP エラー: {e}",
                url=self.BASE_URL,
                status_code=response.status_code if response else None,
            )
        except requests.exceptions.RequestException as e:
            raise NetworkError(
                f"ネットワークエラー: {e}",
                url=self.BASE_URL,
            )

        soup = BeautifulSoup(response.text, "html.parser")

        # ページ構造検証
        if not self._validate_page_structure(soup, self.LIST_PAGE_SELECTORS):
            raise ParsingError(
                "一覧ページの構造が変更されています",
                selector=", ".join(self.LIST_PAGE_SELECTORS),
                url=self.BASE_URL,
            )

        # リンク抽出
        urls = []
        animal_items = soup.select(".animal-item a")
        for link in animal_items:
            href = link.get("href")
            if href:
                # 相対パスを絶対 URL に変換
                absolute_url = urljoin(self.BASE_URL, href)
                urls.append(absolute_url)

        return urls

    def extract_animal_details(self, detail_url: str) -> RawAnimalData:
        """
        高知県の詳細ページから動物情報を抽出

        Args:
            detail_url: 個体詳細ページの URL

        Returns:
            RawAnimalData: 抽出した生データ

        Raises:
            NetworkError: HTTP エラー発生時
            ParsingError: HTML 構造が想定と異なる時
        """
        try:
            response = requests.get(
                detail_url,
                headers=self.HEADERS,
                timeout=self.TIMEOUT,
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise NetworkError(
                f"HTTP エラー: {e}",
                url=detail_url,
                status_code=response.status_code if response else None,
            )
        except requests.exceptions.RequestException as e:
            raise NetworkError(
                f"ネットワークエラー: {e}",
                url=detail_url,
            )

        soup = BeautifulSoup(response.text, "html.parser")

        # ページ構造検証
        if not self._validate_page_structure(soup, self.DETAIL_PAGE_SELECTORS):
            raise ParsingError(
                "詳細ページの構造が変更されています",
                selector=", ".join(self.DETAIL_PAGE_SELECTORS),
                url=detail_url,
            )

        # データ抽出
        species = self._extract_text(soup, ".species")
        sex = self._extract_text(soup, ".sex")
        age = self._extract_text(soup, ".age")
        color = self._extract_text(soup, ".color")
        size = self._extract_text(soup, ".size")
        shelter_date = self._extract_text(soup, ".shelter-date")
        location = self._extract_text(soup, ".location")
        phone = self._extract_text(soup, ".phone")

        # 画像 URL 抽出
        image_urls = self._extract_image_urls(soup, detail_url)

        return RawAnimalData(
            species=species,
            sex=sex,
            age=age,
            color=color,
            size=size,
            shelter_date=shelter_date,
            location=location,
            phone=phone,
            image_urls=image_urls,
            source_url=detail_url,
        )

    def normalize(self, raw_data: RawAnimalData) -> AnimalData:
        """
        生データを統一スキーマに正規化

        DataNormalizer に処理を委譲します。

        Args:
            raw_data: 自治体サイトから抽出した生データ

        Returns:
            AnimalData: 正規化済みデータ
        """
        return DataNormalizer.normalize(raw_data)

    def _validate_page_structure(
        self, soup: BeautifulSoup, expected_selectors: List[str]
    ) -> bool:
        """
        ページ構造が想定通りか検証

        Args:
            soup: BeautifulSoup オブジェクト
            expected_selectors: 期待される CSS セレクターリスト

        Returns:
            bool: すべてのセレクターが存在すれば True
        """
        for selector in expected_selectors:
            if not soup.select_one(selector):
                return False
        return True

    def _extract_text(self, soup: BeautifulSoup, selector: str) -> str:
        """
        指定されたセレクターからテキストを抽出

        Args:
            soup: BeautifulSoup オブジェクト
            selector: CSS セレクター

        Returns:
            str: 抽出されたテキスト（見つからない場合は空文字列）
        """
        element = soup.select_one(selector)
        if element:
            return element.get_text(strip=True)
        return ""

    def _extract_image_urls(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """
        画像 URL を抽出し、絶対 URL に変換

        Args:
            soup: BeautifulSoup オブジェクト
            base_url: ベース URL（相対パス変換用）

        Returns:
            List[str]: 画像の絶対 URL リスト
        """
        image_urls = []
        images = soup.select(".images img")
        for img in images:
            src = img.get("src")
            if src:
                # 相対パスを絶対 URL に変換
                absolute_url = urljoin(base_url, src)
                image_urls.append(absolute_url)
        return image_urls
