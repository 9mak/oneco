"""福島県動物愛護センター rule-based adapter

対象ドメイン: https://www.pref.fukushima.lg.jp/sec/21620a/
（福島県動物愛護センター 中通り（本所）/会津/相双 各支所）

特徴:
- 同一テンプレート上で 6 サイト
  (中通り/会津/相双 × 迷子犬/迷子猫) を運用しており、
  URL パスのみが異なる single_page 形式。
- 1 ページに `<table>` が複数並び、各テーブル 1 個が 1 動物に相当する。
- テーブル内は 2 列構成 (左: ラベル, 右: 値):
    保護日 (管理番号)   令和8年4月28日（火曜日）（n080428-1）
    保護場所             伊達市梁川町広瀬町
    種類／体格           雑／中
    毛の色／長さ         茶白／中
    性別                 メス
    推定年月齢           6歳
    装着品               なし
    その他の特徴等       ...
  最終行は 1 列で写真 (`<img>` 複数枚) のみが入る。
- ラベル文字列にはサイト/動物ごとに以下の表記揺れがある:
    "保護日 (管理番号)" / "保護日（管理番号）"
    "種類／体格"        / "種類/体格"
    "毛の色／長さ"      / "毛の色/長さ"
    "その他の特徴等"    / "その他特徴等"
  そのためインデックスではなくラベル正規化キーでフィールドを引く。
- 動物種別 (犬/猫) はページ HTML 上に明示されないため、
  サイト名 (例: "福島県（中通り 迷子犬）") から推定する。
- 「迷子情報」ページなのにテーブル上は "保護日" と表記されているため、
  保護日 = shelter_date として扱う。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


def _normalize_label(label: str) -> str:
    """ラベル文字列を比較用に正規化する

    全角/半角の括弧・スラッシュ・各種空白 (全角空白/&nbsp;/通常空白) を
    取り除いた素のキー文字列を返す。
    """
    # &nbsp; ( )、全角空白 (　)、通常空白を全て除去
    text = re.sub(r"[\s 　]+", "", label)
    # 半角/全角スラッシュ、半角/全角括弧の差を吸収
    text = text.replace("／", "/").replace("（", "(").replace("）", ")")
    return text


# 正規化済みラベル -> RawAnimalData フィールド名へのマッピング
_LABEL_FIELD_MAP: dict[str, str] = {
    "保護日(管理番号)": "shelter_date",
    "保護場所": "location",
    "種類/体格": "species_size",  # "雑／中" のような複合値、後でパース
    "毛の色/長さ": "color",  # "茶白／中" の前半を毛色として採用
    "毛の色/毛の長さ": "color",  # 中通り猫等で見られる表記揺れ
    "性別": "sex",
    "推定年月齢": "age",
    "装着品": "equipment",  # 直接マップ先は無いが取り出しておく
    "首輪": "equipment",  # 中通り猫等で見られる表記揺れ
    "その他の特徴等": "note",
    "その他特徴等": "note",
}


# 空プレースホルダー判定に使う「主要フィールド」のラベル正規化キー。
# サイト側が雛形だけ並べて実データがまだ入っていない table を除外する。
# 実例 (2026-06 確認):
# - maigo-dog-miharu.html の row=0/row=2 (管理番号 n08-1 / s--1 等)
# - maigo-cat-miharu.html の row=0/row=1 (保護場所が "地内" のみ等)
# - maigo-cat-soso.html の table 0、maigo-dog-aizu.html の唯一の table
#   (全 9〜10 個の table が完全に空のテンプレ)
# これらをそのまま動物データとして取り込むと、location/sex/age/color/size が
# 全件 None の偽レコードが大量発生する (snapshot で 13 件中 9〜10 件)。
_REQUIRED_NONEMPTY_LABELS: tuple[str, ...] = (
    "保護場所",
    "性別",
    "種類/体格",
    "毛の色/長さ",
    "毛の色/毛の長さ",
)
# 主要ラベルのうち最低この数の実値が無いとプレースホルダー扱い。
# 実データの table はだいたい 4〜5 個全部入る一方、プレースホルダーは
# 0〜1 個しか実値が無い (= "地内" だけ残った雛形等) ため 2 が安全な閾値。
_MIN_NONEMPTY_FIELDS: int = 2
# 値セルがこの集合に含まれる場合 (区切り文字/全角空白のみ等の雛形) は空扱い
_PLACEHOLDER_VALUE_RE = re.compile(r"^[\s 　/／\-ー－]*$")


_SITE_PHONE_MAP: dict[str, str] = {
    # 福島県動物愛護センター本所（中通り） 024-953-6400
    "福島県（中通り 迷子犬）": "024-953-6400",
    "福島県（中通り 迷子猫）": "024-953-6400",
    # 福島県動物愛護センター会津支所 0242-29-5517
    "福島県（会津 迷子犬）": "0242-29-5517",
    "福島県（会津 迷子猫）": "0242-29-5517",
    # 福島県動物愛護センター相双支所 0244-26-1351
    "福島県（相双 迷子犬）": "0244-26-1351",
    "福島県（相双 迷子猫）": "0244-26-1351",
}


class PrefFukushimaAdapter(SinglePageTableAdapter):
    """福島県動物愛護センター用 rule-based adapter

    中通り(本所) / 会津 / 相双 × 迷子犬 / 迷子猫 の 6 サイトで共通テンプレート。
    各動物は `<table>` 単位で表現され、同一ページ内に複数 table が並ぶ。
    """

    # main_body 配下の table 1 個 = 1 動物。
    # ページ全体で <table> が他に出ないため、安全側で main_body 配下に絞る。
    ROW_SELECTOR: ClassVar[str] = "div#main_body table"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 基底の cells ベース既定実装は使わない (ラベルベース抽出のため)。
    # 契約として宣言だけしておく。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    LOCATION_COLUMN: ClassVar[int | None] = None
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """基底の `_load_rows` を呼び、空プレースホルダー table を除外する

        実サイトの 6 ページのうち多くは「テンプレートだけ並んでおり値が
        全部空」の table を残しており、これを無条件に取り込むと
        sex/age/color/size/location が全て None の偽レコードが大量に
        生成される (snapshot で 13 件中 10 件以上)。
        fetch_animal_list の段階で空 table を返さなくなり、
        `extract_animal_details` は実データ table のみを相手にする。
        """
        rows = super()._load_rows()
        filtered = [t for t in rows if not self._is_empty_placeholder_table(t)]
        # キャッシュも上書きしておく (二重フィルタを避ける)
        self._rows_cache = filtered
        return filtered

    @classmethod
    def _is_empty_placeholder_table(cls, table: Tag) -> bool:
        """値が実質的に空のテンプレート table か判定する

        判定基準:
        - 2 列構成 (`<td>` * 2) の `<tr>` が 1 行も無ければ空とみなす。
        - 主要ラベル ("保護場所" / "性別" / "種類/体格" / "毛の色/長さ" 等)
          の値セルのうち、実値 (区切り文字/空白のみではない値) が
          `_MIN_NONEMPTY_FIELDS` 個未満なら空プレースホルダーとみなす。
        """
        label_to_value: dict[str, str] = {}
        has_two_col_row = False
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 2:
                continue
            has_two_col_row = True
            label_raw = tds[0].get_text(separator="", strip=True)
            value = tds[1].get_text(separator=" ", strip=True)
            key = _normalize_label(label_raw)
            label_to_value[key] = value

        if not has_two_col_row:
            # 値セルが一つも無い (相双猫 table 1-4 等) → 空とみなす
            return True

        nonempty_count = 0
        for label in _REQUIRED_NONEMPTY_LABELS:
            value = label_to_value.get(label, "")
            if value and not _PLACEHOLDER_VALUE_RE.match(value):
                nonempty_count += 1

        return nonempty_count < _MIN_NONEMPTY_FIELDS

    def extract_animal_details(self, virtual_url: str, category: str = "lost") -> RawAnimalData:
        """1 個の `<table>` から RawAnimalData を構築する

        各 `<tr>` の最初の `<td>` をラベル、2 番目の `<td>` を値として読み出し、
        正規化したラベル文字列で `_LABEL_FIELD_MAP` を引く。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        table = rows[idx]

        fields: dict[str, str] = {}
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 2:
                # 写真のみの行 (colspan=2) や空行はスキップ
                continue
            label_raw = tds[0].get_text(separator="", strip=True)
            value = tds[1].get_text(separator=" ", strip=True)
            # &nbsp; や全角空白の末尾混入を除去
            value = re.sub(r"[ 　]+", " ", value).strip()
            key = _normalize_label(label_raw)
            field = _LABEL_FIELD_MAP.get(key)
            if field is not None:
                fields[field] = value

        # "種類／体格" → 種類部分のみ取り出して species 判定の補強に使う
        # ただし species は最終的にサイト名 (犬/猫) で決定する
        species_size = fields.get("species_size", "")
        size = ""
        if "／" in species_size or "/" in species_size:
            parts = re.split(r"[／/]", species_size, maxsplit=1)
            if len(parts) == 2:
                size = parts[1].strip()

        # "毛の色／長さ" → 前半のみを color として採用
        color_raw = fields.get("color", "")
        color = color_raw
        if "／" in color_raw or "/" in color_raw:
            color = re.split(r"[／/]", color_raw, maxsplit=1)[0].strip()

        species = self._infer_species_from_site_name(self.site_config.name)

        # 支所別の代表電話を注入する。サイト名が _SITE_PHONE_MAP に
        # 無い場合は phone を空のままにし、誤った番号が出ることを防ぐ。
        phone_raw = _SITE_PHONE_MAP.get(self.site_config.name, "")
        phone = self._normalize_phone(phone_raw) if phone_raw else ""

        try:
            return RawAnimalData(
                species=species,
                sex=fields.get("sex", ""),
                age=fields.get("age", ""),
                color=color,
                size=size,
                shelter_date=fields.get("shelter_date", self.SHELTER_DATE_DEFAULT),
                location=fields.get("location", ""),
                phone=phone,
                image_urls=self._extract_row_images(table, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫) を推定する"""
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return "その他"


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 6 サイトを同一 adapter にマップする。
for _site_name in (
    "福島県（中通り 迷子犬）",
    "福島県（中通り 迷子猫）",
    "福島県（会津 迷子犬）",
    "福島県（会津 迷子猫）",
    "福島県（相双 迷子犬）",
    "福島県（相双 迷子猫）",
):
    SiteAdapterRegistry.register(_site_name, PrefFukushimaAdapter)
