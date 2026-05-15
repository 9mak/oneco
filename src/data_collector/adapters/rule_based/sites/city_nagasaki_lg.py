"""長崎市動物愛護管理センター rule-based adapter

対象ドメイン: https://www.city.nagasaki.lg.jp/site/doubutsuaigo/

特徴:
- 同一テンプレート上で 2 サイト (犬里親募集 / 猫里親募集) を運用しており、
  URL のページ ID のみが異なる single_page 形式:
    .../site/doubutsuaigo/list7-19.html (犬里親募集)
    .../site/doubutsuaigo/list7-18.html (猫里親募集)
- 長崎市の CMS テンプレートは本文が `div#main_body` 配下に出力され、
  個別記事は `div.info_list_wrap > div.info_list > ul > li > div.list_pack`
  というネストで列挙される。各 `list_pack` は次の構造を持つ:
    <div class="list_pack">
      <div class="article_txt">
        <span class="article_date">YYYY年M月D日更新</span>
        <span class="article_title"><a href="...">{タイトル}</a></span>
      </div>
    </div>
- テーブル形式ではなくリンク列形式のため、`SinglePageTableAdapter` の
  `td/th` ベース既定実装ではなく `extract_animal_details` をオーバーライド
  して `span.article_date` / `span.article_title` から値を取得する。
- 在庫 0 件 (募集なし) の期間はページ自体は存在するが本文の
  `div.info_list` に `<li>` が含まれない、または「現在...ありません/
  おりません」等の告知文だけが入る。この場合は `ParsingError` ではなく
  空リストを返す (川崎市 adapter と同様)。
- 動物種別 (犬/猫) はサイト名から推定する (HTML には明示されない)。
- 収容日に相当する日付は `article_date` の「YYYY年M月D日更新」表記から
  ISO 8601 (`YYYY-MM-DD`) に変換する。
- 長崎市ページは fixture 化される際に二重 UTF-8 mojibake (本来 UTF-8 の
  バイト列を Latin-1 として解釈してから再度 UTF-8 として保存) になる
  ケースがあるため、HTML キャッシュ取得時に逆変換を試みる。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter

# 「現在...ありません」「現在...いません」「現在...おりません」等の
# 0 件告知パターン (川崎市 adapter と同じ表記揺れを許容)
_EMPTY_STATE_PATTERN = re.compile(r"(?:現在|現時点)[^。]*?(?:ありません|いません|おりません)")

# 「YYYY年M月D日」「YYYY年M月D日更新」「YYYY/M/D」等を緩く拾う
_DATE_RE = re.compile(r"(\d{4})\s*[年/\-\.]\s*(\d{1,2})\s*[月/\-\.]\s*(\d{1,2})")


class CityNagasakiLgAdapter(SinglePageTableAdapter):
    """長崎市動物愛護管理センター用 rule-based adapter

    犬里親募集 / 猫里親募集 の 2 サイトで共通テンプレートを使用する
    single_page 形式。本文 `div#main_body` 配下の
    `div.info_list_wrap > div.info_list > ul > li > div.list_pack`
    を 1 動物として扱う。
    在庫 0 件 (告知 `<p>` のみ / `<li>` が無い) の場合は空リストを返す。
    """

    # 各動物 (記事) は `div.list_pack` で表現される
    ROW_SELECTOR: ClassVar[str] = "div.info_list_wrap div.list_pack"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 基底の cells ベース既定実装は使わない (リンク列形式のため)。
    # 契約として明示する。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    LOCATION_COLUMN: ClassVar[int | None] = None
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """list_url の HTML を取得し、`div.list_pack` をキャッシュ

        - 二重 UTF-8 mojibake (latin-1 解釈 → utf-8 再エンコード) を補正
        - `div.info_list_wrap` 配下の `div.list_pack` を抽出
        - 該当要素が無ければ空リストとして返す
          (`fetch_animal_list` 側で告知文を確認した上で例外化するか判定)
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        html = self._html_cache
        # mojibake 検出: ページに「長崎」が含まれない場合は
        # latin-1 → utf-8 の逆変換を試みる。失敗したら元のまま。
        if "長崎" not in html:
            try:
                html = html.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass

        # 復元後の HTML をキャッシュに反映 (extract_animal_details で
        # 同じ HTML を再利用できるようにするため)
        self._html_cache = html

        soup = BeautifulSoup(html, "html.parser")
        rows = [r for r in soup.select(self.ROW_SELECTOR) if isinstance(r, Tag)]
        self._rows_cache = rows
        return rows

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """動物リスト取得 (在庫 0 件でも ParsingError を出さない)

        基底実装は rows が空のとき例外を出すが、長崎市のサイトは
        里親募集が 0 件の期間でもページ自体は存在し
        「現在...いません」等の告知だけが入るため、これを検出して
        空リストを返す。本文ブロックそのものが見つからない
        (テンプレート崩壊) 場合は ParsingError として扱う。
        """
        rows = self._load_rows()
        category = self.site_config.category

        if not rows:
            html = self._html_cache or ""
            soup = BeautifulSoup(html, "html.parser")
            main_body = soup.find(id="main_body")
            info_wrap = soup.select_one("div.info_list_wrap")
            # 告知文が入っているか / 本文ブロックが存在するなら 0 件と扱う
            if (
                info_wrap is not None
                or main_body is not None
                or _EMPTY_STATE_PATTERN.search(html)
                or "情報はありません" in html
                or "募集はありません" in html
            ):
                return []
            # 本文ブロックも告知も無い (テンプレート崩壊) ときは ParsingError
            raise ParsingError(
                "動物ブロックが見つかりません",
                selector=self.ROW_SELECTOR,
                url=self.site_config.list_url,
            )

        return [(f"{self.site_config.list_url}#row={i}", category) for i in range(len(rows))]

    def extract_animal_details(self, virtual_url: str, category: str = "adoption") -> RawAnimalData:
        """`div.list_pack` から RawAnimalData を構築する

        - 動物種別はサイト名から推定 (犬/猫)
        - 収容日 (shelter_date) は `span.article_date` の「YYYY年M月D日更新」
          を ISO 8601 (`YYYY-MM-DD`) に変換
        - 場所 (location) は `span.article_title` のテキストから取得
          (長崎市のページ構造ではタイトル以外に場所情報が無いため
          記事タイトルをそのまま location として保持し、後段の
          normalizer で都道府県名を補完する想定)
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        pack = rows[idx]

        date_el = pack.select_one("span.article_date")
        title_el = pack.select_one("span.article_title")
        date_text = date_el.get_text(strip=True) if isinstance(date_el, Tag) else ""
        title_text = (
            title_el.get_text(separator=" ", strip=True) if isinstance(title_el, Tag) else ""
        )

        shelter_date = self._parse_iso_date(date_text)
        species = self._infer_species_from_site_name(self.site_config.name)

        try:
            return RawAnimalData(
                species=species,
                sex="",
                age="",
                color="",
                size="",
                shelter_date=shelter_date,
                location=title_text,
                phone="",
                image_urls=self._extract_row_images(pack, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _parse_iso_date(text: str) -> str:
        """「YYYY年M月D日(更新)」「YYYY/M/D」等を ISO 8601 に変換

        該当パターンが見つからなければ空文字列を返す
        (RawAnimalData は文字列フィールドなので空可)。
        """
        if not text:
            return ""
        m = _DATE_RE.search(text)
        if not m:
            return ""
        y, mo, d = m.group(1), m.group(2), m.group(3)
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫/その他) を推定する"""
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return "その他"


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 2 サイトを同一 adapter にマップする。
# `sites.yaml` の `prefecture: 長崎県` かつ `city.nagasaki.lg.jp` ドメイン。
for _site_name in (
    "長崎市動物愛護管理センター（犬里親募集）",
    "長崎市動物愛護管理センター（猫里親募集）",
):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, CityNagasakiLgAdapter)
