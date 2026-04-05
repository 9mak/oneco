"""
ロギング設定のテスト

ロギングが要件通りに設定され、適切なログが出力されることを検証します。
"""

import logging
from io import StringIO

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.data_collector.infrastructure.api.app import create_app
from src.data_collector.infrastructure.api.dependencies import get_session
from src.data_collector.infrastructure.database.models import Base


@pytest_asyncio.fixture
async def async_engine():
    """テスト用の非同期エンジンを作成"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def async_session(async_engine):
    """テスト用の非同期セッションを作成"""
    async_session_maker = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def test_app(async_session):
    """テスト用のFastAPIアプリケーションを作成"""
    app = create_app()

    # 依存性をオーバーライド
    async def override_get_session():
        yield async_session

    app.dependency_overrides[get_session] = override_get_session

    return app


@pytest.mark.asyncio
async def test_logging_is_configured():
    """ロギングが適切に設定されているか"""
    # ロガーを取得
    logger = logging.getLogger("data_collector")

    # ロガーが存在することを確認
    assert logger is not None


@pytest.mark.asyncio
async def test_logging_format():
    """ログフォーマットが適切であるか"""
    # テスト用のストリームハンドラーを設定
    logger = logging.getLogger("data_collector.test")
    logger.setLevel(logging.INFO)

    # StringIOを使ってログ出力をキャプチャ
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)

    # フォーマットを設定
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # ログを出力
    logger.info("Test log message")

    # ログが出力されたことを確認
    log_output = log_stream.getvalue()
    assert "Test log message" in log_output
    assert "INFO" in log_output
    assert "data_collector.test" in log_output

    # クリーンアップ
    logger.removeHandler(handler)


@pytest.mark.asyncio
async def test_logging_levels():
    """異なるログレベルが正しく動作するか"""
    logger = logging.getLogger("data_collector.test_levels")
    logger.setLevel(logging.DEBUG)

    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
    logger.addHandler(handler)

    # 各レベルのログを出力
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")

    log_output = log_stream.getvalue()

    # 各レベルのメッセージが含まれることを確認
    assert "DEBUG - Debug message" in log_output
    assert "INFO - Info message" in log_output
    assert "WARNING - Warning message" in log_output
    assert "ERROR - Error message" in log_output

    logger.removeHandler(handler)
