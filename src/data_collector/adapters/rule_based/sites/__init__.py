"""rule-based site-specific adapter package.

このパッケージのインポート時に、`pkgutil.iter_modules` で配下の各 site
adapter モジュールを動的に import し、`SiteAdapterRegistry` への module-level
`register()` 呼び出しを発火させる。

`__main__.py` が `from .adapters.rule_based import sites` する (または本パッケージ
を import する) ことで、91 テンプレ全 adapter が SiteAdapterRegistry に登録される。
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
