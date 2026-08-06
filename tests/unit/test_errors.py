from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.errors import raise_for_domain_error
from app.domain.errors import (
    DomainError,
    InvalidShortCodeError,
    InvalidUrlError,
    LinkDisabledError,
    LinkExpiredError,
    LinkNotFoundError,
    ShortCodeTakenError,
)

# ---------------------------------------------------------------------------
# Domain error classes: construction, message, attribute, isinstance
# ---------------------------------------------------------------------------


def test_invalid_url_error_message_and_attribute() -> None:
    err = InvalidUrlError("bad scheme")
    assert err.reason == "bad scheme"
    assert str(err) == "Invalid target URL: bad scheme"
    assert isinstance(err, DomainError)


def test_invalid_short_code_error_message_and_attribute() -> None:
    err = InvalidShortCodeError("too short")
    assert err.reason == "too short"
    assert str(err) == "Invalid short code: too short"
    assert isinstance(err, DomainError)


def test_short_code_taken_error_message_and_attribute() -> None:
    err = ShortCodeTakenError("abc123")
    assert err.short_code == "abc123"
    assert str(err) == "Short code already taken: abc123"
    assert isinstance(err, DomainError)


def test_link_not_found_error_message_and_attribute() -> None:
    err = LinkNotFoundError("abc123")
    assert err.short_code == "abc123"
    assert str(err) == "Link not found: abc123"
    assert isinstance(err, DomainError)


def test_link_expired_error_message_and_attribute() -> None:
    err = LinkExpiredError("abc123")
    assert err.short_code == "abc123"
    assert str(err) == "Link expired: abc123"
    assert isinstance(err, DomainError)


def test_link_disabled_error_message_and_attribute() -> None:
    err = LinkDisabledError("abc123")
    assert err.short_code == "abc123"
    assert str(err) == "Link disabled: abc123"
    assert isinstance(err, DomainError)


# ---------------------------------------------------------------------------
# raise_for_domain_error: mapped status codes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("exc", "expected_status"),
    [
        (InvalidUrlError("bad"), 422),
        (InvalidShortCodeError("bad"), 422),
        (ShortCodeTakenError("code"), 409),
        (LinkNotFoundError("code"), 404),
        (LinkExpiredError("code"), 410),
        (LinkDisabledError("code"), 404),
    ],
)
def test_raise_for_domain_error_mapped(exc: DomainError, expected_status: int) -> None:
    with pytest.raises(HTTPException) as info:
        raise_for_domain_error(exc)
    assert info.value.status_code == expected_status
    assert info.value.detail == str(exc)
    assert info.value.__cause__ is exc


def test_raise_for_domain_error_preserves_chaining() -> None:
    original = LinkNotFoundError("abc")
    with pytest.raises(HTTPException) as info:
        raise_for_domain_error(original)
    assert info.value.__cause__ is original


# ---------------------------------------------------------------------------
# raise_for_domain_error: unmapped DomainError subclass -> 500 fallback
# ---------------------------------------------------------------------------


class _UnknownDomainError(DomainError):
    def __init__(self) -> None:
        super().__init__("unknown domain failure")


def test_raise_for_domain_error_unmapped_falls_back_to_500() -> None:
    exc = _UnknownDomainError()
    with pytest.raises(HTTPException, match="500") as info:
        raise_for_domain_error(exc)
    assert info.value.status_code == 500
    assert info.value.detail == "unknown domain failure"
    assert info.value.__cause__ is exc
