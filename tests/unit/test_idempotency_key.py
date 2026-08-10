from __future__ import annotations

from app.services.agent import make_write_idempotency_key

_ARGS_A = {
    "date": "today",
    "skills": [{"skill": "parking", "assessment": "good", "note": "did parking"}],
}
_ARGS_A_SHUFFLED = {
    "skills": [{"skill": "parking", "assessment": "good", "note": "did parking"}],
    "date": "today",
}
_ARGS_B = {
    "date": "today",
    "skills": [{"skill": "roundabouts", "assessment": "ok", "note": "roundabout ok"}],
}


def test_identical_retries_collide() -> None:
    k1 = make_write_idempotency_key("log_lesson", _ARGS_A, "2026-08-10")
    k2 = make_write_idempotency_key("log_lesson", _ARGS_A, "2026-08-10")
    assert k1 == k2


def test_argument_key_order_does_not_break_collision() -> None:
    # Canonical JSON (sort_keys) means key order in the dict must not matter.
    assert make_write_idempotency_key("log_lesson", _ARGS_A, "2026-08-10") == (
        make_write_idempotency_key("log_lesson", _ARGS_A_SHUFFLED, "2026-08-10")
    )


def test_distinct_calls_do_not_collide() -> None:
    k1 = make_write_idempotency_key("log_lesson", _ARGS_A, "2026-08-10")
    k2 = make_write_idempotency_key("log_lesson", _ARGS_B, "2026-08-10")
    assert k1 != k2


def test_same_args_different_day_do_not_collide() -> None:
    k1 = make_write_idempotency_key("log_lesson", _ARGS_A, "2026-08-10")
    k2 = make_write_idempotency_key("log_lesson", _ARGS_A, "2026-08-11")
    assert k1 != k2


def test_key_is_prefixed_with_tool_name() -> None:
    assert make_write_idempotency_key("log_lesson", _ARGS_A, "2026-08-10").startswith(
        "log_lesson:"
    )
