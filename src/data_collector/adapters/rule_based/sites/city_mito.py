"""水戸市動物愛護センター rule-based adapter

対象ドメイン: https://www.city.mito.lg.jp/site/doubutsuaigo/

特徴:
- 同一テンプレート (Mito City CMS) 上で 2 サイトを運用する:
    - https://www.city.mito.lg.jp/site/doubutsuaigo/list358.html
      (迷子ペット情報 / lost)
    - https://www.city.mito.lg.jp/site/doubutsuaigo/2043.html
      (愛護センター収容中の動物たち / sheltered)
- いずれも 1 ページに動物情報をまとめて掲載する single_page サイトで、
  個別 detail ページは存在しない。
- 配信状態によって 2 形態を取る:
    (a) 0 件状態 (本フィクスチャがこのケース): `div#main_body` 配下に
        `div.info_list ul li span.article_title a` のサブカテゴリ
        リンクのみが並び、動物テーブルは存在しない。
    (b) 動物が掲載されているとき: `div#main_body` 配下に `<table>` が
        並び、各 `<table>` 1 個が 1 動物に対応するラベル/値の縦並び形式。
- 0 件状態は `ParsingError` ではなく "0 件" として扱い、
  `fetch_animal_list` は空リストを返す (CityMachidaAdapter と同方針)。
- 動物種別 (犬/猫/その他) はサイト名から推定できないため、テーブル値から
  抽出する。サイト共通連絡先 (029-xxx-xxxx 等) は動物個別のフィールドに
  流入させない。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter

# 0 件状態の検出パターン:
# (a) 「現在、…の情報はありません」「いません」「おりません」等の告知文。
#     表記揺れ ("収容/保護/迷子" × "犬/猫/動物/ペット") を吸収する。
_EMPTY_STATE_TEXT_PATTERN = re.compile(
    r"(?:現在|今|ただ今)[^。]*?"
    r"(?:収容|保護|迷子|愛護)?[^。]*?"
    r"(?:動物|犬|猫|ペット)[^。]*?"
    r"(?:おりません|ありません|いません)"
)


class CityMitoAdapter(SinglePageTableAdapter):
    """水戸市動物愛護センター用 rule-based adapter

    同一テンプレート上で 2 サイト (迷子ペット情報 / 収容中の動物たち) を
    運用する single_page 形式。各動物は本文配下の `<table>` ブロックで
    表現される想定だが、配信状態としては 0 件 (サブカテゴリ案内のみの
    インデックスページ) も正常系として頻発するため、empty state を許容する。
    """

    # 本文 (`div#main_body`) 配下の `<table>` 1 個 = 1 動物。
    # ヘッダ/サイドバー等にも別 table が現れる可能性があるため
    # 本文コンテナに絞ってテンプレート要素を巻き込まないようにする。
    ROW_SELECTOR: ClassVar[str] = "div#main_body table"
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
        `ParsingError` を投げるが、水戸市サイトでは下記いずれかが正常な
        0 件状態として頻発する:

        - 本文に「現在、収容動物はありません。」等の告知文がある
        - 本文に動物テーブルが無く、サブカテゴリ案内 (info_list) のみが並ぶ
          (本フィクスチャがこのケース)

        いずれかに該当すれば空リストを返す。
        それ以外で行が見つからなかった場合のみ ParsingError を伝播する。
        """
        rows = self._load_rows()
        if not rows:
            if self._is_empty_state():
                # 「現在、収容動物はありません」or サブカテゴリ案内のみ
                return []
            raise ParsingError(
                "行要素が見つかりません",
                selector=self.ROW_SELECTOR,
                url=self.site_config.list_url,
            )
        category = self.site_config.category
        return [(f"{self.site_config.list_url}#row={i}", category) for i in range(len(rows))]

    def extract_animal_details(
        self, virtual_url: str, category: str = "sheltered"
    ) -> RawAnimalData:
        """1 個の `<table>` から RawAnimalData を構築する

        水戸市 CMS のテーブルは「項目名 / 値」が左右に並ぶ縦並び構造を
        想定する (CityMachidaAdapter と同等)。テーブル内の各 `<tr>` から
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
        # 水戸市 CMS の実テンプレート HTML が入手できていないため、
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
            "捕獲日": "shelter_date",
            "収容場所": "location",
            "保護場所": "location",
            "発見場所": "location",
            "捕獲場所": "location",
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
                shelter_date=fields.get("shelter_date", self.SHELTER_DATE_DEFAULT),
                location=fields.get("location", ""),
                phone="",
                image_urls=self._extract_row_images(table, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

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

    def _is_empty_state(self) -> bool:
        """0 件状態のページかを判定する

        以下のいずれかに該当するとき True:
        - 本文 (`div#main_body`) 内に告知文 (「現在…ありません」等) がある
        - 本文に `<table>` が無く、`div.info_list` (サブカテゴリ案内) が
          存在する (本フィクスチャがこのパターン)

        どちらでもない場合 False を返し、呼出側 (`fetch_animal_list`) で
        ParsingError を投げさせる。
        """
        if not self._html_cache:
            return False
        soup = BeautifulSoup(self._html_cache, "html.parser")
        main_body = soup.select_one("div#main_body")
        if main_body is None:
            # 本文コンテナ自体が無いのは想定外なので empty とは判定しない
            return False
        body_text = main_body.get_text(separator=" ", strip=True)
        if _EMPTY_STATE_TEXT_PATTERN.search(body_text):
            return True
        # 本文に table が無く、サブカテゴリ案内のみが並ぶインデックスページ
        has_table = main_body.find("table") is not None
        has_info_list = main_body.select_one("div.info_list") is not None
        if not has_table and has_info_list:
            return True
        return False

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫/その他) を推定する

        水戸市の 2 サイト名 (「迷子ペット情報」「愛護センター収容中の動物たち」)
        はいずれも犬/猫の明示が無いため通常は空文字を返し、テーブル値に
        フォールバックする。将来サイト名が変更され「犬」「猫」を含むように
        なった場合に備えた汎用ロジック。
        """
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return ""


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 2 サイトを同一 adapter にマップする。
# `sites.yaml` の `prefecture: 茨城県` かつ `city.mito.lg.jp` ドメイン。
for _site_name in (
    "水戸市（迷子ペット情報）",
    "水戸市（愛護センター収容中の動物たち）",
):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, CityMitoAdapter)
