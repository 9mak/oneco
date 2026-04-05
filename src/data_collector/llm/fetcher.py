"""
ページ取得フェッチャー

静的HTML取得（requests）とJavaScript実行が必要なサイト向け
Playwright取得の2種類を提供する。
PDFダウンロード＆テキスト抽出にも対応する。
"""

import io
from abc import ABC, abstractmethod

import requests

from ..adapters.municipality_adapter import NetworkError

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    pdfplumber = None  # type: ignore[assignment]

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None  # type: ignore[assignment]


class PageFetcher(ABC):
    """ページ取得の抽象基底クラス"""

    @abstractmethod
    def fetch(self, url: str) -> str:
        """
        URLからHTMLを取得する

        Args:
            url: 取得対象のURL

        Returns:
            HTMLテキスト

        Raises:
            NetworkError: 取得失敗時
        """
        raise NotImplementedError


class StaticFetcher(PageFetcher):
    """requestsを使った静的HTMLフェッチャー"""

    def fetch(self, url: str) -> str:
        """
        requestsでHTMLを取得する

        Args:
            url: 取得対象のURL

        Returns:
            HTMLテキスト

        Raises:
            NetworkError: HTTP エラーまたは接続エラー時
        """
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            response.encoding = response.apparent_encoding
            return response.text
        except requests.RequestException as e:
            raise NetworkError(
                message=f"ページ取得失敗: {e}",
                url=url,
                status_code=getattr(e.response, "status_code", None)
                if hasattr(e, "response")
                else None,
            )


class PdfFetcher(PageFetcher):
    """PDFをダウンロードしてテキストを抽出するフェッチャー"""

    def fetch(self, url: str) -> str:
        """
        PDFをダウンロードしてテキストを返す（HTML代わりにLLMへ渡す）

        Args:
            url: 取得対象のPDF URL

        Returns:
            PDFから抽出したテキスト（<pre>タグで囲んだ形式）

        Raises:
            NetworkError: ダウンロード失敗またはテキスト抽出失敗時
        """
        if pdfplumber is None:  # pragma: no cover
            raise NetworkError(
                message="pdfplumber がインストールされていません",
                url=url,
            )

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            pdf_bytes = response.content
        except requests.RequestException as e:
            raise NetworkError(
                message=f"PDFダウンロード失敗: {e}",
                url=url,
                status_code=getattr(e.response, "status_code", None)
                if hasattr(e, "response")
                else None,
            )

        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                pages_text = []
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        pages_text.append(text)
            extracted = "\n\n".join(pages_text)
        except Exception as e:
            raise NetworkError(
                message=f"PDFテキスト抽出失敗: {e}",
                url=url,
            )

        return f"<pre>{extracted}</pre>"


class PlaywrightFetcher(PageFetcher):
    """Playwright同期APIを使ったJavaScript対応フェッチャー"""

    def __init__(
        self,
        wait_until: str = "networkidle",
        wait_selector: str | None = None,
        timeout: int = 30000,
    ) -> None:
        """
        Args:
            wait_until: ページ読み込み完了の待機条件（デフォルト: "networkidle"）
            wait_selector: 追加で待機するCSSセレクター（Noneの場合は待機しない）
            timeout: タイムアウト（ミリ秒、デフォルト: 30000）
        """
        self.wait_until = wait_until
        self.wait_selector = wait_selector
        self.timeout = timeout

    def fetch(self, url: str) -> str:
        """
        Playwrightを使ってJavaScript実行後のHTMLを取得する

        Args:
            url: 取得対象のURL

        Returns:
            HTMLテキスト（Unicodeエンコード済み）

        Raises:
            NetworkError: 取得失敗時
        """
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (X11; Linux x86_64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                )
                page = context.new_page()
                page.goto(url, wait_until=self.wait_until, timeout=self.timeout)
                if self.wait_selector:
                    page.wait_for_selector(self.wait_selector, timeout=self.timeout)
                content = page.content()
                browser.close()
                return content
        except Exception as e:
            raise NetworkError(
                message=f"Playwrightページ取得失敗: {e}",
                url=url,
            )
