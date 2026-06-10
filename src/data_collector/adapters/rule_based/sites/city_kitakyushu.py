"""北九州市動物愛護センター rule-based adapter

対象ドメイン: https://www.city.kitakyushu.lg.jp/contents/

特徴:
- 同一テンプレート上で 2 サイト (保護犬/譲渡犬) を運用しており、
  URL パターンのみが異なる:
    - .../contents/924_11831.html  (収容されている犬の一覧 / sheltered)
    - .../contents/924_11834.html  (譲渡対象犬の紹介 / adoption)
- 1 ページに `<table>` 形式で動物情報が並ぶ single_page サイト。
  個別 detail ページは存在しない。
- ページ内に複数 `<table>` が存在し、収容情報以外の表
  (返還手数料等) が先に並ぶことがあるため、対象テーブルを
  `<caption>` テキストで識別する必要がある。
- 対象テーブル構造 (1 行 = 1 頭, 列順):
    <caption>収容表</caption>
    <thead>収容日 / 収容期限 / 区 / 種類（推定） / 毛色 / 性別 / 体格 / 備考</thead>
    <tbody><tr><td>...</td>... × 8</tr> ...</tbody>
- 収容数 0 件のときは `<tbody>` が無いか、データ行が存在しない
  状態になる。本 adapter では「データ行 0 件」として空リストを返す。
- 動物種別 (犬) はサイト名から推定する (北九州市は犬のみ運用)。
- フィクスチャは UTF-8 バイト列を Latin-1 として再保存した二重
  エンコーディング状態のことがあるため、テスト側で逆変換を行う。
"""

from __future__ import annotations

from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter

# 対象テーブルを `<caption>` で識別するためのキーワード
_TARGET_CAPTION_KEYWORDS = ("収容表", "譲渡")
# 譲渡犬テーブル (924_11834) を判別するキーワード (列順が保護犬と異なる)
_ADOPTION_CAPTION_KEYWORDS = ("譲渡",)


