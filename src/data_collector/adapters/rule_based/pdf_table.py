"""PdfTableAdapter - PDF 形式サイト用の汎用基底

香川県動物愛護センター、茨城県等の PDF 公開型サイトに対応。
1. 一覧ページから PDF リンクを抽出
2. 各 PDF をダウンロード
3. pdfplumber でテキスト抽出
4. サブクラスの `_parse_pdf_text` で複数動物 dict に分割
5. fetch_animal_list は仮想 URL (`<pdf_url>#row=N`) を返す
"""

from __future__ import annotations

import io
from typing import ClassVar

import requests
from bs4 import BeautifulSoup

from ...domain.models import AnimalData, RawAnimalData
from ..municipality_adapter import NetworkError, ParsingError
from .base import RuleBasedAdapter

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    pdfplumber = None  # type: ignore[assignment]


class PdfTableAdapter(RuleBasedAdapter):
    """PDF 抽出の rule-based 共通基底

    派生クラスは下記を定義する:
    - `PDF_LINK_SELECTOR`: 一覧ページから PDF リンクを取る CSS セレクタ
    - `_parse_pdf_text(pdf_text: str) -> list[dict]`:
      抽出 PDF テキストを動物 dict のリストに分割するメソッド
    """

    PDF_LINK_SELECTOR: ClassVar[str] = ""
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    def __init__(self, site_config) -> None:
        super().__init__(site_config)
        # PDF URL -> animal records cache
        self._pdf_cache: dict[str, list[dict]] = {}

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        abstracts = getattr(cls, "__abstractmethods__", frozenset())
        if not abstracts and not cls.PDF_LINK_SELECTOR:
            raise TypeError(f"{cls.__name__} must define PDF_LINK_SELECTOR class variable")

    # ─────────────────── MunicipalityAdapter 実装 ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        list_html = self._http_get(self.site_config.list_url)
        soup = BeautifulSoup(list_html, "html.parser")
        pdf_links = soup.select(self.PDF_LINK_SELECTOR)
        if not pdf_links:
            raise ParsingError(
                "PDF リンクが見つかりません",
                selector=self.PDF_LINK_SELECTOR,
                url=self.site_config.list_url,
            )

        urls: list[tuple[str, str]] = []
        category = self.site_config.category
        for link in pdf_links:
            href = link.get("href")
            if not href or not isinstance(href, str):
                continue
            pdf_url = self._absolute_url(href)
            records = self._load_pdf_records(pdf_url)
            for i in range(len(records)):
                urls.append((f"{pdf_url}#row={i}", category))
        return urls

    def extract_animal_details(self, virtual_url: str, category: str = "adoption") -> RawAnimalData:
        # virtual_url: "https://.../foo.pdf#row=N"
        if "#row=" not in virtual_url:
            raise ParsingError(f"無効な仮想 URL: {virtual_url}", url=virtual_url)
        pdf_url, row_part = virtual_url.split("#row=", 1)
        idx = int(row_part)

        records = self._load_pdf_records(pdf_url)
        if idx >= len(records):
            raise ParsingError(
                f"row index {idx} out of range (total {len(records)})",
                url=virtual_url,
            )
        record = records[idx]

        try:
            return RawAnimalData(
                species=record.get("species", ""),
                sex=record.get("sex", ""),
                age=record.get("age", ""),
                color=record.get("color", ""),
                size=record.get("size", ""),
                shelter_date=record.get("shelter_date", self.SHELTER_DATE_DEFAULT),
                location=record.get("location", ""),
                phone=self._normalize_phone(record.get("phone", "")),
                image_urls=record.get("image_urls", []),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    def normalize(self, raw_data: RawAnimalData) -> AnimalData:
        return self._default_normalize(raw_data)

    # ─────────────────── 抽象 (サブクラスで定義) ───────────────────

    def _parse_pdf_text(self, pdf_text: str) -> list[dict]:
        """PDF 抽出テキストから動物 dict のリストを返す（サブクラスで実装）"""
        raise NotImplementedError("subclass must implement _parse_pdf_text")

    # ─────────────────── ヘルパー ───────────────────

    def _load_pdf_records(self, pdf_url: str) -> list[dict]:
        """PDF をダウンロード→テキスト抽出→パースしてキャッシュ"""
        if pdf_url in self._pdf_cache:
            return self._pdf_cache[pdf_url]

        pdf_bytes = self._download_pdf(pdf_url)
        pdf_text = self._extract_pdf_text(pdf_bytes)
        records = self._parse_pdf_text(pdf_text)
        self._pdf_cache[pdf_url] = records
        return records

    def _download_pdf(self, url: str) -> bytes:
        try:
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            return response.content
        except requests.RequestException as e:
            raise NetworkError(f"PDF ダウンロード失敗: {e}", url=url) from e

    def _extract_pdf_text(self, pdf_bytes: bytes) -> str:
        if pdfplumber is None:  # pragma: no cover
            raise NetworkError("pdfplumber が利用不可")
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                pages = []
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        pages.append(text)
                return "\n\n".join(pages)
        except Exception as e:
            raise ParsingError(f"PDF テキスト抽出失敗: {e}") from e
