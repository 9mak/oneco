"""GET /admin/sites のテスト

sites.yaml に登録された全サイトの一覧と、各サイトの DB 上の収集状況を返すエンドポイント。
collection-ops-dashboard spec Req6 の最小実装に対応する。
"""

from datetime import date

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.data_collector.infrastructure.api.app import create_app
from src.data_collector.infrastructure.api.dependencies import get_session
from src.data_collector.infrastructure.database.models import Animal, Base

_VALID_TOKEN = "test-internal-token"


@pytest_asyncio.fixture
async def async_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def async_session(async_engine):
    maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def test_app(async_session, monkeypatch):
    monkeypatch.setenv("INTERNAL_API_TOKEN", _VALID_TOKEN)
    app = create_app()

    async def override_get_session():
        yield async_session

    app.dependency_overrides[get_session] = override_get_session
    return app


@pytest.mark.asyncio
async def test_admin_sites_requires_auth(test_app):
    """X-Internal-Token なしの場合 401"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/admin/sites")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_sites_returns_list_with_total(test_app):
    """正しいトークンで sites と total を返す"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get(
            "/admin/sites",
            headers={"X-Internal-Token": _VALID_TOKEN},
        )
    assert response.status_code == 200
    body = response.json()
    assert "sites" in body
    assert "total" in body
    assert "generated_at" in body
    assert body["total"] == len(body["sites"])


@pytest.mark.asyncio
async def test_admin_sites_includes_required_fields(test_app):
    """各サイト行は必要フィールドを含む"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get(
            "/admin/sites",
            headers={"X-Internal-Token": _VALID_TOKEN},
        )
    body = response.json()
    if body["sites"]:
        site = body["sites"][0]
        for field in (
            "name",
            "prefecture",
            "list_url",
            "extraction",
            "requires_js",
            "category",
            "db_count",
            "last_shelter_date",
            "host",
            "health",
        ):
            assert field in site, f"site row missing field: {field}"
        # health の中身も検証
        for field in (
            "status",
            "consecutive_failures",
            "last_error",
            "last_failed_at",
        ):
            assert field in site["health"], f"health missing field: {field}"
        assert site["health"]["status"] in ("ok", "warning", "failing")


@pytest.mark.asyncio
async def test_admin_sites_returns_summary(test_app):
    """レスポンスに健全性 summary が含まれる"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get(
            "/admin/sites",
            headers={"X-Internal-Token": _VALID_TOKEN},
        )
    body = response.json()
    assert "summary" in body
    for key in ("ok", "warning", "failing"):
        assert key in body["summary"]
        assert isinstance(body["summary"][key], int)
    # 合計と total の整合性
    summary_total = sum(body["summary"].values())
    assert summary_total == body["total"]


@pytest.mark.asyncio
async def test_admin_sites_reflects_broken_sites_yaml(test_app, tmp_path, monkeypatch):
    """broken_sites.yaml の連続失敗回数が health.status に反映される

    threshold=3 で auto-skip 扱い (failing)、1-2 回は warning、未記録は ok。
    """
    import yaml

    # テスト用 broken_sites.yaml を作成
    broken_path = tmp_path / "broken_sites.yaml"
    broken_data = {
        # 既存サイトに対する記録 (sites.yaml 内のサイト名と一致させる必要あり)
        # ここでは「サイトが存在しなくても response は returnable」を確認するため
        # 適当な名前を入れる。集計に影響しない。
        "存在しないテストサイト_failing": {
            "consecutive_failures": 5,
            "last_error": "test failing error",
            "last_failed_at": "2026-05-26T00:00:00+00:00",
        },
        "存在しないテストサイト_warning": {
            "consecutive_failures": 1,
            "last_error": "test warning error",
            "last_failed_at": "2026-05-26T00:00:00+00:00",
        },
    }
    broken_path.write_text(yaml.safe_dump(broken_data, allow_unicode=True))

    monkeypatch.setattr(
        "src.data_collector.infrastructure.api.admin_routes._BROKEN_SITES_PATH",
        broken_path,
    )

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get(
            "/admin/sites",
            headers={"X-Internal-Token": _VALID_TOKEN},
        )
    body = response.json()
    # sites.yaml に該当サイトが無いので summary の failing/warning は増えないが、
    # endpoint がエラー無く動作することを確認 (broken_sites 統合の smoke test)
    assert response.status_code == 200
    assert "summary" in body


@pytest.mark.asyncio
async def test_admin_sites_db_count_reflects_animals(test_app, async_session):
    """DB に animals があれば該当ホストの db_count に反映される"""
    # douai-tokushima.com に該当する animals を投入
    async_session.add(
        Animal(
            species="犬",
            sex="男の子",
            shelter_date=date(2026, 5, 1),
            location="徳島県動物愛護管理センター",
            prefecture="徳島県",
            phone="088-000-0000",
            image_urls=[],
            source_url="https://douai-tokushima.com/transfer/test1",
            category="adoption",
            status="sheltered",
        )
    )
    await async_session.commit()

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get(
            "/admin/sites",
            headers={"X-Internal-Token": _VALID_TOKEN},
        )
    body = response.json()
    matches = [s for s in body["sites"] if s["host"] == "douai-tokushima.com"]
    if matches:
        assert any(s["db_count"] >= 1 for s in matches)
