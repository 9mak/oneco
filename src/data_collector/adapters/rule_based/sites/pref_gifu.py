"""岐阜県迷い犬情報 rule-based adapter

対象ドメイン: https://www.pref.gifu.lg.jp/

特徴:
- `https://www.pref.gifu.lg.jp/page/1638.html` は岐阜県生活衛生課が
  運営する「迷い犬情報」ハブページで、ページ自体には動物個別の情報は
  掲載されず、県内 12 保健所 (岐阜・西濃・揖斐 等) への
  リンク表 (`<table>`) のみが置かれている。各保健所のサブページに飛ぶと
  個別の迷い犬情報が掲載される構造。
- 構造が「ハブ + リンク」のため、本ページから直接抽出できる動物は常に
  0 件。基底 `SinglePageTableAdapter` は行 0 件で `ParsingError` を
  投げる仕様だが、本サイトでは 0 件が正常状態であるため、
  `fetch_animal_list` をオーバーライドして空リストを返す。
- ハブ表自体は `保健所名 / 区域` の見出しを持つ案内テーブル
  (見出し行 + 各行 2 保健所、計 6 行) であり、動物情報行ではない。
  本 adapter はこのテンプレート構造を `_HUB_HEADER_PATTERN` で検出して
  「正常な 0 件ハブページ」と判定する。検出できない場合のみ
  `ParsingError` を伝播させる (将来テンプレートが変わった場合の
  silent failure 防止)。
- 12 保健所の個別サブページ (例: `/page/6304.html` 岐阜保健所) は
  別 site / 別 adapter の責務として扱う想定。
"""

from __future__ import annotations

import re
from typing import ClassVar

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter

# ハブテーブルの見出しに必ず含まれる文字列。
# 「保健所名」+「区域」で 2 列ペア × 2 セットの計 4 列ヘッダ構造。
_HUB_HEADER_PATTERN = re.compile(r"保健所名.*?区域", re.DOTALL)
# ページタイトル / 案内文に登場する迷い犬情報ハブを示す代表的フレーズ。
# 表記揺れ吸収のため複数候補を OR で許容する。
_HUB_BODY_PATTERN = re.compile(r"(?:迷い犬情報|保健所では[^。]*?保護|保健所をクリック)")


class PrefGifuAdapter(SinglePageTableAdapter):
    """岐阜県迷い犬情報ハブページ用 rule-based adapter

    `pref.gifu.lg.jp/page/1638.html` は 12 保健所への案内ハブで、
    ページ自体には動物情報が無い。常に 0 件を返す empty-state 専用 adapter。
    """

    # ハブテーブルの行も拾えるよう一応 selector を定義しておくが、
    # `fetch_animal_list` をオーバーライドするため実際には使われない。
    ROW_SELECTOR: ClassVar[str] = "table tr"
    SKIP_FIRST_ROW: ClassVar[bool] = True
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    LOCATION_COLUMN: ClassVar[int | None] = None
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """ハブページから動物の仮想 URL を返す

        本ページは常に 0 件のハブ構造である。テンプレートが
        想定通り (保健所名 / 区域 の案内表 or 案内文) であることを
        確認した上で空リストを返す。テンプレートが大幅に変わった場合は
        ParsingError を投げて手動検知できるようにする。
        """
        # `_load_rows` は HTML を取得 + キャッシュする副作用を持つため呼ぶ
        self._load_rows()
        html = self._html_cache or ""

        if _HUB_HEADER_PATTERN.search(html) or _HUB_BODY_PATTERN.search(html):
            # 想定通りのハブページ → 0 件で正常
            return []

        # ハブの目印が一切ない = テンプレート変更や別ページが返ってきた可能性
        raise ParsingError(
            "岐阜県迷い犬情報ハブページの目印が見つかりません",
            url=self.site_config.list_url,
        )

    def extract_animal_details(self, virtual_url: str, category: str = "lost") -> RawAnimalData:
        """ハブページからは動物が取れないため呼ばれた時点で異常

        `fetch_animal_list` が常に空リストを返すため、通常の収集
        パイプラインからは呼ばれない。直接呼ばれた場合は ParsingError。
        """
        raise ParsingError(
            "岐阜県迷い犬情報ハブページに動物詳細は存在しません",
            url=virtual_url,
        )


# ─────────────────── サイト登録 ───────────────────
# sites.yaml の `name: 岐阜県（迷い犬情報）` と完全一致させる。
_SITE_NAME = "岐阜県（迷い犬情報）"
if SiteAdapterRegistry.get(_SITE_NAME) is None:
    SiteAdapterRegistry.register(_SITE_NAME, PrefGifuAdapter)
