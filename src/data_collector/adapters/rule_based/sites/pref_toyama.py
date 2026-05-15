"""富山県（迷い犬・ねこ情報）rule-based adapter

対象ドメイン: https://www.pref.toyama.jp/1207/kurashi/seikatsu/seikatsu/doubutsuaigo/syuyou/

特徴:
- 富山県公式サイト (`pref.toyama.jp`) の県 CMS テンプレートを使用する
  single_page サイト。
- 一覧 URL (`/1207/.../syuyou/index.html`) は実体としては「各厚生センター・支所
  へのリンクを並べた窓口インデックスページ」であり、動物個別の収容情報は
  ここには掲載されない (各支所の子ページ niikawa.html / tyubu.html /
  takaoka.html / tonami.html / 各支所 etc. に分散している)。
- 本フィクスチャの本文 (`#tmp_main`) では、`table.datatable` の中に
  各厚生センター名の `<a>` リンクが並ぶだけで、動物データを含む
  「ラベル/値」の縦並びテーブルは存在しない。
- この状態を rule-based adapter としては正常な「0 件」として扱う必要があり、
  基底 `SinglePageTableAdapter.fetch_animal_list` の素のままだと
  `ParsingError("行要素が見つかりません")` が投げられてしまうため、
  `fetch_animal_list` を override してインデックスページ判定を行い、
  該当時は空リストを返す (CityMitoAdapter / CityMachidaAdapter と同方針)。
- 将来、子ページ単体を adapter 化することは別途検討する (現状は 0 件状態の
  index ページに対する正常終了の保証がスコープ)。
- 動物個別データを抽出する経路 (`extract_animal_details`) は、万一将来この
  ページに動物テーブルが直接掲載されるようになった場合に備えて、
  「ラベル/値」の縦並びテーブルから RawAnimalData を構築する汎用ロジックを
  実装しておく (CityMitoAdapter と同等の構造)。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


# 0 件状態の検出用テキストパターン
# 富山県のインデックスページには「各厚生センター・支所で保護している
# 迷い犬・ねこの情報を掲載しています」等の案内文があり、本文に動物テーブルが
# 無い (= 子ページに誘導するだけ) のが通常の運用。明示的な「現在おりません」
# 文言は無いケースが多いため、案内文の存在を 0 件のシグナルとして使う。
_INDEX_GUIDANCE_TEXT_PATTERN = re.compile(
    r"(?:各厚生センター|厚生センター|支所)[^。]*?"
    r"(?:迷い犬|迷子|保護|収容|情報)"
)

# 一般的な「現在 N 件は無い」告知文のパターン (将来別ページで使われた場合用)
_EMPTY_STATE_TEXT_PATTERN = re.compile(
    r"(?:現在|今|ただ今)[^。]*?"
    r"(?:収容|保護|迷子|愛護)?[^。]*?"
    r"(?:動物|犬|猫|ペット|情報)[^。]*?"
    r"(?:おりません|ありません|いません)"
)


class PrefToyamaAdapter(SinglePageTableAdapter):
    """富山県（迷い犬・ねこ情報）用 rule-based adapter

    `pref.toyama.jp` の県 CMS で運用される single_page サイト。
    本文 (`div#tmp_main`) 配下の `<table>` 1 個 = 1 動物 を想定するが、
    実態は厚生センター・支所への窓口リンク (`table.datatable` の中に
    `<a>` 並び) のみが掲載されたインデックスページであり、その状態を
    正常な 0 件として扱う。
    """

    # 本文 (`div#tmp_main`) 配下の `<table>` を行候補とする。
    # ただし `table.datatable` (= 各厚生センター窓口リンクの一覧) は
    # 動物テーブルではないため `_load_rows()` で除外する。
    ROW_SELECTOR: ClassVar[str] = "div#tmp_main table"
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

        富山県の `/1207/.../syuyou/index.html` は、各厚生センター・支所への
        窓口リンクを並べたインデックスページであり、動物個別の収容情報は
        含まないのが通常運用。本実装では:

        - 本文 (`#tmp_main`) 配下に動物テーブルが見つからない、かつ
        - 案内文 (「各厚生センター…情報」 or 「現在…ありません」) が確認できる

        場合に空リストを返し、それ以外で行が見つからなかった場合のみ
        基底実装と同じく `ParsingError` を伝播する。
        """
        rows = self._load_rows()
        if not rows:
            if self._is_empty_state():
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
        """1 個の `<table>` から RawAnimalData を構築する

        富山県 CMS の動物テーブルは「項目名 / 値」が左右に並ぶ縦並び構造を
        想定する (CityMitoAdapter と同等の汎用ロジック)。各 `<tr>` から
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
        # 富山県 CMS の動物個別ページが入手できていないため、
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

        # species: テーブル値を優先し、無ければサイト名から推定 (空可)
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
        """list_url の HTML を 1 回だけ取得して動物テーブル行をキャッシュ

        基底実装と同等だが、富山県インデックスページの「厚生センター窓口
        リンク一覧」(`table.datatable` および `<a>` だけを含むテーブル) は
        動物テーブルではないため除外する。
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        soup = BeautifulSoup(self._html_cache, "html.parser")
        candidates = soup.select(self.ROW_SELECTOR)
        candidates = [t for t in candidates if isinstance(t, Tag)]

        rows: list[Tag] = []
        for table in candidates:
            if self._is_office_link_table(table):
                # 厚生センター窓口の一覧 (動物テーブルではない) は除外
                continue
            if self._is_layout_table(table):
                # 内部にさらに table を抱えるレイアウト用テーブルや、
                # セル内容が画像 + 入れ子テーブルだけの装飾テーブルは
                # 動物データではないため除外
                continue
            # 動物テーブルは「ラベル/値」の <tr> を 1 行以上含む想定。
            # 値の無いリンクのみのテーブルや、ヘッダ行 (<th> のみ) しか
            # 存在しないテーブルも動物データではないため除外する。
            if not self._has_data_rows(table):
                continue
            rows.append(table)

        if self.SKIP_FIRST_ROW and rows:
            rows = rows[1:]
        self._rows_cache = rows
        return rows

    @staticmethod
    def _is_office_link_table(table: Tag) -> bool:
        """テーブルが「厚生センター窓口リンクの一覧」かを判定する

        以下のいずれか:
        - `class="datatable"` が付与されている (本フィクスチャで使用)
        - 内部の `<td>` セルがほぼ全てリンク (`<a>`) で構成されている
        """
        cls = table.get("class")
        if cls and "datatable" in cls:
            return True
        tds = [td for td in table.find_all("td") if isinstance(td, Tag)]
        if not tds:
            return False
        link_only = sum(
            1
            for td in tds
            if td.find("a") is not None
            and not td.get_text(strip=True).replace(
                td.find("a").get_text(strip=True), ""
            ).strip()
        )
        # 全 td がリンクのみで構成されていれば窓口テーブルとみなす
        return link_only == len(tds)

    @staticmethod
    def _is_layout_table(table: Tag) -> bool:
        """テーブルがレイアウト目的 (動物データではない) かを判定する

        富山県 CMS では「マップ画像 + 厚生センター窓口リンクテーブル」を
        並べるためにラッパー `<table>` が使われている。本判定では:

        - 内部に別の `<table>` を抱えるテーブル (ネスト構造のラッパー) は
          動物データではないとみなす。
        - セルが画像のみ / リンクのみ / 入れ子テーブルのみで構成され
          意味のあるテキスト値が無いテーブルもレイアウト用とみなす。
        """
        # 入れ子テーブルがあればレイアウト目的
        if table.find("table") is not None:
            return True
        return False

    @staticmethod
    def _has_data_rows(table: Tag) -> bool:
        """テーブルが「ラベル/値」の縦並びデータ行を含むかを判定する

        いずれかの `<tr>` が `<td>` を 2 セル以上持つことを期待する。
        ヘッダ行 (`<th>` のみ) や、リンクだけを並べた `<td>` 1 セルの
        テーブルでは False を返す。
        """
        for tr in table.find_all("tr"):
            if not isinstance(tr, Tag):
                continue
            cells = [c for c in tr.find_all(["td", "th"]) if isinstance(c, Tag)]
            if len(cells) >= 2:
                return True
        return False

    def _is_empty_state(self) -> bool:
        """0 件状態のページかを判定する

        以下のいずれかに該当するとき True:
        - 本文 (`div#tmp_main`) 内に厚生センター窓口の案内文がある
          (本フィクスチャがこのパターン)
        - 本文に「現在…おりません/ありません」等の告知文がある
        - 本文に動物テーブルが無く、`table.datatable` (窓口リンク一覧) が
          存在する

        どちらでもない場合 False を返し、呼出側 (`fetch_animal_list`) で
        ParsingError を投げさせる。
        """
        if not self._html_cache:
            return False
        soup = BeautifulSoup(self._html_cache, "html.parser")
        main_body = soup.select_one("div#tmp_main")
        if main_body is None:
            # 本文コンテナ自体が無いのは想定外なので empty とは判定しない
            return False
        body_text = main_body.get_text(separator=" ", strip=True)
        if _EMPTY_STATE_TEXT_PATTERN.search(body_text):
            return True
        if _INDEX_GUIDANCE_TEXT_PATTERN.search(body_text):
            return True
        # 本文に動物テーブルが無く、窓口リンク一覧 (datatable) のみが並ぶ
        # インデックスページ
        has_office_table = (
            main_body.select_one("table.datatable") is not None
        )
        if has_office_table:
            return True
        return False

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫/その他) を推定する

        富山県のサイト名は「富山県（迷い犬・ねこ情報）」のように犬と猫を
        併記する形なので通常は空文字を返し、テーブル値にフォールバックする。
        """
        has_dog = "犬" in name
        has_cat = "猫" in name or "ねこ" in name
        if has_dog and not has_cat:
            return "犬"
        if has_cat and not has_dog:
            return "猫"
        return ""


# ─────────────────── サイト登録 ───────────────────
# sites.yaml の `name` フィールドに完全一致させる。
# (`prefecture: 富山県` かつ `pref.toyama.jp` ドメインのサイト)
_SITE_NAME = "富山県（迷い犬猫情報）"
if SiteAdapterRegistry.get(_SITE_NAME) is None:
    SiteAdapterRegistry.register(_SITE_NAME, PrefToyamaAdapter)
