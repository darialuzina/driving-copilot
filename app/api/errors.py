from __future__ import annotations

from typing import NoReturn

from fastapi import HTTPException, status

from app.domain.errors import (
    DomainError,
    InvalidShortCodeError,
    InvalidUrlError,
    LinkDisabledError,
    LinkExpiredError,
    LinkNotFoundError,
    ShortCodeTakenError,
)

_STATUS_BY_ERROR: dict[type[DomainError], int] = {
    InvalidUrlError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    InvalidShortCodeError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ShortCodeTakenError: status.HTTP_409_CONFLICT,
    LinkNotFoundError: status.HTTP_404_NOT_FOUND,
    LinkExpiredError: status.HTTP_410_GONE,
    LinkDisabledError: status.HTTP_404_NOT_FOUND,
}


def raise_for_domain_error(exc: DomainError) -> NoReturn:
    """Преобразует доменную ошибку в HTTP-ответ FastAPI."""
    status_code = _STATUS_BY_ERROR.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)
    raise HTTPException(status_code=status_code, detail=str(exc)) from exc
