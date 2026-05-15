"""町田市保健所 rule-based adapter

対象ドメイン: https://www.city.machida.tokyo.jp/iryo/hokenjo/pet/mayoi/

特徴:
- 同一テンプレート (Machida City CMS) 上で 3 サイトが運用されている:
    - https://www.city.machida.tokyo.jp/iryo/hokenjo/pet/mayoi/syuyou.html
      (収容動物のお知らせ)
    - https://www.city.machida.tokyo.jp/iryo/hokenjo/pet/mayoi/hogo.html
      (保護情報)
    - https://www.city.machida.tokyo.jp/iryo/hokenjo/pet/mayoi/pet_fumei/index.html
      (捜索：飼い主が探している)
- 1 ページに複数動物がテーブル形式で並ぶ single_page サイト。
  個別 detail ページは存在しない。
- 動物が収容/保護中のとき: `article` 配下の本文 `div.wysiwyg_wp` 内に
  `<table>` が並び、各 `<table>` 1 個が 1 動物に対応する想定。
- 動物が 0 件のとき (本フィクスチャがこのケース):
  「現在、収容動物はありません。」のような告知 `<p>` のみが本文に並ぶ。
  この状態は ParsingError ではなく "0 件" として扱い、
  `fetch_animal_list` は空リストを返す (PrefKyotoAdapter と同様の方針)。
- 動物種別 (犬/猫/その他) はサイト名上では明示されないため、
  テーブル値からの抽出を優先しサイト名は推定の補助に留める。
- 連絡先 (042-722-6727 等) は `aside.contact` のサイト共通連絡先で、
  動物個別のフィールドではないため RawAnimalData.phone へは流入させない。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


# 「現在、収容動物はありません。」「保護動物はおりません」等の 0 件告知パターン。
# 表記揺れ (おりません/ありません/いません) と「収容/保護」両方を吸収する。
_EMPTY_STATE_PATTERN = re.compile(
    r"(?:収容|保護)(?:動物|犬|猫)[^。]*?(?:おりません|ありません|いません)"
)


class CityMachidaAdapter(SinglePageTableAdapter):
    """町田市保健所用 rule-based adapter

    同一テンプレート上で 3 サイトを運用する single_page 形式。
    各動物は `article` 配下本文の `<table>` ブロックで表現される想定だが、
    日常的に 0 件状態となるため empty state を正常系として扱う。
    """

    # 本文 (`article`) 配下の `<table>` 1 個 = 1 動物。
    # ヘッダ・フッタ・サイドナビにも別 table を持つ可能性があるため
    # `article` に絞ることでテンプレート要素を巻き込まないようにする。
    ROW_SELECTOR: ClassVar[str] = "article table"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 値の取り出しはオーバーライドした `extract_animal_details` が
    # ラベル/値の縦並びレイアウトを直接スキャンするため
    # `COLUMN_FIELDS` は宣言のみ (基底契約の充足)。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        0: "species",
        1: "color",
        2: "sex",
        3: "size",
        4: "shelter_date",
    }
    LOCATION_COLUMN: ClassVar[int | None] = None
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """一覧ページから動物の仮想 URL を返す

        基底 `SinglePageTableAdapter.fetch_animal_list` は行が 0 件のとき
        `ParsingError` を投げるが、町田市サイトでは「現在、収容動物は
        ありません。」という告知ページが正常状態として頻繁に発生する
        (フィクスチャもこのケース)。
        empty state テキストを検出した場合は空リストを返し、
        それ以外で行が見つからなかった場合のみ ParsingError を伝播する。
        """
        rows = self._load_rows()
        if not rows:
            if self._html_cache and _EMPTY_STATE_PATTERN.search(self._html_cache):
                # 「現在、収容動物はありません」等の正常な 0 件状態
                return []
            raise ParsingError(
                "行要素が見つかりません",
                selector=self.ROW_SELECTOR,
                url=self.site_config.list_url,
            )
        category = self.site_config.category
        return [
            (f"{self.site_config.list_url}#row={i}", category)
            for i in range(len(rows))
        ]

    def extract_animal_details(
        self, virtual_url: str, category: str = "sheltered"
    ) -> RawAnimalData:
        """1 個の `<table>` から RawAnimalData を構築する

        町田市 CMS のテーブルは「項目名 / 値」が左右に並ぶ縦並び構造を
        想定する (PrefKyotoAdapter と同等)。テーブル内の各 `<tr>` から
        最後のセルを値、それ以前のいずれかのセルにラベルが含まれている
        ものとして読み取る。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        table = rows[idx]
        trs = [tr for tr in table.find_all("tr") if isinstance(tr, Tag)]

        # ラベル → RawAnimalData フィールド名のマッピング。
        # 町田市の実テンプレート HTML が入手できていないため、
        # 一般的な保護/収容動物テーブルで想定される項目を網羅的にマップする。
        label_to_field = {
            "種類": "species",
            "種別": "species",
            "犬種": "species",
            "猫種": "species",
            "毛色": "color",
            "毛の色": "color",
            "色": "color",
            "性別": "sex",
            "体格": "size",
            "大きさ": "size",
            "年齢": "age",
            "推定年齢": "age",
            "収容日": "shelter_date",
            "保護日": "shelter_date",
            "発見日": "shelter_date",
            "収容場所": "location",
            "保護場所": "location",
            "発見場所": "location",
            "場所": "location",
        }

        fields: dict[str, str] = {}
        for tr in trs:
            cells = [c for c in tr.find_all(["td", "th"]) if isinstance(c, Tag)]
            if len(cells) < 2:
                continue
            value_cell = cells[-1]
            value_text = value_cell.get_text(separator=" ", strip=True)
            value_text = re.sub(r"[ 　]+", " ", value_text).strip()
            for label_cell in cells[:-1]:
                label_text = label_cell.get_text(separator="", strip=True)
                matched = False
                for label, field in label_to_field.items():
                    if field in fields:
                        continue
                    if label in label_text:
                        fields[field] = value_text
                        matched = True
                        break
                if matched:
                    break

        # species: テーブル値を優先し、無ければサイト名から推定
        species = fields.get("species", "") or self._infer_species_from_site_name(
            self.site_config.name
        )

        try:
            return RawAnimalData(
                species=species,
                sex=fields.get("sex", ""),
                age=fields.get("age", ""),
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=fields.get(
                    "shelter_date", self.SHELTER_DATE_DEFAULT
                ),
                location=fields.get("location", ""),
                phone="",
                image_urls=self._extract_row_images(table, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(
                f"RawAnimalData バリデーション失敗: {e}", url=virtual_url
            ) from e

    # ─────────────────── ヘルパー ───────────────────

    def _load_rows(self) -> list[Tag]:
        """list_url の HTML を 1 回だけ取得して行をキャッシュ

        基底実装と同等の挙動 (BeautifulSoup html.parser)。
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        soup = BeautifulSoup(self._html_cache, "html.parser")
        rows = soup.select(self.ROW_SELECTOR)
        rows = [r for r in rows if isinstance(r, Tag)]
        if self.SKIP_FIRST_ROW and rows:
            rows = rows[1:]
        self._rows_cache = rows
        return rows

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫/その他) を推定する

        町田市の 3 サイト名はいずれも犬/猫の明示が無いため、
        通常は空文字を返す (テーブル値にフォールバック)。
        将来サイト名が変更され「犬」「猫」を含むようになった場合に備えた
        汎用ロジック。
        """
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return ""


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 3 サイトを同一 adapter にマップする。
# `sites.yaml` の `prefecture: 東京都` かつ `city.machida.tokyo.jp` ドメイン。
for _site_name in (
    "町田市（収容動物のお知らせ）",
    "町田市（保護情報）",
    "町田市（捜索：飼い主が探している）",
):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, CityMachidaAdapter)
