"""山口県動物愛護センター（収容動物）rule-based adapter

対象ドメイン: https://www.pref.yamaguchi.lg.jp/site/doubutuaigo/

特徴:
- 対象ページ (`list25-151.html`) は山口県動物愛護センター直下の
  「健康福祉センター収容犬・猫情報」インデックスページであり、ここ自体には
  個別の動物情報は掲載されない。代わりに県内 8 健康福祉センター
  (周南/山口/宇部/長門/萩/防府/岩国/柳井/下関 等) の収容動物情報ページへの
  リンク一覧と注意事項が並ぶ典型的な「ハブ」ページ構成。
- ページ HTML は本文中に動物個別ブロックを持たないため、`fetch_animal_list`
  は通常 0 件 (空リスト) を返す。これは `pref_wakayama` / `pref_kanagawa`
  adapter と同様の「ハブページで本文 0 件状態が常態」パターンと整合する。
- 将来的に同じテンプレート上へ動物個別ブロック (テーブル / カード) が
  インライン掲載されるよう変更された場合に備え、典型的な動物カード /
  テーブル要素を `ROW_SELECTOR` で拾えるようにしておく。検出された場合は
  ラベル → フィールドのマップに従って属性を取り出す。
- 山口県の HTML レスポンスは fixture 上で UTF-8 バイト列を Latin-1 として
  誤解釈し再 UTF-8 化された二重エンコーディング (mojibake) になっている
  ことがあり、`_load_rows` で「山口」が含まれていない場合に限って
  逆変換 (latin-1 → utf-8) を試みる。実運用 (`requests`) では正しい UTF-8
  で受け取るため、この処理は冪等に no-op となる。
- 動物種別 (犬/猫/その他) はサイト名 (「収容動物」) からは特定できないため、
  HTML 中に種別が明示されている場合はそれを優先し、見つからなければ空文字。
- 本ページに収容日表記は無いため `SHELTER_DATE_DEFAULT` は空文字 (不明扱い)。
- 在庫 0 件のページでも `ParsingError` を出さず `fetch_animal_list` は
  空リストを返す (基底実装の "rows 空 → 例外" を上書き)。
- ページ構造はインデックス上の各リンクが `div.list_pack > div.article_txt`
  内にあるため、これらをサイドバー扱いとして ROW として誤検出しないよう、
  `ROW_SELECTOR` は本文の動物個別ブロック (`div.p-card-detail` 等の典型
  クラス、もしくは `#main_body table`) に限定する。
"""

from __future__ import annotations

from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


