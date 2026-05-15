"""横浜市動物愛護センター rule-based adapter

対象ドメイン: https://www.city.yokohama.lg.jp/kurashi/sumai-kurashi/pet-dobutsu/aigo/maigo/

特徴:
- 同一テンプレート上で 3 サイト (収容犬/収容猫/収容その他動物) を運用しており、
  URL パターンのみが異なる:
    - .../aigo/maigo/shuyoinfo.html         (収容犬)
    - .../aigo/maigo/20121004094818.html    (収容猫)
    - .../aigo/maigo/20121004110429.html    (収容その他動物)
- 1 ページに `<table>` 形式で動物情報が並ぶ single_page サイト。
  個別 detail ページは存在しない。
- テーブル構造 (1 行 = 1 頭):
    <table>
      <caption>収容動物情報</caption>
      <tr>(ヘッダ) <th>収容日・収容場所</th><th>写真</th><th>種類</th>
                  <th>性別</th><th>毛色</th><th>体格</th><th>その他</th></tr>
      <tr>(データ行 N 件)
        <td>{収容日 + 収容場所}</td>
        <td><img src="..."></td>
        <td>{種類}</td>
        <td>{性別}</td>
        <td>{毛色}</td>
        <td>{体格}</td>
        <td>{その他}</td>
      </tr>
    </table>
- 収容数 0 件のときは「現在、{ç¬|ç«|ãã®ä»åç©}の収容情報はありません。」のような
  プレースホルダ行が 1 つ入ったテーブルになる。本 adapter はこれを検出し、
  `fetch_animal_list` から空リストを返す (ParsingError は出さない)。
- 動物種別はサイト名から推定する (HTML には「種類」列に犬種等の具体名が入る)。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter

# 0 件プレースホルダ行を検出するパターン。
# 例: 「現在、犬の収容情報はありません。」「現在、猫の収容情報はありません」
_EMPTY_PLACEHOLDER_RE = re.compile(r"現在.*収容情報.*ありません")


class CityYokohamaAdapter(SinglePageTableAdapter):
    """横浜市動物愛護センター用 rule-based adapter

    収容犬/収容猫/収容その他動物 の 3 サイトで共通テンプレートを使用する。
    `<table>` ヘッダ行 + データ行 N 件の single_page 形式。
    """

    # `wysiwyg_wp` div 配下のテーブルの行のみを対象とする。
    # ページ内に他テーブルが追加された場合に備えてスコープを限定する。
    ROW_SELECTOR: ClassVar[str] = "div.wysiwyg_wp table tr"
    # 1 行目はヘッダ (`<th>`) なので除外
    SKIP_FIRST_ROW: ClassVar[bool] = True
    # 列インデックス → RawAnimalData フィールド名 のマッピング。
    # 列 0 は「収容日・収容場所」を 1 セルにまとめた表記なので独自処理が必要。
    # 列 1 は写真 (img) なのでテキスト抽出対象外。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        2: "species",
        3: "sex",
        4: "color",
        5: "size",
    }
    LOCATION_COLUMN: ClassVar[int | None] = None  # 列 0 から独自抽出
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """テーブル行を仮想 URL に変換する

        収容数 0 件の場合 (プレースホルダ行のみ) は空リストを返す。
        テーブル自体が存在しない場合は ParsingError (基底実装)。
        """
        rows = self._load_rows()
        if not rows:
            # 行 (ヘッダ含む) が一切無い = テーブル不在。基底実装に合わせて例外。
            raise ParsingError(
                "行要素が見つかりません",
                selector=self.ROW_SELECTOR,
                url=self.site_config.list_url,
            )
        # 0 件プレースホルダのみの場合は空リスト (= 在庫 0 件) を返す
        data_rows = [r for r in rows if not self._is_empty_placeholder(r)]
        category = self.site_config.category
        return [(f"{self.site_config.list_url}#row={i}", category) for i in range(len(data_rows))]

    def extract_animal_details(self, virtual_url: str, category: str = "adoption") -> RawAnimalData:
        """テーブル行から RawAnimalData を構築する

        基底のセルベース既定実装に対し、列 0 (収容日・収容場所) の分割と
        species のサイト名推定を加える。
        """
        rows = [r for r in self._load_rows() if not self._is_empty_placeholder(r)]
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
                fields[field_name] = cells[col_idx].get_text(separator=" ", strip=True)

        # 列 0: 「収容日・収容場所」を分割
        shelter_date, location = "", ""
        if cells:
            shelter_date, location = self._split_date_and_location(cells[0])

        # 動物種別はサイト名から推定 (HTML の「種類」は犬種名など具体的な値)
        species = self._infer_species_from_site_name(self.site_config.name)

        try:
            return RawAnimalData(
                species=species,
                sex=fields.get("sex", ""),
                age="",
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=shelter_date or self.SHELTER_DATE_DEFAULT,
                location=location,
                phone="",
                image_urls=self._extract_row_images(row, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _is_empty_placeholder(row: Tag) -> bool:
        """0 件時のプレースホルダ行 (「現在、…の収容情報はありません」) かを判定"""
        text = row.get_text(separator=" ", strip=True)
        return bool(_EMPTY_PLACEHOLDER_RE.search(text))

    @staticmethod
    def _split_date_and_location(cell: Tag) -> tuple[str, str]:
        """列 0 の「収容日 + 収容場所」セルを (shelter_date, location) に分割

        セル内は `<br>` 区切りで複数行になっているのが通例:
            令和8年5月7日<br>横浜市中区...
        または「収容日：…<br>収容場所：…」のラベル付き。
        """
        # 改行区切りでテキスト抽出
        text = cell.get_text(separator="\n", strip=False)
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

        date = ""
        loc = ""
        # ラベル付きを優先的にパース
        for line in lines:
            for sep in ("：", ":"):
                if sep in line:
                    label, value = line.split(sep, 1)
                    label, value = label.strip(), value.strip()
                    if "収容日" in label and not date:
                        date = value
                    elif ("収容場所" in label or "場所" in label) and not loc:
                        loc = value
                    break
        # ラベルが無い場合は順序で推定 (1 行目=日付、2 行目=場所)
        if not date and lines:
            # 「令和」「平成」「年」「月」「/」「-」のいずれかを含む 1 行目を日付候補とする
            first = lines[0]
            if any(kw in first for kw in ("令和", "平成", "年", "/", "-")):
                date = first
                if len(lines) >= 2 and not loc:
                    loc = lines[1]
        if not loc and len(lines) >= 2 and not any((("：" in ln) or (":" in ln)) for ln in lines):
            loc = lines[1]
        return date, loc

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫/その他) を推定する"""
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return "その他"


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 3 サイトを同一 adapter にマップする。
for _site_name in (
    "横浜市（収容犬）",
    "横浜市（収容猫）",
    "横浜市（収容その他動物）",
):
    SiteAdapterRegistry.register(_site_name, CityYokohamaAdapter)
