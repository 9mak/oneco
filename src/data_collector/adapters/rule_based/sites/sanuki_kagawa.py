"""さぬき動物愛護センター (pref.kagawa.lg.jp) rule-based adapter

対象 URL: https://www.pref.kagawa.lg.jp/s-doubutuaigo/sanukidouaicenter/jyouto/s04u6e190311095146.html

特徴:
- 香川県さぬき動物愛護センターの「譲渡犬猫」情報ページ。
  本文中に PDF へのリンク (`/documents/6103/0318dog.pdf`,
  `/documents/6103/0321cat.pdf` 等) が並び、各 PDF が一覧表形式で
  複数頭の譲渡候補動物を掲載する (sites.yaml の `pdf_multi_animal: true`)。
- 一覧ページ自体が JS で動的に DOM を組み立てる構成のため、`requires_js`
  が設定され Playwright で取得する必要がある。
  PlaywrightFetchMixin を WordPressListAdapter と多重継承する。
- 一覧ページから抽出するのは個別 detail HTML ページではなく **PDF URL**。
  rule-based adapter は PDF を HTML として fetch することができないため、
  `extract_animal_details` はネットワークアクセスせず、PDF URL と
  ファイル名 (`dog`/`cat`) から推定した species・category・固定の
  施設情報 (location/phone) のみを持つ最小 RawAnimalData を構築する。
  PDF 内の個別動物情報の抽出はパイプライン後段の PDF/LLM 処理が担う。
- 在庫 0 件 (PDF が掲示されない月) は ParsingError ではなく空リストを返す。

カバーサイト (1):
- さぬき動物愛護センター（譲渡犬猫）
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..playwright import PlaywrightFetchMixin
from ..registry import SiteAdapterRegistry
from ..wordpress_list import FieldSpec, WordPressListAdapter


# 施設情報 (sites.yaml に記載が無い固定値。香川県公式サイトより)
_CENTER_NAME = "さぬき動物愛護センター"
_CENTER_PHONE = "087-815-2255"


class SanukiKagawaAdapter(PlaywrightFetchMixin, WordPressListAdapter):
    """さぬき動物愛護センター（譲渡犬猫） rule-based adapter

    一覧ページから PDF リンクを抽出し、各 PDF URL を 1 動物単位の
    detail URL として返す。PDF 自体の中身解析は本 adapter のスコープ外
    (パイプライン側で `pdf_multi_animal` フラグに従い処理される)。
    """

    # ─────────────────── Playwright 設定 ───────────────────
    # PDF リンク自体が描画されたら抽出可能。
    # 実ページは jQuery で本文ブロックを差し込むため、
    # 該当パスのアンカーが現れるまで待機する。
    WAIT_SELECTOR: ClassVar[str | None] = "a[href*='/documents/6103/']"

    # ─────────────────── WordPressList 設定 ───────────────────
    # PDF へのリンクのみを拾う (sites.yaml の pdf_link_pattern と同一)。
    LIST_LINK_SELECTOR: ClassVar[str] = (
        "a[href*='/documents/6103/'][href$='.pdf']"
    )

    # detail HTML を持たないため FieldSpec は使用しないが、
    # 基底クラスのインタフェース上は宣言しておく。
    FIELD_SELECTORS: ClassVar[dict[str, FieldSpec]] = {}

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """一覧ページから PDF URL を抽出する (0 件は正常系として許容)

        基底 `WordPressListAdapter.fetch_animal_list` は detail link が
        1 件も無い場合 ParsingError を投げるが、本サイトは PDF が
        差し替えられる過渡期や月単位での未掲示状態が日常的に発生する
        ため、0 件は空リストとして扱う。
        """
        html = self._http_get(self.site_config.list_url)
        soup = BeautifulSoup(html, "html.parser")

        links = soup.select(self.LIST_LINK_SELECTOR)
        if not links:
            return []

        urls: list[tuple[str, str]] = []
        seen: set[str] = set()
        category = self.site_config.category
        for link in links:
            href = link.get("href")
            if not href or not isinstance(href, str):
                continue
            absolute = self._absolute_url(href)
            if absolute in seen:
                continue
            seen.add(absolute)
            urls.append((absolute, category))
        return urls

    def extract_animal_details(
        self, detail_url: str, category: str = "adoption"
    ) -> RawAnimalData:
        """PDF URL から最小 RawAnimalData を構築する

        PDF はバイナリで HTML として fetch できないため、ネットワーク
        アクセスは行わず URL から推定可能な情報 (species, 施設情報) のみ
        を持つ RawAnimalData を返す。PDF 内部の個別動物情報抽出は
        pipeline 後段 (PDF テキスト化 + LLM 抽出) が担当する。

        Args:
            detail_url: PDF の絶対 URL (`/documents/6103/XXXXdog.pdf` 等)
            category: site_config.category 由来 ("adoption")

        Returns:
            species をファイル名から推定した最小 RawAnimalData。
            image_urls には PDF URL 自体を入れて pipeline 後段で参照可能にする。

        Raises:
            ParsingError: detail_url が PDF URL として妥当でない場合
        """
        if not detail_url.lower().endswith(".pdf"):
            raise ParsingError(
                f"PDF URL ではありません: {detail_url}",
                url=detail_url,
            )

        species = self._infer_species_from_pdf_url(detail_url)

        try:
            return RawAnimalData(
                species=species,
                sex="",
                age="",
                color="",
                size="",
                shelter_date="",
                location=_CENTER_NAME,
                phone=self._normalize_phone(_CENTER_PHONE),
                image_urls=[detail_url],
                source_url=detail_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(
                f"RawAnimalData バリデーション失敗: {e}", url=detail_url
            ) from e

    # ─────────────────── 種別推定 ───────────────────

    @staticmethod
    def _infer_species_from_pdf_url(url: str) -> str:
        """PDF URL のファイル名から species を推定する

        さぬきセンターの PDF 命名規則:
        - `0318dog.pdf` / `dog0321.pdf` 等 "dog" を含む → "犬"
        - `0321cat.pdf` / `cat0318.pdf` 等 "cat" を含む → "猫"
        - 上記いずれにも該当しない → "" (後段で補完)
        """
        if not url:
            return ""
        name = url.rsplit("/", 1)[-1].lower()
        has_dog = bool(re.search(r"dog", name))
        has_cat = bool(re.search(r"cat", name))
        if has_dog and not has_cat:
            return "犬"
        if has_cat and not has_dog:
            return "猫"
        return ""


# ─────────────────── サイト登録 ───────────────────
_SITE_NAME = "さぬき動物愛護センター（譲渡犬猫）"
if SiteAdapterRegistry.get(_SITE_NAME) is None:
    SiteAdapterRegistry.register(_SITE_NAME, SanukiKagawaAdapter)
