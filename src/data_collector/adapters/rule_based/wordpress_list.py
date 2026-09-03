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

import logging
from dataclasses import dataclass
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ...domain.models import AnimalData, RawAnimalData
from ..municipality_adapter import ParsingError
from .base import RuleBasedAdapter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FieldSpec:
    """フィールド抽出仕様

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


class WordPressListAdapter(RuleBasedAdapter):
    """list+detail 形式の rule-based 抽出共通基底

    派生クラスは下記クラス変数を定義する:

    - `LIST_LINK_SELECTOR`: 一覧ページ内の detail link CSS セレクタ
    - `FIELD_SELECTORS`: フィールド名 -> FieldSpec の辞書
    - `IMAGE_SELECTOR`: 画像 img 要素のセレクタ（複数取得）
    - `NEXT_PAGE_SELECTOR`: 一覧が複数ページに分かれる場合の「次へ」リンクの
      CSS セレクタ（省略時は 1 ページ目のみ読む従来動作）
    """

    LIST_LINK_SELECTOR: ClassVar[str] = ""
    FIELD_SELECTORS: ClassVar[dict[str, FieldSpec]] = {}
    IMAGE_SELECTOR: ClassVar[str] = "img"
    # 空文字 = ページ送りを辿らない。定義した派生クラスだけが複数ページを読む。
    NEXT_PAGE_SELECTOR: ClassVar[str] = ""
    MAX_LIST_PAGES: ClassVar[int] = 10

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        # 抽象メソッドが残っていない最終派生のみ厳格チェック
        abstracts = getattr(cls, "__abstractmethods__", frozenset())
        if not abstracts and not cls.LIST_LINK_SELECTOR:
            raise TypeError(f"{cls.__name__} must define LIST_LINK_SELECTOR class variable")

    # ─────────────────── MunicipalityAdapter 実装 ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """一覧ページから detail URL を集める。

        `NEXT_PAGE_SELECTOR` を定義した派生クラスでは「次へ」リンクを最後まで
        辿る。定義していない派生クラスは list_url の 1 ページ目だけを読む
        従来動作のまま。

        沖縄県動物愛護管理センターの行方不明犬 (2ページ) / 行方不明猫 (3ページ)
        で 2 ページ目以降が丸ごと未収集になり、実サイト111件に対し本番 API は
        86件、URL 集合の差は25件 (全て `missing_view`) だった (T132)。

        上限到達・循環検知いずれで打ち切った場合も `self.list_truncated` を
        立てる。CollectorService はこのフラグを見て prune_disappeared
        (消滅同期削除) をスキップする (T059)。打ち切り区間に未取得の実在個体が
        残っている可能性があり、部分集合のまま消滅判定すると誤って公開から
        削除してしまうため。
        """
        urls: list[tuple[str, str]] = []
        seen: set[str] = set()
        category = self.site_config.category
        visited_pages: set[str] = set()
        page_url = self.site_config.list_url
        truncated = False

        for _ in range(self.MAX_LIST_PAGES):
            if page_url in visited_pages:
                # next リンクが既訪問ページを指す異常系 (循環)。この先に未取得の
                # ページが残っている可能性があるため、上限到達と同様に打ち切り扱い。
                truncated = True
                logger.warning(
                    "[%s] 一覧のページ送りで循環を検知しました (既訪問ページへの"
                    "再遷移: %s)。未取得のページが残っている可能性があります",
                    self.site_config.name,
                    page_url,
                )
                break
            visited_pages.add(page_url)

            html = self._http_get(page_url)
            soup = BeautifulSoup(html, "html.parser")
            for link in soup.select(self.LIST_LINK_SELECTOR):
                href = link.get("href")
                if not href or not isinstance(href, str):
                    continue
                absolute = self._absolute_url(href, base=page_url)
                if absolute in seen:
                    continue
                seen.add(absolute)
                urls.append((absolute, category))

            if not self.NEXT_PAGE_SELECTOR:
                break
            next_link = soup.select_one(self.NEXT_PAGE_SELECTOR)
            next_href = next_link.get("href") if isinstance(next_link, Tag) else None
            if not next_href or not isinstance(next_href, str):
                break
            page_url = self._absolute_url(next_href, base=page_url)
        else:
            # 上限で打ち切った = まだ next が残っている可能性があり、
            # 静かな掲載漏れになるため必ずログに残す。
            if self.NEXT_PAGE_SELECTOR:
                truncated = True
                logger.warning(
                    "[%s] 一覧のページ送りが上限 %d ページに達しました。"
                    "未取得のページが残っている可能性があります: %s",
                    self.site_config.name,
                    self.MAX_LIST_PAGES,
                    page_url,
                )

        self.list_truncated = truncated

        # 全ページを通して detail link 0 件なら「現在その種別の収容動物がいない」
        # 真ゼロとして空リストを返す。_http_get が成功し HTML パースまで通って
        # いるのにリンクだけ無い状態は、例えば douaicenter.jp/animal/list/protect/dog
        # のように動物がいないカテゴリでよく発生する。サイト DOM 構造変化による
        # 偽陰性は scripts/adapter_live_test.py / zero_count_audit で別途検出する運用。
        #
        # 判定は 1 ページ目だけでなく全ページの集計で行う。1 ページ目が空でも next が
        # あり 2 ページ目以降に実データがある構成では、1 ページ目基準だと収集済みの
        # データを無警告で握り潰してしまうため。
        return urls

    def extract_animal_details(self, detail_url: str, category: str = "adoption") -> RawAnimalData:
        html = self._http_get(detail_url)
        soup = BeautifulSoup(html, "html.parser")

        fields: dict[str, str] = {}
        for name, spec in self.FIELD_SELECTORS.items():
            value = self._extract_field(soup, spec)
            fields[name] = value

        # 派生クラスがあれば URL や他フィールドからの補完を実施
        self._postprocess_fields(fields, detail_url, soup)

        # 全フィールドが空文字 = HTML 構造がそもそも見当たらない
        if not any(fields.values()):
            raise ParsingError(
                "detail ページから 1 フィールドも抽出できませんでした",
                url=detail_url,
            )
        # shelter_date が空 or 解析不能の場合は DataNormalizer 側で「データ取得日」
        # にフォールバックされる（全 adapter 共通のセーフネット）。

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
                # 個体識別: 派生が FIELD_SELECTORS にキーを足せば開通する。
                # name/management_number は監査(2026-06-11)指摘で追加(将来の派生
                # が FIELD_SELECTORS だけで足したときの kochi 同型サイレントドロップを予防)。
                breed=fields.get("breed", ""),
                description=fields.get("description", ""),
                name=fields.get("name", ""),
                management_number=fields.get("management_number", ""),
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=detail_url) from e

    def normalize(self, raw_data: RawAnimalData) -> AnimalData:
        return self._default_normalize(raw_data)

    def _postprocess_fields(
        self, fields: dict[str, str], detail_url: str, soup: BeautifulSoup
    ) -> None:
        """抽出後のフィールドを派生クラスで補完するためのフック (in-place 変更)。

        例: URL から species を推測したり、別 selector で電話番号を補ったりする。
        デフォルトは何もしない。
        """
        return None

    def _infer_species_from_url(self) -> str:
        """site_config.list_url に `/dog` / `/cat` が含まれていれば対応する種別を返す。

        派生クラスで species 補完したいとき (`_postprocess_fields` 内) に呼ぶ
        共通ヘルパー。判定不能なら空文字を返す。
        """
        url = getattr(getattr(self, "site_config", None), "list_url", "") or ""
        url_lower = url.lower()
        if "/dog" in url_lower or "/inu" in url_lower:
            return "犬"
        if "/cat" in url_lower or "/neko" in url_lower:
            return "猫"
        return ""

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
