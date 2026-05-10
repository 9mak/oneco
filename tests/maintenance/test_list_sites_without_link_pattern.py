"""list_sites_without_link_pattern スクリプトのロジック単体テスト"""

import importlib.util
import sys
from pathlib import Path

import pytest

from src.data_collector.llm.config import SiteConfig

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "maintenance" / "list_sites_without_link_pattern.py"


@pytest.fixture(scope="module")
def needs_link_pattern():
    """ファイルパスからスクリプトを動的にロードして関数を取得"""
    spec = importlib.util.spec_from_file_location("list_sites_module", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["list_sites_module"] = module
    spec.loader.exec_module(module)
    return module.needs_link_pattern


def _site(**kwargs) -> SiteConfig:
    """SiteConfig with defaults filled in"""
    defaults = {
        "name": "test",
        "prefecture": "高知県",
        "prefecture_code": "39",
        "list_url": "https://example.com/",
    }
    defaults.update(kwargs)
    return SiteConfig(**defaults)


class TestNeedsLinkPattern:
    def test_no_pattern_no_flags_needs_pattern(self, needs_link_pattern):
        assert needs_link_pattern(_site()) is True

    def test_with_list_link_pattern_does_not_need(self, needs_link_pattern):
        assert needs_link_pattern(_site(list_link_pattern="a.detail")) is False

    def test_with_pdf_link_pattern_does_not_need(self, needs_link_pattern):
        assert needs_link_pattern(_site(pdf_link_pattern="a[href$=.pdf]")) is False

    def test_single_page_does_not_need(self, needs_link_pattern):
        assert needs_link_pattern(_site(single_page=True)) is False

    def test_requires_js_alone_still_needs(self, needs_link_pattern):
        """requires_js だけでは link pattern 不要にならない"""
        assert needs_link_pattern(_site(requires_js=True)) is True
