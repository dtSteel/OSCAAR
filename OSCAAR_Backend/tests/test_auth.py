import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as c:
        yield c


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_register_and_login(client):
    # Register
    response = await client.post("/api/v1/auth/register", json={
        "full_name": "Dr. Test User",
        "email": "test@example.com",
        "password": "SecurePassword123!",
        "language": "en",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"
    assert data["role"] == "researcher"

    # Login
    response = await client.post("/api/v1/auth/login", json={
        "email": "test@example.com",
        "password": "SecurePassword123!",
    })
    assert response.status_code == 200
    assert "access_token" in response.json()


@pytest.mark.asyncio
async def test_register_duplicate_email(client):
    payload = {
        "full_name": "Dr. Duplicate",
        "email": "duplicate@example.com",
        "password": "SecurePassword123!",
        "language": "en",
    }
    await client.post("/api/v1/auth/register", json=payload)
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    await client.post("/api/v1/auth/register", json={
        "full_name": "Dr. Wrong",
        "email": "wrong@example.com",
        "password": "CorrectPassword123!",
        "language": "en",
    })
    response = await client.post("/api/v1/auth/login", json={
        "email": "wrong@example.com",
        "password": "WrongPassword123!",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_without_token(client):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_weak_password_rejected(client):
    response = await client.post("/api/v1/auth/register", json={
        "full_name": "Dr. Weak",
        "email": "weak@example.com",
        "password": "short",
        "language": "en",
    })
    assert response.status_code == 422
