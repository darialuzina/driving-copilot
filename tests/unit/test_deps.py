from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.api.deps import to_response
from app.config import Settings
from app.domain.link import Link
from app.domain.value_objects import ShortCode, TargetUrl


def _link(
    *,
    disabled: bool = False,
    expires_at: datetime | None = None,
    id_: int | None = 1,
    clicks: int = 0,
) -> Link:
    return Link(
        short_code=ShortCode("abcd"),
        target_url=TargetUrl("https://example.com"),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        expires_at=expires_at,
        clicks=clicks,
        disabled=disabled,
        id=id_,
    )


# ---------------------------------------------------------------------------
# to_response
# ---------------------------------------------------------------------------


def test_to_response_raises_on_unsaved_link() -> None:
    link = _link(id_=None)
    with pytest.raises(ValueError, match="cannot serialize an unsaved link"):
        to_response(link)


def test_to_response_active_link(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.api.deps.get_settings",
        lambda: Settings(base_url="http://sho.rt"),
    )
    resp = to_response(_link(expires_at=None))
    assert resp.id == 1
    assert resp.short_code == "abcd"
    assert resp.target_url == "https://example.com"
    assert resp.short_url == "http://sho.rt/abcd"
    assert resp.status == "active"
    assert resp.clicks == 0
    assert resp.disabled is False
    assert resp.expires_at is None


def test_to_response_strips_trailing_slash_in_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.deps.get_settings",
        lambda: Settings(base_url="http://sho.rt/"),
    )
    assert to_response(_link()).short_url == "http://sho.rt/abcd"


def test_to_response_expired_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.api.deps.get_settings",
        lambda: Settings(base_url="http://sho.rt"),
    )
    past = datetime.now(UTC) - timedelta(hours=1)
    assert to_response(_link(expires_at=past)).status == "expired"


def test_to_response_disabled_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.api.deps.get_settings",
        lambda: Settings(base_url="http://sho.rt"),
    )
    assert to_response(_link(disabled=True)).status == "disabled"


# ---------------------------------------------------------------------------
# get_link_service
# ---------------------------------------------------------------------------
