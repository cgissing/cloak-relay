import pytest
import pytest_asyncio
from aiohttp.test_utils import TestClient, TestServer

from cloak_relay.server import create_app


class FakeManager:
    async def health(self):
        return {"ok": True, "sessions": []}

    async def tabs(self):
        return {"tabs": []}

    async def start_session(self, session_id, **kwargs):
        return {"sessionId": session_id, "kwargs": kwargs}

    async def close_session(self, session_id):
        return {"sessionId": session_id, "closed": True}

    async def clear_session(self, session_id, **kwargs):
        return {"sessionId": session_id, "cleared": True}

    async def navigate(self, session_id, url):
        return {"sessionId": session_id, "url": url}

    async def snapshot(self, session_id, **kwargs):
        return {"sessionId": session_id, "content": "Example", **kwargs}

    async def click(self, session_id, selector, **kwargs):
        return {"sessionId": session_id, "selector": selector, **kwargs}

    async def type_text(self, session_id, selector, text, **kwargs):
        return {"sessionId": session_id, "selector": selector, "text": text, **kwargs}

    async def scroll(self, session_id, direction, amount):
        return {"sessionId": session_id, "direction": direction, "amount": amount}

    async def screenshot(self, session_id, **kwargs):
        return {"sessionId": session_id, "data": "cG5n", **kwargs}

    async def evaluate(self, session_id, expression):
        return {"sessionId": session_id, "result": expression}


@pytest_asyncio.fixture
async def client():
    test_client = TestClient(TestServer(create_app(FakeManager())))
    await test_client.start_server()
    try:
        yield test_client
    finally:
        await test_client.close()


@pytest.mark.asyncio
async def test_health_endpoint_returns_ok(client):
    response = await client.get("/health")
    assert response.status == 200
    assert await response.json() == {"ok": True, "sessions": []}


@pytest.mark.asyncio
async def test_navigate_defaults_session_id(client):
    response = await client.post("/api/navigate", json={"url": "https://example.com"})
    assert response.status == 200
    assert await response.json() == {"sessionId": "default", "url": "https://example.com"}


@pytest.mark.asyncio
async def test_click_requires_selector(client):
    response = await client.post("/api/click", json={})
    assert response.status == 400
    body = await response.json()
    assert "selector" in body["error"]


@pytest.mark.asyncio
async def test_start_session_passes_runtime_options(client):
    response = await client.post(
        "/api/session/start",
        json={"sessionId": "alpha", "headless": True, "humanize": False, "geoip": True},
    )
    assert response.status == 200
    body = await response.json()
    assert body["sessionId"] == "alpha"
    assert body["kwargs"]["headless"] is True
    assert body["kwargs"]["humanize"] is False
    assert body["kwargs"]["geoip"] is True


@pytest.mark.asyncio
async def test_start_session_defaults_to_headless(client):
    response = await client.post("/api/session/start", json={"sessionId": "alpha"})
    assert response.status == 200
    body = await response.json()
    assert body["kwargs"]["headless"] is True
    assert body["kwargs"]["humanize"] is True
