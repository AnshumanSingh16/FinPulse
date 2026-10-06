import httpx


async def test_request_id_is_generated(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")

    assert response.headers["x-request-id"].startswith("req_")


async def test_valid_incoming_request_id_is_propagated(client: httpx.AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Request-ID": "web-abc.123"})

    assert response.headers["x-request-id"] == "web-abc.123"


async def test_unsafe_incoming_request_id_is_replaced(client: httpx.AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Request-ID": "bad id\twith junk"})

    assert response.headers["x-request-id"].startswith("req_")


async def test_cors_allows_configured_web_origin(client: httpx.AsyncClient) -> None:
    response = await client.options(
        "/health",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


async def test_cors_rejects_other_origins(client: httpx.AsyncClient) -> None:
    response = await client.get("/health", headers={"Origin": "https://evil.example"})

    assert "access-control-allow-origin" not in response.headers
