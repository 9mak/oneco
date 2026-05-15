"""愛媛県動物愛護センター rule-based adapter

対象ドメイン: https://www.pref.ehime.jp/page/

特徴:
- 同一テンプレート上で 2 サイト
  (収容中=迷い犬猫、譲渡予定) を運用しており、URL の page ID のみ異なる
  single_page 形式:
    .../page/16976.html  (収容中 / lost)
    .../page/17125.html  (譲渡予定 / adoption)
- 1 ページに複数の動物テーブル (`<table class="sp_table_wrap">`) が並び、
  各テーブルは 1 行 (1 動物) を持つ。個別 detail ページは存在しない。
  典型的な並び:

      <p><strong>5月8日　八幡浜市　犬</strong></p>
      <div class="sp_table_wrap2">
        <table class="sp_table_wrap">
          <thead>
            <tr><th>No.</th><th>拾得捕獲場所</th><th>種類</th>
                <th>毛色</th><th>性別</th><th>体格</th><th>備考</th></tr>
          </thead>
          <tbody>
            <tr>
              <td>1</td>
              <td><p>八幡浜市</p><p>大平</p></td>
              <td>バセットハウンド風</td>
              <td>白茶</td>
              <td>メス</td>
              <td>中</td>
              <td>
                <p><img alt="..." src="/uploaded/image/65619.jpg"></p>
                <p>※赤い革製の首輪あり</p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

- テーブル直前の `<p><strong>...</strong></p>` には
  「{月日}　{市町村}　{犬|猫|...}」が記載されており、
    * 月日 -> 収容日 (年は当該ページ更新日付から推定。掲載年が明示されない
      ことがあるため、最終的に空文字で「不明」扱いとなるケースもある)
    * 市町村 -> 場所のヒント (テーブル内の場所と通常一致)
    * 犬/猫/その他 -> species (テーブル内の「種類」は品種名なので利用しない)
  ただし、すべてのテーブルでこのヘッダ段落が存在するとは限らないため
  `species` はサイト名 (収容中=未指定、譲渡予定=未指定) と段落見出しの
  両方から推定し、いずれも特定できなければ "その他" を返す。
- ページ全体 (data_collector が `requests` で取得した実 HTML) は UTF-8 で
  返却されるが、リポジトリに保存されたフィクスチャは UTF-8 バイト列を
  Latin-1 として解釈してから再 UTF-8 化された二重エンコーディング
  (mojibake) になっているため、`_load_rows` で「愛媛」が見当たらない場合に
  限って逆変換を試みる (千葉県 adapter と同方針)。
- 在庫 0 件 (テーブルが 1 つも無い) のページでも ParsingError を出さず
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

# 「{月}月{日}日　{市町村}　{犬|猫|...}」を抽出する正規表現。
# 全角/半角空白の両方を許容する。
_HEADER_LINE_RE = re.compile(
    r"(\d{1,2})\s*月\s*(\d{1,2})\s*日"
    r"[\s　]+([^\s　]+)"
    r"[\s　]+([^\s　]+)"
)

# 「更新日：YYYY年M月D日」形式から年を取り出す
_UPDATE_YEAR_RE = re.compile(r"更新日[:：]\s*(\d{4})\s*年")


class PrefEhimeAdapter(SinglePageTableAdapter):
    """愛媛県動物愛護センター用 rule-based adapter

    収容中 (迷い犬猫) と譲渡予定の 2 サイトで共通テンプレートを使用する
    single_page 形式。各動物は `<table class="sp_table_wrap">` ブロックで
    表現される。
    """

    # 各動物テーブル
    ROW_SELECTOR: ClassVar[str] = "table.sp_table_wrap"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 基底の cells ベース既定実装は使わず、tbody > tr > td の並びを
    # 明示的に扱う。契約として COLUMN_FIELDS は宣言する。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        1: "location",  # 拾得捕獲場所
        2: "breed",  # 種類 (species ではなく品種)
        3: "color",  # 毛色
        4: "sex",  # 性別
        5: "size",  # 体格
    }
    LOCATION_COLUMN: ClassVar[int | None] = 1
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """list_url の HTML を取得し、動物テーブルをキャッシュ

        - 二重 UTF-8 mojibake (latin-1 解釈 → utf-8 再エンコード) を補正
        - `<table class="sp_table_wrap">` のうち tbody 行を持つものだけを返す
          (空のサマリ用テーブルや末尾の `<table class="datatable">` 等を除外)
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        html = self._html_cache
        # mojibake 検出: 本文に「愛媛」が含まれない場合は
        # latin-1 → utf-8 の逆変換を試みる。失敗したら元のまま。
        if "愛媛" not in html:
            try:
                html = html.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
        # 補正後の HTML を再キャッシュ (extract_animal_details 側で再利用)
        self._html_cache = html

        soup = BeautifulSoup(html, "html.parser")
        rows: list[Tag] = []
        for table in soup.select(self.ROW_SELECTOR):
            if not isinstance(table, Tag):
                continue
            tbody = table.find("tbody")
            if not isinstance(tbody, Tag):
                continue
            data_trs = [
                tr
                for tr in tbody.find_all("tr", recursive=False)
                if isinstance(tr, Tag) and tr.find("td")
            ]
            if not data_trs:
                continue
            rows.append(table)

        self._rows_cache = rows
        return rows

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """動物リスト取得 (在庫 0 件でも ParsingError を出さない)

        基底実装は rows が空のとき例外を出すが、愛媛県のサイトは
        収容動物が居ない期間でもページ自体は存在するため、空リストを返す。
        """
        rows = self._load_rows()
        category = self.site_config.category
        return [(f"{self.site_config.list_url}#row={i}", category) for i in range(len(rows))]

    def extract_animal_details(self, virtual_url: str, category: str = "lost") -> RawAnimalData:
        """テーブルブロックから RawAnimalData を構築する

        - テーブル直前の `<p><strong>{月日} {市町村} {犬|猫|...}</strong></p>`
          を読み取り、収容日と species のヒントを得る
        - tbody の最初の `<tr>` から各 td を取り出す
        - 備考列 (最終 td) から `<img>` を集める
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        table = rows[idx]

        # 1) 直前の見出し段落から月日・場所ヒント・species ヒントを取得
        header_month_day, header_location, header_species = self._parse_header_paragraph(table)

        # 2) ページの「更新日：YYYY年M月D日」から年を推定し、
        #    月日と組み合わせて ISO 形式の収容日を作る
        shelter_date = self._build_shelter_date(header_month_day)

        # 3) tbody > tr > td から各属性を抽出
        tbody = table.find("tbody")
        first_row: Tag | None = None
        if isinstance(tbody, Tag):
            for tr in tbody.find_all("tr", recursive=False):
                if isinstance(tr, Tag) and tr.find("td"):
                    first_row = tr
                    break

        location = ""
        color = ""
        sex = ""
        size = ""
        image_urls: list[str] = []

        if first_row is not None:
            cells = [
                td
                for td in first_row.find_all(["td", "th"], recursive=False)
                if isinstance(td, Tag)
            ]
            # cells: [No., 場所, 種類, 毛色, 性別, 体格, 備考(画像)]
            if len(cells) > self.LOCATION_COLUMN:  # type: ignore[operator]
                location = cells[self.LOCATION_COLUMN].get_text(  # type: ignore[index]
                    separator=" ", strip=True
                )
            if len(cells) > 3:
                color = cells[3].get_text(separator=" ", strip=True)
            if len(cells) > 4:
                sex = cells[4].get_text(separator=" ", strip=True)
            if len(cells) > 5:
                size = cells[5].get_text(separator=" ", strip=True)
            # 備考 (最終列) からの画像
            if len(cells) > 6:
                image_urls = self._extract_cell_images(cells[6], virtual_url)
            elif cells:
                # 想定外のカラム数でも最終 td から画像を試みる
                image_urls = self._extract_cell_images(cells[-1], virtual_url)

        # location が取れなかった場合のみ見出し段落のヒントを使う
        if not location and header_location:
            location = header_location

        # species: 見出し段落のヒント -> サイト名 -> "その他" の優先順
        species = header_species or self._infer_species_from_site_name(self.site_config.name)

        try:
            return RawAnimalData(
                species=species,
                sex=sex,
                age="",
                color=color,
                size=size,
                shelter_date=shelter_date or self.SHELTER_DATE_DEFAULT,
                location=location,
                phone="",
                image_urls=image_urls,
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _parse_header_paragraph(table: Tag) -> tuple[str, str, str]:
        """table の直前にある `<p><strong>...</strong></p>` を解析する

        Returns:
            (month_day, location, species_hint)。取れなかった要素は空文字。
        """
        # table が `<div class="sp_table_wrap2">` 等で包まれているケースもあり、
        # 直接の前兄弟と親要素の前兄弟の両方を探す。
        candidates: list[Tag] = []
        for sib in table.find_all_previous(limit=10):
            if isinstance(sib, Tag) and sib.name == "p":
                candidates.append(sib)
                if len(candidates) >= 5:
                    break

        for p in candidates:
            strong = p.find("strong")
            if not isinstance(strong, Tag):
                continue
            text = strong.get_text(separator=" ", strip=True)
            m = _HEADER_LINE_RE.search(text)
            if not m:
                continue
            month, day, loc, sp_text = m.group(1), m.group(2), m.group(3), m.group(4)
            month_day = f"{int(month):02d}-{int(day):02d}"
            species_hint = ""
            if "犬" in sp_text:
                species_hint = "犬"
            elif "猫" in sp_text:
                species_hint = "猫"
            elif sp_text:
                species_hint = "その他"
            return month_day, loc, species_hint
        return "", "", ""

    def _build_shelter_date(self, month_day: str) -> str:
        """`MM-DD` とページ更新年から ISO 形式 `YYYY-MM-DD` を作る

        年が特定できない場合は空文字 (= 不明扱い) を返す。
        """
        if not month_day:
            return ""
        year = self._extract_update_year(self._html_cache or "")
        if not year:
            return ""
        return f"{year}-{month_day}"

    @staticmethod
    def _extract_update_year(html: str) -> str:
        """ページの「更新日：YYYY年M月D日」から年だけを取り出す"""
        m = _UPDATE_YEAR_RE.search(html)
        if not m:
            return ""
        return f"{int(m.group(1)):04d}"

    def _extract_cell_images(self, cell: Tag, virtual_url: str) -> list[str]:
        """セル内の `<img src=...>` を絶対 URL のリストに変換する"""
        urls: list[str] = []
        for img in cell.find_all("img"):
            src = img.get("src")
            if src and isinstance(src, str):
                urls.append(self._absolute_url(src, base=virtual_url))
        return self._filter_image_urls(urls, virtual_url)

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫/その他) を推定する

        愛媛県のサイト名は「収容中」「譲渡予定」のいずれも犬猫を区別しない
        ため、明示的に "犬" / "猫" を含まない場合は "その他" を返す。
        実運用では見出し段落から species を取得できることが多い。
        """
        if "犬猫以外" in name or "以外" in name:
            return "その他"
        if "犬" in name and "猫" not in name:
            return "犬"
        if "猫" in name and "犬" not in name:
            return "猫"
        return "その他"


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 2 サイトを同一 adapter にマップする。
for _site_name in (
    "愛媛県動物愛護センター（収容中）",
    "愛媛県動物愛護センター（譲渡予定）",
):
    SiteAdapterRegistry.register(_site_name, PrefEhimeAdapter)
