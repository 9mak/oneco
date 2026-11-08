"""W006 T073: 独自ドメイン oneco.pet。公開 URL（base_url）は Worker が実際に配信するホストで、旧 URL（workers.dev）は止めない。

- base_url のホストは wrangler.jsonc の routes に custom_domain として書く（ダッシュボードだけで付けると、毎晩の deploy 後に残るかを設定から読めない）。
- 自治体への写真許諾の依頼メール（T630）に workers.dev の URL を書いているので、workers_dev は true のまま残す。
  routes があると wrangler の既定値は false になり、次の deploy で旧 URL が黙って止まる。
- deadman（.github/workflows/v2-deadman.yml）は base_url の data.json を見る。
- build.py の既定値（config.json が無いとき）も同じ URL にそろえる。
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

V2 = Path(__file__).resolve().parent.parent
REPO = V2.parent


def _jsonc(path: Path) -> dict[str, Any]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("//")]
    return json.loads("\n".join(lines))


def _base_url() -> str:
    return str(json.loads((V2 / "site" / "config.json").read_text(encoding="utf-8"))["base_url"])


def test_base_url_is_oneco_pet() -> None:
    assert _base_url() == "https://oneco.pet"


def test_base_url_host_is_custom_domain_of_the_worker() -> None:
    routes = _jsonc(V2 / "ops" / "wrangler.jsonc").get("routes", [])
    custom = {r.get("pattern") for r in routes if isinstance(r, dict) and r.get("custom_domain") is True}
    assert urlsplit(_base_url()).hostname in custom


def test_old_workers_dev_url_stays_on() -> None:
    assert _jsonc(V2 / "ops" / "wrangler.jsonc").get("workers_dev") is True


def test_deadman_watches_base_url() -> None:
    wf = (REPO / ".github" / "workflows" / "v2-deadman.yml").read_text(encoding="utf-8")
    m = re.search(r"^\s*SITE:\s*(\S+)\s*$", wf, re.M)
    assert m is not None
    assert m.group(1).rstrip("/") == _base_url().rstrip("/")


def test_build_default_base_url_matches_config() -> None:
    spec = importlib.util.spec_from_file_location("oneco_site_build_domain", V2 / "site" / "build.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.DEFAULT_CFG["base_url"] == _base_url()
