"""RuleBasedAdapter - rule-based 抽出アダプターの共通基底

既存 `MunicipalityAdapter` ABC を継承し、HTTP 取得、URL 正規化、
電話番号抽出、画像 URL フィルタなどの共通ヘルパーを提供する。

サイト固有の派生クラスはこの基底 (またはこれを介する 4 種別 base) を継承し、
selector 定数のみを定義することで動作する Template Method 構造。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from ...domain.models import AnimalData, RawAnimalData
from ...domain.normalizer import DataNormalizer
from ...llm.config import SiteConfig
from ..municipality_adapter import MunicipalityAdapter, NetworkError
from ..politeness import ONECO_USER_AGENT

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FieldSpec:
    """フィールド抽出仕様 (dt/dd, th/td ベースの label 抽出用)

    Attributes:
        label: 定義リスト/テーブルの見出しテキスト（例: "性別"）。
            str を渡せば単一ラベル、tuple/list を渡せば複数候補の OR 検索になり、
            最初に値を取れたラベルを採用する。
        selector: 直接 CSS セレクタで取得する場合のセレクタ。
            label と排他的（両方指定された場合は selector 優先）。
        attr: 取得する属性名（"text" の場合は要素テキスト、それ以外は要素属性）。
    """

    label: str | tuple[str, ...] | None = None
    selector: str | None = None
    attr: str = "text"


# サイト共通の HTTP ヘッダ（User-Agent は politeness の共通定数で統一）
_DEFAULT_HEADERS = {"User-Agent": ONECO_USER_AGENT}
_DEFAULT_TIMEOUT_SEC = 30

# HTML 取得結果がこれより短ければ「構造崩壊 or 空ページ」の警告を出す。
# 正常なサイトは少なくとも数 KB のテンプレ HTML が返るため 500B は十分余裕がある。
# (Task #9 の snapshot 件数比較と併用される adapter 破損補助検出)
_MIN_HTML_SIZE_BYTES = 500

# 電話番号抽出パターン
# (a) 区切りあり: "088-826-2364", "088 826 2364", "072(963)6211",
#     "055（273）5034", "059−256−4168"
#
# T146 で 2 点直した:
#  1. 市外局番に先頭 0 を要求する。以前は `\d{2,4}` で、"管理番号 2026-09-0007"
#     (栃木県の迷子動物ページの実表記) が電話番号として通っていた。本番の
#     全公開個体を実測した時点では実害 0 件 (76 種すべて `0` 始まりの正常な
#     形式) だが、管理番号を電話抽出に通す adapter が 1 つできた時点で
#     でたらめな番号を公開する。日本の固定電話・携帯は必ず 0 で始まる。
#  2. 全角ハイフン (三重 `059−256−4168`)、半角括弧 (東大阪 `072(963)6211`)、
#     全角括弧 (山梨 `055（273）5034`) を区切りとして受ける。いずれも実在の
#     自治体ページの表記で、従来はすべて空文字に落ちていた。
_PHONE_SEP_OPEN = r"[-\s‐‑‒–—―−－ー(（]"
_PHONE_SEP_CLOSE = r"[-\s‐‑‒–—―−－ー)）]"
_PHONE_HYPHEN_RE = re.compile(
    rf"\b(0\d{{1,3}}){_PHONE_SEP_OPEN}(\d{{1,4}}){_PHONE_SEP_CLOSE}(\d{{4}})\b"
)
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
        # 並列収集時に同一ドメインの site adapter 間で politeness throttle を
        # 共有する。MunicipalityAdapter.__init__ がインスタンスローカルな
        # RequestThrottle を生成するが、サイト切り替えでリセットされると
        # サーバ WAF にバースト判定される (実例: 名古屋市 3 サイト 403)。
        # 同一 list_url ホスト全体で 1 つの throttle を共有して順序保証。
        from ..politeness import get_throttle_for_url

        self._throttle = get_throttle_for_url(site_config.list_url)

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

        # アクセス間隔の保証（偽計業務妨害リスク低減）。
        # site_config.request_interval（最小1.0秒）を最小間隔として待機する。
        self._polite_wait(getattr(self.site_config, "request_interval", None))

        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            status = getattr(e.response, "status_code", None) if e.response is not None else None
            raise NetworkError(f"HTTP エラー: {e}", url=url, status_code=status) from e
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"ネットワークエラー: {e}", url=url) from e

        # requests は charset 未指定の text/* に ISO-8859-1 を仮定する
        # (RFC 2616 §3.7.1)。<meta charset=...> でしか文字コードを宣言しない
        # 自治体サイトで日本語が文字化けするため、ヘッダ未指定時は
        # byte 検出 (apparent_encoding) にフォールバックする。
        if "charset=" not in response.headers.get("Content-Type", "").lower():
            response.encoding = response.apparent_encoding
        text = response.text
        # 構造崩壊 / 空ページ検出: HTTP 200 でも本文が極端に短いケースを警告ログに出す。
        # adapter 個別の ParsingError と snapshot 件数比較 (Task #9) のバックアップとして、
        # サイト側のメンテナンス画面や reverse-proxy エラー画面を可視化する。
        if len(text) < _MIN_HTML_SIZE_BYTES:
            site_name = getattr(getattr(self, "site_config", None), "name", "?")
            logger.warning(
                f"[{site_name}] HTML 取得サイズが小さい ({len(text)}B < {_MIN_HTML_SIZE_BYTES}B): "
                f"構造崩壊 or 空ページの可能性 (url={url})"
            )
        return text

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

        prefecture は DataNormalizer 内で source_url から推定される。URL の
        ドメインで判別できないサイト（自治体共通基盤系等）では `prefecture=None`
        になるため、site_config.prefecture をフォールバックとして上書きする。

        phone は `site_config.phone` をフォールバックする（T146）。個体ページに
        電話が載っていないサイトが多く、本番実測で全公開個体の 22.6% が
        phone=null だった。`site_config.phone`（sites.yaml に人が一次ソースから
        1 回書く）を使うのは**抽出できなかったときだけ**で、個体ごとに管轄
        保健所が違うサイトでは抽出値をそのまま残す。

        **注入は DataNormalizer に渡す前に行う。** 正規化後の AnimalData を
        書き換える形にすると `DataNormalizer._normalize_phone`（桁数 10/11 の
        検証）と `_sanitize_public_phone`（070/080/090/050 = 個人の携帯・IP
        電話を公開 phone から落とす）を迂回してしまい、sites.yaml に 1 行
        足すだけでその安全策をすり抜けられる（PR #327 reviewer F-01）。
        raw 側に入れておけば、人が書いた値も自治体ページから抽出した値と
        まったく同じ検査を通る。

        Args:
            raw_data: 抽出した生データ

        Returns:
            正規化済み AnimalData

        Raises:
            ValidationError: DataNormalizer のバリデーション失敗時
        """
        if not raw_data.phone and self.site_config.phone:
            raw_data = raw_data.model_copy(update={"phone": self.site_config.phone})
        an = DataNormalizer.normalize(raw_data)
        if an.prefecture is None and self.site_config.prefecture:
            return an.model_copy(update={"prefecture": self.site_config.prefecture})
        return an

    # ─────────────────── label 抽出 ヘルパー (dt/dd, th/td) ───────────────────
    # 元は WordPressListAdapter 専用だったが、table/single_page 系 adapter からも
    # 使えるよう基底へ昇格した (T401)。WordPressListAdapter の挙動は変えない。

    def _extract_field(self, soup: BeautifulSoup, spec: FieldSpec) -> str:
        """FieldSpec に従ってフィールド値を抽出"""
        # selector 直接指定の場合
        if spec.selector:
            el = soup.select_one(spec.selector)
            if el is None:
                return ""
            return self._get_value(el, spec.attr)

        # label 経由 (定義リスト or テーブル)
        if spec.label:
            value = self._extract_by_label(soup, spec.label)
            return value
        return ""

    def _extract_by_label(self, soup: BeautifulSoup, label: str | tuple[str, ...]) -> str:
        """定義リスト (<dt><dd>) またはテーブル (<th><td>) で label を探す。

        label に tuple/list を渡すと OR 検索になり、最初にヒットしたラベルの
        値を返す（複数表記が並ぶサイト構造に対応するため）。
        """
        labels = (label,) if isinstance(label, str) else tuple(label)

        def _lookup(match) -> str:
            # 定義リスト (<dt><dd>)
            for dt in soup.find_all("dt"):
                if isinstance(dt, Tag) and match(dt.get_text(strip=True)):
                    dd = dt.find_next_sibling("dd")
                    if dd and (text := dd.get_text(strip=True)):
                        return text
            # テーブル (<th><td>)
            for th in soup.find_all("th"):
                if isinstance(th, Tag) and match(th.get_text(strip=True)):
                    td = th.find_next_sibling("td")
                    if td and (text := td.get_text(strip=True)):
                        return text
            return ""

        # 1st pass: 完全一致を優先（label="色" が "特色" を誤って拾うのを防ぐ）
        for lbl in labels:
            if value := _lookup(lambda cell, lbl=lbl: cell == lbl):
                return value
        # 2nd pass: 部分一致フォールバック（"色"→"毛色" 等のラベル簡略指定に後方互換）
        for lbl in labels:
            if value := _lookup(lambda cell, lbl=lbl: lbl in cell):
                return value
        return ""

    def _get_value(self, el: Tag, attr: str) -> str:
        if attr == "text":
            return el.get_text(strip=True)
        v = el.get(attr)
        return v if isinstance(v, str) else ""
