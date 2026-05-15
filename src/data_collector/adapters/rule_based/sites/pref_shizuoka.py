"""静岡県（保護犬猫情報）rule-based adapter

対象ドメイン:
    https://www.pref.shizuoka.jp/kenkofukushi/eiseiyakuji/dobutsuaigo/1066835/index.html

特徴:
- 県の動物愛護担当ページ。静岡県本体は迷い犬情報を当該インデックスページに
  「管理番号付きの detail ページへのリンク」として並べ、実データは個別の
  detail ページ (例: `1066835/1082590.html`) に存在する典型的なハブ + 詳細
  構造である。実 HTML 内の動物 detail データは、Single-page 形式と異なり
  インデックス側にはほぼ存在せず「リンクテキスト中の管理番号」のみが拾える。
- 政令市 (静岡市/浜松市) の保護犬猫はこのページには掲載されず、外部リンク
  (city.shizuoka.lg.jp / hama-aikyou.jp) で別途案内される。インデックス内の
  外部参照リンク (`<ul class="objectlink">`) は動物データではないので除外する。
- 動物個別データの起点は本文 (`#content`) 内の `ul.listlink > li > a` で、
  href が "1066835/<page_id>.html" 形式の県内 detail ページを指す。
  リンクテキストは "迷い犬情報 2605GD001" のように見出し + 管理番号。
- 種別 (犬/猫) はサイト名 (「保護犬猫情報」) からは特定できないが、
  本ページは「迷い犬情報一覧」というタイトルなので犬として扱う。
  リンクテキストに「犬」「猫」のキーワードが含まれる場合はそちらを優先する。
- 本ページに収容日表記は無いため `SHELTER_DATE_DEFAULT` は空文字 (不明扱い)。
- ページ HTML が二重 UTF-8 mojibake 状態 (本来 UTF-8 のバイト列を Latin-1 と
  して再解釈し、再 UTF-8 化されている) で fixture 化されているケースがあり、
  `_load_rows` で「静岡」が含まれていない場合に限り逆変換 (latin-1 → utf-8)
  を試みる。実運用 (`requests`) では正しい UTF-8 で受け取るため、本処理は
  二重には適用されない (冪等)。
- 在庫 0 件のページでも `ParsingError` を出さず `fetch_animal_list` は
  空リストを返す (基底実装の "rows 空 → 例外" を上書き)。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter

# 「迷い犬情報　2605GD001」のような見出し+管理番号からの抽出
# 管理番号は半角英数字のみ (例: 2605GD001 / 2605CD001)
_MGMT_NUMBER_RE = re.compile(r"([A-Z0-9]{6,})")


class PrefShizuokaAdapter(SinglePageTableAdapter):
    """静岡県（保護犬猫情報）用 rule-based adapter

    インデックスページ (`1066835/index.html`) 内の `ul.listlink > li > a`
    を各動物 row として扱い、href が指す detail ページ URL と
    管理番号 (リンクテキスト中) を最低限の情報として抽出する。
    detail ページの中身までは取得しない (LLM パスや別ジョブで補強する想定)。
    """

    # 動物個別エントリの起点は本文内 `ul.listlink > li`。
    # 本文外のサイドバー (`nav#lnavi` 等) や外部リンク一覧 (`ul.objectlink`)
    # を誤検出しないよう、article#content 配下に限定する。
    ROW_SELECTOR: ClassVar[str] = "article#content ul.listlink > li"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 値の取り出しは `extract_animal_details` のオーバーライドが
    # 行うため `COLUMN_FIELDS` は契約宣言のみ (基底既定実装は使わない)。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    LOCATION_COLUMN: ClassVar[int | None] = None
    # 静岡県のインデックスページに収容日表記は無い (detail 側に有り) ため空文字
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """list_url の HTML を取得し、動物リンク `<li>` をキャッシュ

        - 二重 UTF-8 mojibake (latin-1 解釈 → utf-8 再エンコード) を補正
        - 本文外 (サイドバー、外部リンク一覧) を除外するため article#content
          配下の `ul.listlink > li` のみを対象とする
        - 見つからなければ空配列 (在庫 0 件として扱う)
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        html = self._html_cache
        # mojibake 検出: ページに「静岡」が含まれない場合は
        # latin-1 → utf-8 の逆変換を試みる。失敗したら元のまま。
        if "静岡" not in html:
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
            if not isinstance(elm, Tag):
                continue
            # 内部に <a href> が無い行 (ナビゲーション等) は除外
            anchor = elm.find("a", href=True)
            if not isinstance(anchor, Tag):
                continue
            rows.append(elm)

        self._rows_cache = rows
        return rows

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """動物リスト取得 (在庫 0 件でも ParsingError を出さない)

        各 row (`<li>`) 内の `<a href>` の絶対 URL をそのまま source_url
        として返す。SinglePageTableAdapter の仮想 URL (`#row=N`) ではなく
        実 URL を使うことで、detail ページが将来必要になった際にも
        そのまま fetch できるようにしておく。
        """
        rows = self._load_rows()
        category = self.site_config.category
        urls: list[tuple[str, str]] = []
        seen: set[str] = set()
        for li in rows:
            anchor = li.find("a", href=True)
            if not isinstance(anchor, Tag):
                continue
            href = anchor.get("href")
            if not isinstance(href, str) or not href.strip():
                continue
            absolute = self._absolute_url(href)
            if absolute in seen:
                continue
            seen.add(absolute)
            urls.append((absolute, category))
        return urls

    def extract_animal_details(self, detail_url: str, category: str = "sheltered") -> RawAnimalData:
        """インデックスページ上のリンク行から RawAnimalData を構築する

        detail ページは fetch せず、インデックス側で得られる情報
        (管理番号 / リンク見出しから推定する species) のみで構成する。
        収容日 / 場所 / 性別等は detail 側にあるため空文字で埋める。
        """
        rows = self._load_rows()
        anchor = self._find_row_anchor(rows, detail_url)
        if anchor is None:
            raise ParsingError(
                f"detail URL {detail_url} に対応する row が見つかりません",
                url=detail_url,
            )

        text = anchor.get_text(separator=" ", strip=True)
        # 種別はリンクテキスト > サイト名 > ページ見出し の順で推定する。
        # 本ページ (1066835) は「迷い犬情報一覧」なので既定で「犬」。
        species = self._infer_species(text, self.site_config.name)

        try:
            return RawAnimalData(
                species=species,
                sex="",
                age="",
                color="",
                size="",
                shelter_date=self.SHELTER_DATE_DEFAULT,
                location="",
                phone="",
                image_urls=[],
                source_url=detail_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=detail_url) from e

    # ─────────────────── ヘルパー ───────────────────

    def _find_row_anchor(self, rows: list[Tag], detail_url: str) -> Tag | None:
        """detail_url に一致する row 内の `<a>` を返す

        href は相対形式で格納されているので絶対 URL に変換した上で照合する。
        """
        for li in rows:
            anchor = li.find("a", href=True)
            if not isinstance(anchor, Tag):
                continue
            href = anchor.get("href")
            if not isinstance(href, str):
                continue
            if self._absolute_url(href) == detail_url:
                return anchor
        return None

    @staticmethod
    def _extract_management_number(text: str) -> str:
        """リンクテキストから管理番号 (例: '2605GD001') を抽出する

        テスト/将来拡張用のヘルパー。RawAnimalData には専用フィールドが
        無いため現時点では値の格納先は無い。
        """
        m = _MGMT_NUMBER_RE.search(text)
        return m.group(1) if m else ""

    @staticmethod
    def _infer_species(link_text: str, site_name: str) -> str:
        """リンクテキスト > サイト名 の優先順で species を推定する

        本ページは「迷い犬情報一覧」 (静岡県 1066835) を起点とするため、
        リンクテキスト中の「犬」「猫」キーワードを優先し、無ければ「犬」を
        既定値として返す。
        """
        for source in (link_text, site_name):
            if not source:
                continue
            # 「犬猫」のような複合語が出る場合は「その他」扱い
            if "犬猫" in source:
                # detail で species 不明なケースは「その他」より「犬」優先
                # (本ページのリンクは全て迷い犬情報のため)
                return "犬"
            if "犬" in source:
                return "犬"
            if "猫" in source:
                return "猫"
        return "犬"


# ─────────────────── サイト登録 ───────────────────
# sites.yaml の `name: 静岡県（保護犬猫情報）` と完全一致させる。
_SITE_NAME = "静岡県（保護犬猫情報）"
if SiteAdapterRegistry.get(_SITE_NAME) is None:
    SiteAdapterRegistry.register(_SITE_NAME, PrefShizuokaAdapter)
