"""愛知県わんにゃんナビ (wannyan-navi.pref.aichi.jp) rule-based adapter

対象ドメイン: https://wannyan-navi.pref.aichi.jp/

特徴:
- 愛知県動物愛護センターが運営する譲渡対象犬猫の里親募集サイト。
  ドメインそのものが愛知県専用で、譲渡 (adoption) 用途のみ運用される。
- ページ全体が Bubble.io で構築された SPA であり、`requests` 取得段階の
  HTML には動物カードや詳細リンクは一切含まれない。一覧/詳細ともに
  JavaScript 実行後の DOM が必要なため `PlaywrightFetchMixin` を併用する。
- Bubble.io アプリは個別ページパス (例: `/dog/...`, `/cat/...`,
  `/version-test/...`) や URL ハッシュで詳細遷移するパターンが混在する。
  安定したリンクパスを 1 つに固定できないため、`LIST_LINK_SELECTOR` は
  「動物詳細を指す可能性が高い `<a>`」を緩めに拾い、ナビゲーション系
  (`/about`, `/contact`, `/login`, `/signup`, 外部 SNS 等) は除外する
  方針を取る。
- 詳細ページは `<dl>/<dt>/<dd>` または `<table>/<th>/<td>` 形式で
  「種類 / 性別 / 年齢 / 毛色 / 大きさ / 収容日 / 場所 / 連絡先」を
  表示する想定。`WordPressListAdapter._extract_by_label` の標準実装と
  福岡市等で導入済みの `<td>/<td>` 2 列フォールバックを併用する。
- カテゴリは sites.yaml で `adoption` 固定。
- species (動物種別) は detail URL → list URL → サイト名の順で「犬」/
  「猫」を推定する。サイト名「愛知県わんにゃんナビ」自体には犬/猫の
  区別が無いため、URL 由来で取れない場合は空文字のまま返す
  (ParsingError にしない)。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..playwright import PlaywrightFetchMixin
from ..registry import SiteAdapterRegistry
from ..wordpress_list import FieldSpec, WordPressListAdapter

# 詳細ページ候補と判定する URL パスのキーワード。
# Bubble.io アプリの典型的な動物詳細パスを網羅的に列挙する。
_DETAIL_PATH_HINTS = (
    "/dog",
    "/cat",
    "/animal",
    "/pet",
    "/detail",
    "/profile",
    "/version-test",
)

# ナビゲーション/外部リンク等として除外したい URL キーワード。
_EXCLUDE_PATH_HINTS = (
    "/about",
    "/contact",
    "/login",
    "/signup",
    "/news",
    "/event",
    "/seminar",
    "/policy",
    "/privacy",
    "/faq",
    "/sitemap",
    "/index",
    "/home",
    "twitter.com",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "line.me",
    "mailto:",
    "tel:",
)


class WannyanNaviAichiAdapter(PlaywrightFetchMixin, WordPressListAdapter):
    """愛知県わんにゃんナビ rule-based adapter

    Bubble.io 製 SPA のため `PlaywrightFetchMixin` を第一基底に置いて
    `_http_get` を JS 実行後 HTML 取得に差し替える。
    """

    # Bubble.io が動物カードを描画完了するまで待つセレクタ。
    # 詳細リンクとして解釈される `<a>` または、Bubble がレンダー後に
    # body 配下に挿入する任意要素のいずれかが存在すれば良い。
    WAIT_SELECTOR: ClassVar[str | None] = (
        "a[href*='/dog'], a[href*='/cat'], a[href*='/animal'], .bubble-element, main"
    )

    # 一覧ページの動物カード `<a>` を緩めに拾う。
    # 取得後 `fetch_animal_list` で `_DETAIL_PATH_HINTS` /
    # `_EXCLUDE_PATH_HINTS` に基づき詳細リンクのみへ絞り込む。
    LIST_LINK_SELECTOR: ClassVar[str] = "a[href]"

    # 詳細ページのフィールドラベル想定。
    FIELD_SELECTORS: ClassVar[dict[str, FieldSpec]] = {
        "species": FieldSpec(label="種類"),
        "sex": FieldSpec(label="性別"),
        "age": FieldSpec(label="年齢"),
        "color": FieldSpec(label="毛色"),
        "size": FieldSpec(label="大きさ"),
        "shelter_date": FieldSpec(label="収容日"),
        "location": FieldSpec(label="場所"),
        "phone": FieldSpec(label="連絡先"),
    }

    # 動物画像。Bubble.io は CDN (bubble.io / cdn.bubble.io) 上の
    # 画像も多用するが、ここでは body 配下の `<img>` を一律取得し、
    # `_filter_image_urls` でテンプレート由来 (logo/header/icon 等) を
    # 除外する。
    IMAGE_SELECTOR: ClassVar[str] = "img"

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """一覧ページから詳細リンク候補を抽出する

        Bubble.io SPA は静的 HTML 上には目的のリンクが無いため、
        Playwright 後 HTML から `<a href>` を全件拾い、
        `_is_detail_url` で動物詳細らしい URL のみを残す。
        該当 0 件の場合は ParsingError ではなく空リストを返す
        (実運用上、譲渡可能個体が 0 件の状態が日常的に発生し得るため)。
        """
        html = self._http_get(self.site_config.list_url)
        soup = BeautifulSoup(html, "html.parser")

        links = soup.select(self.LIST_LINK_SELECTOR)
        if not links:
            return []

        urls: list[tuple[str, str]] = []
        seen: set[str] = set()
        category = self.site_config.category
        for link in links:
            href = link.get("href")
            if not href or not isinstance(href, str):
                continue
            if not self._is_detail_url(href):
                continue
            absolute = self._absolute_url(href)
            if absolute in seen:
                continue
            seen.add(absolute)
            urls.append((absolute, category))
        return urls

    def extract_animal_details(self, detail_url: str, category: str = "adoption") -> RawAnimalData:
        """detail ページから RawAnimalData を構築する

        - 標準 `WordPressListAdapter` のフィールド抽出に加え、
          species ラベルが空のときは detail URL → list URL の順で
          「犬」「猫」を推定して補完する。
        - 1 フィールドも抽出できない場合は ParsingError。
        """
        html = self._http_get(detail_url)
        soup = BeautifulSoup(html, "html.parser")

        fields: dict[str, str] = {}
        for name, spec in self.FIELD_SELECTORS.items():
            value = self._extract_field(soup, spec)
            fields[name] = value

        if not any(fields.values()):
            raise ParsingError(
                "detail ページから 1 フィールドも抽出できませんでした",
                url=detail_url,
            )

        if not fields.get("species"):
            inferred = self._infer_species_from_url(detail_url) or self._infer_species_from_url(
                self.site_config.list_url
            )
            if inferred:
                fields["species"] = inferred

        image_urls = self._extract_images(soup, detail_url)

        try:
            return RawAnimalData(
                species=fields.get("species", ""),
                sex=fields.get("sex", ""),
                age=fields.get("age", ""),
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=fields.get("shelter_date", ""),
                location=fields.get("location", ""),
                phone=self._normalize_phone(fields.get("phone", "")),
                image_urls=image_urls,
                source_url=detail_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=detail_url) from e

    # ─────────────────── 抽出ヘルパー拡張 ───────────────────

    def _extract_by_label(self, soup: BeautifulSoup, label: str) -> str:
        """`<dt>/<dd>`, `<th>/<td>` に加えて `<td>/<td>` 2 列も探す"""
        value = super()._extract_by_label(soup, label)
        if value:
            return value

        for td in soup.find_all("td"):
            if not isinstance(td, Tag):
                continue
            cell_text = td.get_text(strip=True)
            if not cell_text or label not in cell_text:
                continue
            sibling = td.find_next_sibling("td")
            if sibling is None:
                continue
            sibling_text = sibling.get_text(strip=True)
            if sibling_text:
                return sibling_text
        return ""

    def _filter_image_urls(self, urls: list[str], base_url: str) -> list[str]:
        """テンプレート由来の装飾画像を除外する (フェイルセーフ付き)"""
        filtered = [
            u
            for u in urls
            if "logo" not in u.lower()
            and "icon" not in u.lower()
            and "header" not in u.lower()
            and "footer" not in u.lower()
            and "favicon" not in u.lower()
            and "ogp" not in u.lower()
        ]
        return filtered if filtered else urls

    # ─────────────────── 判定ヘルパー ───────────────────

    @staticmethod
    def _is_detail_url(href: str) -> bool:
        """動物詳細ページらしい URL かどうかを判定する

        - 除外キーワード (`_EXCLUDE_PATH_HINTS`) を含む → False
        - 詳細キーワード (`_DETAIL_PATH_HINTS`) のいずれかを含む → True
        - それ以外 → False
        """
        lowered = href.lower()
        for ex in _EXCLUDE_PATH_HINTS:
            if ex in lowered:
                return False
        for hint in _DETAIL_PATH_HINTS:
            if hint in lowered:
                return True
        return False

    @staticmethod
    def _infer_species_from_url(url: str) -> str:
        """URL パスから動物種別を推定する

        - `/dog` を含む or "dog" 単語 → "犬"
        - `/cat` を含む or "cat" 単語 → "猫"
        - それ以外 → ""
        """
        if not url:
            return ""
        lowered = url.lower()
        has_dog = "/dog" in lowered or bool(re.search(r"\bdog\b", lowered))
        has_cat = "/cat" in lowered or bool(re.search(r"\bcat\b", lowered))
        if has_dog and not has_cat:
            return "犬"
        if has_cat and not has_dog:
            return "猫"
        return ""


# ─────────────────── サイト登録 ───────────────────
# sites.yaml の `name` フィールドと完全一致する 1 サイト名で登録する。
_SITE_NAME = "愛知県わんにゃんナビ"
if SiteAdapterRegistry.get(_SITE_NAME) is None:
    SiteAdapterRegistry.register(_SITE_NAME, WannyanNaviAichiAdapter)
