"""
LlmAdapter - MunicipalityAdapter準拠の汎用LLMベースアダプター

YAML設定とLLMプロバイダーを使って、任意の自治体サイトから
保護動物データを構造化抽出する。
"""

import logging
import re
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..adapters.municipality_adapter import MunicipalityAdapter, NetworkError
from ..domain.models import AnimalData, RawAnimalData
from ..domain.normalizer import DataNormalizer
from .config import SiteConfig
from .fetcher import PageFetcher, PdfFetcher, PlaywrightFetcher, StaticFetcher
from .html_preprocessor import HtmlPreprocessor
from .providers.base import ExtractionResult, LlmProvider

logger = logging.getLogger(__name__)


class CollectionStats:
    """1回の収集実行の統計"""

    def __init__(self) -> None:
        self.api_calls: int = 0
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.success_count: int = 0
        self.fail_count: int = 0
        self.skip_count: int = 0

    @property
    def estimated_cost_usd(self) -> float:
        """Haiku推定コスト（入力$0.25/MTok, 出力$1.25/MTok）"""
        input_cost = self.total_input_tokens * 0.25 / 1_000_000
        output_cost = self.total_output_tokens * 1.25 / 1_000_000
        return input_cost + output_cost

    def record_extraction(self, result: ExtractionResult) -> None:
        self.api_calls += 1
        self.total_input_tokens += result.input_tokens
        self.total_output_tokens += result.output_tokens


