"""ワンニャピアあきた (wannyapia.akita.jp) rule-based adapter

注意: このサイトは JavaScript で動物データを動的描画しているため、
`requests` ベースの fetch では空 HTML が返る。本 adapter は静的 HTML
から判別可能なリンク (/pages/protective-dogs|cats への補助リンク等)
だけを抽出し、本格運用時は sites.yaml で `requires_js: true` への
切替を検討すること（その際は `PlaywrightFetchMixin` と組み合わせ可能）。

カバーサイト (2):
- ワンニャピアあきた（譲渡犬）
- ワンニャピアあきた（譲渡猫）
"""

from __future__ import annotations

from typing import ClassVar

from bs4 import BeautifulSoup

from ....domain.models import AnimalData, RawAnimalData
from ...municipality_adapter import ParsingError
from ..base import RuleBasedAdapter
from ..registry import SiteAdapterRegistry


class WannyapiaAkitaAdapter(RuleBasedAdapter):
    """ワンニャピアあきた adapter

    静的 HTML では動物データが取得できないため、現状は常に空リストを返す。
    `requires_js: true` 化 + `PlaywrightFetchMixin` 適用が必要。
    """

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        try:
            html = self._http_get(self.site_config.list_url)
        except Exception:
            return []
        # JS必須サイト: 静的 HTML に動物データなし → 空リスト
        # 将来 PlaywrightFetchMixin で置き換える際は selector を追加実装する
        return []

    def extract_animal_details(
        self, detail_url: str, category: str = "adoption"
    ) -> RawAnimalData:
        raise ParsingError(
            "wannyapia.akita.jp は JS 必須のため詳細抽出未対応 "
            "(requires_js: true への切替が必要)",
            url=detail_url,
        )

    def normalize(self, raw_data: RawAnimalData) -> AnimalData:
        return self._default_normalize(raw_data)


SiteAdapterRegistry.register("ワンニャピアあきた（譲渡犬）", WannyapiaAkitaAdapter)
SiteAdapterRegistry.register("ワンニャピアあきた（譲渡猫）", WannyapiaAkitaAdapter)