class CityKitakyushuAdapter(SinglePageTableAdapter):
    """北九州市動物愛護センター用 rule-based adapter

    保護犬 (924_11831) / 譲渡犬 (924_11834) の 2 サイトで共通テンプレート。
    `<table>` ヘッダ行 + データ行 N 件の single_page 形式。

    ただし保護犬と譲渡犬は同一 adapter でも**列構造が異なる**:
    - 保護犬 (収容表):   収容日 / 期限 / 区 / 種類 / 毛色 / 性別 / 体格 / 備考
    - 譲渡犬 (譲渡対象): 番号 / 種類 / 性別 / 毛色 / 推定生年 / フィラリア / 備考 / 写真

    また譲渡犬テーブルには「推定生年」(age 推定) と「写真」(画像 URL) 列が
    存在するため、本 adapter は対象テーブルの種別に応じて列マッピングと
    画像抽出ロジックを切り替える (2026-06 拡張)。
    """

    # ROW_SELECTOR は基底契約上必須だが、本 adapter は `_load_rows` を
    # オーバーライドして `<caption>` ベースで対象テーブルを選ぶため
    # 直接 select には使わない (フォールバック用に残す)。
    ROW_SELECTOR: ClassVar[str] = "table tr"
    SKIP_FIRST_ROW: ClassVar[bool] = False  # tbody > tr のみ抽出するため不要
    # 保護犬 (収容表) 用の列マッピング。
    # 列 0 (収容日) は shelter_date, 列 1 (収容期限) と列 7 (備考) は使わない。
    # 列 2 (区) を location, 列 3 (種類) は犬種詳細だが species にも使う、
    # ただし species はサイト名から「犬」固定で上書きする。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        0: "shelter_date",
        2: "location",
        3: "species",
        4: "color",
        5: "sex",
        6: "size",
    }
    # 譲渡犬 (譲渡対象の成犬の一覧) 用の列マッピング。
    # 列 0 (番号/愛称) と列 5 (フィラリア)・列 6 (備考) は RawAnimalData に
    # 直接マップしない。列 7 (写真) は別途 image_urls として処理する。
    _ADOPTION_COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        1: "species",
        2: "sex",
        3: "color",
        4: "age",
    }
    # 譲渡犬テーブルの「写真」列インデックス (<a href="*.jpg"> リンクが並ぶ)
    _ADOPTION_PHOTO_COLUMN: ClassVar[int] = 7
    LOCATION_COLUMN: ClassVar[int | None] = 2
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ページ末尾の担当課お問い合わせ電話 (北九州市保健福祉局生活衛生課)。
    # 動物テーブルに個別電話番号が無いため全件で共通利用する (2026-05 観測)。
    _CENTER_TEL: ClassVar[str] = "093-581-1800"

    # ─────────────────── オーバーライド ───────────────────

    # 対象テーブルが譲渡犬テーブルかを行抽出時に判定し extract 時に参照する
    _is_adoption_table_cache: bool = False

    def _load_rows(self) -> list[Tag]:
        """対象テーブル (`<caption>` に「収容表」等を含む) のデータ行のみ返す

        ページ内に複数 `<table>` が存在し得るため `<caption>` で対象を絞る。
        対象テーブルが見つからない場合は空リストを返す (呼出側で 0 件扱い)。
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        soup = BeautifulSoup(self._html_cache, "html.parser")
        target_table = self._find_target_table(soup)
        if target_table is None:
            self._rows_cache = []
            self._is_adoption_table_cache = False
            return self._rows_cache

        # caption から保護犬/譲渡犬を判別し、extract 時の列マッピング切替に使う
        self._is_adoption_table_cache = self._is_adoption_table(target_table)

        # `<tbody>` 配下の `<tr>` を優先。無ければ `<thead>` を除く全 `<tr>`
        tbody = target_table.find("tbody")
        rows: list[Tag]
        if isinstance(tbody, Tag):
            rows = [r for r in tbody.find_all("tr") if isinstance(r, Tag)]
        else:
            all_rows = [r for r in target_table.find_all("tr") if isinstance(r, Tag)]
            # thead 内の行を除外
            thead = target_table.find("thead")
            if isinstance(thead, Tag):
                head_rows = {id(r) for r in thead.find_all("tr")}
                rows = [r for r in all_rows if id(r) not in head_rows]
            else:
                # thead が無い場合は最初の行 (ヘッダ相当) を捨てる
                rows = all_rows[1:] if all_rows else []

        # `<th>` のみのヘッダ行が tbody 内に紛れ込んでいる場合は除外
        rows = [r for r in rows if r.find("td") is not None]
        self._rows_cache = rows
        return self._rows_cache

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """テーブル行を仮想 URL に変換する

        対象テーブルが無い / データ行 0 件の場合は空リストを返す
        (在庫 0 件は ParsingError ではなく空リストで表現する)。
        """
        rows = self._load_rows()
        category = self.site_config.category
        return [(f"{self.site_config.list_url}#row={i}", category) for i in range(len(rows))]

    def extract_animal_details(self, virtual_url: str, category: str = "adoption") -> RawAnimalData:
        """テーブル行から RawAnimalData を構築する

        対象テーブルが保護犬 (収容表) か譲渡犬 (譲渡対象) かを `_load_rows` 時の
        判定 (`_is_adoption_table_cache`) に基づいて列マッピングを切り替える。
        species はサイト名 (犬固定) で常に上書きする。
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

        column_map = (
            self._ADOPTION_COLUMN_FIELDS if self._is_adoption_table_cache else self.COLUMN_FIELDS
        )
        fields: dict[str, str] = {}
        for col_idx, field_name in column_map.items():
            if col_idx < len(cells):
                fields[field_name] = cells[col_idx].get_text(separator=" ", strip=True)

        # 動物種別はサイト名から推定 (北九州市は犬のみ運用だが将来拡張に備える)
        species = self._infer_species_from_site_name(self.site_config.name)
        # HTML の「種類」列 (例: 柴, 雑) は犬種詳細のため species 本体には使わず、
        # 必要なら color と並べて補助情報として残せるが、ここではサイト名推定を優先。
        if not species:
            species = fields.get("species", "")

        # 画像 URL は譲渡犬テーブルでは「写真」列の <a href="*.jpg"> から取得する。
        # 保護犬テーブルには画像列が存在しないため空リスト。
        if self._is_adoption_table_cache:
            image_urls = self._extract_adoption_photo_links(row, virtual_url)
        else:
            image_urls = self._extract_row_images(row, virtual_url)

        try:
            return RawAnimalData(
                species=species,
                # 「種類」列 (柴/雑 等) は species 本体に使わず品種として保存する
                breed=fields.get("species", ""),
                sex=fields.get("sex", ""),
                age=fields.get("age", ""),
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=fields.get("shelter_date", self.SHELTER_DATE_DEFAULT),
                location=fields.get("location", ""),
                phone=self._CENTER_TEL,
                image_urls=image_urls,
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _find_target_table(soup: BeautifulSoup) -> Tag | None:
        """`<caption>` テキストで対象テーブル (収容表/譲渡対象) を識別する

        ページ内に複数 `<table>` (返還手数料等) が存在し得るため、
        `<caption>` のテキストで対象を絞る。見つからない場合は
        ヒューリスティクスで「収容日」を含む `<th>` を持つ最大の表を選ぶ。
        """
        for table in soup.find_all("table"):
            if not isinstance(table, Tag):
                continue
            caption = table.find("caption")
            if isinstance(caption, Tag):
                text = caption.get_text(strip=True)
                if any(kw in text for kw in _TARGET_CAPTION_KEYWORDS):
                    return table
        # フォールバック: 「収容日」「種類」を含むヘッダを持つ最初の表
        for table in soup.find_all("table"):
            if not isinstance(table, Tag):
                continue
            header_text = " ".join(th.get_text(strip=True) for th in table.find_all("th"))
            if "収容日" in header_text and ("種類" in header_text or "毛色" in header_text):
                return table
        return None

    @staticmethod
    def _is_adoption_table(table: Tag) -> bool:
        """対象テーブルが譲渡犬 (譲渡対象) テーブルかを `<caption>` で判定する

        保護犬テーブルは「収容表」、譲渡犬テーブルは「譲渡対象の成犬の一覧」
        のように caption が異なる。caption が無い場合は保護犬扱い (False)。
        """
        caption = table.find("caption")
        if not isinstance(caption, Tag):
            return False
        text = caption.get_text(strip=True)
        return any(kw in text for kw in _ADOPTION_CAPTION_KEYWORDS)

    def _extract_adoption_photo_links(self, row: Tag, base_url: str) -> list[str]:
        """譲渡犬テーブルの「写真」列の <a href="*.jpg"> から画像 URL を取得する

        実サイト (924_11834) では写真列に `<a href="/files/xxx.jpg">写真N</a>`
        のリンクが複数並ぶ (img タグは無い)。基底の `_extract_row_images` は
        img タグ前提のため、本サイト用にリンク抽出を行う。
        """
        cells = row.find_all(["td", "th"])
        if self._ADOPTION_PHOTO_COLUMN >= len(cells):
            return []
        photo_cell = cells[self._ADOPTION_PHOTO_COLUMN]
        urls: list[str] = []
        for a in photo_cell.find_all("a"):
            href = a.get("href")
            if not isinstance(href, str):
                continue
            # 画像拡張子を持つリンクのみ採用 (PDF 等のリンクが混ざる場合に備える)
            lowered = href.lower().split("?", 1)[0]
            if not lowered.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                continue
            urls.append(self._absolute_url(href, base=base_url))
        # 重複除去 (順序保持)
        seen: set[str] = set()
        deduped: list[str] = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                deduped.append(u)
        return self._filter_image_urls(deduped, base_url)

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫/その他) を推定する"""
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return ""


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 2 サイトを同一 adapter にマップする。
for _site_name in (
    "北九州市（保護犬）",
    "北九州市（譲渡犬）",
):
    SiteAdapterRegistry.register(_site_name, CityKitakyushuAdapter)
