"""大阪市 (おおさかワンニャンセンター) rule-based adapter

対象ドメイン: https://www.city.osaka.lg.jp/kenko/page/

特徴:
- 同一テンプレート上で 4 サイト (迷子犬/迷子猫/譲渡犬/譲渡猫) を運用しており、
  URL の page ID のみが異なる single_page 形式:
    .../page/0000110901.html (迷子犬 = 収容犬情報)
    .../page/0000117147.html (迷子猫 = 収容猫情報)
    .../page/0000206024.html (譲渡犬)
    .../page/0000206027.html (譲渡猫)
- 1 ページに複数動物がブロック形式で並ぶ。個別 detail ページは存在しない。
- 各動物は次のような並びで `<div class="sub_h3_box"><h3>` を起点に表現される:
    <div class="sub_h3_box"><h3>識別番号／A2605120001</h3></div>
    <div class="mol_imageblock clearfix">
      <div class="mol_imageblock_left">
        <div class="mol_imageblock_w_long700 mol_imageblock_img_al_left">
          <div class="mol_imageblock_img">
            <a href="..."><img class="mol_imageblock_img_large" src="..." alt="..." /></a>
          </div>
          <p>・収容日／2026年5月12日<br />
             ・掲載期限／2026年5月19日<br />
             ・収容場所／大阪市住之江区<br />
             ・種類／雑種<br />
             ・毛色／茶白<br />
             ・性別／メス<br />
             ・推定年齢／成犬<br />
             ・体格／中<br />
             ・首輪／無<br />
             ・その他／</p>
        </div>
      </div>
    </div>
- 在庫 0 件のときは「識別番号／」(値が空) の H3 と
  「現在、収容情報はありません。」alt の画像が代わりに表示される。
  これらはデータとして抽出せず空リストを返す。
- ページの mojibake 対応: fixture 上では UTF-8 バイト列を Latin-1 と誤認して
  再 UTF-8 化された二重エンコーディング状態になっている場合がある。
  `_load_rows` で「大阪」が含まれていないときに限り逆変換を試みる。
- 種別 (犬/猫) はサイト名から推定する (HTML の「種類」は "雑種"/"柴犬" 等の
  品種名のため)。
- テーブル形式ではなく `<p>` 内の `・ラベル／値<br>` の並びで構造化されているので
  基底 `SinglePageTableAdapter` の `td/th` ベース既定実装は使わず、
  `extract_animal_details` をオーバーライドする。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


# 「YYYY年MM月DD日」を ISO 形式に変換するための正規表現
_DATE_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")

# 在庫 0 件プレースホルダ画像の alt 文言 (テンプレート由来)
_EMPTY_PLACEHOLDER_ALT = "現在、収容情報はありません"


class CityOsakaAdapter(SinglePageTableAdapter):
    """大阪市動物管理センター用 rule-based adapter

    迷子犬/迷子猫/譲渡犬/譲渡猫 の 4 サイトで共通テンプレートを使用する
    single_page 形式。各動物は `<div class="sub_h3_box"><h3>識別番号／...</h3></div>`
    を起点としたブロックで表現される。
    """

    # 各動物の起点となる H3 (識別番号)
    ROW_SELECTOR: ClassVar[str] = "div.sub_h3_box h3"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 基底の cells ベース既定実装は使わない (`<p>` 内の `・ラベル／値<br>` を解析する)。
    # 契約として明示する。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    LOCATION_COLUMN: ClassVar[int | None] = None
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # 属性段落のラベル → RawAnimalData フィールド名
    _LABEL_TO_FIELD: ClassVar[dict[str, str]] = {
        "収容日": "shelter_date",
        "収容場所": "location",
        "種類": "breed",
        "毛色": "color",
        "性別": "sex",
        "推定年齢": "age",
        "年齢": "age",
        "体格": "size",
    }

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """list_url の HTML を取得し、動物ブロックの起点 h3 をキャッシュ

        - 二重 UTF-8 mojibake (latin-1 解釈 → utf-8 再エンコード) を補正
        - 「識別番号／」を含まない h3 (本来出ないがガード) を除外
        - 「識別番号／」の値が空 (在庫 0 件プレースホルダ) は除外
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        html = self._html_cache
        # mojibake 検出: ページタイトルや本文に「大阪」が含まれない場合は
        # latin-1 → utf-8 の逆変換を試みる。失敗したら元のまま。
        if "大阪" not in html:
            try:
                html = html.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass

        soup = BeautifulSoup(html, "html.parser")
        rows: list[Tag] = []
        for h3 in soup.select(self.ROW_SELECTOR):
            if not isinstance(h3, Tag):
                continue
            text = h3.get_text(strip=True)
            # 動物データの h3 は必ず「識別番号／」を含む
            if "識別番号" not in text:
                continue
            # 「識別番号／」(値が空) は在庫 0 件プレースホルダなので除外
            management_number = self._extract_management_number(text)
            if not management_number:
                # 値が空の場合は隣接画像で更にダメ押し確認 (alt が
                # "現在、収容情報はありません。" であることが多い)
                if self._is_empty_placeholder_after(h3):
                    continue
                # alt から判別できない場合も識別番号が空なら採用しない
                continue
            rows.append(h3)

        self._rows_cache = rows
        return rows

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """動物リスト取得 (在庫 0 件でも ParsingError を出さない)

        基底実装は rows が空のとき例外を出すが、大阪市のサイトは
        収容動物が居ない期間でもページ自体は存在するため、空リストを返す。
        """
        rows = self._load_rows()
        category = self.site_config.category
        return [
            (f"{self.site_config.list_url}#row={i}", category)
            for i in range(len(rows))
        ]

    def extract_animal_details(
        self, virtual_url: str, category: str = "adoption"
    ) -> RawAnimalData:
        """`<h3>識別番号／...</h3>` を起点とした動物ブロックから抽出する

        基底の `td/th` 既定実装は使わず、直後の
        `<div class="mol_imageblock">` 内 `<p>` 群を解析する。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        h3 = rows[idx]

        # h3 直後の <div class="mol_imageblock"> を取得
        imageblock = self._find_imageblock_after(h3)

        fields: dict[str, str] = {}
        image_urls: list[str] = []

        if imageblock is not None:
            # 画像 URL を集める (a > img.mol_imageblock_img_large 優先、なければ全 img)
            for img in imageblock.find_all("img"):
                src = img.get("src")
                if not src or not isinstance(src, str):
                    continue
                # プレースホルダ alt の画像はスキップ (在庫ありブロックには
                # 通常出ないが念のため)
                alt = img.get("alt") or ""
                if isinstance(alt, str) and _EMPTY_PLACEHOLDER_ALT in alt:
                    continue
                # 別ウィンドウアイコン (new_window01.svg 等) は除外
                if "new_window" in src or src.endswith(".svg"):
                    continue
                image_urls.append(self._absolute_url(src, base=virtual_url))

            # 属性 <p> を解析 (内部 <br> 区切り、各行が "・ラベル／値" 形式)
            for p in imageblock.find_all("p"):
                text = p.get_text(separator="\n", strip=False)
                for line in text.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    # 行頭の中黒「・」を除去
                    if line.startswith("・"):
                        line = line[1:].strip()
                    # 全角スラッシュ「／」または半角「/」または全角コロン「：」で分割
                    label, value = self._split_label_value(line)
                    if label is None:
                        continue
                    field = self._LABEL_TO_FIELD.get(label)
                    if field and value and field not in fields:
                        if field == "shelter_date":
                            fields[field] = self._parse_date(value) or value
                        else:
                            fields[field] = value

        # 種別はサイト名から推定 (HTML の「種類」は品種名のため)
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
    def _extract_management_number(h3_text: str) -> str:
        """「識別番号／A2605120001」から管理番号 "A2605120001" を返す

        値が空 (在庫 0 件プレースホルダ) の場合は空文字を返す。
        全角スラッシュ「／」/ 半角「/」/ 全角コロン「：」/ 半角「:」の
        いずれかを区切りとして許容する。
        """
        for sep in ("／", "/", "：", ":"):
            if sep in h3_text:
                _, _, value = h3_text.partition(sep)
                return value.strip()
        return ""

    @staticmethod
    def _is_empty_placeholder_after(h3: Tag) -> bool:
        """h3 直後の画像 alt が「現在、収容情報はありません。」かを判定する"""
        for sib in h3.parent.find_next_siblings() if h3.parent else []:
            if not isinstance(sib, Tag):
                continue
            if sib.name in ("h2", "h3"):
                break
            for img in sib.find_all("img"):
                alt = img.get("alt") or ""
                if isinstance(alt, str) and _EMPTY_PLACEHOLDER_ALT in alt:
                    return True
            # 1 つ先の sibling まで見れば十分
            return False
        return False

    @staticmethod
    def _find_imageblock_after(h3: Tag) -> Tag | None:
        """h3 を含む sub_h3_box の次に出現する mol_imageblock を返す

        テンプレート構造:
          <div class="sub_h3_box"><h3>識別番号／...</h3></div>
          <div class="mol_imageblock clearfix">...</div>
        """
        # h3 の直接の親 (div.sub_h3_box) の sibling を順に走査
        anchor: Tag | None = h3.parent if isinstance(h3.parent, Tag) else None
        if anchor is None:
            return None
        for sib in anchor.find_next_siblings():
            if not isinstance(sib, Tag):
                continue
            # 別動物の起点 / 別セクションに到達したら打ち切り
            if sib.name in ("h2", "h3"):
                break
            if "sub_h2_box" in (sib.get("class") or []):
                break
            if "sub_h3_box" in (sib.get("class") or []):
                break
            if sib.name == "div":
                classes = sib.get("class") or []
                if "mol_imageblock" in classes:
                    return sib
                # 念のため内側に mol_imageblock がある場合も拾う
                inner = sib.find("div", class_="mol_imageblock")
                if isinstance(inner, Tag):
                    return inner
        return None

    @staticmethod
    def _split_label_value(line: str) -> tuple[str | None, str]:
        """「ラベル／値」または「ラベル：値」を分割する

        Returns:
            (label, value) ラベルが見当たらなければ (None, "")
        """
        for sep in ("／", "/", "：", ":"):
            if sep in line:
                label, _, value = line.partition(sep)
                return label.strip(), value.strip()
        return None, ""

    @staticmethod
    def _parse_date(text: str) -> str:
        """「2026年5月12日」を "2026-05-12" に変換する

        変換できなければ空文字を返す。
        """
        m = _DATE_RE.search(text)
        if not m:
            return ""
        y, mo, d = m.group(1), m.group(2), m.group(3)
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫) を推定する"""
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return "その他"


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 4 サイトを同一 adapter にマップする。
for _site_name in (
    "大阪市（迷子犬）",
    "大阪市（迷子猫）",
    "大阪市（譲渡犬）",
    "大阪市（譲渡猫）",
):
    SiteAdapterRegistry.register(_site_name, CityOsakaAdapter)
