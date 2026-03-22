"""
HTML前処理によるLLMトークン数の削減

HTMLから不要要素（script, style, nav等）を除去し、LLM向けに最適化する。
img タグは画像URL抽出のため保持する。
"""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup


class HtmlPreprocessor:
    """HTMLを前処理してLLM向けに最適化"""

    REMOVE_TAGS = [
        "script",
        "style",
        "nav",
        "footer",
        "header",
        "iframe",
        "noscript",
        "svg",
        "meta",
        "link",
    ]

    @staticmethod
    def preprocess(html: str, base_url: str) -> str:
        """
        HTMLを前処理してLLM向けに最適化

        Args:
            html: 元のHTML文字列
            base_url: 相対URL解決用のベースURL

        Returns:
            前処理済みHTML文字列（不要要素除去、URL正規化済み）
        """
        soup = BeautifulSoup(html, "html.parser")

        # 不要要素を除去
        for tag_name in HtmlPreprocessor.REMOVE_TAGS:
            for tag in soup.find_all(tag_name):
                tag.decompose()

        # 相対URLを絶対URLに変換（img, a タグ）
        for img in soup.find_all("img"):
            src = img.get("src")
            if src:
                img["src"] = urljoin(base_url, src)

        for a in soup.find_all("a"):
            href = a.get("href")
            if href:
                a["href"] = urljoin(base_url, href)

        # HTML文字列を取得
        result = str(soup)

        # 連続空白・改行を正規化
        result = re.sub(r"\n{3,}", "\n\n", result)
        result = re.sub(r"[ \t]+", " ", result)

        return result.strip()

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        テキストの推定トークン数を算出

        日本語テキストは文字数 × 1.5、英語テキストは単語数 × 1.3 を目安に算出。
        混在テキストの場合は文字数ベースで概算する。

        Args:
            text: 推定対象のテキスト

        Returns:
            推定トークン数
        """
        if not text:
            return 0
        return int(len(text) * 1.5)
