"""神奈川県動物愛護センター rule-based adapter

対象ドメイン: https://www.pref.kanagawa.jp/osirase/1594/awc/lost/

特徴:
- 同一テンプレート上で 4 サイト (保護犬/保護猫/その他動物/センター外保護動物)
  を運用する single_page 形式。URL パスのみ異なる:
    .../awc/lost/dog.html      (保護犬)
    .../awc/lost/cat.html      (保護猫)
    .../awc/lost/other.html    (その他動物)
    .../awc/lost/outside.html  (センター外保護動物)
- 神奈川県動物愛護センターは保護動物の詳細を主に PDF (`assets/pdf/lost/*.pdf`)
  で配布しており、HTML ページ本文には動物個別データが掲載されないことが多い。
  代わりに「当所で保護している犬の情報 (PDF)」というダウンロードボタンが
  常時掲示される 0 件状態のページとして提供される。
- 将来的に HTML 内へ動物個別ブロックがインラインで掲載される可能性に備え、
  典型的な動物カード/テーブル要素を ROW_SELECTOR で拾えるようにしておく。
- ページ HTML が二重 UTF-8 mojibake 状態 (本来 UTF-8 のバイト列を Latin-1
  として再解釈) で fixture 化されているケースがあり、`_load_rows` で
  逆変換を試みる。
- 在庫 0 件のページでも `ParsingError` を出さず `fetch_animal_list` は
  空リストを返す。
- 動物種別 (犬/猫/その他) は HTML 上に明示されないため、サイト名から推定する
  ("センター外保護動物" のように犬猫いずれも含むケースは "その他" 扱い)。
- 収容日もページに掲載されないため空文字 (不明扱い)。
"""

from __future__ import annotations

from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


class PrefKanagawaAdapter(SinglePageTableAdapter):
    """神奈川県動物愛護センター用 rule-based adapter

    保護犬 / 保護猫 / その他動物 / センター外保護動物 の 4 サイトで
    共通テンプレートを使用する single_page 形式。
    実サイトでは動物詳細が PDF 配布のため HTML 本文に動物データが
    無い 0 件状態が通常。adapter としては HTML 内に動物カードが
    挿入されたケースも処理できる構造にしておく。
    """

    # 本文 (`main` 内 `section`) 配下に動物カードが配置される想定。
    # 実サイトに動物データが載るときの典型として `div.p-card-detail`
    # (個別動物カード) と `table` (属性テーブル) の両方を候補とする。
    # 0 件状態のページではこれらは出現せず、_load_rows は空配列を返す。
    ROW_SELECTOR: ClassVar[str] = (
        "main div.p-card-detail, main div.p-animal-detail, main section table"
    )
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 値の取り出しは `extract_animal_details` のオーバーライドが
    # 行うため `COLUMN_FIELDS` は契約宣言のみ (基底既定実装は使わない)。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    LOCATION_COLUMN: ClassVar[int | None] = None
    # 神奈川県サイトには収容日表記が無い (PDF 配布) ため空文字
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
        # mojibake 検出: ページに「神奈川」が含まれない場合は
        # latin-1 → utf-8 の逆変換を試みる。失敗したら元のまま。
        if "神奈川" not in html:
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

        基底実装は rows が空のとき例外を出すが、神奈川県のサイトは
        通常運用が「動物詳細は PDF で配布、HTML 本文は告知のみ」のため
        在庫 0 件のページが正常状態として頻出する。空リストを返す。
        """
        rows = self._load_rows()
        category = self.site_config.category
        return [(f"{self.site_config.list_url}#row={i}", category) for i in range(len(rows))]

    def extract_animal_details(
        self, virtual_url: str, category: str = "sheltered"
    ) -> RawAnimalData:
        """動物カード / テーブルから RawAnimalData を構築する

        テーブル (縦並び「項目名/値」) と div カード (フリーテキスト) の
        両方に対応する。ラベルから値への対応は京都府 adapter と同等。
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
        # 神奈川県サイトの実テンプレートが入手できていないため、
        # 一般的な保護動物テーブル/カードで想定される項目を網羅的にマップする。
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
                cells = [c for c in tr.find_all(["td", "th"]) if isinstance(c, Tag)]
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

        # species はサイト名 (犬/猫/その他のヒント) を優先採用する
        species = self._infer_species_from_site_name(self.site_config.name)
        if not species:
            species = fields.get("species", "")

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
                image_urls=self._extract_row_images(block, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫/その他) を推定する

        - "犬猫以外" / "その他" / "センター外" / "他" を含む → "その他"
          ("センター外保護動物" は犬猫含むため種別不定 → その他扱い)
        - "犬" を含む → "犬"
        - "猫" を含む → "猫"
        - いずれにも該当しない → "" (空文字)
        """
        if "犬猫以外" in name or "その他" in name or "センター外" in name:
            return "その他"
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return ""


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 4 サイトを同一 adapter にマップする。
# `sites.yaml` の `prefecture: 神奈川県` かつ `pref.kanagawa.jp` ドメインのもの。
# (横須賀市・横浜市・川崎市は別ドメイン/別 adapter の責務なので含まない)
for _site_name in (
    "神奈川県動物愛護センター（保護犬）",
    "神奈川県動物愛護センター（保護猫）",
    "神奈川県動物愛護センター（その他動物）",
    "神奈川県動物愛護センター（センター外保護動物）",
):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, PrefKanagawaAdapter)
