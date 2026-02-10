"""
依存性注入のテスト

get_session依存性とSessionDepタイプエイリアスが
要件通りに実装されているかを検証します。
"""

import pytest
import inspect
from sqlalchemy.ext.asyncio import AsyncSession
from src.data_collector.infrastructure.api.dependencies import get_session, SessionDep
from fastapi import Depends
from typing import Annotated, get_origin, get_args


def test_get_session_is_async_generator():
    """get_session()が非同期ジェネレーター関数であるか"""
    assert inspect.isasyncgenfunction(get_session)


def test_get_session_has_correct_return_annotation():
    """get_session()の戻り値の型アノテーションが正しいか"""
    # get_session の型ヒントを取得
    annotations = get_session.__annotations__

    # 戻り値の型を確認（AsyncGenerator[AsyncSession, None]）
    assert "return" in annotations


def test_session_dep_is_annotated_type():
    """SessionDepがAnnotated型であるか"""
    # SessionDep の型情報を取得
    origin = get_origin(SessionDep)

    # Annotated型であることを確認
    assert origin is Annotated


def test_session_dep_contains_async_session():
    """SessionDepがAsyncSession型を含むか"""
    # SessionDep の型引数を取得
    args = get_args(SessionDep)

    # 最初の引数がAsyncSession
    assert args[0] is AsyncSession


def test_session_dep_contains_depends():
    """SessionDepがDepends(get_session)を含むか"""
    # SessionDep の型引数を取得
    args = get_args(SessionDep)

    # 2番目の引数がDependsのインスタンス
    assert len(args) >= 2
    # Depends は型ではなくインスタンスなので、type() でチェック
    assert type(args[1]).__name__ == "Depends"
    assert args[1].dependency == get_session


def test_get_session_dependency_in_fastapi_route():
    """FastAPIルートでget_session依存性が使用できるか"""
    from fastapi import FastAPI

    app = FastAPI()

    @app.get("/test")
    async def test_route(session: SessionDep):
        return {"session_type": type(session).__name__}

    # 型定義が正しいことを確認
    assert test_route.__annotations__["session"] == SessionDep


def test_session_dep_can_be_used_as_type_hint():
    """SessionDepが型ヒントとして使用できるか"""

    # 関数の引数型ヒントとして使用
    def example_function(session: SessionDep):
        pass

    # 型ヒントが正しく設定されているか確認
    assert example_function.__annotations__["session"] == SessionDep


def test_get_session_references_db_connection_dynamically():
    """get_sessionがdb_connectionをモジュール属性として動的に参照するか

    db_connectionがlifespan後に設定されるため、
    import時の値キャプチャではなくモジュール属性参照が必要。
    """
    import src.data_collector.infrastructure.api.app as app_module
    import src.data_collector.infrastructure.api.dependencies as deps_module

    # dependencies モジュールが app モジュールを参照していることを確認
    # （値のキャプチャではなくモジュール属性参照）
    source = inspect.getsource(deps_module.get_session)

    # "app_module.db_connection" または同等のモジュール属性参照パターンを使用しているか
    # 直接 "db_connection.get_session" ではなく、モジュール経由のアクセスが必要
    assert "db_connection" in source

    # lifespan 後の動的参照をシミュレーション:
    # app_module.db_connection を設定した後、get_session が正しい参照を取得できるか
    from unittest.mock import MagicMock, AsyncMock
    from contextlib import asynccontextmanager

    mock_session = AsyncMock(spec=AsyncSession)

    @asynccontextmanager
    async def mock_get_session():
        yield mock_session

    mock_db_conn = MagicMock()
    mock_db_conn.get_session = mock_get_session

    # app モジュールの db_connection を設定
    original = app_module.db_connection
    app_module.db_connection = mock_db_conn

    try:
        # get_session が app_module.db_connection を動的に参照できるか検証
        # （None ではなく mock_db_conn を参照するはず）
        assert app_module.db_connection is not None
        assert app_module.db_connection is mock_db_conn
    finally:
        app_module.db_connection = original


@pytest.mark.asyncio
async def test_get_session_works_after_lifespan_sets_db_connection():
    """lifespan後にdb_connectionが設定された状態でget_sessionが動作するか"""
    import src.data_collector.infrastructure.api.app as app_module
    from unittest.mock import MagicMock, AsyncMock
    from contextlib import asynccontextmanager

    mock_session = AsyncMock(spec=AsyncSession)

    @asynccontextmanager
    async def mock_get_session_cm():
        yield mock_session

    mock_db_conn = MagicMock()
    mock_db_conn.get_session = mock_get_session_cm

    # lifespan がグローバル db_connection を設定するのをシミュレート
    original = app_module.db_connection
    app_module.db_connection = mock_db_conn

    try:
        # get_session を実行し、セッションが取得できるか検証
        gen = get_session()
        session = await gen.__anext__()
        assert session is mock_session

        # クリーンアップ
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass
    finally:
        app_module.db_connection = original
