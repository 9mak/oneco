"""共通テスト設定

INTERNAL_API_TOKEN を全テスト一括で設定する。PATCH /animals/{id}/status
等の内部認証エンドポイントを叩くテストでは、X-Internal-Token ヘッダーに
この値を付与すれば 401 を回避できる。
"""

import os

# テスト中は固定値で内部 API トークンを設定
os.environ.setdefault("INTERNAL_API_TOKEN", "test-internal-token")

INTERNAL_API_HEADERS = {"X-Internal-Token": "test-internal-token"}
