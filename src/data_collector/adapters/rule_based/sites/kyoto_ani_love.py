"""京都動物愛護センター rule-based adapter

対象ドメイン: https://kyoto-ani-love.com/

特徴:
- 同一テンプレート上で 2 サイト (迷子犬 / 迷子猫) が運用されており、
  URL のみ異なる single_page 形式:
    - https://kyoto-ani-love.com/lost-animal/dog/  (迷子犬, lost)
    - https://kyoto-ani-love.com/lost-animal/cat/  (迷子猫, lost)
- 一覧ページの本文 (`div.information-care-lost-content`) 配下に
  `<div class="content">` カードが並び、各カード内の
  `<table class="info">` が 1 動物に対応する。
- カード構造の例:
    <div class="content">
      <h2>３月１７日保護犬</h2>
      <table class="info">
        <tr><th>受入日</th><td>３月１７日</td></tr>
        <tr><th>保護日</th><td>３月１７日</td></tr>
        <tr><th>保護場所</th><td>南区西九条比永城町</td></tr>
        <tr><th>品種</th><td>柴</td></tr>
        <tr><th>毛色</th><td>茶</td></tr>
        <tr><th>性別</th><td>オス</td></tr>
        <tr><th>推定年齢</th><td>成犬</td></tr>
        <tr><th>体格</th><td>中</td></tr>
      </table>
      <h3>備考</h3>
      <div class="note clearfix"><p>首輪等なし</p></div>
    </div>
- 動物種別 (犬/猫) は HTML 上にラベルとして明示されておらず、
  サイト名 (例: "京都市ペットラブ（迷子犬）") から推定する。
- 0 件状態: 現在保護中の動物が居ないとき本文に table が並ばないため、
  本 adapter では行 0 件を在庫 0 件として空リストで返し ParsingError は
  投げない方針とする (在庫 0 件可の制約に準拠)。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


class KyotoAniLoveAdapter(SinglePageTableAdapter):
    """京都動物愛護センター用 rule-based adapter

    迷子犬 / 迷子猫 の 2 サイトで共通テンプレート。
    各動物は `div.information-care-lost-content` 内の
    `div.content > table.info` で表現される single_page 形式。
    """

    # 本文配下の各カード内 `<table class="info">` 1 個 = 1 動物。
    # 本文 div に絞ることで、ヘッダ/サイドバー等の他 table を巻き込まない。
    ROW_SELECTOR: ClassVar[str] = "div.information-care-lost-content div.content table.info"
    # 各テーブルが 1 件分のためヘッダ行除外は不要
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 値の取り出しはオーバーライドした `extract_animal_details` が
    # ラベル一致でスキャンするため `COLUMN_FIELDS` は契約上の宣言のみ。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    LOCATION_COLUMN: ClassVar[int | None] = None
    # 受入日 / 保護日はカード内に存在するため空文字をデフォルトにしておく
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # `<th>` ラベル → RawAnimalData フィールド名のマッピング。
    # 同義ラベル (品種/犬種/猫種、保護日/受入日 等) を網羅する。
    # 同一フィールドに複数候補がある場合は最初に見つかったものを採用する。
    LABEL_FIELDS: ClassVar[dict[str, str]] = {
        # 場所
        "保護場所": "location",
        "収容場所": "location",
        "発見場所": "location",
        # 品種 (=種類詳細)。species 推定はサイト名優先、HTML 値はフォールバック。
        "品種": "species_detail",
        "犬種": "species_detail",
        "猫種": "species_detail",
        "種類": "species_detail",
        "種別": "species_detail",
        # 毛色
        "毛色": "color",
        "毛の色": "color",
        # 性別
        "性別": "sex",
        # 年齢
        "推定年齢": "age",
        "年齢": "age",
        # 体格
        "体格": "size",
        "大きさ": "size",
        # 収容/保護日 (保護日を優先、無ければ受入日)
        "保護日": "shelter_date",
        "受入日": "shelter_date_fallback",
    }

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """一覧ページから動物の仮想 URL を返す

        基底 `SinglePageTableAdapter.fetch_animal_list` は行 0 件のとき
        ParsingError を投げるが、京都動物愛護センターは在庫 0 件状態
        (テーブル無し) が正常運用としてあり得るため、空リストを返す。
        """
        rows = self._load_rows()
        category = self.site_config.category
        return [(f"{self.site_config.list_url}#row={i}", category) for i in range(len(rows))]

    def extract_animal_details(self, virtual_url: str, category: str = "lost") -> RawAnimalData:
        """1 個の `<table class="info">` から RawAnimalData を構築する

        基底の `td/th` 列インデックスベース実装ではなく、
        各 `<tr>` の `<th>` ラベル文字列で値を引く。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        table = rows[idx]
        fields = self._extract_labeled_rows(table)

        # 収容日: 保護日を優先、無ければ受入日 (shelter_date_fallback)
        shelter_date = fields.get("shelter_date") or fields.get(
            "shelter_date_fallback", self.SHELTER_DATE_DEFAULT
        )

        # species はサイト名から推定 (HTML 上に "犬"/"猫" の明示は無い)。
        # 推定不能の場合は species_detail (品種) で代替する。
        species = self._infer_species_from_site_name(self.site_config.name)
        if not species:
            species = fields.get("species_detail", "")

        # 画像: カード内 (table の親 `<div class="content">`) から探す。
        # table 自体に img は無いケースが多いので親要素まで遡る。
        image_source: Tag = table
        parent = table.find_parent("div", class_="content")
        if isinstance(parent, Tag):
            image_source = parent

        try:
            return RawAnimalData(
                species=species,
                sex=fields.get("sex", ""),
                age=fields.get("age", ""),
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=shelter_date,
                location=fields.get("location", ""),
                phone="",
                image_urls=self._extract_row_images(image_source, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    # ─────────────────── ヘルパー ───────────────────

    def _extract_labeled_rows(self, table: Tag) -> dict[str, str]:
        """`<tr><th>label</th><td>value</td></tr>` を辞書化する

        - 同一フィールドへの値が複数 tr に存在する場合は最初を優先。
        - ラベルが `LABEL_FIELDS` に無い行はスキップ。
        - 値の前後空白は除去し、複数空白は単一スペースに圧縮する。
        """
        result: dict[str, str] = {}
        for tr in table.find_all("tr"):
            if not isinstance(tr, Tag):
                continue
            th = tr.find("th")
            td = tr.find("td")
            if not isinstance(th, Tag) or not isinstance(td, Tag):
                continue
            label = th.get_text(strip=True)
            value = td.get_text(separator=" ", strip=True)
            value = re.sub(r"[ 　]+", " ", value).strip()
            field = self.LABEL_FIELDS.get(label)
            if field and field not in result:
                result[field] = value
        return result

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫) を推定する

        - "迷子犬" / "犬" を含む → "犬"
        - "迷子猫" / "猫" を含む → "猫"
        - 不明 → "" (HTML 値にフォールバック)
        """
        if "犬" in name and "猫" not in name:
            return "犬"
        if "猫" in name and "犬" not in name:
            return "猫"
        return ""


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 2 サイトを同一 adapter にマップする。
# サイト名は `src/data_collector/config/sites.yaml` の表記に厳密一致させる。
for _site_name in (
    "京都市ペットラブ（迷子犬）",
    "京都市ペットラブ（迷子猫）",
):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, KyotoAniLoveAdapter)
