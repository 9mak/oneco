"""共通テスト設定

INTERNAL_API_TOKEN を全テスト一括で設定する。PATCH /animals/{id}/status
等の内部認証エンドポイントを叩くテストでは、X-Internal-Token ヘッダーに
この値を付与すれば 401 を回避できる。

また、BROKEN_SITES_PATH を tmp に向け、テスト中に本物の
`data/broken_sites.yaml` が書き換えられるのを防ぐ。
"""

import os
import tempfile
from pathlib import Path

# テスト中は固定値で内部 API トークンを設定
os.environ.setdefault("INTERNAL_API_TOKEN", "test-internal-token")

# data/broken_sites.yaml の書き換えを抑止する（テスト分離）。
# `BrokenSitesTracker(state_path=tmp_path / "broken_sites.yaml")` のように
# 明示的に渡しているテストはこの env を参照しないため影響なし。
# `__main__.main()` 経由でデフォルトパスが使われるケースをガードする。
_BROKEN_SITES_SANDBOX = Path(tempfile.gettempdir()) / "oneco-test-broken-sites.yaml"
os.environ.setdefault("BROKEN_SITES_PATH", str(_BROKEN_SITES_SANDBOX))

INTERNAL_API_HEADERS = {"X-Internal-Token": "test-internal-token"}
