"""Shared access-token check for /api/* (KANGAROO_ACCESS_TOKEN; blank disables it)."""

from typing import Annotated

from fastapi import Header, HTTPException, Query, Request, status


def require_token(
    request: Request,
    x_access_token: Annotated[str | None, Header()] = None,
    access_token: Annotated[str | None, Query()] = None,
) -> None:
    # EventSource can't send headers, so the SSE endpoint takes ?access_token=.
    token = request.app.state.access_token

    if token and token not in (x_access_token, access_token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or wrong access token.")
