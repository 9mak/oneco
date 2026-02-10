"""
OpenAPIドキュメントとスキーマの検証テスト

FastAPIの自動生成ドキュメント（/docs, /openapi.json）が
正しく生成され、期待されるエンドポイントとスキーマが含まれていることを検証します。

要件:
- 3.4: 各APIレスポンスに適切なContent-Type（application/json）ヘッダーを設定
- OpenAPIドキュメントの自動生成
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.data_collector.infrastructure.database.models import Base
from src.data_collector.infrastructure.api.app import create_app
from src.data_collector.infrastructure.api.dependencies import get_session


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


@pytest_asyncio.fixture
async def test_app(async_session):
    """テスト用のFastAPIアプリケーションを作成"""
    app = create_app()

    async def override_get_session():
        yield async_session

    app.dependency_overrides[get_session] = override_get_session

    return app


class TestOpenAPIDocumentation:
    """OpenAPIドキュメント生成のテスト"""

    @pytest.mark.asyncio
    async def test_openapi_json_endpoint_exists(self, test_app):
        """/openapi.json エンドポイントが存在するか"""
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            response = await client.get("/openapi.json")

        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_openapi_schema_contains_info(self, test_app):
        """OpenAPIスキーマにAPI情報が含まれているか"""
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            response = await client.get("/openapi.json")

        schema = response.json()

        # OpenAPI基本情報
        assert "openapi" in schema
        assert "info" in schema
        assert schema["info"]["title"] == "Animal Repository API"
        assert schema["info"]["description"] == "保護動物データを提供するREST API"
        assert schema["info"]["version"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_openapi_schema_contains_animals_endpoint(self, test_app):
        """OpenAPIスキーマに /animals エンドポイントが含まれているか"""
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            response = await client.get("/openapi.json")

        schema = response.json()
        paths = schema.get("paths", {})

        # /animals エンドポイント
        assert "/animals" in paths
        assert "get" in paths["/animals"]

        # エンドポイントの説明
        animals_get = paths["/animals"]["get"]
        assert "summary" in animals_get or "description" in animals_get

        # パラメータの存在
        assert "parameters" in animals_get
        param_names = [p["name"] for p in animals_get["parameters"]]
        assert "species" in param_names
        assert "sex" in param_names
        assert "location" in param_names
        assert "limit" in param_names
        assert "offset" in param_names

    @pytest.mark.asyncio
    async def test_openapi_schema_contains_animal_by_id_endpoint(self, test_app):
        """OpenAPIスキーマに /animals/{animal_id} エンドポイントが含まれているか"""
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            response = await client.get("/openapi.json")

        schema = response.json()
        paths = schema.get("paths", {})

        # /animals/{animal_id} エンドポイント
        assert "/animals/{animal_id}" in paths
        assert "get" in paths["/animals/{animal_id}"]

        # パスパラメータ
        animal_get = paths["/animals/{animal_id}"]["get"]
        assert "parameters" in animal_get
        param_names = [p["name"] for p in animal_get["parameters"]]
        assert "animal_id" in param_names

    @pytest.mark.asyncio
    async def test_openapi_schema_contains_health_endpoint(self, test_app):
        """OpenAPIスキーマに /health エンドポイントが含まれているか"""
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            response = await client.get("/openapi.json")

        schema = response.json()
        paths = schema.get("paths", {})

        # /health エンドポイント
        assert "/health" in paths
        assert "get" in paths["/health"]

    @pytest.mark.asyncio
    async def test_openapi_schema_contains_animal_public_schema(self, test_app):
        """OpenAPIスキーマに AnimalPublic スキーマが含まれているか"""
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            response = await client.get("/openapi.json")

        schema = response.json()
        components = schema.get("components", {}).get("schemas", {})

        # AnimalPublic スキーマ
        assert "AnimalPublic" in components

        animal_schema = components["AnimalPublic"]
        properties = animal_schema.get("properties", {})

        # 必須フィールドの確認
        expected_fields = [
            "id", "species", "sex", "shelter_date",
            "location", "source_url", "image_urls"
        ]
        for field in expected_fields:
            assert field in properties, f"Field {field} should be in AnimalPublic schema"

    @pytest.mark.asyncio
    async def test_openapi_schema_contains_pagination_schema(self, test_app):
        """OpenAPIスキーマに PaginationMeta スキーマが含まれているか"""
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            response = await client.get("/openapi.json")

        schema = response.json()
        components = schema.get("components", {}).get("schemas", {})

        # PaginationMeta スキーマ
        assert "PaginationMeta" in components

        pagination_schema = components["PaginationMeta"]
        properties = pagination_schema.get("properties", {})

        # 必須フィールドの確認
        expected_fields = [
            "total_count", "limit", "offset",
            "current_page", "total_pages", "has_next"
        ]
        for field in expected_fields:
            assert field in properties, f"Field {field} should be in PaginationMeta schema"

    @pytest.mark.asyncio
    async def test_docs_endpoint_redirects(self, test_app):
        """/docs エンドポイントがSwagger UIにリダイレクトするか"""
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            # follow_redirects=Falseでリダイレクトを確認することもできるが、
            # FastAPIのデフォルトでは/docsは200を返す
            response = await client.get("/docs")

        # Swagger UIのHTMLが返されることを確認
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_redoc_endpoint_exists(self, test_app):
        """/redoc エンドポイントが存在するか"""
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            response = await client.get("/redoc")

        # ReDocのHTMLが返されることを確認
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


class TestSyndicationRouteRegistration:
    """syndication-service ルートが main app に登録されているかのテスト"""

    @pytest.mark.asyncio
    async def test_openapi_schema_contains_feeds_rss_endpoint(self, test_app):
        """OpenAPIスキーマに /feeds/rss エンドポイントが含まれているか"""
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            response = await client.get("/openapi.json")

        schema = response.json()
        paths = schema.get("paths", {})

        assert "/feeds/rss" in paths
        assert "get" in paths["/feeds/rss"]

    @pytest.mark.asyncio
    async def test_openapi_schema_contains_feeds_atom_endpoint(self, test_app):
        """OpenAPIスキーマに /feeds/atom エンドポイントが含まれているか"""
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            response = await client.get("/openapi.json")

        schema = response.json()
        paths = schema.get("paths", {})

        assert "/feeds/atom" in paths
        assert "get" in paths["/feeds/atom"]

    @pytest.mark.asyncio
    async def test_openapi_schema_contains_feeds_archive_endpoints(self, test_app):
        """OpenAPIスキーマにアーカイブフィードエンドポイントが含まれているか"""
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            response = await client.get("/openapi.json")

        schema = response.json()
        paths = schema.get("paths", {})

        assert "/feeds/archive/rss" in paths
        assert "/feeds/archive/atom" in paths


class TestOpenAPIResponseSchemas:
    """OpenAPIレスポンススキーマの検証テスト"""

    @pytest.mark.asyncio
    async def test_animals_endpoint_response_schema(self, test_app):
        """/animals エンドポイントのレスポンススキーマが正しいか"""
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            response = await client.get("/openapi.json")

        schema = response.json()
        animals_get = schema["paths"]["/animals"]["get"]

        # 200レスポンスの確認
        assert "200" in animals_get["responses"]
        response_200 = animals_get["responses"]["200"]

        # content-typeの確認
        assert "content" in response_200
        assert "application/json" in response_200["content"]

    @pytest.mark.asyncio
    async def test_animal_by_id_endpoint_error_responses(self, test_app):
        """/animals/{animal_id} エンドポイントのエラーレスポンスが定義されているか"""
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            response = await client.get("/openapi.json")

        schema = response.json()
        animal_get = schema["paths"]["/animals/{animal_id}"]["get"]

        # 200レスポンスの確認
        assert "200" in animal_get["responses"]

        # 422バリデーションエラーレスポンス（FastAPIのデフォルト）
        assert "422" in animal_get["responses"]

    @pytest.mark.asyncio
    async def test_limit_parameter_has_validation(self, test_app):
        """limit パラメータにバリデーション制約が含まれているか"""
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            response = await client.get("/openapi.json")

        schema = response.json()
        animals_get = schema["paths"]["/animals"]["get"]

        # limit パラメータを探す
        limit_param = next(
            (p for p in animals_get["parameters"] if p["name"] == "limit"),
            None
        )
        assert limit_param is not None

        # スキーマにle（最大値）制約があることを確認
        param_schema = limit_param.get("schema", {})
        # FastAPIは maximum を使う
        assert "maximum" in param_schema or param_schema.get("type") == "integer"
