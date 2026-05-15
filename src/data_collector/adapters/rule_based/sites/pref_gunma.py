"""群馬県動物愛護センター rule-based adapter

対象ドメイン: https://www.pref.gunma.jp/

特徴:
- 同一ドメイン (pref.gunma.jp) 上で 3 サイトが共通テンプレートを使用する
  single_page 形式:
    - https://www.pref.gunma.jp/page/167499.html  (本所 保護犬)
    - https://www.pref.gunma.jp/page/179441.html  (東部支所 保護犬)
    - https://www.pref.gunma.jp/page/167523.html  (本所 保護猫)
- 群馬県 CMS の本文 (`#main_body` 配下 `div.detail_free`) は次のような並び:
    <div class="detail_free">
      <h2>飼い主さんを探しています</h2>
      <h3>収容情報</h3>
      <ul>...</ul>
      <h4>{地域名}（市町村...）</h4>
      <p>　現在、保管期間中の犬はおりません。　</p>
      ... (地域ごとに繰り返し)
    </div>
- 動物が収容されている場合は地域 `<h4>` の後に動物情報のブロック
  (テーブル / 段落 / 画像) が並ぶ想定。0 件のときは
  「現在、保管期間中の犬はおりません」「現在、保管期間中の猫はおりません」
  といった告知 `<p>` のみが置かれる。
- 個別 detail ページは存在しない single_page 形式。
- 動物種別 (犬/猫) はサイト名から推定する (URL パスや本文には
  明示されないため)。
- 0 件状態は ParsingError ではなく正常系として空リストを返す。
- このページは UTF-8 が正しく宣言されており、二重 UTF-8 mojibake は
  発生しない想定だが、念のため京都府 / 千葉県 adapter と同等の
  防御的補正は行わない (現状のフィクスチャに必要が無い)。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter

# 「現在、保管期間中の犬はおりません」「保護している猫はおりません」など
# 0 件告知パターン。表記揺れ (おりません/ありません/いません、犬/猫) を吸収。
_EMPTY_STATE_PATTERN = re.compile(
    r"(?:保管期間中|保護している|収容している|現在)[^。]*?"
    r"(?:犬|猫|動物|ペット)[^。]*?"
    r"(?:おりません|ありません|いません)"
)


class PrefGunmaAdapter(SinglePageTableAdapter):
    """群馬県動物愛護センター用 rule-based adapter

    本所 (保護犬/保護猫) と東部支所 (保護犬) の計 3 サイトで
    共通テンプレートを使用する single_page 形式。
    各動物データは本文 `div.detail_free` 配下に並ぶ想定。
    """

    # 本文 (`div#main_body` 配下) の動物データ起点。動物が居るときは
    # `div.detail_free` 内に地域別 `<h4>` + 各動物の table/段落が並ぶ。
    # 動物データの粒度は地域ブロック単位ではなく「テーブル単位」で扱うのが
    # 千葉県 / 京都府 adapter と整合的なため、本文 div 配下の `<table>` を
    # 1 動物として扱う。0 件時はテーブルが存在しないため fetch_animal_list
    # が空リストを返す。
    ROW_SELECTOR: ClassVar[str] = "div#main_body div.detail_free table"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 値の取り出しはオーバーライドした `extract_animal_details` が
    # 縦並びレイアウト (ラベル/値) を直接スキャンするため、
    # `COLUMN_FIELDS` は契約として宣言のみ。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        0: "species",
        1: "color",
        2: "sex",
        3: "size",
        4: "age",
        5: "shelter_date",
    }
    LOCATION_COLUMN: ClassVar[int | None] = None
    # 群馬県サイトには動物個別の収容日が必ず明示されているとは限らないため
    # デフォルト値は空文字 (不明扱い)。
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """list_url の HTML を取得し、動物テーブルをキャッシュする

        - 「お問い合わせ先」テーブル (caption/thead に "お問い合わせ" や
          "名称"/"所在地"/"電話番号" を含む) はサイト共通連絡先のため除外する。
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        soup = BeautifulSoup(self._html_cache, "html.parser")
        rows: list[Tag] = []
        for table in soup.select(self.ROW_SELECTOR):
            if not isinstance(table, Tag):
                continue
            if self._is_contact_table(table):
                continue
            rows.append(table)

        self._rows_cache = rows
        return rows

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """一覧ページから動物の仮想 URL を返す

        基底 `SinglePageTableAdapter.fetch_animal_list` は行が 0 件のとき
        `ParsingError` を投げるが、群馬県サイトでは
        「現在、保管期間中の犬はおりません」のような告知ページが正常状態
        として頻繁に発生する。empty state テキストを検出した場合は
        空リストを返し、それ以外で行が見つからなかった場合のみ
        ParsingError を伝播する。
        """
        rows = self._load_rows()
        if not rows:
            if self._html_cache and _EMPTY_STATE_PATTERN.search(self._html_cache):
                # 「現在、保管期間中の犬はおりません」等の正常な 0 件状態
                return []
            raise ParsingError(
                "行要素が見つかりません",
                selector=self.ROW_SELECTOR,
                url=self.site_config.list_url,
            )
        category = self.site_config.category
        return [(f"{self.site_config.list_url}#row={i}", category) for i in range(len(rows))]

    def extract_animal_details(
        self, virtual_url: str, category: str = "sheltered"
    ) -> RawAnimalData:
        """1 個の `<table>` から RawAnimalData を構築する

        群馬県 CMS のテーブルは「項目名 / 値」が左右に並ぶ縦並び構造を
        想定する。各 `<tr>` から最後のセルを値、それ以前のいずれかの
        セルにラベルが含まれているものとして読み取る。
        実装は京都府 / 佐賀県 adapter と同等の縦並び抽出。

        合わせて、テーブル直前の `<h4>` 地域名が取得できれば location に
        補完する (テーブル内に「保護場所」が明示されていない場合の
        フォールバック)。
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

        # ラベル → RawAnimalData フィールド名のマッピング。
        # 群馬県の実テンプレート (動物が居る時) は入手できていないため、
        # 一般的な保護動物テーブルで想定される項目を網羅的にマップする。
        label_to_field = {
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
            "体型": "size",
            "年齢": "age",
            "推定年齢": "age",
            "推定": "age",
            "保護日": "shelter_date",
            "収容日": "shelter_date",
            "保管日": "shelter_date",
            "保護場所": "location",
            "収容場所": "location",
            "発見場所": "location",
            "保管場所": "location",
        }

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
                for label, field in label_to_field.items():
                    if field in fields:
                        continue
                    if label in label_text:
                        fields[field] = value_text
                        matched = True
                        break
                if matched:
                    break

        # location が空ならテーブル直前 (兄弟方向に遡る) の `<h4>` 地域名で補完
        if not fields.get("location"):
            region = self._find_preceding_region_label(table)
            if region:
                fields["location"] = region

        # species はサイト名 (犬/猫) を優先採用、テーブル値はフォールバック
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
                image_urls=self._extract_row_images(table, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _is_contact_table(table: Tag) -> bool:
        """お問い合わせ先テーブルを除外するための判定

        - `<caption>` に「お問い合わせ」を含む
        - `<thead>` の `<th>` に「電話番号」「所在地」「名称」が
          並んでいる
        のいずれかを満たすテーブルを連絡先テーブルと見なす。
        """
        caption = table.find("caption")
        if isinstance(caption, Tag):
            caption_text = caption.get_text(strip=True)
            if "お問い合わせ" in caption_text or "問合せ" in caption_text:
                return True

        thead = table.find("thead")
        if isinstance(thead, Tag):
            ths = [th.get_text(strip=True) for th in thead.find_all("th") if isinstance(th, Tag)]
            joined = "".join(ths)
            if "電話番号" in joined and ("所在地" in joined or "名称" in joined):
                return True
        return False

    @staticmethod
    def _find_preceding_region_label(table: Tag) -> str:
        """テーブルの前に出現する直近の `<h4>` テキストを返す

        群馬県の本文は「<h4>地域名（市町村...）</h4>」の後に動物データが
        並ぶため、テーブルの兄弟を遡って最初に見つけた `<h4>` を地域名と見なす。
        無ければ空文字を返す。
        """
        for sib in table.find_previous_siblings():
            if not isinstance(sib, Tag):
                continue
            if sib.name == "h4":
                return sib.get_text(strip=True)
            # 別の動物 h2/h3 セクションに到達したら打ち切り
            if sib.name in ("h2", "h3"):
                break
        return ""

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫) を推定する

        - "保護犬" / "犬" を含む → "犬"
        - "保護猫" / "猫" を含む → "猫"
        - それ以外 → "" (空文字、テーブル値にフォールバック)
        """
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return ""


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 3 サイトを同一 adapter にマップする。
# `sites.yaml` の `prefecture: 群馬県` かつ `pref.gunma.jp` ドメインのもの。
for _site_name in (
    "群馬県動物愛護センター（保護犬）",
    "群馬県動物愛護センター東部支所（保護犬）",
    "群馬県動物愛護センター（保護猫）",
):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, PrefGunmaAdapter)
