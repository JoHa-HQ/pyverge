"""httpx transports that converge versioned JSON payloads."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import httpx

from pyverge.adapters.runtime import ConvergenceRuntime
from pyverge.runtime.context import MigrationContext
from pyverge.runtime.manager.types import TargetPolicy

from .policy import HttpPolicy

if TYPE_CHECKING:
    from pyverge.runtime import Runner

_BODY_HEADERS = frozenset({"content-length", "content-encoding", "transfer-encoding"})
_VERSION_HEADER = "content-version"
_ACCEPT_HEADER = "accept-version"


def _is_json(headers: httpx.Headers) -> bool:
    content_type = headers.get("content-type", "")
    media_type = content_type.split(";", 1)[0].strip().lower()
    return media_type == "application/json" or media_type.endswith("+json")


def _json_body(request: httpx.Request) -> dict[str, Any] | None:
    if not _is_json(request.headers):
        return None
    try:
        payload = json.loads(request.content)
    except (httpx.RequestNotRead, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _encode(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode()


def _request_headers(
    headers: httpx.Headers,
    payload: dict[str, Any],
    response_target: TargetPolicy | None,
) -> list[tuple[str, str]]:
    ignored = {_VERSION_HEADER, _ACCEPT_HEADER}
    merged = [
        (key, value)
        for key, value in headers.multi_items()
        if key.lower() not in _BODY_HEADERS and key.lower() not in ignored
    ]
    version = payload.get("version")
    if version is not None:
        merged.append((_VERSION_HEADER, str(version)))
    if isinstance(response_target, str):
        merged.append((_ACCEPT_HEADER, response_target))
    return merged


def _should_converge_response(
    response: httpx.Response, response_target: TargetPolicy | None
) -> bool:
    return (
        response_target is not None
        and response.is_success
        and _is_json(response.headers)
    )


def _replaced_body(
    response: httpx.Response,
    payload: dict[str, Any],
    request: httpx.Request,
) -> httpx.Response:
    headers = [
        (key, value)
        for key, value in response.headers.multi_items()
        if key.lower() not in _BODY_HEADERS
    ]
    return httpx.Response(
        response.status_code,
        headers=headers,
        content=_encode(payload),
        extensions=response.extensions,
        request=request,
        history=response.history,
    )


class PyvergeTransport(httpx.BaseTransport):
    """Converge JSON payloads inside a synchronous ``httpx`` client.

    The transport is configured with one strategy before the client is created.
    It sees outgoing requests, not remote handlers, so a handler-specific target
    belongs to a separate transport/client pair.
    """

    def __init__(
        self,
        runtime: ConvergenceRuntime,
        *,
        policy: HttpPolicy | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._runtime = runtime
        self._policy = policy or HttpPolicy()
        self._transport = transport or httpx.HTTPTransport()

    @property
    def runtime(self) -> ConvergenceRuntime:
        """Return the convergence runtime used by this transport."""
        return self._runtime

    @property
    def policy(self) -> HttpPolicy:
        """Return the request/response strategy."""
        return self._policy

    @property
    def transport(self) -> httpx.BaseTransport:
        """Return the inner transport."""
        return self._transport

    def bind(self, runner: Runner, *, validate_health: bool = True) -> None:
        """Bind the runtime runner and optionally validate registry health."""
        self._runtime.bind(runner)
        if validate_health:
            self._runtime.validate_health()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Converge the request body and its optional response."""
        context = self._runtime.context_for(request)
        body = _json_body(request)
        if body is None:
            converged_request = request
        else:
            converged = self._runtime.converge_sync(
                body, self._policy.target, context=context
            )
            converged_request = self._request(request, converged)
        response = self._transport.handle_request(converged_request)
        return self._response(response, converged_request, context)

    def close(self) -> None:
        """Close the inner transport."""
        self._transport.close()

    def _request(
        self, request: httpx.Request, payload: dict[str, Any]
    ) -> httpx.Request:
        return httpx.Request(
            request.method,
            request.url,
            headers=_request_headers(
                request.headers, payload, self._policy.response_target
            ),
            content=_encode(payload),
            extensions=request.extensions,
        )

    def _response(
        self,
        response: httpx.Response,
        request: httpx.Request,
        context: MigrationContext | None,
    ) -> httpx.Response:
        if not _should_converge_response(response, self._policy.response_target):
            return response
        response.read()
        if not response.content:
            return response
        try:
            parsed = response.json()
        except ValueError:
            return response
        if not isinstance(parsed, dict):
            return response
        converged = self._runtime.converge_sync(
            parsed, self._policy.response_target, context=context
        )
        if not isinstance(converged, dict):
            return response
        return _replaced_body(response, converged, request)


class PyvergeAsyncTransport(httpx.AsyncBaseTransport):
    """Converge JSON payloads inside an asynchronous ``httpx`` client.

    The transport is configured with one strategy before the client is created.
    It sees outgoing requests, not remote handlers, so a handler-specific target
    belongs to a separate transport/client pair.
    """

    def __init__(
        self,
        runtime: ConvergenceRuntime,
        *,
        policy: HttpPolicy | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._runtime = runtime
        self._policy = policy or HttpPolicy()
        self._transport = transport or httpx.AsyncHTTPTransport()

    @property
    def runtime(self) -> ConvergenceRuntime:
        """Return the convergence runtime used by this transport."""
        return self._runtime

    @property
    def policy(self) -> HttpPolicy:
        """Return the request/response strategy."""
        return self._policy

    @property
    def transport(self) -> httpx.AsyncBaseTransport:
        """Return the inner transport."""
        return self._transport

    def bind(self, runner: Runner, *, validate_health: bool = True) -> None:
        """Bind the runtime runner and optionally validate registry health."""
        self._runtime.bind(runner)
        if validate_health:
            self._runtime.validate_health()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Converge the request body and its optional response."""
        context = self._runtime.context_for(request)
        body = _json_body(request)
        if body is None:
            converged_request = request
        else:
            converged = await self._runtime.converge(
                body, self._policy.target, context=context
            )
            converged_request = self._request(request, converged)
        response = await self._transport.handle_async_request(converged_request)
        return await self._response(response, converged_request, context)

    async def aclose(self) -> None:
        """Close the inner transport."""
        await self._transport.aclose()

    def _request(
        self, request: httpx.Request, payload: dict[str, Any]
    ) -> httpx.Request:
        return httpx.Request(
            request.method,
            request.url,
            headers=_request_headers(
                request.headers, payload, self._policy.response_target
            ),
            content=_encode(payload),
            extensions=request.extensions,
        )

    async def _response(
        self,
        response: httpx.Response,
        request: httpx.Request,
        context: MigrationContext | None,
    ) -> httpx.Response:
        if not _should_converge_response(response, self._policy.response_target):
            return response
        await response.aread()
        if not response.content:
            return response
        try:
            parsed = response.json()
        except ValueError:
            return response
        if not isinstance(parsed, dict):
            return response
        converged = await self._runtime.converge(
            parsed, self._policy.response_target, context=context
        )
        if not isinstance(converged, dict):
            return response
        return _replaced_body(response, converged, request)


__all__ = ["PyvergeAsyncTransport", "PyvergeTransport"]