class LlmAdapter(MunicipalityAdapter):
    """MunicipalityAdapter準拠の汎用LLMベースアダプター"""

    def __init__(
        self,
        site_config: SiteConfig,
        provider: LlmProvider,
        preprocessor: Optional[HtmlPreprocessor] = None,
        fetcher: Optional[PageFetcher] = None,
    ) -> None:
        super().__init__(
            prefecture_code=site_config.prefecture_code,
            municipality_name=site_config.name,
        )
        self.site_config = site_config
        self.provider = provider
        self.preprocessor = preprocessor or HtmlPreprocessor()
        self.stats = CollectionStats()
        self._fetcher = fetcher  # テスト用インジェクション（Noneの場合は動的選択）
        # pdf_multi_animal 用キャッシュ: PDF URL -> List[RawAnimalData]
        self._multi_cache: Dict[str, List[RawAnimalData]] = {}

    def fetch_animal_list(self) -> List[Tuple[str, str]]:
        """一覧ページから(detail_url, category)リストを返す"""
        all_urls: List[Tuple[str, str]] = []
        current_url: Optional[str] = self.site_config.list_url
        pages_visited = 0

        while current_url:
            if (
                self.site_config.max_pages
                and pages_visited >= self.site_config.max_pages
            ):
                logger.info(
                    f"[{self.site_config.name}] max_pages ({self.site_config.max_pages}) に到達"
                )
                break

            logger.info(f"[{self.site_config.name}] 一覧ページ取得: {current_url}")
            html = self._fetch_page(current_url)
            detail_urls = self._extract_detail_urls(html, current_url)

            if self.site_config.pdf_multi_animal:
                # PDF一覧表モード: 各PDF URLを事前に全件抽出してキャッシュし、
                # 仮想URLリスト (pdf_url#0, pdf_url#1, ...) を返す
                for pdf_url in detail_urls:
                    virtual_pairs = self._expand_multi_animal_pdf(
                        pdf_url, self.site_config.category
                    )
                    for pair in virtual_pairs:
                        if pair not in all_urls:
                            all_urls.append(pair)
            else:
                for url in detail_urls:
                    pair = (url, self.site_config.category)
                    if pair not in all_urls:
                        all_urls.append(pair)

            pages_visited += 1

            # ページネーション検出（次ページリンク）
            current_url = self._find_next_page(html, current_url)
            if current_url:
                time.sleep(self.site_config.request_interval)

        logger.info(
            f"[{self.site_config.name}] {len(all_urls)} 件の詳細URLを収集"
        )
        return all_urls

    def extract_animal_details(
        self, detail_url: str, category: str = "adoption"
    ) -> RawAnimalData:
        """詳細ページからLLMで構造化データを抽出

        pdf_multi_animal モードの場合、detail_url は 'pdf_url#index' 形式の仮想URLとなる。
        その場合はキャッシュから対応する RawAnimalData を返す。
        """
        # pdf_multi_animal モード: 仮想URL (#index) からキャッシュを参照
        if self.site_config.pdf_multi_animal and "#" in detail_url:
            return self._get_from_multi_cache(detail_url, category)

        time.sleep(self.site_config.request_interval)
        html = self._fetch_page(detail_url)

        # HTML前処理
        cleaned_html = self.preprocessor.preprocess(html, detail_url)

        # LLM抽出
        result = self.provider.extract_animal_data(
            html_content=cleaned_html,
            source_url=detail_url,
            category=category,
        )
        self.stats.record_extraction(result)

        # ExtractionResult → RawAnimalData
        fields = result.fields
        return RawAnimalData(
            species=fields.get("species", ""),
            sex=fields.get("sex", ""),
            age=fields.get("age", ""),
            color=fields.get("color", ""),
            size=fields.get("size", ""),
            shelter_date=fields.get("shelter_date", ""),
            location=fields.get("location", ""),
            phone=fields.get("phone", ""),
            image_urls=fields.get("image_urls", []),
            source_url=detail_url,
            category=category,
        )

    def normalize(self, raw_data: RawAnimalData) -> AnimalData:
        """DataNormalizerに委譲"""
        return DataNormalizer.normalize(raw_data)

    def log_stats(self) -> None:
        """収集統計をログ出力"""
        logger.info(
            f"[{self.site_config.name}] 統計: "
            f"API呼出={self.stats.api_calls}, "
            f"成功={self.stats.success_count}, "
            f"失敗={self.stats.fail_count}, "
            f"スキップ={self.stats.skip_count}, "
            f"入力トークン={self.stats.total_input_tokens}, "
            f"出力トークン={self.stats.total_output_tokens}, "
            f"推定コスト=${self.stats.estimated_cost_usd:.4f}"
        )

    def _expand_multi_animal_pdf(
        self, pdf_url: str, category: str
    ) -> List[Tuple[str, str]]:
        """
        PDF一覧表から複数動物を抽出してキャッシュし、仮想URLリストを返す

        仮想URL形式: '{pdf_url}#{index}' （例: '.../0322dog.pdf#0'）

        Args:
            pdf_url: PDFのURL
            category: カテゴリ

        Returns:
            List[Tuple[str, str]]: (仮想URL, category) のリスト
        """
        if pdf_url in self._multi_cache:
            raw_list = self._multi_cache[pdf_url]
        else:
            time.sleep(self.site_config.request_interval)
            content = self._fetch_page(pdf_url)

            # URLファイル名から種別ヒントを決定
            hint_species = ""
            lower_url = pdf_url.lower()
            if "dog" in lower_url:
                hint_species = "犬"
            elif "cat" in lower_url or "neko" in lower_url:
                hint_species = "猫"

            result = self.provider.extract_multiple_animals(
                content=content,
                source_url=pdf_url,
                category=category,
                hint_species=hint_species,
            )
            self.stats.api_calls += 1
            self.stats.total_input_tokens += result.input_tokens
            self.stats.total_output_tokens += result.output_tokens

            raw_list = []
            for fields in result.animals:
                # species ヒントで上書き（URLから確実に分かる場合）
                if hint_species and not fields.get("species"):
                    fields["species"] = hint_species

                raw_list.append(
                    RawAnimalData(
                        species=fields.get("species", hint_species or ""),
                        sex=fields.get("sex", ""),
                        age=fields.get("age", ""),
                        color=fields.get("color", ""),
                        size=fields.get("size", ""),
                        shelter_date=fields.get("shelter_date", ""),
                        location=fields.get("location", ""),
                        phone=fields.get("phone", ""),
                        image_urls=fields.get("image_urls", []),
                        source_url=pdf_url,
                        category=category,
                    )
                )

            self._multi_cache[pdf_url] = raw_list
            logger.info(
                f"[{self.site_config.name}] PDF一覧抽出完了: {pdf_url} → {len(raw_list)} 件"
            )

        return [(f"{pdf_url}#{i}", category) for i in range(len(raw_list))]

    def _get_from_multi_cache(
        self, virtual_url: str, category: str
    ) -> RawAnimalData:
        """
        仮想URL (pdf_url#index) からキャッシュ済み RawAnimalData を取得

        Args:
            virtual_url: '{pdf_url}#{index}' 形式の仮想URL
            category: カテゴリ

        Returns:
            RawAnimalData

        Raises:
            ValueError: キャッシュが見つからない場合
        """
        # '#' の最後の出現でsplit（URLにフラグメントが含まれることはないが念のため）
        last_hash = virtual_url.rfind("#")
        pdf_url = virtual_url[:last_hash]
        index = int(virtual_url[last_hash + 1:])

        if pdf_url not in self._multi_cache:
            # キャッシュミス: 再抽出
            self._expand_multi_animal_pdf(pdf_url, category)

        raw_list = self._multi_cache.get(pdf_url, [])
        if index >= len(raw_list):
            raise ValueError(
                f"multi-animal キャッシュ範囲外: {virtual_url} (count={len(raw_list)})"
            )
        return raw_list[index]

    def _fetch_page(self, url: str) -> str:
        """URLからHTML（またはPDFテキスト）を取得"""
        if self._fetcher is not None:
            # テスト用インジェクション済みフェッチャーを使用
            return self._fetcher.fetch(url)
        # .pdf で終わるURLはPdfFetcherを使用
        if url.lower().endswith(".pdf"):
            return PdfFetcher().fetch(url)
        if self.site_config.requires_js:
            fetcher: PageFetcher = PlaywrightFetcher(
                wait_selector=self.site_config.wait_selector
            )
        else:
            fetcher = StaticFetcher()
        return fetcher.fetch(url)

    def _extract_detail_urls(self, html: str, base_url: str) -> List[str]:
        """一覧ページHTMLから詳細ページURLを抽出"""
        if self.site_config.single_page:
            # 一覧ページ自体に動物情報が埋め込まれている（個別詳細ページなし）
            return [base_url]
        if self.site_config.pdf_link_pattern:
            # CSSセレクターでPDFリンクを抽出
            return self._extract_urls_by_selector(
                html, base_url, self.site_config.pdf_link_pattern
            )
        if self.site_config.list_link_pattern:
            # CSSセレクターで抽出
            return self._extract_urls_by_selector(
                html, base_url, self.site_config.list_link_pattern
            )
        else:
            # LLMで推定
            cleaned_html = self.preprocessor.preprocess(html, base_url)
            links = self.provider.extract_detail_links(cleaned_html, base_url)
            self.stats.api_calls += 1
            return links

    def _extract_urls_by_selector(
        self, html: str, base_url: str, selector: str
    ) -> List[str]:
        """CSSセレクターでリンクを抽出"""
        soup = BeautifulSoup(html, "html.parser")
        urls: List[str] = []
        for a_tag in soup.select(selector):
            href = a_tag.get("href")
            if href:
                absolute_url = urljoin(base_url, href)
                if absolute_url not in urls:
                    urls.append(absolute_url)
        return urls

    def _find_next_page(self, html: str, current_url: str) -> Optional[str]:
        """ページネーションの次ページリンクを検出"""
        soup = BeautifulSoup(html, "html.parser")

        # 一般的な「次へ」パターン
        next_patterns = ["次へ", "次のページ", "Next", "next", ">>", "›", "次"]
        for pattern in next_patterns:
            link = soup.find("a", string=lambda s: s and pattern in s)
            if link and link.get("href"):
                return urljoin(current_url, link["href"])

        # class/rel ベースの検出
        for attr in ["next", "pagination-next"]:
            link = soup.find("a", class_=attr) or soup.find("a", rel=attr)
            if link and link.get("href"):
                return urljoin(current_url, link["href"])

        return None


def validate_extraction(fields: Dict) -> List[str]:
    """
    抽出結果のバリデーション

    Returns:
        エラーメッセージのリスト（空なら妥当）
    """
    errors: List[str] = []
    if not fields.get("species"):
        errors.append("species が空です")
    if not fields.get("shelter_date"):
        errors.append("shelter_date が空です")
    return errors
