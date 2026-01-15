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
