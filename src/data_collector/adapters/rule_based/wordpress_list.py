"""WordPressListAdapter - list+detail 構造の汎用基底

WordPress 系（および類似の構造）の自治体サイトで、
1. 一覧ページから detail ページの URL を CSS セレクタで抽出
2. 各 detail ページから定義リスト (`<dt>項目名</dt><dd>値</dd>`) または
   テーブル (`<th>項目名</th><td>値</td>`) で各フィールドを抽出
する典型パターンを共通化する。

派生クラスは `LIST_LINK_SELECTOR` / `FIELD_SELECTORS` / `IMAGE_SELECTOR` を
クラス変数として定義するだけで動作する。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ...domain.models import AnimalData, RawAnimalData
from ..municipality_adapter import ParsingError
from .base import RuleBasedAdapter


@dataclass(frozen=True)
class FieldSpec:
    """フィールド抽出仕様

    Attributes:
        label: 定義リスト/テーブルの見出しテキスト（例: "性別"）。
            完全一致または in による部分一致でマッチさせる。
        selector: 直接 CSS セレクタで取得する場合のセレクタ。
            label と排他的（両方指定された場合は selector 優先）。
        attr: 取得する属性名（"text" の場合は要素テキスト、それ以外は要素属性）。
    """

    label: str | None = None
    selector: str | None = None
    attr: str = "text"


class WordPressListAdapter(RuleBasedAdapter):
    """list+detail 形式の rule-based 抽出共通基底

    派生クラスは下記クラス変数を定義する:

    - `LIST_LINK_SELECTOR`: 一覧ページ内の detail link CSS セレクタ
    - `FIELD_SELECTORS`: フィールド名 -> FieldSpec の辞書
    - `IMAGE_SELECTOR`: 画像 img 要素のセレクタ（複数取得）
    """

    LIST_LINK_SELECTOR: ClassVar[str] = ""
    FIELD_SELECTORS: ClassVar[dict[str, FieldSpec]] = {}
    IMAGE_SELECTOR: ClassVar[str] = "img"

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        # 抽象メソッドが残っていない最終派生のみ厳格チェック
        abstracts = getattr(cls, "__abstractmethods__", frozenset())
        if not abstracts and not cls.LIST_LINK_SELECTOR:
            raise TypeError(f"{cls.__name__} must define LIST_LINK_SELECTOR class variable")

    # ─────────────────── MunicipalityAdapter 実装 ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        html = self._http_get(self.site_config.list_url)
        soup = BeautifulSoup(html, "html.parser")

        links = soup.select(self.LIST_LINK_SELECTOR)
        if not links:
            raise ParsingError(
                "detail link が見つかりません",
                selector=self.LIST_LINK_SELECTOR,
                url=self.site_config.list_url,
            )

        urls: list[tuple[str, str]] = []
        seen: set[str] = set()
        category = self.site_config.category
        for link in links:
            href = link.get("href")
            if not href or not isinstance(href, str):
                continue
            absolute = self._absolute_url(href)
            if absolute in seen:
                continue
            seen.add(absolute)
            urls.append((absolute, category))
        return urls

    def extract_animal_details(self, detail_url: str, category: str = "adoption") -> RawAnimalData:
        html = self._http_get(detail_url)
        soup = BeautifulSoup(html, "html.parser")

        fields: dict[str, str] = {}
        for name, spec in self.FIELD_SELECTORS.items():
            value = self._extract_field(soup, spec)
            fields[name] = value

        # 全フィールドが空文字 = HTML 構造がそもそも見当たらない
        if not any(fields.values()):
            raise ParsingError(
                "detail ページから 1 フィールドも抽出できませんでした",
                url=detail_url,
            )

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

    def normalize(self, raw_data: RawAnimalData) -> AnimalData:
        return self._default_normalize(raw_data)

    # ─────────────────── ヘルパー ───────────────────

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

    def _extract_by_label(self, soup: BeautifulSoup, label: str) -> str:
        """定義リスト (<dt><dd>) またはテーブル (<th><td>) で label を探す"""
        # 定義リスト
        for dt in soup.find_all("dt"):
            if not isinstance(dt, Tag):
                continue
            if label in dt.get_text(strip=True):
                dd = dt.find_next_sibling("dd")
                if dd:
                    return dd.get_text(strip=True)
        # テーブル
        for th in soup.find_all("th"):
            if not isinstance(th, Tag):
                continue
            if label in th.get_text(strip=True):
                td = th.find_next_sibling("td")
                if td:
                    return td.get_text(strip=True)
        return ""

    def _extract_images(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        imgs = soup.select(self.IMAGE_SELECTOR)
        urls: list[str] = []
        for img in imgs:
            src = img.get("src")
            if src and isinstance(src, str):
                urls.append(self._absolute_url(src, base=base_url))
        return self._filter_image_urls(urls, base_url)

    def _get_value(self, el: Tag, attr: str) -> str:
        if attr == "text":
            return el.get_text(strip=True)
        v = el.get(attr)
        return v if isinstance(v, str) else ""
