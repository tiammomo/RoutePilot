"""Shared API error helpers for route handlers."""

from __future__ import annotations

from fastapi import HTTPException


def error_detail(message: str, code: str | None = None) -> dict[str, str | bool]:
    detail: dict[str, str | bool] = {"success": False, "error": message}
    if code:
        detail["code"] = code
    return detail


def raise_api_error(status_code: int, message: str, code: str | None = None) -> None:
    raise HTTPException(status_code=status_code, detail=error_detail(message=message, code=code))
