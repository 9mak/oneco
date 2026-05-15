"""船橋市動物愛護指導センター rule-based adapter

対象ドメイン: https://www.city.funabashi.lg.jp/kurashi/doubutsu/003/

特徴:
- 同一テンプレート上で 2 サイト (収容犬猫 / 譲渡可能犬猫) を運用しており、
  URL パターンのみが異なる:
    - .../003/p013242.html      (収容犬猫)
    - .../003/joutoindex.html   (譲渡可能犬猫)
- 1 ページに `<table>` 形式で動物情報が並ぶ single_page サイト。
  個別 detail ページは存在しない。
- テーブル構造 (1 行 = 1 頭, ヘッダ行 + データ行 N 件):
    <table style="width: 800; height: 96;">
      <caption>公示内容 ...</caption>
      <tbody>
        <tr> (ヘッダ)
          <th>番号</th><th>収容年月日</th><th>公示満了日</th>
          <th>収容場所</th><th>動物種</th><th>種類</th>
          <th>毛色</th><th>性別</th><th>体格</th><th>備考</th>
          <th>写真</th>
        </tr>
        <tr> (データ行 N 件)
          <td>{番号}</td><td>{収容年月日}</td><td>{公示満了日}</td>
          <td>{収容場所}</td><td>{動物種=犬|猫}</td><td>{種類}</td>
          <td>{毛色}</td><td>{性別}</td><td>{体格}</td><td>{備考}</td>
          <td><img src="..."></td>
        </tr>
      </tbody>
    </table>
- 収容数 0 件のときはテーブルにヘッダ行のみが残る。本 adapter は
  `SKIP_FIRST_ROW=True` でヘッダを除外し、結果として `fetch_animal_list` が
  空リストを返す (ParsingError は出さない)。
- 動物種別は HTML の「動物種」列に明示されている (犬 / 猫) ので、
  サイト名推定に頼らずそのまま使う。
"""

from __future__ import annotations

from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


class CityFunabashiAdapter(SinglePageTableAdapter):
    """船橋市動物愛護指導センター用 rule-based adapter

    収容犬猫 / 譲渡可能犬猫 の 2 サイトで共通テンプレートを使用する。
    `<table>` ヘッダ行 + データ行 N 件の single_page 形式。
    """

    # `boxEntryFreeform` 配下のテーブルの行のみを対象とする。
    # ページ内に他テーブルが追加された場合に備えてスコープを限定する。
    ROW_SELECTOR: ClassVar[str] = "div.boxEntryFreeform table tr"
    # 1 行目はヘッダ (`<th>`) なので除外
    SKIP_FIRST_ROW: ClassVar[bool] = True
    # 列インデックス → RawAnimalData フィールド名 のマッピング。
    # 列 0 (番号), 列 2 (公示満了日), 列 9 (備考), 列 10 (写真) は
    # RawAnimalData に対応するフィールドが無いため除外する。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        1: "shelter_date",  # 収容年月日
        3: "location",      # 収容場所
        4: "species",       # 動物種 (犬 / 猫)
        6: "color",         # 毛色
        7: "sex",           # 性別
        8: "size",          # 体格
    }
    LOCATION_COLUMN: ClassVar[int | None] = 3
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """テーブル行を仮想 URL に変換する

        収容数 0 件の場合 (ヘッダ行のみ) は空リストを返す。
        テーブル自体が存在しない場合は ParsingError。
        """
        # テーブルそのものが存在しない場合は明示的にエラー。
        # (rows のみで判断すると「ヘッダ行のみ」と区別できない)
        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)
        soup = BeautifulSoup(self._html_cache, "html.parser")
        if soup.select_one("div.boxEntryFreeform table") is None:
            raise ParsingError(
                f"テーブルが見つかりません",
                selector="div.boxEntryFreeform table",
                url=self.site_config.list_url,
            )

        rows = self._load_rows()
        # _load_rows は SKIP_FIRST_ROW=True によりヘッダ行を除外済み。
        # 結果が空 = データ行 0 件 (= 在庫 0 件) として正常扱いする。
        if not rows:
            return []
        category = self.site_config.category
        return [
            (f"{self.site_config.list_url}#row={i}", category)
            for i in range(len(rows))
        ]

    def extract_animal_details(
        self, virtual_url: str, category: str = "adoption"
    ) -> RawAnimalData:
        """テーブル行から RawAnimalData を構築する

        基底のセルベース既定実装に加え、画像列 (列 10) の絶対 URL 化と、
        動物種列 (列 4) を species にそのまま使う処理を行う。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        row = rows[idx]
        cells = row.find_all(["td", "th"])

        fields: dict[str, str] = {}
        for col_idx, field_name in self.COLUMN_FIELDS.items():
            if col_idx < len(cells):
                fields[field_name] = cells[col_idx].get_text(
                    separator=" ", strip=True
                )

        location = fields.get("location", "")
        # 「動物種」列はサイトによっては空欄や記号があり得るので、
        # 空のときはサイト名から推定する (フォールバック)。
        species = fields.get("species", "").strip()
        if not species:
            species = self._infer_species_from_site_name(self.site_config.name)

        try:
            return RawAnimalData(
                species=species,
                sex=fields.get("sex", ""),
                age="",
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=fields.get("shelter_date", self.SHELTER_DATE_DEFAULT),
                location=location,
                phone="",
                image_urls=self._extract_row_images(row, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(
                f"RawAnimalData バリデーション失敗: {e}", url=virtual_url
            ) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫/その他) を推定する

        船橋市の 2 サイトはどちらも「犬猫」を含むので確定はできないが、
        HTML の動物種列が空のときの最終フォールバックとして "犬" を返す。
        """
        if "犬猫" in name:
            return "犬"
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return "その他"


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 2 サイトを同一 adapter にマップする。
for _site_name in (
    "船橋市（収容犬猫）",
    "船橋市（譲渡可能犬猫）",
):
    SiteAdapterRegistry.register(_site_name, CityFunabashiAdapter)
