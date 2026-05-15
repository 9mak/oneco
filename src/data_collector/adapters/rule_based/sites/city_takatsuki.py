"""高槻市保健所 rule-based adapter

対象ドメイン: https://www.city.takatsuki.osaka.jp/soshiki/39/2752.html

特徴:
- 高槻市保健所の「行方不明になった犬・猫の受付・照会」ページ。
  1 ページに犬・猫の収容情報がテーブル形式で並ぶ single_page 形式。
  個別 detail ページは存在しない。
- ページ本文は `div#main_body > div.detail_free` に集約され、その中に
  以下の複数 `<table>` がテンプレートとして並ぶ:
    1. 「お問い合わせ先」(高槻市保健所/警察署の電話番号)
    2. 動物情報用の枠 (本フィクスチャでは中身が空 `<tbody></tbody>`)
    3. 「返還手数料の内訳」
    4. 「必要な手数料額（例）」
  動物が収容されている時のみ、見出し
  「ここから、高槻市保健所に収容されている犬・猫の情報をご覧いただけます」
  以降に動物テーブルが現れる想定。
- 在庫 0 件のとき (本フィクスチャがこのケース) は本文に
  「現在、掲載する情報はありません。」の `<p>` のみが並び、
  動物テーブルは存在しない。これは正常な 0 件状態として扱い、
  `fetch_animal_list` は空リストを返す (CityMachidaAdapter 等と同方針)。
- お問い合わせ先・返還手数料テーブルはサイト共通テンプレート要素であり、
  動物個別の情報ではないため、`<table>` の見出しテキストで除外する。
- 動物種別 (犬/猫) はテーブル本文の値を優先し、
  得られない場合はサイト名 (「迷子犬猫」) からは推定不能のため空文字。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


class CityTakatsukiAdapter(SinglePageTableAdapter):
    """高槻市保健所用 rule-based adapter

    迷子犬猫の収容情報ページ (single_page 形式)。
    本文中の `<table>` のうち、お問い合わせ先・返還手数料といった
    テンプレート要素を除外し、残った動物テーブルを 1 件 = 1 動物として
    扱う。在庫 0 件のときは空リストを返す。
    """

    # `div.detail_free` 配下のテーブル全体を一旦集める。
    # ヘッダ・フッタ等の共通テンプレートを巻き込まないようスコープを絞る。
    # 実際の動物テーブルかどうかは fetch_animal_list で更にフィルタする。
    ROW_SELECTOR: ClassVar[str] = "div.detail_free table"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 値の取り出しはオーバーライドした `extract_animal_details` が
    # 「ラベル/値」縦並びレイアウトを直接スキャンするため
    # `COLUMN_FIELDS` は基底契約の充足のためだけに宣言する。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        0: "species",
        1: "color",
        2: "sex",
        3: "size",
        4: "shelter_date",
    }
    LOCATION_COLUMN: ClassVar[int | None] = None
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # 「現在、掲載する情報はありません。」等の 0 件告知パターン。
    # 高槻市は「掲載する情報はありません」が定型。表記揺れに備えて
    # 「収容/保護動物はおりません/いません」もカバーする。
    _EMPTY_STATE_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"(?:掲載する情報[^。]*?ありません"
        r"|(?:収容|保護)(?:動物|犬|猫)[^。]*?(?:おりません|ありません|いません))"
    )

    # 動物情報ではないテンプレートテーブルを判定するための見出しキーワード。
    # `<th>` / 1 行目セルにこれらが含まれていたら除外する。
    _TEMPLATE_TABLE_KEYWORDS: ClassVar[tuple[str, ...]] = (
        "お問い合わせ先",
        "返還手数料",
        "内訳",
        "金額",
        "手数料額",
    )

    # ラベル → RawAnimalData フィールド名のマッピング。
    # 高槻市の動物テーブル実 HTML が入手できていない (在庫 0 件のため)
    # ので、一般的な保健所の収容動物テーブルで想定される項目を網羅する。
    _LABEL_TO_FIELD: ClassVar[dict[str, str]] = {
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

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """動物リスト取得 (在庫 0 件でも ParsingError を出さない)

        基底実装は `<table>` が 0 件のとき `ParsingError` を投げるが、
        高槻市のテンプレートでは「現在、掲載する情報はありません。」と
        いう告知ページが正常状態として頻繁に発生する (フィクスチャも
        このケース)。empty state テキストを検出した場合は空リストを返し、
        テンプレートテーブル (お問い合わせ先 / 返還手数料 等) のみ残った
        場合も 0 件として扱う。
        """
        rows = self._load_rows()
        if not rows:
            if self._html_cache and self._EMPTY_STATE_PATTERN.search(
                self._html_cache
            ):
                # 「現在、掲載する情報はありません。」等の正常な 0 件状態
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
        self, virtual_url: str, category: str = "lost"
    ) -> RawAnimalData:
        """1 個の動物テーブルから RawAnimalData を構築する

        高槻市のテーブルは「ラベル / 値」が左右に並ぶ縦並び構造を想定
        (CityMachidaAdapter と同等)。テーブル内の各 `<tr>` から最後の
        セルを値、それ以前のいずれかのセルにラベルが含まれているもの
        として読み取る。
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
                for label, field in self._LABEL_TO_FIELD.items():
                    if field in fields:
                        continue
                    if label in label_text:
                        fields[field] = value_text
                        matched = True
                        break
                if matched:
                    break

        # species: テーブル値から推定 (具体名 → 犬/猫 への正規化)、
        # 取得できない場合はサイト名から推定 (高槻市の「迷子犬猫」では
        # 犬/猫の特定不可なので通常は空文字)。
        species_raw = fields.get("species", "")
        species = self._infer_species_from_breed(species_raw) or species_raw
        if not species:
            species = self._infer_species_from_site_name(self.site_config.name)

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
        """list_url の HTML を 1 回だけ取得し、動物テーブルのみキャッシュ

        基底実装と同等の挙動 (BeautifulSoup html.parser) に加え、
        以下を除外する:
          - 中身が空 (`<tr>` が 0 個) のテーブル
          - お問い合わせ先 / 返還手数料 等のテンプレートテーブル
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        soup = BeautifulSoup(self._html_cache, "html.parser")
        candidates = soup.select(self.ROW_SELECTOR)
        rows: list[Tag] = []
        for tbl in candidates:
            if not isinstance(tbl, Tag):
                continue
            trs = [tr for tr in tbl.find_all("tr") if isinstance(tr, Tag)]
            if not trs:
                # 空テーブル (動物枠だけ用意されているプレースホルダ)
                continue
            if self._is_template_table(tbl):
                # お問い合わせ先 / 返還手数料 等の共通テンプレート
                continue
            rows.append(tbl)
        if self.SKIP_FIRST_ROW and rows:
            rows = rows[1:]
        self._rows_cache = rows
        return rows

    @classmethod
    def _is_template_table(cls, table: Tag) -> bool:
        """テンプレートテーブル (お問い合わせ先 / 返還手数料 等) かを判定

        テーブル内の `<th>` セル、もしくは 1 行目のいずれかのセルに
        テンプレート用キーワードが含まれている場合に True。
        """
        # まず <th> を優先的に走査
        ths = [th for th in table.find_all("th") if isinstance(th, Tag)]
        for th in ths:
            text = th.get_text(separator="", strip=True)
            if any(kw in text for kw in cls._TEMPLATE_TABLE_KEYWORDS):
                return True
        # <th> が無い、もしくは見出しが一致しない場合は 1 行目セルを確認
        first_row = table.find("tr")
        if isinstance(first_row, Tag):
            for cell in first_row.find_all(["td", "th"]):
                if not isinstance(cell, Tag):
                    continue
                text = cell.get_text(separator="", strip=True)
                if any(kw in text for kw in cls._TEMPLATE_TABLE_KEYWORDS):
                    return True
        return False

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

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別を推定する (フォールバック)

        高槻市のサイト名「高槻市（迷子犬猫）」は犬/猫いずれも含むため
        単独で特定はできず、空文字を返す。将来サイト名が「迷子犬」
        「迷子猫」のように分割された場合に備えた汎用ロジック。
        """
        has_dog = "犬" in name
        has_cat = "猫" in name
        if has_dog and has_cat:
            return ""
        if has_dog:
            return "犬"
        if has_cat:
            return "猫"
        return ""


# ─────────────────── サイト登録 ───────────────────
# `sites.yaml` の `prefecture: 大阪府` かつ `city.takatsuki.osaka.jp` ドメイン。
for _site_name in ("高槻市（迷子犬猫）",):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, CityTakatsukiAdapter)
