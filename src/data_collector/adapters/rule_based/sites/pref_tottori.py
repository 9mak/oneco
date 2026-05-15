"""鳥取県（迷子動物情報）rule-based adapter

対象ドメイン: https://www.pref.tottori.lg.jp/

特徴:
- 1 ページに「中部総合事務所収容動物」「西部総合事務所収容動物」の
  2 ブロックが並ぶ single_page 形式。各ブロックは
    <h2 class="Title">
      <span ...>中部総合事務所収容動物　電話 (0858)23-3149  FAX (0858)23-4803</span>
    </h2>
    <div class="Contents">
      <table>
        <tbody>
          <tr> <th>収容日時</th> <th>収容場所</th> <th>種類</th> <th>品種</th>
               <th>毛色</th> <th>性別</th> <th>推定年齢</th>
               <th>体格、その他特徴</th> <th>詳細情報</th> <th>備考</th> </tr>
          <tr> <td>...</td>... </tr>     # 動物 1 件
          ...
        </tbody>
      </table>
    </div>
  というレイアウトで構成される。在庫 0 件のときも同じ表が
  「全セルが空白の 1 行」を含む形で残るため、空セル行は除外する必要がある。
- 西部表はヘッダー行も `<td>` (背景色付き) で実装されており `<th>` ではないが、
  最初の行のテキストが「収容日時 / 収容場所 / 種類 / ...」となるため、
  「最初のセルに『収容日時』を含む行」をヘッダーとして除外する。
- 東部圏域 (鳥取市) は別サイト (city.tottori.lg.jp) で公開されており、
  本ページには案内文しか無いため対象外。
- 個別 detail ページは存在しないため `single_page=True` 前提で
  `SinglePageTableAdapter` を継承し、`_load_rows` / `extract_animal_details`
  を独自にオーバーライドする。
- 直前の `<h2 class="Title"> <span>...</span> </h2>` から所管保健所名と
  電話番号が取れるため、`location` 不足分の補完および `phone` に利用する。
- 実運用 (`_http_get`) では requests が UTF-8 として正しく取得するが、
  既存サイト adapter (千葉・愛媛など) と同様、本文に「鳥取」が見当たらない
  場合に限って二重 UTF-8 (latin-1 → utf-8) の逆変換を試みる防御を入れる。
- 在庫 0 件 (実データ行が 1 件も無い) のページでも `ParsingError` を出さず
  空リストを返す (掲載動物が居ない期間でもページ自体は存在するため)。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter

# 「電話 (XXXX)YY-ZZZZ」「電話XXX-YYY-ZZZZ」等から番号部分を抽出する正規表現。
# 半角/全角括弧、半角/全角ハイフン、空白を許容する。
_PHONE_RE = re.compile(
    r"電話[\s　]*[\(（]?\s*(\d{2,5})\s*[\)）]?\s*[-－‐]?\s*(\d{2,4})\s*[-－‐]?\s*(\d{3,4})"
)

# 見出し span から所管 (中部/西部/東部 等) を抽出する正規表現。
_OFFICE_RE = re.compile(r"(東部|中部|西部|鳥取市)[^\s　]*")


class PrefTottoriAdapter(SinglePageTableAdapter):
    """鳥取県（迷子動物情報）用 rule-based adapter

    1 ページに 2 つの保健所ブロック (中部・西部) が並ぶ single_page 形式。
    各ブロック内の `<table>` から 1 行 = 1 動物として抽出する。
    """

    # 各動物表 (中部・西部の収容動物表のみ採用)
    ROW_SELECTOR: ClassVar[str] = "table"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 基底の cells ベース既定実装は使わず、tr の並びを明示的に扱う。
    # 契約として COLUMN_FIELDS は宣言する。
    # cells: [収容日時, 収容場所, 種類, 品種, 毛色, 性別,
    #         推定年齢, 体格その他特徴, 詳細情報, 備考]
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        0: "shelter_date",  # 収容日時
        1: "location",  # 収容場所
        2: "species",  # 種類 (犬/猫等)
        3: "breed",  # 品種
        4: "color",  # 毛色
        5: "sex",  # 性別
        6: "age",  # 推定年齢
        7: "size",  # 体格、その他特徴
    }
    LOCATION_COLUMN: ClassVar[int | None] = 1
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """list_url の HTML を取得し、対象となる動物 tr 要素のリストをキャッシュ

        - 二重 UTF-8 mojibake (latin-1 解釈 → utf-8 再エンコード) を補正
        - 「中部/西部総合事務所収容動物」見出し配下の `<table>` のみを対象とする
        - ヘッダー行 (最初のセルに『収容日時』を含む行) は除外
        - 全セルが空白の行 (掲載動物が居ない時のプレースホルダ) も除外
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        html = self._html_cache
        # mojibake 検出: 本文に「鳥取」が含まれない場合は
        # latin-1 → utf-8 の逆変換を試みる。失敗したら元のまま。
        if "鳥取" not in html:
            try:
                html = html.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
        # 補正後の HTML を再キャッシュ (extract_animal_details 側で再利用)
        self._html_cache = html

        soup = BeautifulSoup(html, "html.parser")
        rows: list[Tag] = []
        for table in soup.find_all("table"):
            if not isinstance(table, Tag):
                continue
            # この table が収容動物表か判定: 直前の見出し span に
            # 「収容動物」を含むかでフィルタする
            if not self._is_shelter_table(table):
                continue
            tbody = table.find("tbody") or table
            if not isinstance(tbody, Tag):
                continue
            for tr in tbody.find_all("tr", recursive=False):
                if not isinstance(tr, Tag):
                    continue
                cells = [
                    c for c in tr.find_all(["td", "th"], recursive=False) if isinstance(c, Tag)
                ]
                if not cells:
                    continue
                # ヘッダー行除外: 最初のセルに「収容日時」を含む
                first_text = cells[0].get_text(separator=" ", strip=True)
                if "収容日時" in first_text:
                    continue
                # 全セルが空白なら除外 (在庫 0 件のプレースホルダ行)
                joined = "".join(c.get_text(strip=True).replace("\xa0", "") for c in cells)
                if not joined.strip():
                    continue
                rows.append(tr)

        self._rows_cache = rows
        return rows

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """動物リスト取得 (在庫 0 件でも ParsingError を出さない)

        基底実装は rows が空のとき例外を出すが、鳥取県のサイトは
        収容動物が居ない期間でもページ自体は存在するため、空リストを返す。
        """
        rows = self._load_rows()
        category = self.site_config.category
        return [(f"{self.site_config.list_url}#row={i}", category) for i in range(len(rows))]

    def extract_animal_details(self, virtual_url: str, category: str = "lost") -> RawAnimalData:
        """tr 1 件から RawAnimalData を構築する

        - tr の親 `<table>` の直前にある `<h2 class="Title"> <span>` から
          所管保健所と電話番号を抽出して location 補完および phone に使う
        - 種別は『種類』セルの文字列から「犬/猫/その他」に正規化
        - 備考列 (最終 td) から `<img>` を集める
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        tr = rows[idx]

        # 1) 所属 table と見出しから所管・電話番号を取得
        table = tr.find_parent("table")
        office_label, phone_raw = (
            self._parse_section_header(table) if isinstance(table, Tag) else ("", "")
        )

        # 2) 各セルから値を取得
        cells = [c for c in tr.find_all(["td", "th"], recursive=False) if isinstance(c, Tag)]
        fields: dict[str, str] = {}
        for col_idx, field_name in self.COLUMN_FIELDS.items():
            if col_idx < len(cells):
                fields[field_name] = cells[col_idx].get_text(separator=" ", strip=True)

        # 3) 場所: テーブル内の「収容場所」を優先し、空なら所管保健所名で補完
        location = fields.get("location", "").strip()
        if not location and office_label:
            location = office_label

        # 4) species: 「種類」セルから犬/猫/その他に正規化
        species = self._normalize_species(fields.get("species", ""))

        # 5) 画像: 備考列 (最終 td) から取得
        image_urls: list[str] = []
        if cells:
            image_urls = self._extract_cell_images(cells[-1], virtual_url)

        try:
            return RawAnimalData(
                species=species,
                sex=fields.get("sex", ""),
                age=fields.get("age", ""),
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=fields.get("shelter_date", self.SHELTER_DATE_DEFAULT),
                location=location,
                phone=self._normalize_phone(phone_raw),
                image_urls=image_urls,
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _is_shelter_table(table: Tag) -> bool:
        """その table が「中部/西部総合事務所収容動物」セクション配下か判定

        親をたどって `class="Contents"` の直前 `class="h2frame"` 配下の
        h2 テキストに「収容動物」を含むかで判定する。
        該当しない table (お問い合わせ先一覧、ペット保護案内など) は除外。
        """
        # 直前の h2 (ContentsBlock 単位) を最大 30 ノード遡って探す
        for sib in table.find_all_previous(limit=30):
            if not isinstance(sib, Tag):
                continue
            if sib.name == "h2":
                text = sib.get_text(separator=" ", strip=True)
                return "収容動物" in text
        return False

    @staticmethod
    def _parse_section_header(table: Tag) -> tuple[str, str]:
        """table 直前の `<h2 class="Title">` から所管と電話番号を抽出

        Returns:
            (office_label, phone_raw)。取れなかった要素は空文字。
            office_label は「中部総合事務所」「西部総合事務所」等。
        """
        for sib in table.find_all_previous(limit=30):
            if not isinstance(sib, Tag):
                continue
            if sib.name != "h2":
                continue
            text = sib.get_text(separator=" ", strip=True)
            office_match = _OFFICE_RE.search(text)
            office_label = ""
            if office_match:
                # "中部" → "中部総合事務所", "鳥取市" → "鳥取市保健所"
                head = office_match.group(1)
                if head == "鳥取市":
                    office_label = "鳥取市保健所"
                else:
                    office_label = f"{head}総合事務所"
            phone_match = _PHONE_RE.search(text)
            phone_raw = ""
            if phone_match:
                phone_raw = f"{phone_match.group(1)}-{phone_match.group(2)}-{phone_match.group(3)}"
            return office_label, phone_raw
        return "", ""

    @staticmethod
    def _normalize_species(raw: str) -> str:
        """『種類』セルの文字列を 犬/猫/その他 に正規化"""
        if not raw:
            return "その他"
        if "犬" in raw:
            return "犬"
        if "猫" in raw:
            return "猫"
        return "その他"

    def _extract_cell_images(self, cell: Tag, virtual_url: str) -> list[str]:
        """セル内の `<img src=...>` を絶対 URL のリストに変換する"""
        urls: list[str] = []
        for img in cell.find_all("img"):
            src = img.get("src")
            if src and isinstance(src, str):
                urls.append(self._absolute_url(src, base=virtual_url))
        return self._filter_image_urls(urls, virtual_url)


# ─────────────────── サイト登録 ───────────────────
SiteAdapterRegistry.register("鳥取県（迷子動物情報）", PrefTottoriAdapter)
