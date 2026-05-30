"""Unified API error payload helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ApiError(Exception):
    code: str
    message: str
    hint: str = ""
    retryable: bool = False
    detail: str = ""
    status_code: int = 400

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "hint": self.hint,
            "retryable": self.retryable,
        }
        if self.detail:
            payload["detail"] = self.detail
        return payload


def raise_api_error(
    *,
    code: str,
    message: str,
    hint: str = "",
    retryable: bool = False,
    detail: str = "",
    status_code: int = 400,
) -> None:
    raise ApiError(
        code=code,
        message=message,
        hint=hint,
        retryable=retryable,
        detail=detail,
        status_code=status_code,
    )
