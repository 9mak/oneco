"""倉敷市（保護動物）rule-based adapter

対象ドメイン: https://www.city.kurashiki.okayama.jp/kurashi/pet/1013042/

特徴:
- 1 ページに保護動物が `<ul class="listlink"><li><a>...</a></li>...</ul>`
  形式で並ぶ single_page 形式。個別 detail ページへリンクされてはいるが、
  データの主要項目（収容日 / 収容場所 / 動物種別 / 性別）は一覧の `<a>`
  テキストにすべて埋め込まれているため、一覧ページのみで抽出する。
- `<a>` テキスト例:
    "令和08年04月30日　児島小川　猫（雑種）♀"
  全角スペース (　) で 4 フィールドに分割される:
    [収容日, 収容場所, 動物種別（種類）, 性別記号]
- 在庫 0 件のときは `<ul class="listlink">` が出ないか空の可能性があるため、
  ParsingError ではなく空リストを返す（pref_shimane と同方針）。
- fixture が二重 UTF-8 mojibake になっている場合があるため、本文に「倉敷」
  が含まれない場合のみ latin-1 → utf-8 で逆変換を試みる。
- 問い合わせ先電話番号 (086-434-9829) は `#reference` ブロックに固定で
  記載されているのでサイト共通値として全行に注入する。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


# 「令和YY年MM月DD日」「YYYY年M月D日」「YYYY/M/D」「YYYY-M-D」を ISO に揃える
_REIWA_RE = re.compile(r"令和\s*(\d{1,2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
_GREG_DATE_RE = re.compile(
    r"(\d{4})\s*[年/\-.]\s*(\d{1,2})\s*[月/\-.]\s*(\d{1,2})"
)
# 動物種別フィールド: 「猫（雑種）」「犬（トイプードル）」など
_SPECIES_BREED_RE = re.compile(r"^\s*([^（(\s]+)\s*(?:[（(]([^）)]*)[）)])?\s*$")
# 性別記号 → 文字列マッピング
_SEX_MAP = {
    "♂": "オス",
    "♀": "メス",
    "オス": "オス",
    "メス": "メス",
    "雄": "オス",
    "雌": "メス",
}


class CityKurashikiAdapter(SinglePageTableAdapter):
    """倉敷市 保護動物情報 rule-based adapter

    一覧ページ (`ul.listlink > li`) の各 `<a>` テキストに収容日・場所・
    種類・性別が全角スペース区切りで 1 行に格納される single_page 形式。
    """

    ROW_SELECTOR: ClassVar[str] = "ul.listlink > li"
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # 問い合わせ先電話番号（ページに固定で 1 つだけ記載されている）
    _CONTACT_PHONE: ClassVar[str] = "086-434-9829"

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """list_url の HTML を取得し、`<li>` 行をキャッシュ

        - mojibake 補正（本文に「倉敷」が含まれない場合のみ）
        - リンクを持たない `<li>` は除外（在庫 0 件時のフォールバック行など）
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        html = self._html_cache
        if "倉敷" not in html:
            try:
                html = html.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
        self._html_cache = html

        soup = BeautifulSoup(html, "html.parser")
        rows: list[Tag] = []
        for li in soup.select(self.ROW_SELECTOR):
            if not isinstance(li, Tag):
                continue
            a = li.find("a")
            if not isinstance(a, Tag):
                continue
            if not a.get_text(strip=True):
                continue
            rows.append(li)

        self._rows_cache = rows
        return rows

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """動物リスト取得（在庫 0 件でも ParsingError を出さない）

        倉敷市のページは保護動物が居ない期間でも 404 にはならず、
        単に `<ul class="listlink">` 配下の `<li>` が消えるだけと想定し、
        その場合は空リストを返す。
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
        """`<li><a>` テキストから RawAnimalData を構築する

        テキスト例:
            "令和08年04月30日　児島小川　猫（雑種）♀"

        全角スペースで 4 分割し、それぞれ
        [shelter_date, location, species(+breed), sex] として解釈する。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        li = rows[idx]
        a = li.find("a")
        if not isinstance(a, Tag):
            raise ParsingError(
                "li 内に <a> が見つかりません", url=virtual_url
            )

        text = a.get_text(separator=" ", strip=True)
        # 全角スペース・半角スペース・タブいずれでも分割対象とするが、
        # 倉敷市の表記は基本的に全角スペース 1 個区切り。
        parts = [p for p in re.split(r"[　\s]+", text) if p]

        date_text = parts[0] if len(parts) > 0 else ""
        location = parts[1] if len(parts) > 1 else ""
        # 倉敷市の表記では「猫（雑種）♀」のように species と sex が
        # 全角スペース無しで連結している場合がある。1 トークンで来た場合は
        # 末尾の性別記号を切り出して species 部分と sex 部分に分割する。
        species_breed = parts[2] if len(parts) > 2 else ""
        sex_token = parts[3] if len(parts) > 3 else ""
        if not sex_token and species_breed:
            species_breed, sex_token = self._split_species_sex(species_breed)

        shelter_date = self._parse_shelter_date(date_text)
        species = self._parse_species(species_breed)
        sex = self._parse_sex(sex_token)

        # detail ページ URL は `<a href>`（在れば絶対化）。無ければ仮想 URL。
        href = a.get("href")
        if isinstance(href, str) and href:
            source_url = self._absolute_url(href, base=self.site_config.list_url)
        else:
            source_url = virtual_url

        try:
            return RawAnimalData(
                species=species,
                sex=sex,
                age="",
                color="",
                size="",
                shelter_date=shelter_date or self.SHELTER_DATE_DEFAULT,
                location=location,
                phone=self._normalize_phone(self._CONTACT_PHONE),
                image_urls=[],
                source_url=source_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(
                f"RawAnimalData バリデーション失敗: {e}", url=virtual_url
            ) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _parse_shelter_date(text: str) -> str:
        """収容日文字列から ISO 形式 `YYYY-MM-DD` を返す

        - 令和XX年MM月DD日 → 2018 + XX 年に換算
        - YYYY年MM月DD日 / YYYY/MM/DD / YYYY-MM-DD → そのまま
        - 不明な形式は空文字
        """
        if not text:
            return ""
        m = _REIWA_RE.search(text)
        if m:
            yy, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            # 令和元年 = 2019 → 2018 + 1
            year = 2018 + yy
            return f"{year:04d}-{mo:02d}-{d:02d}"
        m = _GREG_DATE_RE.search(text)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return f"{y:04d}-{mo:02d}-{d:02d}"
        return ""

    @staticmethod
    def _parse_species(text: str) -> str:
        """「猫（雑種）」「犬（トイプードル）」等から species を犬/猫/その他へ"""
        if not text:
            return ""
        m = _SPECIES_BREED_RE.match(text)
        head = m.group(1) if m else text
        if "犬" in head and "猫" not in head:
            return "犬"
        if "猫" in head and "犬" not in head:
            return "猫"
        return "その他"

    @staticmethod
    def _split_species_sex(text: str) -> tuple[str, str]:
        """「猫（雑種）♀」のような連結文字列を species 部と sex 記号に分割

        末尾に ♂ / ♀ / 雄 / 雌 が含まれていればその直前で切る。
        該当しなければ (text, "") を返す。
        """
        if not text:
            return ("", "")
        for token in ("♂", "♀", "雄", "雌"):
            i = text.rfind(token)
            if i >= 0:
                return (text[:i].strip(), token)
        return (text, "")

    @staticmethod
    def _parse_sex(text: str) -> str:
        """性別記号/文字列を「オス」「メス」に正規化"""
        if not text:
            return ""
        for token, value in _SEX_MAP.items():
            if token in text:
                return value
        return ""


# ─────────────────── サイト登録 ───────────────────
SiteAdapterRegistry.register("倉敷市（保護動物）", CityKurashikiAdapter)
