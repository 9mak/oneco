"""高知県動物愛護センター rule-based adapter (KochiAdapter wrapper)

既存 `KochiAdapter` (src/data_collector/adapters/kochi_adapter.py、798 行の
hand-written rule-based 実装) を `RuleBasedAdapter` インターフェースに合わせて
ラップし、`SiteAdapterRegistry` に登録する。

既存 `__main__.py` には Kochi 専用の独立実行パス (KochiAdapter() 直接 instantiate)
があり、本 wrapper はそれと並列に rule-based 経路でも Kochi を扱えるようにする。
sites.yaml の "高知県動物愛護センター" エントリが extraction: "rule-based" 指定
(またはデフォルト) の時、run_rule_based_sites からも収集される。
"""

from __future__ import annotations

from ....domain.models import AnimalData, RawAnimalData
from ...kochi_adapter import KochiAdapter
from ..base import RuleBasedAdapter
from ..registry import SiteAdapterRegistry


class KochiApcAdapter(RuleBasedAdapter):
    """KochiAdapter を SiteConfig 経由で instantiate するラッパー"""

    def __init__(self, site_config) -> None:
        super().__init__(site_config)
        self._kochi = KochiAdapter()

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        return self._kochi.fetch_animal_list()

    def extract_animal_details(self, detail_url: str, category: str = "adoption") -> RawAnimalData:
        return self._kochi.extract_animal_details(detail_url, category)

    def normalize(self, raw_data: RawAnimalData) -> AnimalData:
        return self._kochi.normalize(raw_data)


SiteAdapterRegistry.register("高知県動物愛護センター", KochiApcAdapter)
