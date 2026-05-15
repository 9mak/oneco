"""枚方市保健所 rule-based adapter

対象ドメイン: https://www.city.hirakata.osaka.jp/0000001430.html

特徴:
- 枚方市の CMS (mol_* クラスを使う molecule 系テンプレート) で
  運用されている収容動物情報ページ。
- 1 ページに「収容犬」「収容猫」の見出し (`<h4 class="block_index_X">`)
  が並び、その下に該当種別のカードが掲載される single_page 形式。
  detail ページは存在しないため、一覧から直接抽出する。
- 在庫 0 件のときは「掲載情報が無い場合でも、犬が行方不明になったら
  速やかに当課までご連絡ください。」のような告知文だけが表示され、
  動物カード相当の HTML は出現しない。これは正常状態として扱い、
  `fetch_animal_list` は ParsingError ではなく空リストを返す。
- 動物カードの構造はサイトの掲載パターンに依存するため、CMS の
  画像付き molecule (`div.mol_imageblock`) を ROW_SELECTOR とし、
  種別 (犬/猫) は直前の `<h4>` 見出しから推定する (CityKashiwaAdapter
  と同方針)。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


class CityHirakataAdapter(SinglePageTableAdapter):
    """枚方市保健所 (収容動物情報) 用 rule-based adapter

    `<h4 class="block_index_*">収容犬|収容猫</h4>` の下に並ぶ
    画像付きカード (`div.mol_imageblock`) を 1 動物として扱う
    single_page 形式。
    """

    # 各動物カードの起点 (CMS の画像 molecule)
    ROW_SELECTOR: ClassVar[str] = "div.mol_imageblock"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # `<p>ラベル：値</p>` 並びを直接スキャンするため
    # `COLUMN_FIELDS` は基底契約の充足のためだけに宣言する。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        0: "species",
        1: "sex",
        2: "color",
        3: "shelter_date",
        4: "location",
    }
    LOCATION_COLUMN: ClassVar[int | None] = 4
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # 「種別：雑種」のようなラベル → RawAnimalData フィールド名のマッピング
    _LABEL_TO_FIELD: ClassVar[dict[str, str]] = {
        "種類": "species",
        "種別": "species",
        "犬種": "species",
        "猫種": "species",
        "毛色": "color",
        "色": "color",
        "性別": "sex",
        "場所": "location",
        "収容場所": "location",
        "収容": "shelter_date",
        "収容日": "shelter_date",
        "保護日": "shelter_date",
        "発見日": "shelter_date",
        "年齢": "age",
        "推定年齢": "age",
        "体格": "size",
        "大きさ": "size",
        "体重": "size",
    }

    # 「掲載情報が無い場合でも、犬が行方不明になったら…」等の 0 件告知。
    # 枚方市テンプレートでは「掲載情報が無い」フレーズが必ず本文中に
    # 含まれるためこれを empty-state の signal とする。
    _EMPTY_STATE_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"掲載情報[がは]?(?:無|な)い"
    )

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """一覧ページから動物の仮想 URL を返す

        基底実装は行が 0 件のとき `ParsingError` を投げるが、枚方市の
        テンプレートでは「掲載情報が無い場合でも…」の告知文だけが
        出る正常な 0 件状態が発生し得る。本文に empty-state テキストを
        検出した場合は空リストを返し、それ以外で行が見つからなかった
        場合のみ `ParsingError` を伝播する。
        """
        rows = self._load_rows()
        if not rows:
            if self._html_cache and self._EMPTY_STATE_PATTERN.search(
                self._html_cache
            ):
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
        """1 個の `div.mol_imageblock` カードから RawAnimalData を構築する

        基底の `td/th` ベース実装は使わず、カード内 `<p>ラベル：値</p>`
        並びをスキャンする。species は直前の `<h4>収容犬</h4>` /
        `<h4>収容猫</h4>` 見出しを最優先で採用する。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        card = rows[idx]

        # カード内の <p> をスキャンしてラベル：値 を抽出
        fields: dict[str, str] = {}
        for p in card.find_all("p"):
            if not isinstance(p, Tag):
                continue
            text = p.get_text(separator=" ", strip=True)
            if not text:
                continue
            for sep in ("：", ":"):
                if sep in text:
                    label, value = text.split(sep, 1)
                    label = label.strip()
                    value = value.strip()
                    field = self._LABEL_TO_FIELD.get(label)
                    if field and value and field not in fields:
                        fields[field] = value
                    break

        # species: 直前の <h4>収容犬</h4>/<h4>収容猫</h4> を最優先
        species = self._infer_species_from_heading(card)
        if not species:
            species = self._infer_species_from_breed(fields.get("species", ""))

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
                image_urls=self._extract_row_images(card, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(
                f"RawAnimalData バリデーション失敗: {e}", url=virtual_url
            ) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _infer_species_from_heading(card: Tag) -> str:
        """カード直前の `<h4>` (または `<h3>`) 見出しから動物種別を推定する

        枚方市テンプレートでは `<h4 class="block_index_3">収容犬</h4>`
        と `<h4 class="block_index_5">収容猫</h4>` のような見出しの後に
        該当種別のカードが配置される。直前の h4/h3 を後方に辿って
        最初に見つかった「犬」「猫」を採用する。
        """
        for prev in card.find_all_previous(["h2", "h3", "h4"]):
            if not isinstance(prev, Tag):
                continue
            text = prev.get_text(strip=True)
            if "犬" in text:
                return "犬"
            if "猫" in text:
                return "猫"
            # h2 まで遡っても種別が見つからなければ打ち切り
            if prev.name == "h2":
                break
        return ""

    @staticmethod
    def _infer_species_from_breed(breed: str) -> str:
        """「種類」値 (柴犬/雑種/三毛猫等) から動物種別を推定する"""
        if not breed:
            return ""
        if "犬" in breed:
            return "犬"
        if "猫" in breed:
            return "猫"
        return ""


# ─────────────────── サイト登録 ───────────────────
# `sites.yaml` の `name: 枚方市（収容動物）` に対応する。
# 他テストが registry を clear するケースを考慮して冪等に登録する。
if SiteAdapterRegistry.get("枚方市（収容動物）") is None:
    SiteAdapterRegistry.register("枚方市（収容動物）", CityHirakataAdapter)
