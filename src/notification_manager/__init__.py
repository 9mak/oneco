"""
notification-manager パッケージ

LINE Messaging API連携による条件付きパーソナライズ通知システム。

⚠️ MVP リリース時点で本番未配線（未公開機能）⚠️
- FastAPI app に create_notification_router() が登録されていない
- CollectorService に NotificationManagerClient が注入されていない
  (src/data_collector/__main__.py の collector エントリポイントが
   create_notification_manager_client_from_env() を呼んでいない)

そのため LINE 通知は本番でゼロ発火する状態。本パッケージは将来公開予定の
ライブラリ・テストコードとして同梱されており、本番有効化は別 PR で配線が必要。
Codex リリースレビュー C-2 で指摘。
"""

__version__ = "0.1.0"
