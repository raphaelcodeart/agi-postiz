from typing import Optional

class WordpressApiError(Exception):
    """Base exception for all WordPress REST API operations."""
    def __init__(self, message: str, status_code: Optional[int] = None, category: str = "unknown"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.category = category  # auth_error, network_error, server_error, invalid_url, not_found, unknown


class WordpressAuthError(WordpressApiError):
    def __init__(self, message: str = "Credenziali WordPress non valide"):
        super().__init__(message, status_code=401, category="auth_error")


class WordpressUnsafeUrlError(WordpressApiError):
    """Raised when a site/api URL fails SSRF validation (private/loopback/link-local target, or non-HTTPS)."""
    def __init__(self, message: str):
        super().__init__(message, status_code=None, category="invalid_url")
