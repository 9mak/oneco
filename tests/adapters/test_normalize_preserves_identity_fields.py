"""全 rule-based adapter の normalize() が個体識別フィールドを落とさない構造的回帰テスト。

CLAUDE.md / PR #171-180: breed/name/management_number/description のサイレントドロップが
6 回連続で本番に出た。個別 adapter の `extract_animal_details` レベルのドロップは各 adapter の
fixture テスト (CLAUDE.md Rule #1: `normalize(raw)` 戻り値 AnimalData でアサート) で守るが、
本テストは **normalize() レイヤの構造的トリップワイヤ**として機能する:

将来いずれかの adapter が `normalize()` を override して RawAnimalData を再構築する際に
識別フィールドを落とした場合 (CLAUDE.md Rule #3 違反)、**列挙漏れなく全 adapter 横断で**
検出する。新規 adapter を追加すれば自動的に本テストの対象に含まれる。

4 識別フィールドを全て埋めた合成 RawAnimalData を各 adapter の `normalize()` に通し、
戻り値 AnimalData で 4 フィールドが非空で残ることを検証する。
"""

from __future__ import annotations

import pytest

# パッケージ import で sites/__init__.py が pkgutil 経由で全 adapter を registry に登録する
import data_collector.adapters.rule_based.sites  # noqa: F401
from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

_IDENTITY_FIELDS = ("breed", "name", "management_number", "description")

# parametrize はコレクション時に評価される。上の import で registry は既に充填済み。
# adapter クラスはこの時点 (コレクション時) でスナップショットしておく。
# test_registry.py が実行時に `_registry.clear()` するため、実行時の get() に
# 依存すると None が返り得る (コレクションは全テスト実行前に1回走るので安全)。
_REGISTERED = sorted(SiteAdapterRegistry.all_registered())
_ADAPTER_CLASSES = {name: SiteAdapterRegistry.get(name) for name in _REGISTERED}


def _make_config(site_name: str) -> SiteConfig:
    """normalize() のみ呼ぶための最小 SiteConfig (ネットワークは発生しない)。"""
    return SiteConfig(
        name=site_name,
        prefecture="高知県",
        prefecture_code="39",
        list_url="http://example.com/list.html",
        category="adoption",
        single_page=True,
    )


def _make_raw() -> RawAnimalData:
    """4 識別フィールドを全て非空で埋めた合成 raw。"""
    return RawAnimalData(
        species="犬",
        breed="柴犬",
        name="平助",
        management_number="D24018",
        description="人懐っこい性格です",
        sex="オス",
        age="2歳",
        color="茶",
        size="中型",
        shelter_date="2026-05-07",
        location="高知市",
        phone="088-822-0588",
        image_urls=["http://example.com/a.jpg"],
        source_url="http://example.com/a",
        category="adoption",
    )


def test_registry_is_populated() -> None:
    """前提: 全 adapter が登録されている (空だと下のテストが空振りするため明示検証)。"""
    assert len(_REGISTERED) > 100, (
        f"登録 adapter 数が想定より少ない ({len(_REGISTERED)})。sites パッケージの "
        f"自動 import が壊れている可能性がある。"
    )


@pytest.mark.parametrize("site_name", _REGISTERED)
def test_normalize_preserves_identity_fields(site_name: str) -> None:
    # コレクション時にスナップショットしたクラスを使う (実行時の registry clear に非依存)
    adapter_cls = _ADAPTER_CLASSES[site_name]
    assert adapter_cls is not None, f"{site_name} の adapter クラスが取得できない"

    adapter = adapter_cls(_make_config(site_name))
    normalized = adapter.normalize(_make_raw())

    for field in _IDENTITY_FIELDS:
        value = getattr(normalized, field, None)
        assert value, (
            f"{site_name} の normalize() が識別フィールド '{field}' を落とした "
            f"(raw は非空だが AnimalData.{field}={value!r})。normalize() override で "
            f"RawAnimalData を再構築する際は全フィールドを名前付き引数で引き継ぐこと "
            f"(CLAUDE.md Rule #3)。"
        )
