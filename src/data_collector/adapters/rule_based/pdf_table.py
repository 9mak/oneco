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
from ..politeness import ONECO_USER_AGENT
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

    # PDF ダウンロードのサイズ上限 (20MB)。
    # サイト側が悪意または事故で巨大ファイルを返した時に OOM や長時間 hang を
    # 起こさないためのガード。実運用の保健所 PDF は通常 1MB 以下。
    PDF_MAX_BYTES: ClassVar[int] = 20 * 1024 * 1024

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
        # PDF リンク 0 件は「現在公開中の収容情報 PDF がない」真ゼロとして扱う。
        # 茨城県や香川県の保健福祉事務所サイト等では、月次/週次の収容 PDF が
        # 翌期に差し替わる過程で一時的に 0 件になる正常状態が発生する。
        # サイト DOM 構造変化による偽陰性は zero_count_audit で別途検出する運用。
        if not pdf_links:
            return []

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
                # 個体識別: 派生 PDF サブクラスが records に該当キーを生成すれば開通する。
                # 監査(2026-06-11)指摘で追加 (kochi 同型サイレントドロップを予防)。
                breed=record.get("breed", ""),
                description=record.get("description", ""),
                name=record.get("name", ""),
                management_number=record.get("management_number", ""),
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
        """PDF を `PDF_MAX_BYTES` 上限付きでダウンロードする。

        - Content-Length が宣言されていれば事前チェックして即時 reject
        - chunk 単位で読み込み累積サイズが上限を超えたら接続切断 + NetworkError
        - 上限を超えなければ raw bytes を返す
        """
        # アクセス間隔の保証（偽計業務妨害リスク低減）
        self._polite_wait(getattr(self.site_config, "request_interval", None))
        try:
            with requests.get(
                url,
                timeout=60,
                stream=True,
                headers={"User-Agent": ONECO_USER_AGENT},
            ) as response:
                response.raise_for_status()

                # Content-Length 宣言があれば事前 reject
                declared = response.headers.get("Content-Length")
                if declared is not None:
                    try:
                        if int(declared) > self.PDF_MAX_BYTES:
                            raise NetworkError(
                                f"PDF サイズ ({declared} bytes) が上限 "
                                f"{self.PDF_MAX_BYTES} bytes を超過",
                                url=url,
                            )
                    except ValueError:
                        # Content-Length が数値でないケースは無視して本体側でチェック
                        pass

                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > self.PDF_MAX_BYTES:
                        raise NetworkError(
                            f"PDF サイズが上限 {self.PDF_MAX_BYTES} bytes を"
                            f"ストリーム読み込み中に超過 (受信 {total} bytes 時点)",
                            url=url,
                        )
                    chunks.append(chunk)
                return b"".join(chunks)
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
