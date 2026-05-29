"""大分市犬の保護収容情報サイト rule-based adapter

対象ドメイン: https://www.city.oita.oita.jp/kurashi/pet/inunohogo/index.html

実構造 (2026-05-29 確認):
- index.html (list_url) は説明文 + **detail 記事 1 つへのリンク** だけ
  (`/oNNN/kurashi/pet/NNNNNNNNNNNNN.html`)
- detail 記事ページに **複数動物がフリーテキストで並ぶ**:
  - 動物ブロック開始: 「令和N年M月D日飼い主さんを探しています」見出し
  - 直後にコロン区切りで:
    - 保護した場所: {地名}
    - 種類: {犬種}
    - 推定年齢: {年齢}
    - 毛色: {色}
    - 性別: {オス/メス}
    - 体格: {大きさ}
    - その他: {備考}
- 「お家がみつかりました」セクション以降は飼い主返却済み = sheltered 解消
  なので除外する

以前は WordPressListAdapter ベースで「1 detail link = 1 動物」と誤想定し、
detail HTML が dl/th-td じゃなくフリーテキストなので全件抽出失敗 (detail_error)
していた。本リファクタで「1 detail link に複数動物」が正解とわかったので、
list → detail を 2 段階 fetch し、detail 1 件から複数 RawAnimalData を返す
構造に書き直し。
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ....domain.models import AnimalData, RawAnimalData
from ...municipality_adapter import ParsingError
from ..base import RuleBasedAdapter
from ..registry import SiteAdapterRegistry

# 動物ブロックの開始見出し:「令和N年M月D日…探しています」
# (「お家がみつかりました」も「飼い主さんからのお迎え…」だが、こちらは
# 後段で除外するためここでは「探しています」のみマッチさせる)
_BLOCK_HEADER_RE = re.compile(r"令和(\d+)年(\d{1,2})月(\d{1,2})日[^\n]*?探しています")

# 「お家がみつかりました」セクション以降は除外
_END_OF_ACTIVE_SECTION = "お家がみつかりました"

# 動物ブロック本文の終端マーカー (次のブロック見出し以外で
# ブロックが終わるケース: 注釈・フッタ・別セクション)
_BLOCK_END_MARKERS: tuple[str, ...] = ("※", "問合せ先", "愛護動物", _END_OF_ACTIVE_SECTION)

# 各動物ブロック内のラベル抽出パターン (改行で値が区切られる前提)
_FIELD_PATTERNS: dict[str, re.Pattern[str]] = {
    "species": re.compile(r"種類[：:]\s*([^\n]+)"),
    "age": re.compile(r"(?:推定年齢|年齢)[：:]\s*([^\n]+)"),
    "color": re.compile(r"毛色[：:]\s*([^\n]+)"),
    "sex": re.compile(r"性別[：:]\s*([^\n]+)"),
    "size": re.compile(r"(?:体格|大きさ)[：:]\s*([^\n]+)"),
    "location": re.compile(r"(?:保護した場所|発見場所|収容場所|場所)[：:]\s*([^\n]+)"),
}

# index.html (list_url) から取り出す detail 記事 URL の形式:
# `/oNNN/kurashi/pet/NNNNNNNNNNNNN.html`
_ARTICLE_HREF_RE = re.compile(r"/o\d+/kurashi/pet/\d+\.html$")


class CityOitaAdapter(RuleBasedAdapter):
    """大分市犬の保護収容情報 single_page rule-based adapter

    list_url 1ページに複数動物がフリーテキストで並ぶ構造。
    「探しています」配下のブロックを 1 動物 = 1 RawAnimalData として返す。
    `#row=N` のフラグメントで個別 URL を生成する (URL は同一ページ)。
    """

    def __init__(self, site_config: Any) -> None:
        super().__init__(site_config)
        self._detail_html_cache: str | None = None
        self._detail_url_cache: str | None = None
        self._blocks_cache: list[dict[str, str]] | None = None

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """list → detail を辿り、detail 内の動物ブロックを `#row=N` URL で返す"""
        blocks = self._load_blocks()
        category = self.site_config.category
        base = self._detail_url_cache or self.site_config.list_url
        return [(f"{base}#row={i}", category) for i in range(len(blocks))]

    def extract_animal_details(
        self, virtual_url: str, category: str = "sheltered"
    ) -> RawAnimalData:
        """`#row=N` から対応する動物ブロックを取り出し RawAnimalData を構築"""
        blocks = self._load_blocks()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(blocks):
            raise ParsingError(
                f"row index {idx} out of range (total {len(blocks)})",
                url=virtual_url,
            )
        block = blocks[idx]
        # 動物種別はサイト名から推定 (大分市は犬専用サイト)
        species = self._infer_species_from_site_name(self.site_config.name) or "犬"

        try:
            return RawAnimalData(
                species=species,
                sex=block.get("sex", ""),
                age=block.get("age", ""),
                color=block.get("color", ""),
                size=block.get("size", ""),
                shelter_date=block.get("shelter_date", ""),
                location=block.get("location", ""),
                # 個別動物の電話番号は無く、ページ末尾に施設代表のみ。
                # location に施設名は載らないため phone は空のままにする。
                phone="",
                image_urls=[],
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    def normalize(self, raw_data: RawAnimalData) -> AnimalData:
        """基底の `_default_normalize` (DataNormalizer ベース) に委譲"""
        return self._default_normalize(raw_data)

    # ─────────────────── ブロック抽出 ───────────────────

    def _load_blocks(self) -> list[dict[str, str]]:
        """list → detail を取得し「探しています」配下の動物ブロックをパース。

        結果はインスタンスにキャッシュされ、fetch_animal_list と
        extract_animal_details の連続呼び出しで HTTP を 2 回 (list + detail)
        に抑える。detail link が無ければ空リストを返す。
        """
        if self._blocks_cache is not None:
            return self._blocks_cache
        if self._detail_html_cache is None:
            # 1) list_url から detail 記事 link を取り出す
            list_html = self._http_get(self.site_config.list_url)
            list_soup = BeautifulSoup(list_html, "html.parser")
            detail_url: str | None = None
            for anchor in list_soup.select("#tmp_contents a[href*='/kurashi/pet/']"):
                href = anchor.get("href")
                if not isinstance(href, str) or not _ARTICLE_HREF_RE.search(href):
                    continue
                detail_url = urljoin(self.site_config.list_url, href)
                break
            if detail_url is None:
                self._blocks_cache = []
                return self._blocks_cache
            # 2) detail HTML を取得
            self._detail_url_cache = detail_url
            self._detail_html_cache = self._http_get(detail_url)

        soup = BeautifulSoup(self._detail_html_cache, "html.parser")
        body = soup.select_one("#tmp_contents") or soup
        text = body.get_text("\n", strip=True)
        # 「お家がみつかりました」以降は除外 (return 済み動物)
        if _END_OF_ACTIVE_SECTION in text:
            text = text.split(_END_OF_ACTIVE_SECTION, 1)[0]

        # 見出しでテキスト分割。re.split with capturing groups は
        # [pre, y, m, d, body, y, m, d, body, ...] を返す。
        parts = _BLOCK_HEADER_RE.split(text)
        blocks: list[dict[str, str]] = []
        for i in range(1, len(parts), 4):
            year = parts[i]
            month = parts[i + 1]
            day = parts[i + 2]
            body_text = parts[i + 3] if i + 3 < len(parts) else ""
            # ブロック本文の終端マーカーで切り詰める
            for marker in _BLOCK_END_MARKERS:
                if marker in body_text:
                    body_text = body_text.split(marker, 1)[0]
                    break
            block = self._extract_block_fields(body_text)
            # 令和N年 → AD (令和元年 = 2019 = 2018 + 1)
            year_ad = 2018 + int(year)
            block["shelter_date"] = f"{year_ad:04d}-{int(month):02d}-{int(day):02d}"
            blocks.append(block)

        self._blocks_cache = blocks
        return blocks

    @staticmethod
    def _extract_block_fields(body_text: str) -> dict[str, str]:
        """ブロック本文 (1動物分のテキスト) から各フィールドを抽出"""
        fields: dict[str, str] = {}
        for fld, pat in _FIELD_PATTERNS.items():
            m = pat.search(body_text)
            if m:
                fields[fld] = m.group(1).strip()
        return fields

    @staticmethod
    def _parse_row_index(url: str) -> int:
        """`...#row=N` から N を取り出す。形式不正は 0 を返す。"""
        if "#row=" not in url:
            return 0
        try:
            return int(url.rsplit("#row=", 1)[-1])
        except ValueError:
            return 0

    # ─────────────────── 種別推定 ───────────────────

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名 ("大分市（保護犬）" 等) から動物種別を推定"""
        has_dog = bool(re.search(r"犬", name))
        has_cat = bool(re.search(r"猫", name))
        if has_dog and has_cat:
            return "その他"
        if has_dog:
            return "犬"
        if has_cat:
            return "猫"
        return ""


# ─────────────────── サイト登録 ───────────────────
for _site_name in ("大分市（保護犬）",):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, CityOitaAdapter)
