"""共通テスト設定

INTERNAL_API_TOKEN を全テスト一括で設定する。PATCH /animals/{id}/status
等の内部認証エンドポイントを叩くテストでは、X-Internal-Token ヘッダーに
この値を付与すれば 401 を回避できる。

また、BROKEN_SITES_PATH / FIELD_QUALITY_DRIFT_PATH を tmp に向け、テスト中に
本物の data/*.yaml が書き換えられるのを防ぐ。
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

# data/field_quality_drift.yaml の書き換えを抑止する（テスト分離）。
# 自己修復ループ Phase 1 の FieldQualityTracker が `__main__.main()` 経由で
# 使われる際の保護。明示的に state_path を渡すテストはこの env を参照しない。
_FIELD_QUALITY_SANDBOX = Path(tempfile.gettempdir()) / "oneco-test-field-quality.yaml"
os.environ.setdefault("FIELD_QUALITY_DRIFT_PATH", str(_FIELD_QUALITY_SANDBOX))

INTERNAL_API_HEADERS = {"X-Internal-Token": "test-internal-token"}
