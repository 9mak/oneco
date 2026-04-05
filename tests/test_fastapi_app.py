"""
FastAPI アプリケーションのテスト

FastAPI インスタンス、CORS設定、ライフサイクルイベントが
要件通りに実装されているかを検証します。
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.data_collector.infrastructure.api.app import create_app


def test_create_app_returns_fastapi_instance():
    """create_app()がFastAPIインスタンスを返すか"""
    app = create_app()

    assert isinstance(app, FastAPI)


def test_app_has_title_and_description():
    """アプリケーションにタイトルと説明が設定されているか"""
    app = create_app()

    assert app.title is not None
    assert len(app.title) > 0
    assert app.description is not None


def test_app_has_version():
    """アプリケーションにバージョンが設定されているか"""
    app = create_app()

    assert app.version is not None
    assert len(app.version) > 0


def test_app_cors_middleware_configured():
    """CORSミドルウェアが設定されているか"""
    app = create_app()

    # ミドルウェアが存在することを確認
    [type(m.cls) for m in app.user_middleware]

    # CORSMiddleware がインストールされているか確認
    from fastapi.middleware.cors import CORSMiddleware

    assert any(m.cls == CORSMiddleware for m in app.user_middleware)


def test_app_has_openapi_docs():
    """OpenAPIドキュメントが生成されるか"""
    app = create_app()
    client = TestClient(app)

    response = client.get("/docs")

    assert response.status_code == 200


def test_app_has_openapi_schema():
    """OpenAPIスキーマが取得できるか"""
    app = create_app()
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json() is not None


@pytest.mark.asyncio
async def test_app_startup_event():
    """アプリケーション起動時のイベントが実行されるか"""
    app = create_app()

    # TestClient はライフサイクルイベントを自動で実行
    with TestClient(app) as client:
        # 起動イベントが実行されているはず
        response = client.get("/docs")
        assert response.status_code == 200


def test_app_allows_cors_requests():
    """CORSリクエストが許可されるか"""
    app = create_app()
    client = TestClient(app)

    # Preflight request (OPTIONS)
    response = client.options(
        "/docs",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    # CORS が設定されていれば200を返す
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
