"""rule-based site-specific adapter package.

このパッケージのインポート時に、`pkgutil.iter_modules` で配下の各 site
adapter モジュールを動的に import し、`SiteAdapterRegistry` への module-level
`register()` 呼び出しを発火させる。

`__main__.py` が `from .adapters.rule_based import sites` する (または本パッケージ
を import する) ことで、bespoke Python adapter 全てが SiteAdapterRegistry に
登録される。それに加えて `config/site_specs/*.yaml` の宣言的な spec も
`GenericAdapter` (T405) 経由でここから登録する。bespoke モジュールを先に
import してから spec を登録するため、同名サイトは bespoke が優先される
(`generic_adapter.register_spec` が既登録なら WARNING を出してスキップする)。
"""

from __future__ import annotations

import importlib
import pkgutil

# Auto-import all sibling modules so each module's
# `SiteAdapterRegistry.register(...)` call fires at import time.
for _finder, _name, _ispkg in pkgutil.iter_modules(__path__):
    if _name.startswith("_"):
        continue
    importlib.import_module(f"{__name__}.{_name}")

# YAML spec 駆動の GenericAdapter を登録する (T405)。bespoke モジュールの
# import が先に完了しているため、名前衝突時は bespoke が優先される。
# 1 spec の読み込み・構築失敗は当該 spec のスキップに留め、他サイトの登録は続ける。
from ..generic_adapter import register_specs as _register_specs  # noqa: E402
from ..site_spec import load_all_specs as _load_all_specs  # noqa: E402

_register_specs(_load_all_specs())
