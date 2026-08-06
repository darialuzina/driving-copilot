from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.domain.errors import InvalidShortCodeError, InvalidUrlError
from app.domain.value_objects import (
    MAX_CODE_LENGTH,
    MAX_URL_LENGTH,
    MIN_CODE_LENGTH,
    ShortCode,
    TargetUrl,
)

# ---------------------------------------------------------------------------
# TargetUrl
# ---------------------------------------------------------------------------


def test_target_url_valid_https() -> None:
    url = TargetUrl("https://example.com")
    assert url.value == "https://example.com"


def test_target_url_valid_http() -> None:
    url = TargetUrl("http://example.com")
    assert url.value == "http://example.com"


def test_target_url_strips_whitespace() -> None:
    url = TargetUrl("  https://example.com  ")
    assert url.value == "https://example.com"


def test_target_url_empty_raises() -> None:
    with pytest.raises(InvalidUrlError, match="empty"):
        TargetUrl("")


def test_target_url_only_whitespace_raises() -> None:
    with pytest.raises(InvalidUrlError, match="empty"):
        TargetUrl("   ")


def test_target_url_too_long_raises() -> None:
    long_url = "https://example.com/" + "a" * (MAX_URL_LENGTH + 1)
    assert len(long_url) > MAX_URL_LENGTH
    with pytest.raises(InvalidUrlError, match="longer than 2048 characters"):
        TargetUrl(long_url)


def test_target_url_max_length_accepted() -> None:
    url = "https://example.com/" + "a" * (MAX_URL_LENGTH - len("https://example.com/"))
    assert len(url) <= MAX_URL_LENGTH
    assert TargetUrl(url).value == url


def test_target_url_bad_scheme_raises() -> None:
    with pytest.raises(InvalidUrlError, match="scheme must be http or https"):
        TargetUrl("ftp://example.com")


def test_target_url_no_scheme_raises() -> None:
    with pytest.raises(InvalidUrlError, match="scheme must be http or https"):
        TargetUrl("not-a-url")


def test_target_url_missing_host_raises() -> None:
    with pytest.raises(InvalidUrlError, match="missing host"):
        TargetUrl("http:///path")


def test_target_url_with_username_raises() -> None:
    with pytest.raises(InvalidUrlError, match="credentials in URL are not allowed"):
        TargetUrl("https://user@example.com")


def test_target_url_with_credentials_raises() -> None:
    with pytest.raises(InvalidUrlError, match="credentials in URL are not allowed"):
        TargetUrl("https://user:pass@example.com")


def test_target_url_loopback_host_raises() -> None:
    with pytest.raises(InvalidUrlError, match="loopback host is not allowed"):
        TargetUrl("https://localhost")


def test_target_url_private_ip_raises() -> None:
    with pytest.raises(InvalidUrlError, match="private or reserved IP is not allowed"):
        TargetUrl("https://10.0.0.1")


def test_target_url_loopback_ip_raises() -> None:
    with pytest.raises(InvalidUrlError, match="private or reserved IP is not allowed"):
        TargetUrl("https://127.0.0.1")


def test_target_url_loopback_ipv6_raises() -> None:
    with pytest.raises(InvalidUrlError, match="private or reserved IP is not allowed"):
        TargetUrl("https://[::1]")


def test_target_url_link_local_ip_raises() -> None:
    with pytest.raises(InvalidUrlError, match="private or reserved IP is not allowed"):
        TargetUrl("https://169.254.1.1")


def test_target_url_reserved_ip_raises() -> None:
    with pytest.raises(InvalidUrlError, match="private or reserved IP is not allowed"):
        TargetUrl("https://240.0.0.1")


def test_target_url_multicast_ip_raises() -> None:
    with pytest.raises(InvalidUrlError, match="private or reserved IP is not allowed"):
        TargetUrl("https://224.0.0.1")


def test_target_url_unspecified_ip_raises() -> None:
    with pytest.raises(InvalidUrlError, match="private or reserved IP is not allowed"):
        TargetUrl("https://0.0.0.0")


def test_target_url_ip6_localhost_raises() -> None:
    with pytest.raises(InvalidUrlError, match="loopback host is not allowed"):
        TargetUrl("https://ip6-localhost")


def test_target_url_uppercase_localhost_raises() -> None:
    with pytest.raises(InvalidUrlError, match="loopback host is not allowed"):
        TargetUrl("https://LOCALHOST")


def test_target_url_public_ipv6_accepted() -> None:
    assert TargetUrl("https://[2001:4860:4860::8888]").value == "https://[2001:4860:4860::8888]"


def test_target_url_public_ip_accepted() -> None:
    url = TargetUrl("https://8.8.8.8")
    assert url.value == "https://8.8.8.8"


def test_target_url_with_port_accepted() -> None:
    url = TargetUrl("https://example.com:8080")
    assert url.value == "https://example.com:8080"


def test_target_url_frozen() -> None:
    url = TargetUrl("https://example.com")
    with pytest.raises(FrozenInstanceError):
        url.value = "https://other.com"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ShortCode
# ---------------------------------------------------------------------------


def test_short_code_min_length_accepted() -> None:
    code = ShortCode("a" * MIN_CODE_LENGTH)
    assert code.value == "a" * MIN_CODE_LENGTH


def test_short_code_max_length_accepted() -> None:
    value = "a" * MAX_CODE_LENGTH
    assert ShortCode(value).value == value


def test_short_code_too_short_raises() -> None:
    with pytest.raises(InvalidShortCodeError, match=r"length must be 4\.\.16"):
        ShortCode("abc")


def test_short_code_too_long_raises() -> None:
    with pytest.raises(InvalidShortCodeError, match=r"length must be 4\.\.16"):
        ShortCode("a" * (MAX_CODE_LENGTH + 1))


def test_short_code_invalid_char_dash_raises() -> None:
    with pytest.raises(InvalidShortCodeError, match="only ASCII letters and digits"):
        ShortCode("ab-cd")


def test_short_code_invalid_char_underscore_raises() -> None:
    with pytest.raises(InvalidShortCodeError, match="only ASCII letters and digits"):
        ShortCode("ab_cd")


def test_short_code_invalid_char_space_raises() -> None:
    with pytest.raises(InvalidShortCodeError, match="only ASCII letters and digits"):
        ShortCode("ab cd")


def test_short_code_invalid_char_unicode_raises() -> None:
    with pytest.raises(InvalidShortCodeError, match="only ASCII letters and digits"):
        ShortCode("abсd")


def test_short_code_all_letters_accepted() -> None:
    assert ShortCode("abcd").value == "abcd"


def test_short_code_all_digits_accepted() -> None:
    assert ShortCode("1234").value == "1234"


def test_short_code_mixed_accepted() -> None:
    assert ShortCode("ab12").value == "ab12"


def test_short_code_does_not_strip_whitespace() -> None:
    with pytest.raises(InvalidShortCodeError, match="only ASCII letters and digits"):
        ShortCode(" abcd ")


def test_short_code_frozen() -> None:
    code = ShortCode("abcd")
    with pytest.raises(FrozenInstanceError):
        code.value = "xxxx"  # type: ignore[misc]
