"""川崎市動物愛護センター rule-based adapter

対象ドメイン: https://www.city.kawasaki.jp/350/page/

特徴:
- 同一テンプレート上で 3 サイト (収容犬 / 収容猫 / 収容その他動物) を
  運用しており、URL のページ ID のみが異なる single_page 形式:
    .../350/page/0000077270.html (収容犬)
    .../350/page/0000109367.html (収容猫)
    .../350/page/0000074729.html (収容その他動物)
- 川崎市の CMS テンプレートは本文が `div.main_naka_kiji` 配下に出力され、
  各セクションは `<div class="mol_contents">` ブロックで構成される。
- 各動物情報は `<h3>` 見出し + 直後の `<div class="mol_textblock">` /
  `<div class="mol_imageblock">` のペアで表現されることが多いが、
  サイト・時期によっては `<table>` ベースで提供されるケースもある。
  本 adapter はまず `<h3>` 起点ブロックを探し、見つからなければ
  `<table>` 行を、いずれも見つからなければ 0 件として扱う。
- 在庫 0 件のときは `mol_textblock` 内 `<p>` に
  「現在、収容（保護）されている犬はいません。」のような告知が入る
  (本フィクスチャがこのケース)。この場合 ParsingError ではなく
  空リストを返す。
- 動物種別 (犬/猫/その他) はサイト名から推定する
  (HTML の「種類」は具体的な犬種名等のことがあるため)。
- 川崎市ページは fixture 化される際に二重 UTF-8 mojibake (本来 UTF-8
  のバイト列を Latin-1 として解釈してから再度 UTF-8 として保存) に
  なるケースがあるため、HTML キャッシュ取得時に逆変換を試みる。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


# 「現在、…の収容情報はありません」「現在、収容（保護）されている犬はいません。」
# 等の 0 件告知パターン。表記揺れ (です/ません/おりません/いません/ありません)
# を緩く吸収する。
_EMPTY_STATE_PATTERN = re.compile(
    r"(?:現在|現時点)[^。]*?(?:ありません|いません|おりません)"
)

# 「収容日：YYYY年MM月DD日」「収容日 2026/05/12」等を緩く拾う
_SHELTER_DATE_RE = re.compile(
    r"収容日[\s:：]*"
    r"(?:(\d{4})\s*[年/\-\.]\s*(\d{1,2})\s*[月/\-\.]\s*(\d{1,2})\s*日?)"
)

# ラベル → RawAnimalData フィールド名
_LABEL_TO_FIELD: dict[str, str] = {
    "種類": "breed",
    "品種": "breed",
    "犬種": "breed",
    "性別": "sex",
    "年齢": "age",
    "推定年齢": "age",
    "毛色": "color",
    "色": "color",
    "体格": "size",
    "大きさ": "size",
    "収容場所": "location",
    "保護場所": "location",
    "場所": "location",
}


class CityKawasakiAdapter(SinglePageTableAdapter):
    """川崎市動物愛護センター用 rule-based adapter

    収容犬 / 収容猫 / 収容その他動物 の 3 サイトで共通テンプレートを使用する
    single_page 形式。
    本文 (`div.main_naka_kiji`) 配下の `<h3>` 起点ブロック、または
    `<table>` 行を 1 動物として扱う。
    在庫 0 件 (告知 `<p>` のみ) の場合は空リストを返す。
    """

    # 起点候補は本文内の `<h3>` (動物別ブロック)。
    # `<table>` ベースの場合は `_load_rows` 側でフォールバック処理する。
    ROW_SELECTOR: ClassVar[str] = "div.main_naka_kiji h3"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 基底の cells ベース既定実装は使わない (ブロックベース抽出のため)。
    # 契約として明示する。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    LOCATION_COLUMN: ClassVar[int | None] = None
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """list_url の HTML を取得し、動物ブロックの起点要素をキャッシュ

        - 二重 UTF-8 mojibake (latin-1 解釈 → utf-8 再エンコード) を補正
        - 本文 `div.main_naka_kiji` 配下から:
          1) `<h3>` ブロック起点を最優先
          2) なければ本文内 `<table>` のデータ行 (`<tr>` with `<td>`) を採用
        - 在庫 0 件は空リストとして返す (`fetch_animal_list` で
          告知文を確認した上で例外化するか判定)
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        html = self._html_cache
        # mojibake 検出: ページに「川崎」が含まれない場合は
        # latin-1 → utf-8 の逆変換を試みる。失敗したら元のまま。
        if "川崎" not in html:
            try:
                html = html.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass

        # 復元後の HTML をキャッシュに反映 (extract_animal_details で
        # 同じ HTML を再利用できるようにするため)
        self._html_cache = html

        soup = BeautifulSoup(html, "html.parser")
        honbun = soup.select_one("div.main_naka_kiji")
        if honbun is None:
            self._rows_cache = []
            return self._rows_cache

        rows: list[Tag] = []

        # 1) <h3> ベースの動物ブロック
        for h3 in honbun.find_all("h3"):
            if not isinstance(h3, Tag):
                continue
            text = h3.get_text(strip=True)
            if not text:
                continue
            # 「保護収容動物情報」「お問い合わせ先」「同じ分類から探す」など
            # ナビ系の見出しは除外
            if self._is_navigation_heading(text):
                continue
            rows.append(h3)

        # 2) フォールバック: 本文内 <table> のデータ行
        if not rows:
            for table in honbun.find_all("table"):
                if not isinstance(table, Tag):
                    continue
                for tr in table.find_all("tr"):
                    if not isinstance(tr, Tag):
                        continue
                    if tr.find("td") is None:
                        # ヘッダ行は除外
                        continue
                    # 全セル空 (`&nbsp;` のみ等) は除外
                    cells = tr.find_all(["td", "th"])
                    if not any(
                        c.get_text(separator="", strip=True)
                         .replace("\xa0", "")
                         .strip()
                        for c in cells
                    ):
                        continue
                    rows.append(tr)

        self._rows_cache = rows
        return rows

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """動物リスト取得 (在庫 0 件でも ParsingError を出さない)

        基底実装は rows が空のとき例外を出すが、川崎市のサイトは
        収容動物が居ない期間でもページ自体は存在し
        「現在、収容（保護）されている犬はいません。」と告知される
        ため、これを検出して空リストを返す。
        本文ブロックそのものが見つからない (テンプレート崩壊) 場合は
        ParsingError として扱う。
        """
        rows = self._load_rows()
        category = self.site_config.category

        if not rows:
            # 「現在、…はいません」「情報はありません」等の正常な 0 件状態
            html = self._html_cache or ""
            if (
                _EMPTY_STATE_PATTERN.search(html)
                or "情報はありません" in html
                or "いません" in html
            ):
                return []
            # 本文も見つからない (テンプレート崩壊) ときは ParsingError
            raise ParsingError(
                "動物ブロックが見つかりません",
                selector=self.ROW_SELECTOR,
                url=self.site_config.list_url,
            )

        return [
            (f"{self.site_config.list_url}#row={i}", category)
            for i in range(len(rows))
        ]

    def extract_animal_details(
        self, virtual_url: str, category: str = "sheltered"
    ) -> RawAnimalData:
        """動物ブロックから RawAnimalData を構築する

        起点要素が `<h3>` の場合は次の `<h3>` までの兄弟要素群から、
        起点が `<tr>` の場合はセルテキストの「ラベル：値」/列順から
        属性を抽出する。動物種別はサイト名から推定する。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        anchor = rows[idx]

        if anchor.name == "tr":
            fields, image_urls = self._extract_from_table_row(
                anchor, virtual_url
            )
        else:
            fields, image_urls = self._extract_from_h3_block(
                anchor, virtual_url
            )

        # 動物種別はサイト名から推定 (HTML 上の「種類」は犬種名等のことがある)
        species = self._infer_species_from_site_name(self.site_config.name)

        try:
            return RawAnimalData(
                species=species,
                sex=fields.get("sex", ""),
                age=fields.get("age", ""),
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=fields.get(
                    "shelter_date", self.SHELTER_DATE_DEFAULT
                ),
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

    def _extract_from_h3_block(
        self, h3: Tag, base_url: str
    ) -> tuple[dict[str, str], list[str]]:
        """`<h3>` 起点の動物ブロックから (fields, image_urls) を抽出

        h3 の次以降の兄弟を「次の <h3> / <h2>」が現れるまで走査し、
        テキスト中の「ラベル：値」(全角/半角コロン) と画像 URL を集める。
        """
        fields: dict[str, str] = {}
        image_urls: list[str] = []

        # h3 自体のテキストにも収容日が入りうる
        head_text = h3.get_text(separator=" ", strip=True)
        self._merge_label_fields(head_text, fields)

        for sib in h3.find_next_siblings():
            if not isinstance(sib, Tag):
                continue
            if sib.name in ("h1", "h2", "h3"):
                # 次の動物ブロック / 別セクションに到達したら打ち切り
                break

            # 画像
            for img in sib.find_all("img"):
                src = img.get("src")
                if isinstance(src, str) and src:
                    image_urls.append(self._absolute_url(src, base=base_url))

            # 段落 / リスト等のテキストから「ラベル：値」を抽出
            for p in sib.find_all(["p", "li", "dd", "dt", "span", "div"]):
                text = p.get_text(separator=" ", strip=True)
                if text:
                    self._merge_label_fields(text, fields)

            # 兄弟自身もテキストノードを持ちうる
            text = sib.get_text(separator=" ", strip=True)
            if text:
                self._merge_label_fields(text, fields)

        # 画像 URL は基底ヘルパで重複除去 + フィルタ
        image_urls = self._filter_image_urls(image_urls, base_url)
        return fields, image_urls

    def _extract_from_table_row(
        self, tr: Tag, base_url: str
    ) -> tuple[dict[str, str], list[str]]:
        """`<tr>` 起点の行から (fields, image_urls) を抽出

        テーブル行は次の 2 形式を想定:
          a) 「ラベル｜値」型 (1 行 = 1 属性) → 行内の <th>/<td> を結合
          b) 「列ヘッダ｜列値」型 (1 行 = 1 動物) → 上位 `<table>` の
             `<thead>` または最初の `<tr>` をヘッダとして対応付け
        """
        fields: dict[str, str] = {}
        image_urls: list[str] = []

        cells = [c for c in tr.find_all(["td", "th"]) if isinstance(c, Tag)]

        # 画像
        for img in tr.find_all("img"):
            src = img.get("src")
            if isinstance(src, str) and src:
                image_urls.append(self._absolute_url(src, base=base_url))

        # ラベル列 (a 型) : <th>ラベル</th><td>値</td> の 2 セル構造
        if len(cells) == 2 and cells[0].name == "th":
            label = cells[0].get_text(separator=" ", strip=True).rstrip("：:")
            value = cells[1].get_text(separator=" ", strip=True)
            self._set_field_by_label(label, value, fields)
            # 値側にも「収容日」等が混じりうる
            self._merge_label_fields(value, fields)
        else:
            # b 型: 列ヘッダと対応付け
            headers = self._table_headers_for_row(tr)
            if headers and len(headers) == len(cells):
                for h, c in zip(headers, cells):
                    text = c.get_text(separator=" ", strip=True)
                    self._set_field_by_label(h, text, fields)
            # ヘッダが取れない場合でも各セルから「ラベル：値」を拾う
            for c in cells:
                text = c.get_text(separator=" ", strip=True)
                if text:
                    self._merge_label_fields(text, fields)

        image_urls = self._filter_image_urls(image_urls, base_url)
        return fields, image_urls

    @staticmethod
    def _table_headers_for_row(tr: Tag) -> list[str]:
        """`tr` が属するテーブルの列見出しリストを返す (`<thead>` 優先)"""
        # 最も近い <table> 祖先
        table = tr.find_parent("table")
        if not isinstance(table, Tag):
            return []
        thead = table.find("thead")
        header_tr: Tag | None = None
        if isinstance(thead, Tag):
            cand = thead.find("tr")
            if isinstance(cand, Tag):
                header_tr = cand
        if header_tr is None:
            first_tr = table.find("tr")
            if isinstance(first_tr, Tag) and first_tr is not tr:
                # 最初の <tr> がヘッダのみ (`<th>` 主体) であればヘッダ扱い
                if first_tr.find("th") is not None and first_tr.find("td") is None:
                    header_tr = first_tr
        if header_tr is None:
            return []
        return [
            th.get_text(separator=" ", strip=True).rstrip("：:")
            for th in header_tr.find_all(["th", "td"])
            if isinstance(th, Tag)
        ]

    @classmethod
    def _merge_label_fields(cls, text: str, fields: dict[str, str]) -> None:
        """テキスト中の「ラベル：値」「収容日 YYYY年…」を抽出して fields に追加"""
        if not text:
            return

        # 収容日の優先抽出 (ISO 形式に整形)
        if "shelter_date" not in fields:
            m = _SHELTER_DATE_RE.search(text)
            if m:
                y, mo, d = m.group(1), m.group(2), m.group(3)
                fields["shelter_date"] = (
                    f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
                )

        # 「ラベル：値」を行ごとに探す (全角/半角コロン)
        for chunk in re.split(r"[\n\r]+|(?<=[。])", text):
            chunk = chunk.strip()
            if not chunk:
                continue
            m = re.match(r"\s*([^:：]{1,8})\s*[:：]\s*(.+)$", chunk)
            if m:
                label = m.group(1).strip()
                value = m.group(2).strip()
                cls._set_field_by_label(label, value, fields)

    @staticmethod
    def _set_field_by_label(
        label: str, value: str, fields: dict[str, str]
    ) -> None:
        """ラベル文字列を `_LABEL_TO_FIELD` で正規化し、空でなければ格納"""
        if not value:
            return
        # ラベルの末尾全角スペース等を除去
        label = label.strip().rstrip("：:")
        # 完全一致を優先
        target = _LABEL_TO_FIELD.get(label)
        if target is None:
            # 部分一致 (「収容場所など」のような付加文字を許容)
            for k, v in _LABEL_TO_FIELD.items():
                if k in label:
                    target = v
                    break
        if target is None:
            return
        if target == "breed":
            # breed は species と区別するが現状の RawAnimalData では
            # species フィールドのみ。サイト名推定値を優先するため
            # ここでは無視する (将来 features 等への格納に拡張可)。
            return
        # 既存値があれば上書きしない (h3 自体のテキスト等を優先)
        if not fields.get(target):
            fields[target] = value

    @staticmethod
    def _is_navigation_heading(text: str) -> bool:
        """ナビゲーション系の見出し (動物データではない) かを判定"""
        if not text:
            return True
        nav_keywords = (
            "お問い合わせ",
            "同じ分類から探す",
            "外部リンク",
            "市公式SNS",
            "ページの",
            "よくある質問",
        )
        for kw in nav_keywords:
            if kw in text:
                return True
        # 「保護収容動物情報」のようにカテゴリ全体の見出しは除外したいが、
        # 動物データのブロック見出しと文字列が被る場合があるため、
        # 厳密には「個別動物」の判定基準が必要。動物データの h3 には
        # 通常「番号」「収容日」「管理番号」等のキーワードが含まれる。
        # ここでは "（この記事の分類）" 等の純ナビのみ除外し、
        # 残りは動物候補として通す。
        if "（この記事の分類）" in text:
            return True
        return False

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫/その他) を推定する"""
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return "その他"


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 3 サイトを同一 adapter にマップする。
# `sites.yaml` の `prefecture: 神奈川県` かつ `city.kawasaki.jp` ドメイン。
for _site_name in (
    "川崎市（収容犬）",
    "川崎市（収容猫）",
    "川崎市（収容その他動物）",
):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, CityKawasakiAdapter)
