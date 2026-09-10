"""generic_adapter / generic_transforms のモジュール契約テスト (T405 reviewer F-02)

- 名前衝突時は bespoke adapter が優先され WARNING を出す (例外にしない)
- 未知の mode / 未知の postprocess 名は ValueError
- register_specs は 1 spec の構築失敗で他 spec の登録を巻き込まない
"""

from __future__ import annotations

import logging

import pytest

from data_collector.adapters.rule_based.generic_adapter import (
    build_adapter_class,
    register_spec,
    register_specs,
)
from data_collector.adapters.rule_based.generic_transforms import apply_postprocess
from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.site_spec import SiteSpec
from data_collector.adapters.rule_based.wordpress_list import (
    FieldSpec,
    WordPressListAdapter,
)


class _BespokeAdapter(WordPressListAdapter):
    LIST_LINK_SELECTOR = "a"
    FIELD_SELECTORS = {"species": FieldSpec(label="種別")}


@pytest.fixture(autouse=True)
def _clean_registry():
    SiteAdapterRegistry._registry.clear()
    yield
    SiteAdapterRegistry._registry.clear()


def _spec(name: str, mode: str = "list_detail") -> SiteSpec:
    return SiteSpec(
        names=(name,),
        mode=mode,  # type: ignore[arg-type]
        list_link_selector="a.item",
        field_selectors={"species": FieldSpec(label="種別")},
    )


class TestRegisterSpec:
    def test_registers_generic_class(self):
        register_spec(_spec("汎用サイト"))
        cls = SiteAdapterRegistry.get("汎用サイト")
        assert cls is not None
        assert issubclass(cls, WordPressListAdapter)
        assert cls.__name__.startswith("Generic")

    def test_bespoke_wins_on_collision_with_warning(self, caplog):
        SiteAdapterRegistry.register("衝突サイト", _BespokeAdapter)
        with caplog.at_level(logging.WARNING):
            register_spec(_spec("衝突サイト"))
        assert SiteAdapterRegistry.get("衝突サイト") is _BespokeAdapter
        assert any(
            rec.levelno == logging.WARNING and "衝突サイト" in rec.getMessage()
            for rec in caplog.records
        )

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError, match="mode"):
            build_adapter_class(_spec("不明モード", mode="bogus"))


class TestRegisterSpecs:
    def test_one_bad_spec_does_not_block_others(self, caplog):
        with caplog.at_level(logging.ERROR):
            register_specs([_spec("壊れたspec", mode="bogus"), _spec("正常spec")])
        assert SiteAdapterRegistry.get("壊れたspec") is None
        assert SiteAdapterRegistry.get("正常spec") is not None
        assert any("壊れたspec" in rec.getMessage() for rec in caplog.records)


class TestApplyPostprocess:
    def test_unknown_transform_raises(self):
        with pytest.raises(ValueError, match="postprocess"):
            apply_postprocess(["no_such_transform"], {}, adapter=None)  # type: ignore[arg-type]
