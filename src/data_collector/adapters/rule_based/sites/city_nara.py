"""奈良市保健所 rule-based adapter

対象ドメイン: https://www.city.nara.lg.jp/life/4/34/

特徴:
- 奈良市の自治体 CMS は本文を `div#main_body` 配下に出力する。
  「ペットの飼養・届出」「保護動物情報」等のサイトはいずれもこの
  テンプレートに乗っており、コンテンツが
    - 行政手続き等の案内記事一覧 (`div.info_list_date > ul > li`)
    - 保護動物のテーブル (`<table>` または `dl`) ブロック
  のいずれか (もしくは両方) で表現される single_page 形式。
  個別の保護動物 detail ページは存在しない (リンク先は手続き案内記事)。
- 各案内記事は次の構造で並ぶ:
    <div class="info_list info_list_date">
      <ul>
        <li>
          <span class="article_title"><a href="/soshiki/97/...">{タイトル}</a></span>
          <span class="article_date">YYYY年M月D日更新</span>
        </li>
        ...
      </ul>
    </div>
  これらは「迷子犬・迷子猫をお探しの方へ」「犬の死亡届」等の手続き
  案内であって動物個体情報ではないため、保護動物 0 件状態として扱う。
- 保護動物が掲載される場合は、本文中に動物テーブル
  (種類/性別/毛色/収容日 等のラベル/値テーブル) が現れる想定。
  この場合は Takatsuki 同様に縦並びのラベル/値ペアから抽出する。
- 動物テーブルがそもそも無く、empty state テキスト
  (「現在、保護動物はありません」等) も無い場合でも、案内記事一覧
  (`div.info_list_date`) が存在するなら正常な 0 件として扱う。
- 奈良市のページは fixture 化される際に二重 UTF-8 mojibake (本来 UTF-8
  のバイト列を Latin-1 として解釈してから再度 UTF-8 として保存) になる
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


class CityNaraAdapter(SinglePageTableAdapter):
    """奈良市保健所用 rule-based adapter

    保護動物情報ページ / ペットの飼養・届出ページのテンプレートに対応する
    single_page 形式。本文 `div#main_body` 配下の動物テーブルを 1 件 = 1
    動物として扱い、行政手続き案内記事しか存在しない 0 件状態では空リスト
    を返す。
    """

    # 本文の動物テーブル候補。お問い合わせ先・関連リンク等のテンプレート
    # 要素を巻き込まないよう `div#main_body` にスコープを絞る。
    # 実際の動物テーブルかどうかは _load_rows で更にフィルタする。
    ROW_SELECTOR: ClassVar[str] = "div#main_body table"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 値の取り出しはオーバーライドした `extract_animal_details` が
    # 「ラベル/値」縦並びレイアウトを直接スキャンするため、
    # `COLUMN_FIELDS` は基底契約の充足のためだけに宣言する。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        0: "species",
        1: "sex",
        2: "color",
        3: "size",
        4: "shelter_date",
    }
    LOCATION_COLUMN: ClassVar[int | None] = None
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # 「現在、保護動物はおりません」「掲載する情報はありません」等の
    # 0 件告知パターン (高槻市・柏市 adapter と同じ表記揺れを許容)
    _EMPTY_STATE_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"(?:掲載する情報[^。]*?ありません"
        r"|(?:現在|現時点)[^。]*?(?:ありません|いません|おりません)"
        r"|(?:収容|保護|譲渡(?:対象)?)(?:動物|犬|猫)[^。]*?"
        r"(?:おりません|ありません|いません))"
    )

    # 動物情報ではないテンプレート table を判定するための見出しキーワード
    _TEMPLATE_TABLE_KEYWORDS: ClassVar[tuple[str, ...]] = (
        "お問い合わせ先",
        "関連リンク",
        "関連情報",
        "申請",
        "届出",
        "手数料",
        "金額",
        "内訳",
    )

    # ラベル → RawAnimalData フィールド名のマッピング
    _LABEL_TO_FIELD: ClassVar[dict[str, str]] = {
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
        "収容場所": "location",
        "保護場所": "location",
        "発見場所": "location",
        "場所": "location",
    }

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """list_url の HTML を 1 回だけ取得し、動物テーブルのみキャッシュ

        - 二重 UTF-8 mojibake (latin-1 解釈 → utf-8 再エンコード) を補正
        - `div#main_body` 配下の `<table>` から、空テーブル及び
          お問い合わせ先 / 関連リンク 等のテンプレート table を除外する
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        html = self._html_cache
        # mojibake 検出: ページに「奈良」「ペット」が含まれない場合は
        # latin-1 → utf-8 の逆変換を試みる。失敗したら元のまま。
        if "奈良" not in html and "ペット" not in html:
            try:
                html = html.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
        # 復元後の HTML をキャッシュに反映 (extract_animal_details で
        # 同じ HTML を再利用できるようにするため)
        self._html_cache = html

        soup = BeautifulSoup(html, "html.parser")
        candidates = soup.select(self.ROW_SELECTOR)
        rows: list[Tag] = []
        for tbl in candidates:
            if not isinstance(tbl, Tag):
                continue
            trs = [tr for tr in tbl.find_all("tr") if isinstance(tr, Tag)]
            if not trs:
                # 空テーブル (動物枠だけ用意されているプレースホルダ)
                continue
            if self._is_template_table(tbl):
                # お問い合わせ先 / 関連リンク 等の共通テンプレート
                continue
            rows.append(tbl)
        if self.SKIP_FIRST_ROW and rows:
            rows = rows[1:]
        self._rows_cache = rows
        return rows

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """動物リスト取得 (在庫 0 件でも ParsingError を出さない)

        基底実装は `<table>` が 0 件のとき `ParsingError` を投げるが、
        奈良市のテンプレートでは:
          - 「現在、保護動物はおりません」等の告知文だけが入るパターン
          - 案内記事 (`div.info_list_date`) のみで動物テーブルが無いパターン
            (本フィクスチャ「ペットの飼養・届出」がこのケース)
          - 本文 (`div#main_body`) は存在するが動物枠が無いパターン
        いずれも保護動物の正常な 0 件状態として扱い、空リストを返す。
        本文ブロックすら見つからない (テンプレート崩壊) 場合のみ
        `ParsingError` を伝播する。
        """
        rows = self._load_rows()
        category = self.site_config.category

        if not rows:
            html = self._html_cache or ""
            soup = BeautifulSoup(html, "html.parser")
            main_body = soup.find(id="main_body")
            info_list = soup.select_one("div.info_list, div.info_list_date")
            # 告知文 / 案内記事一覧 / 本文ブロックのいずれかがあれば 0 件と扱う
            if (
                info_list is not None
                or main_body is not None
                or self._EMPTY_STATE_PATTERN.search(html)
            ):
                return []
            # 本文ブロックも告知も無い (テンプレート崩壊) ときは ParsingError
            raise ParsingError(
                "行要素が見つかりません",
                selector=self.ROW_SELECTOR,
                url=self.site_config.list_url,
            )

        return [(f"{self.site_config.list_url}#row={i}", category) for i in range(len(rows))]

    def extract_animal_details(
        self, virtual_url: str, category: str = "sheltered"
    ) -> RawAnimalData:
        """1 個の動物テーブルから RawAnimalData を構築する

        奈良市の動物テーブルは「ラベル / 値」が左右に並ぶ縦並び構造を
        想定 (Takatsuki / Machida と同等)。テーブル内の各 `<tr>` から
        最後のセルを値、それ以前のいずれかのセルにラベルが含まれて
        いるものとして読み取る。
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
                for label, field in self._LABEL_TO_FIELD.items():
                    if field in fields:
                        continue
                    if label in label_text:
                        fields[field] = value_text
                        matched = True
                        break
                if matched:
                    break

        # species: テーブル値から推定 (具体名 → 犬/猫 への正規化)、
        # 取得できない場合はサイト名から推定。
        species_raw = fields.get("species", "")
        species = self._infer_species_from_breed(species_raw) or species_raw
        if not species:
            species = self._infer_species_from_site_name(self.site_config.name)

        try:
            return RawAnimalData(
                species=species,
                sex=fields.get("sex", ""),
                age=fields.get("age", ""),
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=fields.get("shelter_date", self.SHELTER_DATE_DEFAULT),
                location=fields.get("location", ""),
                phone="",
                image_urls=self._extract_row_images(table, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    # ─────────────────── ヘルパー ───────────────────

    @classmethod
    def _is_template_table(cls, table: Tag) -> bool:
        """テンプレートテーブル (お問い合わせ先 / 関連リンク 等) かを判定

        テーブル内の `<th>` セル、もしくは 1 行目のいずれかのセルに
        テンプレート用キーワードが含まれている場合に True。
        """
        # まず <th> を優先的に走査
        ths = [th for th in table.find_all("th") if isinstance(th, Tag)]
        for th in ths:
            text = th.get_text(separator="", strip=True)
            if any(kw in text for kw in cls._TEMPLATE_TABLE_KEYWORDS):
                return True
        # <th> が無い、もしくは見出しが一致しない場合は 1 行目セルを確認
        first_row = table.find("tr")
        if isinstance(first_row, Tag):
            for cell in first_row.find_all(["td", "th"]):
                if not isinstance(cell, Tag):
                    continue
                text = cell.get_text(separator="", strip=True)
                if any(kw in text for kw in cls._TEMPLATE_TABLE_KEYWORDS):
                    return True
        return False

    @staticmethod
    def _infer_species_from_breed(breed: str) -> str:
        """「種類」値 (柴犬/雑種/三毛猫等) から動物種別を推定する"""
        if not breed:
            return ""
        if "犬" in breed:
            return "犬"
        if "猫" in breed:
            return "猫"
        return ""

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別を推定する (フォールバック)

        奈良市のサイト名「奈良市（保護動物情報）」は犬/猫いずれも明示が
        無いため、通常は空文字を返す。将来サイト名が「保護犬」「保護猫」
        のように分割された場合に備えた汎用ロジック。
        """
        has_dog = "犬" in name
        has_cat = "猫" in name
        if has_dog and has_cat:
            return ""
        if has_dog:
            return "犬"
        if has_cat:
            return "猫"
        return ""


# ─────────────────── サイト登録 ───────────────────
# `sites.yaml` の `prefecture: 奈良県` かつ `city.nara.lg.jp` ドメイン。
for _site_name in ("奈良市（保護動物情報）",):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, CityNaraAdapter)
