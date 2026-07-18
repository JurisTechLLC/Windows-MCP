"""Tests for HTTP bearer-token authentication and startup validation."""

from __future__ import annotations

import asyncio
import logging
import types

import pytest
from click.testing import CliRunner
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from windows_mcp.infrastructure.auth import AuthKeyMiddleware
import windows_mcp.__main__ as cli


async def _ok_handler(request: Request) -> JSONResponse:
    """Simple ASGI handler used by the test app."""
    return JSONResponse({"ok": True})


async def _health_handler(request: Request) -> JSONResponse:
    """Public health endpoint used to test path exemptions."""
    return JSONResponse({"status": "ok"})


def _build_app(auth_token: str | None = None) -> Starlette:
    """Build a Starlette app wrapped by AuthKeyMiddleware when a token is supplied."""
    routes = [
        Route("/", _ok_handler),
        Route("/health", _health_handler),
    ]
    middleware: list[Middleware] = []
    if auth_token:
        middleware.append(Middleware(AuthKeyMiddleware, auth_key=auth_token))
    return Starlette(routes=routes, middleware=middleware)


class TestAuthKeyMiddleware:
    """Bearer-token middleware behaviour."""

    def test_valid_token_accepted(self) -> None:
        client = TestClient(_build_app("super_secret"))
        response = client.get("/", headers={"Authorization": "Bearer super_secret"})
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_missing_header_rejected(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.WARNING, logger="windows_mcp.infrastructure.auth")
        client = TestClient(_build_app("super_secret"))
        response = client.get("/")
        assert response.status_code == 401
        assert response.headers.get("www-authenticate") == "Bearer"
        assert any(
            "missing or malformed Authorization header" in record.message
            for record in caplog.records
        )
        assert any(
            record.message.startswith("Authentication failed:") and "from" in record.message
            for record in caplog.records
        )

    def test_wrong_token_rejected(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.WARNING, logger="windows_mcp.infrastructure.auth")
        client = TestClient(_build_app("super_secret"))
        response = client.get("/", headers={"Authorization": "Bearer wrong_token"})
        assert response.status_code == 401
        assert response.json()["error"] == "Invalid authentication token"
        assert any("invalid token" in record.message for record in caplog.records)

    @pytest.mark.parametrize(
        "header",
        [
            "Basic dXNlcjpwYXNz",
            "Bearersuper_secret",
            "Bearer ",
            "bearer super_secret",
            "",
        ],
    )
    def test_malformed_authorization_rejected(self, header: str) -> None:
        client = TestClient(_build_app("super_secret"))
        response = client.get("/", headers={"Authorization": header})
        assert response.status_code == 401

    def test_public_path_is_unauthenticated(self) -> None:
        client = TestClient(_build_app("super_secret"))
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_failed_attempt_logs_source_ip(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.WARNING, logger="windows_mcp.infrastructure.auth")
        client = TestClient(_build_app("super_secret"))
        client.get("/", headers={"Authorization": "Bearer wrong"})
        [record] = [record for record in caplog.records if record.levelno == logging.WARNING]
        assert "Authentication failed" in record.message
        assert "from" in record.message
        # The timestamp is embedded as an ISO-8601 string by the logger.
        assert any(part.count("-") >= 2 and ":" in part for part in record.message.split())


class TestStartupAuth:
    """Startup-time authentication validation for the serve command."""

    @pytest.fixture(autouse=True)
    def _patch_asyncio(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Avoid asyncio.WindowsSelectorEventLoopPolicy on non-Windows hosts."""
        fake_asyncio = types.SimpleNamespace(
            WindowsSelectorEventLoopPolicy=asyncio.DefaultEventLoopPolicy,
            set_event_loop_policy=lambda _policy: None,
        )
        monkeypatch.setattr(cli, "asyncio", fake_asyncio)

    @pytest.fixture
    def run_server_calls(self, monkeypatch: pytest.MonkeyPatch) -> list[dict]:
        """Capture arguments passed to _run_server without starting anything."""
        calls: list[dict] = []

        def fake_run_server(**kwargs: object) -> None:
            calls.append(kwargs)

        monkeypatch.setattr(cli, "_run_server", fake_run_server)
        return calls

    @pytest.fixture
    def runner(self, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
        """Provide a Click runner with token env vars cleared."""
        for var in ("WINDOWS_MCP_TOKEN", "WINDOWS_MCP_AUTH_KEY"):
            monkeypatch.delenv(var, raising=False)
        return CliRunner()

    def test_remote_http_without_token_is_refused(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli.main,
            ["serve", "--transport", "sse", "--host", "0.0.0.0"],
        )
        assert result.exit_code != 0
        assert "Refusing to bind HTTP transport" in result.output

    def test_remote_http_with_cli_token_starts(
        self, runner: CliRunner, run_server_calls: list[dict]
    ) -> None:
        result = runner.invoke(
            cli.main,
            ["serve", "--transport", "sse", "--host", "0.0.0.0", "--token", "abc123"],
        )
        assert result.exit_code == 0, result.output
        assert len(run_server_calls) == 1
        assert run_server_calls[0]["auth_key"] == "abc123"

    def test_remote_http_with_env_token_starts(
        self, runner: CliRunner, run_server_calls: list[dict], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("WINDOWS_MCP_TOKEN", "env_token")
        result = runner.invoke(
            cli.main,
            ["serve", "--transport", "sse", "--host", "0.0.0.0"],
        )
        assert result.exit_code == 0, result.output
        assert run_server_calls[0]["auth_key"] == "env_token"

    def test_loopback_http_without_token_starts(
        self, runner: CliRunner, run_server_calls: list[dict]
    ) -> None:
        result = runner.invoke(
            cli.main,
            ["serve", "--transport", "sse", "--host", "127.0.0.1"],
        )
        assert result.exit_code == 0, result.output
        assert len(run_server_calls) == 1
        assert run_server_calls[0]["auth_key"] is None
        assert run_server_calls[0]["transport"] == "sse"

    def test_stdio_ignores_missing_token(
        self, runner: CliRunner, run_server_calls: list[dict]
    ) -> None:
        result = runner.invoke(
            cli.main,
            ["serve", "--transport", "stdio"],
        )
        assert result.exit_code == 0, result.output
        assert len(run_server_calls) == 1
        assert run_server_calls[0]["transport"] == "stdio"
        assert run_server_calls[0]["auth_key"] is None

    def test_auth_key_env_is_used_as_fallback(
        self, runner: CliRunner, run_server_calls: list[dict], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("WINDOWS_MCP_AUTH_KEY", "legacy_token")
        result = runner.invoke(
            cli.main,
            ["serve", "--transport", "sse", "--host", "0.0.0.0"],
        )
        assert result.exit_code == 0, result.output
        assert run_server_calls[0]["auth_key"] == "legacy_token"
