"""RuleBasedAdapter - rule-based 抽出アダプターの共通基底

既存 `MunicipalityAdapter` ABC を継承し、HTTP 取得、URL 正規化、
電話番号抽出、画像 URL フィルタなどの共通ヘルパーを提供する。

サイト固有の派生クラスはこの基底 (またはこれを介する 4 種別 base) を継承し、
selector 定数のみを定義することで動作する Template Method 構造。
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

import requests

from ...domain.models import AnimalData, RawAnimalData
from ...domain.normalizer import DataNormalizer
from ...llm.config import SiteConfig
from ..municipality_adapter import MunicipalityAdapter, NetworkError

logger = logging.getLogger(__name__)

# サイト共通の HTTP ヘッダ
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36 "
    "(oneco data collector)"
)
_DEFAULT_HEADERS = {"User-Agent": _DEFAULT_USER_AGENT}
_DEFAULT_TIMEOUT_SEC = 30

# 電話番号抽出パターン
# (a) ハイフン/スペース区切り: "088-826-2364", "088 826 2364"
_PHONE_HYPHEN_RE = re.compile(r"\b(\d{2,4})[-\s](\d{1,4})[-\s](\d{4})\b")
# (b) 区切りなし 10 桁: "0888262364" → 3-3-4 で分割
_PHONE_PLAIN_RE = re.compile(r"\b(0\d{9})\b")
# (c) 区切りなし 11 桁 (携帯): "09012345678" → 3-4-4 で分割
_PHONE_MOBILE_RE = re.compile(r"\b(0[789]0\d{8})\b")


class RuleBasedAdapter(MunicipalityAdapter):
    """rule-based 抽出アダプターの共通基底クラス

    `MunicipalityAdapter` の抽象メソッド (fetch_animal_list /
    extract_animal_details / normalize) はサブクラスで実装する。
    本クラスは派生で繰り返し使うヘルパー群と、`normalize` の
    デフォルト実装 (`_default_normalize`) を提供する。
    """

    def __init__(self, site_config: SiteConfig) -> None:
        super().__init__(
            prefecture_code=site_config.prefecture_code,
            municipality_name=site_config.name,
        )
        self.site_config = site_config

    # ─────────────────── HTTP ヘルパー ───────────────────

    def _http_get(
        self,
        url: str,
        *,
        timeout: int = _DEFAULT_TIMEOUT_SEC,
        extra_headers: dict[str, str] | None = None,
    ) -> str:
        """HTTP GET でページを取得し本文文字列を返す

        Args:
            url: 取得対象 URL
            timeout: タイムアウト秒
            extra_headers: 追加リクエストヘッダ

        Returns:
            レスポンス本文 (text)

        Raises:
            NetworkError: HTTP エラー / ネットワーク例外発生時
        """
        headers = dict(_DEFAULT_HEADERS)
        if extra_headers:
            headers.update(extra_headers)

        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            status = getattr(e.response, "status_code", None) if e.response is not None else None
            raise NetworkError(f"HTTP エラー: {e}", url=url, status_code=status) from e
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"ネットワークエラー: {e}", url=url) from e

        return response.text

    # ─────────────────── URL ヘルパー ───────────────────

    def _absolute_url(self, href: str, base: str | None = None) -> str:
        """相対 URL を絶対 URL に変換する

        Args:
            href: 変換対象 URL（絶対/相対どちらでも可）
            base: 基準 URL（省略時は site_config.list_url）

        Returns:
            絶対 URL
        """
        return urljoin(base or self.site_config.list_url, href)

    # ─────────────────── 電話番号 ヘルパー ───────────────────

    def _normalize_phone(self, raw: str) -> str:
        """文字列から電話番号を抽出して "XXX-XXXX-XXXX" 形式で返す

        Args:
            raw: 電話番号を含む可能性のある文字列

        Returns:
            "088-826-2364" / "090-1234-5678" 形式、または空文字列
        """
        if not raw:
            return ""
        # まず携帯 11 桁（0[789]0始まり）→ 3-4-4 分割
        m = _PHONE_MOBILE_RE.search(raw)
        if m:
            digits = m.group(1)
            return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
        # 次に区切りなし固定電話 10 桁 → 3-3-4 分割
        m = _PHONE_PLAIN_RE.search(raw)
        if m:
            digits = m.group(1)
            return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
        # 最後にハイフン/スペース区切り → そのまま正規化
        m = _PHONE_HYPHEN_RE.search(raw)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        return ""

    # ─────────────────── 画像URL ヘルパー ───────────────────

    def _filter_image_urls(self, urls: list[str], base_url: str) -> list[str]:
        """テンプレート/装飾画像を除外し、動物写真らしいものだけを返す

        WordPress 系サイトでは `/wp-content/themes/` 配下にロゴ等が、
        `/wp-content/uploads/` 配下に動物写真がある慣習に依拠する。
        他の CMS ではサブクラスで上書き可能。

        Args:
            urls: フィルタリング前の画像 URL リスト
            base_url: ベース URL（将来の拡張用）

        Returns:
            フィルタ後の画像 URL リスト。
            uploads パスを含む URL が 1 件もない場合は元リストを返す
            （データ消失防止のフェイルセーフ）。
        """
        filtered = [u for u in urls if "/wp-content/uploads/" in u]
        return filtered if filtered else urls

    # ─────────────────── 正規化 ヘルパー ───────────────────

    def _default_normalize(self, raw_data: RawAnimalData) -> AnimalData:
        """RawAnimalData -> AnimalData の標準変換

        サイト個別の特殊処理が不要な場合は、サブクラスの normalize から
        本メソッドを呼ぶだけで済む。特殊処理が必要なら、サブクラスで
        normalize をオーバーライドして本メソッドの前後にロジックを足す。

        Args:
            raw_data: 抽出した生データ

        Returns:
            正規化済み AnimalData

        Raises:
            ValidationError: DataNormalizer のバリデーション失敗時
        """
        return DataNormalizer.normalize(raw_data)