class PrefYamaguchiAdapter(SinglePageTableAdapter):
    """山口県動物愛護センター（収容動物）用 rule-based adapter

    インデックスページが「県内 8 健康福祉センターの収容情報リンク集」と
    なっており、本文には動物個別データが無い (= 0 件) のが通常運用。
    将来テンプレートに動物個別ブロックがインライン挿入されるケースに備え、
    典型的な動物カード / テーブル要素を抽出する経路も担保しておく。
    """

    # 動物個別ブロックの典型候補:
    # - 県の WordPress 系テンプレートで使われる `div.p-card-detail`
    # - 詳細属性テーブル
    # 本文 (#main_body) 配下に限定し、サイドバー (#sidebar2) や
    # インデックスのリンク一覧 (`div.list_pack`) を誤検出しないようにする。
    ROW_SELECTOR: ClassVar[str] = (
        "#main_body div.p-card-detail, "
        "#main_body div.p-animal-detail, "
        "#main_body div.animal-card, "
        "#main_body table"
    )
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 値の取り出しは `extract_animal_details` のオーバーライドが
    # 行うため `COLUMN_FIELDS` は契約宣言のみ (基底既定実装は使わない)。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    LOCATION_COLUMN: ClassVar[int | None] = None
    # ページ本文に収容日表記が無いため空文字 (不明扱い)
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """list_url の HTML を取得し、動物ブロックを抽出してキャッシュ

        - 二重 UTF-8 mojibake (latin-1 解釈 → utf-8 再エンコード) を補正
        - 動物個別カード / テーブルを `ROW_SELECTOR` で探す
        - 見つからなければ空配列 (在庫 0 件として扱う)
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        html = self._html_cache
        # mojibake 検出: ページに「山口」が含まれない場合は
        # latin-1 → utf-8 の逆変換を試みる。失敗したら元のまま。
        if "山口" not in html:
            try:
                html = html.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass

        # 復元後の HTML をキャッシュに反映 (extract_animal_details で
        # 同じ HTML を再利用できるようにするため)
        self._html_cache = html

        soup = BeautifulSoup(html, "html.parser")
        rows: list[Tag] = []
        for elm in soup.select(self.ROW_SELECTOR):
            if isinstance(elm, Tag):
                rows.append(elm)

        self._rows_cache = rows
        return rows

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """動物リスト取得 (在庫 0 件でも ParsingError を出さない)

        山口県の本ページは通常「8 健康福祉センターのリンク集 + 注意事項」のみで
        本文に動物個別データを持たない。在庫 0 件は正常運用なので
        基底実装のような ParsingError ではなく空リストを返す。
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
        """動物カード / テーブルから RawAnimalData を構築する

        テーブル (縦並び「項目名 / 値」) と div カード (フリーテキスト) の
        両方に対応する。ラベル → フィールドのマップは pref_wakayama と同等。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        block = rows[idx]

        # ラベル → RawAnimalData フィールド名のマッピング。
        # 山口県動物愛護センター固有のテンプレートが入手できていないため、
        # 一般的な保護動物テーブル / カードで想定される項目を網羅的にマップする。
        label_to_field = {
            "種類": "species",
            "種別": "species",
            "犬種": "species",
            "猫種": "species",
            "毛色": "color",
            "毛の色": "color",
            "性別": "sex",
            "体格": "size",
            "大きさ": "size",
            "年齢": "age",
            "推定年齢": "age",
            "保護日": "shelter_date",
            "収容日": "shelter_date",
            "保護場所": "location",
            "収容場所": "location",
            "発見場所": "location",
        }

        fields: dict[str, str] = {}

        # 1) `<table>` 形式: 各 <tr> の最後セルを値、それ以前のセルがラベル
        if block.name == "table":
            for tr in block.find_all("tr"):
                if not isinstance(tr, Tag):
                    continue
                cells = [
                    c for c in tr.find_all(["td", "th"]) if isinstance(c, Tag)
                ]
                if len(cells) < 2:
                    continue
                value_text = cells[-1].get_text(separator=" ", strip=True)
                for label_cell in cells[:-1]:
                    label_text = label_cell.get_text(separator="", strip=True)
                    matched = False
                    for label, field in label_to_field.items():
                        if field in fields:
                            continue
                        if label in label_text:
                            fields[field] = value_text
                            matched = True
                            break
                    if matched:
                        break
        else:
            # 2) `<div>` カード形式: 内部の <p>/<dt>/<dd> を順次走査して
            #    ラベル文字列を含むテキストを見つけ、続く要素 / 同要素
            #    内の値を取り出す
            for elm in block.find_all(["p", "dt", "dd", "li", "span"]):
                if not isinstance(elm, Tag):
                    continue
                text = elm.get_text(separator="", strip=True)
                if not text:
                    continue
                for label, field in label_to_field.items():
                    if field in fields:
                        continue
                    if label in text:
                        # "ラベル：値" "【ラベル】値" の形式から値を抽出
                        for sep in ("：", ":", "】", "/"):
                            if sep in text:
                                value = text.split(sep, 1)[1].strip()
                                if value:
                                    fields[field] = value
                                    break

        try:
            return RawAnimalData(
                species=fields.get("species", ""),
                sex=fields.get("sex", ""),
                age=fields.get("age", ""),
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=fields.get(
                    "shelter_date", self.SHELTER_DATE_DEFAULT
                ),
                location=fields.get("location", ""),
                phone="",
                image_urls=self._extract_row_images(block, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(
                f"RawAnimalData バリデーション失敗: {e}", url=virtual_url
            ) from e


# ─────────────────── サイト登録 ───────────────────
# sites.yaml の `name: 山口県動物愛護センター（収容動物）` と完全一致させる。
_SITE_NAME = "山口県動物愛護センター（収容動物）"
if SiteAdapterRegistry.get(_SITE_NAME) is None:
    SiteAdapterRegistry.register(_SITE_NAME, PrefYamaguchiAdapter)
