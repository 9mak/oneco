"""
ロギング設定

アプリケーション全体で使用するロギング設定を提供します。
構造化ロギング、タイムスタンプ、ログレベル、モジュール名を含みます。
"""

import logging
import sys


def setup_logging(level: str = "INFO", log_format: str | None = None) -> None:
    """
    アプリケーションのロギングを設定

    Args:
        level: ログレベル（DEBUG, INFO, WARNING, ERROR, CRITICAL）
        log_format: ログフォーマット文字列（Noneの場合はデフォルトフォーマット）
    """
    if log_format is None:
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # ログレベルを設定
    log_level = getattr(logging, level.upper(), logging.INFO)

    # ルートロガーを設定
    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,  # 既存の設定を上書き
    )

    # data_collectorモジュール用のロガーを設定
    logger = logging.getLogger("data_collector")
    logger.setLevel(log_level)


def get_logger(name: str) -> logging.Logger:
    """
    指定された名前のロガーを取得

    Args:
        name: ロガー名（通常は __name__ を使用）

    Returns:
        logging.Logger: 設定済みのロガー
    """
    return logging.getLogger(name)
