from __future__ import annotations


class DomainError(Exception):
    """Базовая доменная ошибка. Транспортный слой маппит её в HTTP-код."""


class InvalidUrlError(DomainError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Invalid target URL: {reason}")
        self.reason = reason


class InvalidShortCodeError(DomainError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Invalid short code: {reason}")
        self.reason = reason


class ShortCodeTakenError(DomainError):
    def __init__(self, short_code: str) -> None:
        super().__init__(f"Short code already taken: {short_code}")
        self.short_code = short_code


class LinkNotFoundError(DomainError):
    def __init__(self, short_code: str) -> None:
        super().__init__(f"Link not found: {short_code}")
        self.short_code = short_code


class LinkExpiredError(DomainError):
    def __init__(self, short_code: str) -> None:
        super().__init__(f"Link expired: {short_code}")
        self.short_code = short_code


class LinkDisabledError(DomainError):
    def __init__(self, short_code: str) -> None:
        super().__init__(f"Link disabled: {short_code}")
        self.short_code = short_code
