"""GenericAdapter を駆動する per-site YAML spec のロード (T405)

`src/data_collector/config/site_specs/<slug>.yaml` を読み込み、`SiteSpec`
データクラスへパースする。1 ファイルが複数の `names` (同一テンプレートを
共有する複数 sites.yaml エントリ) を束ねられる (例: douaicenter の 8 サイト)。

`sites.yaml` を汚さない設計のため、`fields`/`phone`/`requires_js` のような
既存の site 単位設定は引き続き sites.yaml 側に残し、本 spec は「DOM から
どう抜くか」だけを持つ。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from .base import FieldSpec

logger = logging.getLogger(__name__)

_SPEC_DIR = Path(__file__).resolve().parents[2] / "config" / "site_specs"

Mode = Literal["list_detail", "table_horizontal", "table_vertical"]


@dataclass(frozen=True)
class SpeciesRule:
    """species 補完ルール

    strategy:
        - "literal": 常に `value` を使う
        - "from_url": list_url の dog/cat 系ヒントで補完 (species が犬/猫
          キーワードを含まない場合のみ)。`generic_transforms.
          species_from_list_url_dog_cat` に委譲する。
        - "from_site_name": サイト名に「犬」「猫」を含むかで判定
        - "none": 何もしない (FIELD_SELECTORS の抽出結果をそのまま使う)
    """

    strategy: Literal["literal", "from_url", "from_site_name", "none"] = "none"
    value: str = ""


@dataclass(frozen=True)
class SiteSpec:
    """1 テンプレート分の抽出仕様。複数 site 名 (`names`) で共有できる。"""

    names: tuple[str, ...]
    mode: Mode
    # list_detail
    list_link_selector: str = ""
    image_selector: str = "img"
    link_exclude_markers: tuple[str, ...] = ()
    # 画像 URL フィルタ戦略。"" = 基底の _filter_image_urls (wp-content/uploads
    # 前提) をそのまま使う。"exclude_no_filename" = 末尾が "/" で終わる
    # (ファイル名が無い) URL を除外する (douai_pref_tochigi_stray のダミー画像対策)。
    image_filter: str = ""
    # True の場合、一覧取得中の例外を握りつぶして空リストを返す
    # (toyohashi_aikuru の元実装と同じ挙動。他サイトでは既定 False =
    # NetworkError 等をそのまま伝播させ broken_sites 追跡に乗せる)。
    swallow_list_errors: bool = False
    # table_*
    row_selector: str = ""
    header_fields: dict[str | tuple[str, ...], str] = field(default_factory=dict)
    column_fields: dict[int, str] = field(default_factory=dict)
    skip_first_row: bool = False
    location_column: int | None = None
    shelter_date_default: str = ""
    # 共通ページ送り
    next_page_selector: str = ""
    max_list_pages: int = 10
    # フィールド抽出 (label -> FieldSpec)
    field_selectors: dict[str, FieldSpec] = field(default_factory=dict)
    species: SpeciesRule = field(default_factory=SpeciesRule)
    postprocess: tuple[str, ...] = ()
    # 掲載 0 件が正常なページ (案内/ハブページ) の判定。
    # 空タプル = 常に基底の抽出フローに従う。
    # 非空 = 判定用の正規表現パターン群 (OR)。1 つでもタイトル/h1/h2 に
    # マッチしたら 0 件として扱う。
    empty_state_patterns: tuple[str, ...] = ()
    # empty_state_patterns が 1 つも無くても常に 0 件を返す (ページ生存確認
    # だけ行い、動物一覧を持たないことが判明済みのサイト用)。
    always_empty: bool = False


def _parse_field_spec(raw: dict[str, Any] | str) -> FieldSpec:
    if isinstance(raw, str):
        return FieldSpec(label=raw)
    label = raw.get("label")
    if isinstance(label, list):
        label = tuple(label)
    return FieldSpec(
        label=label,
        selector=raw.get("selector"),
        attr=raw.get("attr", "text"),
    )


def _parse_header_key(raw_key: str | list[str]) -> str | tuple[str, ...]:
    if isinstance(raw_key, list):
        return tuple(raw_key)
    return raw_key


def _load_spec_file(path: Path) -> SiteSpec:
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    names = raw["names"]
    if isinstance(names, str):
        names = [names]

    field_selectors = {
        name: _parse_field_spec(spec) for name, spec in (raw.get("field_selectors") or {}).items()
    }
    header_fields_raw = raw.get("header_fields") or {}
    header_fields = {_parse_header_key(k): v for k, v in header_fields_raw.items()}
    column_fields_raw = raw.get("column_fields") or {}
    column_fields = {int(k): v for k, v in column_fields_raw.items()}

    species_raw = raw.get("species") or {}
    species = SpeciesRule(
        strategy=species_raw.get("strategy", "none"),
        value=species_raw.get("value", ""),
    )

    return SiteSpec(
        names=tuple(names),
        mode=raw["mode"],
        list_link_selector=raw.get("list_link_selector", ""),
        image_selector=raw.get("image_selector", "img"),
        link_exclude_markers=tuple(raw.get("link_exclude_markers") or ()),
        image_filter=raw.get("image_filter", ""),
        swallow_list_errors=bool(raw.get("swallow_list_errors", False)),
        row_selector=raw.get("row_selector", ""),
        header_fields=header_fields,
        column_fields=column_fields,
        skip_first_row=bool(raw.get("skip_first_row", False)),
        location_column=raw.get("location_column"),
        shelter_date_default=raw.get("shelter_date_default", ""),
        next_page_selector=raw.get("next_page_selector", ""),
        max_list_pages=int(raw.get("max_list_pages", 10)),
        field_selectors=field_selectors,
        species=species,
        postprocess=tuple(raw.get("postprocess") or ()),
        empty_state_patterns=tuple(raw.get("empty_state_patterns") or ()),
        always_empty=bool(raw.get("always_empty", False)),
    )


def load_all_specs(spec_dir: Path | None = None) -> list[SiteSpec]:
    """`config/site_specs/*.yaml` を全て読み込む"""
    directory = spec_dir or _SPEC_DIR
    if not directory.is_dir():
        return []
    specs = []
    for path in sorted(directory.glob("*.yaml")):
        try:
            specs.append(_load_spec_file(path))
        except Exception:
            # 1 ファイルの破損で collector 全体の import を落とさない。
            # 該当 spec だけ ERROR で記録してスキップし、他 spec は生かす。
            logger.exception("site spec の読み込みに失敗しました (skip): %s", path)
            continue
    return specs
