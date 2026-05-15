"""前橋市保健所 rule-based adapter

対象ドメイン: https://www.city.maebashi.gunma.jp/

特徴:
- 1 ページに収容犬の一覧テーブルが置かれた single_page 形式:
    https://www.city.maebashi.gunma.jp/soshiki/kenko/eiseikensa/gyomu/1/1/1/9484.html
- 個別 detail ページ (/47415.html 等) も存在するが、一覧テーブルに
  抽出に必要な属性 (収容日 / 写真 / 収容場所 / 犬種 / 性別) が
  全て掲載されているためここでは一覧から抽出する。
- 一覧テーブルは下記構造:
    <table summary="前橋市保健所における保護（収容）犬情報一覧について">
      <thead>
        <tr>
          <th>管理番号</th><th>写真</th><th>収容場所</th>
          <th>犬種</th><th>性別</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><a href=".../47415.html">2026-05-02</a></td>  ← 管理番号(リンクテキストが収容日)
          <td><a href=".../47415.html"><img src="..."></a></td>
          <td>市之関町</td>
          <td>雑種</td>
          <td>オス</td>
        </tr>
      </tbody>
    </table>
- ページ上にはもう 1 つ「手数料一覧」テーブルが存在するため、
  `summary` 属性で対象テーブルを特定する必要がある。
- 動物種別 (犬) はサイト名から推定する (テーブルの「犬種」列は
  "雑種" / "柴犬" 等の品種名のため)。
- リポジトリ内のフィクスチャは UTF-8 バイト列を Latin-1 として解釈し
  再 UTF-8 化された二重エンコーディング (mojibake) になっている
  ことがあるため、千葉県 adapter と同様に防御的補正を行う。
- 収容犬が 0 件のときは `<tbody>` 内に行が存在しない想定。その場合は
  ParsingError を出さず空リストを返す (実運用での 0 件は正常状態)。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter

# 一覧テーブル本文の各セル位置 (1 行 = 1 動物) を表す列定義。
# 0: 管理番号 (リンクテキストが収容日 "YYYY-MM-DD" になっている)
# 1: 写真
# 2: 収容場所
# 3: 犬種 (品種名: 雑種/柴犬 等)
# 4: 性別
_COL_MANAGEMENT = 0
_COL_PHOTO = 1
_COL_LOCATION = 2
_COL_BREED = 3
_COL_SEX = 4

# 「2026-05-02」のような ISO 形式の日付。前橋市の管理番号セルには
# 収容日 (リンクテキスト) としてこの形式で出てくる。
_ISO_DATE_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")


class CityMaebashiAdapter(SinglePageTableAdapter):
    """前橋市保健所用 rule-based adapter

    収容犬の一覧テーブル (`table[summary*='前橋市']`) から各行を
    1 動物として抽出する single_page 形式の adapter。
    """

    # 「前橋市保健所における…」の summary を持つテーブル本文の各行。
    # ページ上の他テーブル (手数料一覧) を確実に除外する。
    ROW_SELECTOR: ClassVar[str] = "table[summary*='前橋市'] tbody tr"
    # `<thead>` の `<tr>` は CSS 上 `tbody tr` の対象外となるため
    # SKIP_FIRST_ROW は不要 (False)。
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 値の取り出しはオーバーライドした `extract_animal_details` が
    # セルから直接行うため、`COLUMN_FIELDS` は契約として宣言のみ。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        _COL_MANAGEMENT: "shelter_date",  # リンクテキストが ISO 日付
        _COL_LOCATION: "location",
        _COL_BREED: "species",  # 「犬種」(品種名)
        _COL_SEX: "sex",
    }
    LOCATION_COLUMN: ClassVar[int | None] = _COL_LOCATION
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """list_url の HTML を取得し、対象テーブルの行をキャッシュする

        - 二重 UTF-8 mojibake (latin-1 解釈 → utf-8 再エンコード) を
          フィクスチャ用に防御的に補正する (実 HTTP では不要)。
        - `summary` 属性で対象テーブル (前橋市…一覧) を特定し、
          その `<tbody> <tr>` のみを抽出する。
        - `<thead>` 内の見出し行は CSS 上対象外なので除外不要。
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        html = self._html_cache
        # mojibake 検出: 「前橋」が含まれない場合のみ逆変換を試みる
        if "前橋" not in html:
            try:
                html = html.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass

        soup = BeautifulSoup(html, "html.parser")
        rows: list[Tag] = []
        for tr in soup.select(self.ROW_SELECTOR):
            if not isinstance(tr, Tag):
                continue
            # td が無い (= ヘッダ的な行) はスキップ
            if not tr.find("td"):
                continue
            rows.append(tr)

        self._rows_cache = rows
        return rows

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """動物リスト取得 (在庫 0 件でも ParsingError を出さない)

        前橋市の収容犬は 0 件期間が頻繁にあり、その場合 `<tbody>` 内に
        行が存在しない (テーブル自体は残る)。基底実装は 0 行で例外を
        投げるので、ここで明示的に空リストを返す。
        """
        rows = self._load_rows()
        category = self.site_config.category
        return [(f"{self.site_config.list_url}#row={i}", category) for i in range(len(rows))]

    def extract_animal_details(
        self, virtual_url: str, category: str = "sheltered"
    ) -> RawAnimalData:
        """1 行の `<tr>` から RawAnimalData を構築する

        - 管理番号セル (0 列目) のリンクテキストは ISO 形式の収容日
          ("2026-05-02") なので、これを shelter_date に採用する。
        - 種別 (species) は site 名から「犬」を推定し、テーブルの
          「犬種」列 (雑種/柴犬等) は品種名なのでフォールバックに
          留める。
        - 画像 URL は `<img src="//www.city.maebashi.gunma.jp/...">`
          の protocol-relative 形式なので、`_absolute_url` (urljoin)
          で `https://...` に解決される。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        tr = rows[idx]
        cells = [c for c in tr.find_all("td") if isinstance(c, Tag)]

        def _cell_text(i: int) -> str:
            if i >= len(cells):
                return ""
            return cells[i].get_text(separator=" ", strip=True)

        # 管理番号セルから収容日 (ISO 文字列) を抽出
        management_text = _cell_text(_COL_MANAGEMENT)
        shelter_date = self._parse_iso_date(management_text)

        location = _cell_text(_COL_LOCATION)
        breed = _cell_text(_COL_BREED)
        sex = _cell_text(_COL_SEX)

        # species はサイト名から推定 (犬種列は品種名なのでフォールバック)
        species = self._infer_species_from_site_name(self.site_config.name)
        if not species:
            species = breed

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
                image_urls=self._extract_row_images(tr, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _parse_iso_date(text: str) -> str:
        """「2026-05-02」のような文字列から正規化された ISO 日付を返す

        前橋市の管理番号セルにはリンクテキストが ISO 形式で入っており、
        そのまま使えるが念のため zero-padding を保証する。マッチしない
        場合は空文字を返す (収容日不明扱い)。
        """
        m = _ISO_DATE_RE.search(text)
        if not m:
            return ""
        y, mo, d = m.group(1), m.group(2), m.group(3)
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫) を推定する

        前橋市は現状「保護犬」のみだが、将来的に保護猫サイトが
        増える可能性に備えて両対応にしておく。
        """
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return ""


# ─────────────────── サイト登録 ───────────────────
SiteAdapterRegistry.register("前橋市（保護犬）", CityMaebashiAdapter)
