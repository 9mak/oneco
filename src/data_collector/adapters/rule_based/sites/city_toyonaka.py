"""豊中市 (大阪府) rule-based adapter

対象ドメイン: https://www.city.toyonaka.osaka.jp/

特徴:
- 対象 URL は「ペットが迷子になった時の対応方法について」という案内ページで、
  保護動物の一覧そのものは公開されていない。ページに存在するテーブルは
  迷子時の連絡先 (各市町村の管轄一覧) のみで、動物情報を含まない。
  https://www.city.toyonaka.osaka.jp/kurashi/pettp-inuneko/maigo.html
- 将来サイト構成が変わった場合に備えて adapter は登録しておくが、
  現状は常に在庫 0 件 (空リスト) として扱う。
- `single_page_table.SinglePageTableAdapter` の基底実装は行 0 件のとき
  `ParsingError` を投げるため、`fetch_animal_list` をオーバーライドして
  「告知ページ (動物一覧が無いページ)」を判別し、空リストを返す。
- 動物リストが将来追加されたときに備えて `ROW_SELECTOR` は記事本文の
  記事内テーブル行に向けておくが、現状そのセレクタにマッチする
  「動物データ行」は存在しない (フィクスチャでも 0 件)。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


class CityToyonakaAdapter(SinglePageTableAdapter):
    """豊中市 (大阪府) 用 rule-based adapter

    現状は動物一覧を持たない案内ページなので、常に空リストを返す。
    """

    # 記事本文配下のテーブル行に絞る。現状は管轄連絡先テーブル (動物情報なし)
    # しか存在せず、empty state 検出側で除外される。
    ROW_SELECTOR: ClassVar[str] = "table.table_data tr"
    # ヘッダ行は除外
    SKIP_FIRST_ROW: ClassVar[bool] = True
    # 将来動物リストが追加された場合に備えた最小限のマッピング。
    # 現フィクスチャでは _is_announcement_page で 0 件と判定されるため未使用。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    LOCATION_COLUMN: ClassVar[int | None] = None
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # 案内ページであることを示すタイトル/見出しキーワード。
    # 「迷子になった時の対応方法」「捜索方法」「所有者明示」のいずれかが
    # 主見出しに出現するページは、動物一覧を含まない告知ページと判断する。
    _ANNOUNCEMENT_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"(?:迷子になった時の対応方法|捜索方法|所有者明示|"
        r"迷子にしないために)"
    )

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """一覧ページから動物の仮想 URL を返す

        豊中市の対象 URL は「迷子の対応方法」案内ページで動物一覧を
        持たないため、案内ページと判定できた場合は空リストを返す。
        将来動物リスト掲載に切り替わった場合は基底実装どおりに振る舞う。
        """
        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        if self._is_announcement_page(self._html_cache):
            # 動物リストを持たない案内ページ → 在庫 0 件として正常終了
            return []

        # 想定外: 動物一覧テンプレートに変化した場合
        # (基底実装は行 0 件で ParsingError を投げる仕様)
        rows = self._load_rows()
        if not rows:
            # 案内パターンも検出できず行も無い: 構造変化を明示
            raise ParsingError(
                "案内ページパターン未一致かつ行要素も見つかりません",
                selector=self.ROW_SELECTOR,
                url=self.site_config.list_url,
            )
        category = self.site_config.category
        return [
            (f"{self.site_config.list_url}#row={i}", category)
            for i in range(len(rows))
        ]

    def extract_animal_details(
        self, virtual_url: str, category: str = "lost"
    ) -> RawAnimalData:
        """仮想 URL から RawAnimalData を構築する

        現状の豊中市サイトでは `fetch_animal_list` が常に空を返すため、
        本メソッドが呼ばれることは無いが、契約上の実装として残しておく。
        万一呼ばれた場合は基底のテーブル抽出に委譲する。
        """
        return super().extract_animal_details(virtual_url, category=category)

    # ─────────────────── ヘルパー ───────────────────

    @classmethod
    def _is_announcement_page(cls, html: str) -> bool:
        """HTML が「動物一覧を持たない案内ページ」かを判定する

        - <title> または h1 に案内パターンが含まれる
        - もしくは記事本文に「ペットが迷子になった時」の見出しが含まれる
        の何れかで案内ページと判定する。
        """
        if not html:
            return False
        soup = BeautifulSoup(html, "html.parser")
        # title タグ
        title = soup.find("title")
        if title and cls._ANNOUNCEMENT_PATTERN.search(
            title.get_text(strip=True)
        ):
            return True
        # h1 / h2 見出し
        for tag in soup.find_all(["h1", "h2"]):
            text = tag.get_text(strip=True)
            if cls._ANNOUNCEMENT_PATTERN.search(text):
                return True
        return False


# ─────────────────── サイト登録 ───────────────────
# sites.yaml の `豊中市（迷子犬猫）` を本 adapter にマップする。
for _site_name in ("豊中市（迷子犬猫）",):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, CityToyonakaAdapter)
