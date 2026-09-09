"""GenericAdapter - YAML spec 駆動の rule-based adapter (T405)

サイト個別の Python モジュールを書く代わりに、`config/site_specs/<slug>.yaml`
だけで「declarative only」なサイト (CSS セレクタ + ラベル辞書 + 軽い後処理
だけで完結する構造) を賄う。既存 4 base class の Template Method 構造は
一切変えず、`WordPressListAdapter` / `SinglePageTableAdapter` を spec の値で
動的に configure したサブクラスを `type()` で生成するだけ。

対応 mode:
    - "list_detail": WordPressListAdapter ベース (一覧 → 詳細ページ)
    - "table_horizontal": SinglePageTableAdapter + HEADER_FIELDS (見出し文字列
      で列を解決)
    - "table_vertical": SinglePageTableAdapter + COLUMN_FIELDS (固定列インデックス)

いずれの mode でも `empty_state_patterns` / `always_empty` を指定すると、
「動物一覧を持たない案内・ハブページ」を常に 0 件として扱う (fetch_animal_list
をオーバーライド)。

`postprocess` / `species` 補完は現状 list_detail mode のみ配線している
(移行対象の table_* サイトは全て always_empty のハブ/案内ページで、
フィールド後処理を必要としないため)。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from ...domain.models import RawAnimalData
from ..municipality_adapter import ParsingError
from .generic_transforms import apply_postprocess
from .registry import SiteAdapterRegistry
from .single_page_table import SinglePageTableAdapter
from .site_spec import SiteSpec
from .wordpress_list import WordPressListAdapter

logger = logging.getLogger(__name__)


def _is_announcement_page(html: str, patterns: tuple[str, ...]) -> bool:
    """HTML の <title>/h1/h2 が empty_state_patterns のいずれかにマッチするか"""
    if not html or not patterns:
        return False
    compiled = re.compile("|".join(f"(?:{p})" for p in patterns))
    soup = BeautifulSoup(html, "html.parser")
    title = soup.find("title")
    if title and compiled.search(title.get_text(strip=True)):
        return True
    for tag in soup.find_all(["h1", "h2"]):
        if compiled.search(tag.get_text(strip=True)):
            return True
    return False


def _resolve_species(fields: dict[str, str], adapter: Any, spec: SiteSpec) -> None:
    rule = spec.species
    if rule.strategy == "none":
        return
    if rule.strategy == "literal":
        fields["species"] = rule.value
        return
    if rule.strategy == "from_site_name":
        name = getattr(getattr(adapter, "site_config", None), "name", "") or ""
        if "犬" in name:
            fields["species"] = "犬"
        elif "猫" in name:
            fields["species"] = "猫"
        return
    if rule.strategy == "from_url":
        entry = "species_from_list_url_dog_cat"
        if rule.value:
            entry += ":" + rule.value
        apply_postprocess([entry], fields, adapter)
        return


def _make_list_detail_class(spec: SiteSpec, class_name: str) -> type[WordPressListAdapter]:
    def _postprocess_fields(
        self: WordPressListAdapter, fields: dict[str, str], detail_url: str, soup: BeautifulSoup
    ) -> None:
        _resolve_species(fields, self, spec)
        if spec.postprocess:
            apply_postprocess(list(spec.postprocess), fields, self)

    namespace: dict[str, Any] = {
        "LIST_LINK_SELECTOR": spec.list_link_selector,
        "FIELD_SELECTORS": dict(spec.field_selectors),
        "IMAGE_SELECTOR": spec.image_selector,
        "NEXT_PAGE_SELECTOR": spec.next_page_selector,
        "MAX_LIST_PAGES": spec.max_list_pages,
        "LINK_EXCLUDE_MARKERS": spec.link_exclude_markers,
        "_postprocess_fields": _postprocess_fields,
        "__doc__": f"GenericAdapter (list_detail) for {', '.join(spec.names)}",
    }

    if spec.image_filter == "exclude_no_filename":

        def _filter_image_urls(
            self: WordPressListAdapter, urls: list[str], base_url: str
        ) -> list[str]:
            """ファイル名の無い ("/" で終わる) ダミー画像 URL を除外する"""
            return [u for u in urls if u and not u.endswith("/")]

        namespace["_filter_image_urls"] = _filter_image_urls

    if spec.always_empty or spec.empty_state_patterns:

        def fetch_animal_list(self: WordPressListAdapter) -> list[tuple[str, str]]:
            html = self._http_get(self.site_config.list_url)
            if spec.always_empty or _is_announcement_page(html, spec.empty_state_patterns):
                return []
            return WordPressListAdapter.fetch_animal_list(self)

        namespace["fetch_animal_list"] = fetch_animal_list
    elif spec.swallow_list_errors:

        def fetch_animal_list_swallowing(self: WordPressListAdapter) -> list[tuple[str, str]]:
            try:
                return WordPressListAdapter.fetch_animal_list(self)
            except Exception:
                logger.warning(
                    "[%s] 一覧取得に失敗しましたが spec の swallow_list_errors により "
                    "空リストとして扱います",
                    self.site_config.name,
                )
                return []

        namespace["fetch_animal_list"] = fetch_animal_list_swallowing

    return type(class_name, (WordPressListAdapter,), namespace)


def _make_table_class(spec: SiteSpec, class_name: str) -> type[SinglePageTableAdapter]:
    header_fields = dict(spec.header_fields) if spec.mode == "table_horizontal" else {}
    column_fields = dict(spec.column_fields)

    namespace: dict[str, Any] = {
        "ROW_SELECTOR": spec.row_selector,
        "COLUMN_FIELDS": column_fields,
        "HEADER_FIELDS": header_fields,
        "SKIP_FIRST_ROW": spec.skip_first_row,
        "LOCATION_COLUMN": spec.location_column,
        "SHELTER_DATE_DEFAULT": spec.shelter_date_default,
        "NEXT_PAGE_SELECTOR": spec.next_page_selector,
        "MAX_LIST_PAGES": spec.max_list_pages,
        "__doc__": f"GenericAdapter (table) for {', '.join(spec.names)}",
    }

    if spec.always_empty:

        def fetch_animal_list_always_empty(self: SinglePageTableAdapter) -> list[tuple[str, str]]:
            if self._html_cache is None:
                self._html_cache = self._http_get(self.site_config.list_url)
            return []

        def extract_animal_details_always_empty(
            self: SinglePageTableAdapter, virtual_url: str, category: str = "adoption"
        ) -> RawAnimalData:
            # fetch_animal_list が常に空を返すため、本来呼ばれない経路。
            # 誤って呼ばれた場合は架空個体を作らず失敗させる。
            raise ParsingError(
                f"{class_name}: 動物一覧を持たない案内ページのため詳細取得は行いません",
                url=virtual_url,
            )

        namespace["fetch_animal_list"] = fetch_animal_list_always_empty
        namespace["extract_animal_details"] = extract_animal_details_always_empty
    elif spec.empty_state_patterns:

        def fetch_animal_list_with_announcement_check(
            self: SinglePageTableAdapter,
        ) -> list[tuple[str, str]]:
            if self._html_cache is None:
                self._html_cache = self._http_get(self.site_config.list_url)
            html = self._html_cache
            if _is_announcement_page(html, spec.empty_state_patterns):
                return []
            # 想定外: 案内パターンに一致しないテンプレート変化。行も無ければ
            # silent failure を避けるため明示的に失敗させる (city_toyonaka 元実装)。
            rows = self._load_rows()
            if not rows:
                raise ParsingError(
                    "案内ページパターン未一致かつ行要素も見つかりません",
                    selector=self.ROW_SELECTOR,
                    url=self.site_config.list_url,
                )
            category = self.site_config.category
            return [(f"{self.site_config.list_url}#row={i}", category) for i in range(len(rows))]

        namespace["fetch_animal_list"] = fetch_animal_list_with_announcement_check
        # 判定ヘルパー単体を検証したいテスト向けに公開する (city_toyonaka 元実装の
        # `_is_announcement_page(html)` と同じシグネチャで spec のパターンを内包)。
        namespace["_is_announcement_page"] = staticmethod(
            lambda html, _patterns=spec.empty_state_patterns: _is_announcement_page(html, _patterns)
        )

    return type(class_name, (SinglePageTableAdapter,), namespace)


def build_adapter_class(
    spec: SiteSpec,
) -> type[WordPressListAdapter] | type[SinglePageTableAdapter]:
    """spec から動的 adapter class を構築する (未 instantiate)"""
    class_name = "Generic" + re.sub(r"\W", "", spec.names[0]) + "Adapter"
    if spec.mode == "list_detail":
        return _make_list_detail_class(spec, class_name)
    if spec.mode in ("table_horizontal", "table_vertical"):
        return _make_table_class(spec, class_name)
    raise ValueError(f"未知の mode: {spec.mode!r}")


def register_spec(spec: SiteSpec) -> None:
    """spec から adapter class を構築し、names 全てを Registry へ登録する

    サイト固有の bespoke adapter が既に同名で登録済みの場合は上書きしない
    (bespoke 優先の明示的な優先順位ルール)。
    """
    adapter_cls = build_adapter_class(spec)
    for name in spec.names:
        if SiteAdapterRegistry.get(name) is not None:
            logger.warning(
                "GenericAdapter: site '%s' は既に bespoke adapter が登録済みのため "
                "spec 経由の登録をスキップします",
                name,
            )
            continue
        SiteAdapterRegistry.register(name, adapter_cls)
