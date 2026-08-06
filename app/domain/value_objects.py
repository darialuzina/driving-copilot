from __future__ import annotations

import ipaddress
import string
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.domain.errors import InvalidShortCodeError, InvalidUrlError

MAX_URL_LENGTH: int = 2048
ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})
_BLOCKED_HOSTNAMES: frozenset[str] = frozenset({"localhost", "ip6-localhost"})

CODE_ALPHABET: str = string.ascii_letters + string.digits
_CODE_CHARS: frozenset[str] = frozenset(CODE_ALPHABET)
MIN_CODE_LENGTH: int = 4
MAX_CODE_LENGTH: int = 16


def _reject_ssrf(hostname: str) -> None:
    """Блокирует очевидные SSRF-цели на этапе создания (статически, без DNS)."""
    host = hostname.lower().rstrip(".")
    if host in _BLOCKED_HOSTNAMES:
        raise InvalidUrlError("loopback host is not allowed")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return
    if (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        raise InvalidUrlError("private or reserved IP is not allowed")


@dataclass(frozen=True, slots=True)
class TargetUrl:
    """URL назначения. Проверяется при создании: http(s), без SSRF, в пределах длины."""

    value: str

    def __post_init__(self) -> None:
        url = self.value.strip()
        if not url:
            raise InvalidUrlError("empty")
        if len(url) > MAX_URL_LENGTH:
            raise InvalidUrlError(f"longer than {MAX_URL_LENGTH} characters")
        parts = urlsplit(url)
        if parts.scheme not in ALLOWED_SCHEMES:
            raise InvalidUrlError("scheme must be http or https")
        if not parts.hostname:
            raise InvalidUrlError("missing host")
        if parts.username or parts.password:
            raise InvalidUrlError("credentials in URL are not allowed")
        _reject_ssrf(parts.hostname)
        object.__setattr__(self, "value", url)


@dataclass(frozen=True, slots=True)
class ShortCode:
    """Короткий код ссылки. Правило: длина в допустимых пределах, только [A-Za-z0-9]."""

    value: str

    def __post_init__(self) -> None:
        code = self.value
        if not MIN_CODE_LENGTH <= len(code) <= MAX_CODE_LENGTH:
            raise InvalidShortCodeError(f"length must be {MIN_CODE_LENGTH}..{MAX_CODE_LENGTH}")
        if any(ch not in _CODE_CHARS for ch in code):
            raise InvalidShortCodeError("only ASCII letters and digits are allowed")
