from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from app.domain.link import Link, LinkStatus
from app.domain.value_objects import ShortCode, TargetUrl


def make_link(
    *,
    disabled: bool = False,
    expires_at: datetime | None = None,
    clicks: int = 0,
    id_: int | None = 1,
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
# status
# ---------------------------------------------------------------------------


def test_status_active_without_expires_at() -> None:
    link = make_link(expires_at=None)
    now = datetime(2026, 7, 28, tzinfo=UTC)
    assert link.status(now) is LinkStatus.ACTIVE


def test_status_active_with_future_expiry() -> None:
    expires = datetime(2026, 12, 31, tzinfo=UTC)
    link = make_link(expires_at=expires)
    assert link.status(datetime(2026, 7, 28, tzinfo=UTC)) is LinkStatus.ACTIVE


def test_status_expired_when_now_ge_expires_at() -> None:
    expires = datetime(2026, 6, 1, tzinfo=UTC)
    link = make_link(expires_at=expires)
    assert link.status(datetime(2026, 6, 1, tzinfo=UTC)) is LinkStatus.EXPIRED
    assert link.status(datetime(2026, 7, 28, tzinfo=UTC)) is LinkStatus.EXPIRED


def test_status_disabled_wins_over_expired() -> None:
    expires = datetime(2026, 1, 1, tzinfo=UTC)
    link = make_link(disabled=True, expires_at=expires)
    now = datetime(2026, 7, 28, tzinfo=UTC)
    assert link.status(now) is LinkStatus.DISABLED


def test_status_disabled_wins_over_active() -> None:
    link = make_link(disabled=True, expires_at=None)
    assert link.status(datetime(2026, 7, 28, tzinfo=UTC)) is LinkStatus.DISABLED


# ---------------------------------------------------------------------------
# is_active
# ---------------------------------------------------------------------------


def test_is_active_true_for_active_link() -> None:
    link = make_link(expires_at=None)
    assert link.is_active(datetime(2026, 7, 28, tzinfo=UTC)) is True


def test_is_active_false_for_expired_link() -> None:
    expires = datetime(2026, 1, 1, tzinfo=UTC)
    link = make_link(expires_at=expires)
    assert link.is_active(datetime(2026, 7, 28, tzinfo=UTC)) is False


def test_is_active_false_for_disabled_link() -> None:
    link = make_link(disabled=True)
    assert link.is_active(datetime(2026, 7, 28, tzinfo=UTC)) is False


# ---------------------------------------------------------------------------
# with_click
# ---------------------------------------------------------------------------


def test_with_click_increments_clicks() -> None:
    link = make_link(clicks=3)
    clicked = link.with_click()
    assert clicked.clicks == 4


def test_with_click_returns_new_instance() -> None:
    link = make_link(clicks=0)
    clicked = link.with_click()
    assert clicked is not link


def test_with_click_does_not_mutate_original() -> None:
    link = make_link(clicks=5)
    link.with_click()
    assert link.clicks == 5


def test_with_click_preserves_other_fields() -> None:
    link = make_link(clicks=1)
    clicked = link.with_click()
    assert clicked.short_code == link.short_code
    assert clicked.target_url == link.target_url
    assert clicked.created_at == link.created_at
    assert clicked.expires_at == link.expires_at
    assert clicked.disabled == link.disabled
    assert clicked.id == link.id


# ---------------------------------------------------------------------------
# disable
# ---------------------------------------------------------------------------


def test_disable_sets_disabled_true() -> None:
    link = make_link(disabled=False)
    assert link.disable().disabled is True


def test_disable_returns_new_instance() -> None:
    link = make_link(disabled=False)
    assert link.disable() is not link


def test_disable_does_not_mutate_original() -> None:
    link = make_link(disabled=False)
    link.disable()
    assert link.disabled is False


# ---------------------------------------------------------------------------
# immutability
# ---------------------------------------------------------------------------


def test_link_is_frozen() -> None:
    link = make_link()
    with pytest.raises(FrozenInstanceError):
        link.clicks = 10  # type: ignore[misc]


def test_link_equality_by_value() -> None:
    a = make_link()
    b = make_link()
    assert a == b
