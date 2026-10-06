from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

from finpulse.core.errors import NotFoundError, PreconditionFailedError
from finpulse.main import create_app
from tests.conftest import client_for, make_settings

PROBLEM = "application/problem+json"


class Payload(BaseModel):
    months: int


def _app_with_failing_routes() -> FastAPI:
    app = create_app(make_settings())
    router = APIRouter()

    @router.get("/_test/not-found")
    async def not_found() -> None:
        raise NotFoundError("Subject 42 does not exist.", code="subject_not_found")

    @router.get("/_test/precondition")
    async def precondition() -> None:
        raise PreconditionFailedError(extra={"subject_id": "42"})

    @router.post("/_test/validate")
    async def validate(payload: Payload) -> Payload:
        return payload

    @router.get("/_test/crash")
    async def crash() -> None:
        raise RuntimeError("secret internal detail")

    app.include_router(router)
    return app


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async for c in client_for(_app_with_failing_routes()):
        yield c


async def test_domain_error_becomes_problem_json(client: httpx.AsyncClient) -> None:
    response = await client.get("/_test/not-found")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM
    body = response.json()
    assert body["code"] == "subject_not_found"
    assert body["title"] == "Not found"
    assert body["detail"] == "Subject 42 does not exist."
    assert body["type"].endswith("/subject-not-found")
    assert response.headers.get_list("x-request-id") == [body["request_id"]]


async def test_domain_error_extra_is_returned(client: httpx.AsyncClient) -> None:
    response = await client.get("/_test/precondition")

    assert response.status_code == 412
    assert response.json()["extra"] == {"subject_id": "42"}


async def test_validation_error_lists_fields(client: httpx.AsyncClient) -> None:
    response = await client.post("/_test/validate", json={"months": "many"})

    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["errors"][0]["loc"] == ["body", "months"]


async def test_unknown_route_is_problem_json(client: httpx.AsyncClient) -> None:
    response = await client.get("/nope")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM
    assert response.json()["code"] == "route_not_found"


async def test_unhandled_exception_hides_internals(client: httpx.AsyncClient) -> None:
    response = await client.get("/_test/crash")

    assert response.status_code == 500
    assert response.headers["content-type"] == PROBLEM
    body = response.json()
    assert body["code"] == "internal_error"
    assert "secret internal detail" not in response.text
    assert body["request_id"] == response.headers["x-request-id"]
