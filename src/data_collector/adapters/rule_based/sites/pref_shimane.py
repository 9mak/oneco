"""島根県 松江保健所（収容動物）rule-based adapter

対象ドメイン: https://www.pref.shimane.lg.jp/infra/nature/animal/matsue_hoken/

特徴:
- 1 ページに「収容犬」「収容猫」の 2 テーブルが並ぶ single_page 形式。
  個別 detail ページは存在しない。
- 各テーブルは `<caption>収容犬</caption>` または
  `<caption>収容猫</caption>` を持ち、これが species のヒントになる
  (HTML 上の「動物種別」列は "犬"/"猫" 等の値が入るが、空欄のことも多い)。
- ヘッダ行 (7 列): 管理番号 / 写真 / 収容日 / 収容場所 / 動物種別 / 種類 / 性別。
  データ行は `<td>` 要素を持ち、実データが入る。
- 在庫 0 件 (現在保護収容している動物がいない) のときは
  `<th>` だけのプレースホルダ行が並ぶ (= データ行 `<td>` が無い) ので、
  これは除外して空リストを返す。
- 二重 UTF-8 mojibake (Latin-1 解釈 → UTF-8 再エンコード) になっている
  fixture が混在する可能性に備え、本文に「島根」が含まれない場合は
  逆変換を試みる (千葉/愛媛 adapter と同方針)。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


# 「YYYY年M月D日」「YYYY/M/D」「YYYY-M-D」を ISO に揃えるための正規表現
_DATE_RE = re.compile(
    r"(\d{4})\s*[年/\-.]\s*(\d{1,2})\s*[月/\-.]\s*(\d{1,2})"
)
# 月日のみ (年は別途補完): 「M月D日」「M/D」
_MONTH_DAY_RE = re.compile(r"(\d{1,2})\s*[月/]\s*(\d{1,2})")


class PrefShimaneAdapter(SinglePageTableAdapter):
    """島根県 松江保健所 rule-based adapter

    収容犬テーブル + 収容猫テーブルを単一ページから抽出する single_page 形式。
    各動物は `<table>` 内の `<td>` を持つデータ行 1 行に対応する。
    """

    # 各動物データ行 (`<td>` を含む `<tr>`)。
    # ヘッダ行 (`<th>` のみ) や空のプレースホルダ行は `_load_rows` で除外する。
    ROW_SELECTOR: ClassVar[str] = "table tr"
    SKIP_FIRST_ROW: ClassVar[bool] = False

    # 7 列構造: 管理番号 / 写真 / 収容日 / 収容場所 / 動物種別 / 種類 / 性別。
    # species は別途 caption から推定するため `breed` 扱いの「種類」列だけ
    # COLUMN_FIELDS で拾い、それ以外は extract_animal_details で個別処理する。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        3: "location",  # 収容場所
        5: "breed",     # 種類 (品種名)
        6: "sex",       # 性別
    }
    LOCATION_COLUMN: ClassVar[int | None] = 3
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """list_url の HTML を取得し、データ行 (td を含む tr) をキャッシュ

        - mojibake 補正 (本文に「島根」が含まれない場合のみ)
        - `<th>` のみのヘッダ行 / 空セル並びのプレースホルダ行を除外
        - 各 `<tr>` に対応する table の `<caption>` を species ヒントとして
          後段で利用するため、tr 自体をそのまま返す。
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        html = self._html_cache
        if "島根" not in html:
            try:
                html = html.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
        self._html_cache = html

        soup = BeautifulSoup(html, "html.parser")
        rows: list[Tag] = []
        for tr in soup.select(self.ROW_SELECTOR):
            if not isinstance(tr, Tag):
                continue
            tds = tr.find_all("td", recursive=False)
            if not tds:
                # th だけの行 (ヘッダ or 空プレースホルダ) は除外
                continue
            # 全 td が空文字のプレースホルダ行も除外
            if not any(td.get_text(strip=True) for td in tds):
                continue
            rows.append(tr)

        self._rows_cache = rows
        return rows

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """動物リスト取得 (在庫 0 件でも ParsingError を出さない)

        島根県のページは収容動物が居ない期間でもテーブル骨格が残るため、
        基底実装の「rows が空なら例外」では運用できない。空リストを返す。
        """
        rows = self._load_rows()
        category = self.site_config.category
        return [
            (f"{self.site_config.list_url}#row={i}", category)
            for i in range(len(rows))
        ]

    def extract_animal_details(
        self, virtual_url: str, category: str = "sheltered"
    ) -> RawAnimalData:
        """データ行から RawAnimalData を構築する

        セル順: [管理番号, 写真, 収容日, 収容場所, 動物種別, 種類, 性別]
        species は table の `<caption>` (「収容犬」「収容猫」) から推定し、
        失敗した場合は「動物種別」列 (cells[4]) -> サイト名 の順でフォールバックする。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        tr = rows[idx]
        cells = [
            c for c in tr.find_all(["td", "th"], recursive=False)
            if isinstance(c, Tag)
        ]

        def cell_text(i: int) -> str:
            if i >= len(cells):
                return ""
            return cells[i].get_text(separator=" ", strip=True)

        shelter_date = self._parse_shelter_date(cell_text(2))
        location = cell_text(3)
        species_cell = cell_text(4)
        breed = cell_text(5)
        sex = cell_text(6)

        # species 推定: caption -> 動物種別列 -> サイト名 の順
        species = self._infer_species_from_caption(tr)
        if not species:
            species = self._normalize_species(species_cell)
        if not species:
            species = self._infer_species_from_site_name(self.site_config.name)

        # 画像セル (cells[1] = 写真) から `<img src=...>` を集める
        image_urls: list[str] = []
        if len(cells) > 1:
            for img in cells[1].find_all("img"):
                src = img.get("src")
                if src and isinstance(src, str):
                    image_urls.append(self._absolute_url(src, base=virtual_url))

        try:
            return RawAnimalData(
                species=species,
                sex=sex,
                age="",
                color="",
                size="",
                shelter_date=shelter_date or self.SHELTER_DATE_DEFAULT,
                location=location,
                phone="",
                image_urls=image_urls,
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(
                f"RawAnimalData バリデーション失敗: {e}", url=virtual_url
            ) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _parse_shelter_date(text: str) -> str:
        """収容日セル文字列から ISO 形式 `YYYY-MM-DD` を返す

        年が含まれない (例: "5月10日") 場合は空文字を返す
        (年の推定は不確かなので「不明」として委譲する)。
        """
        if not text:
            return ""
        m = _DATE_RE.search(text)
        if m:
            y, mo, d = m.group(1), m.group(2), m.group(3)
            return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
        return ""

    @staticmethod
    def _infer_species_from_caption(tr: Tag) -> str:
        """tr が属する table の `<caption>` から species を推定する"""
        table = tr.find_parent("table")
        if not isinstance(table, Tag):
            return ""
        caption = table.find("caption")
        if not isinstance(caption, Tag):
            return ""
        text = caption.get_text(strip=True)
        if "犬" in text and "猫" not in text:
            return "犬"
        if "猫" in text and "犬" not in text:
            return "猫"
        if "犬" in text and "猫" in text:
            return "その他"
        return ""

    @staticmethod
    def _normalize_species(text: str) -> str:
        """「動物種別」列の文字列を犬/猫/その他 に丸める"""
        if not text:
            return ""
        if "犬" in text and "猫" not in text:
            return "犬"
        if "猫" in text and "犬" not in text:
            return "猫"
        return "その他"

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から species を推定する (最終フォールバック)"""
        if "犬" in name and "猫" not in name:
            return "犬"
        if "猫" in name and "犬" not in name:
            return "猫"
        return "その他"


# ─────────────────── サイト登録 ───────────────────
SiteAdapterRegistry.register(
    "島根県 松江保健所（収容動物）", PrefShimaneAdapter
)
