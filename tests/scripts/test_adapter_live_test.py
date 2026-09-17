"""adapter_live_test.py のテスト

実 HTTP を伴う test_site は対象外にし、adapter に渡す SiteConfig の組み立てだけを固定する。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import adapter_live_test as alt  # noqa: E402


class TestBuildSiteConfig:
    def test_every_site_matches_production_loader(self):
        """T416: live test が adapter に渡す SiteConfig は本番の収集と同じ値でなければならない

        項目を手で写していたため phone・default_species・fields などが落ち、本番では
        取れている電話や species が live test では欠けて見えていた。
        """
        from data_collector.llm.config import SiteConfigLoader

        production = {
            site.name: site.model_dump()
            for site in SiteConfigLoader.load(ROOT / "src/data_collector/config/sites.yaml").sites
        }

        mismatched = [
            name
            for name, raw in alt.load_sites_yaml().items()
            if alt.build_site_config(raw).model_dump() != production[name]
        ]

        assert mismatched == []
