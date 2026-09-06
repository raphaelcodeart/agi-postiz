from typing import Optional

class BufferApiError(Exception):
    """Base exception for all Buffer API operations."""
    def __init__(
        self, 
        message: str, 
        status_code: Optional[int] = None, 
        error_code: Optional[str] = None,
        is_temporary: bool = False,
        category: str = "unknown"
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.is_temporary = is_temporary
        self.category = category  # e.g., "auth_expired", "rate_limit", "invalid_media", "validation_failed"

class BufferAuthError(BufferApiError):
    """Auth related errors (invalid token, expired access token, etc.)."""
    def __init__(self, message: str, status_code: int = 401, error_code: Optional[str] = None):
        super().__init__(
            message=message,
            status_code=status_code,
            error_code=error_code,
            is_temporary=False,
            category="auth_error"
        )

class BufferRateLimitError(BufferApiError):
    """Rate limit errors (HTTP 429)."""
    def __init__(self, message: str, status_code: int = 429, error_code: Optional[str] = None):
        super().__init__(
            message=message,
            status_code=status_code,
            error_code=error_code,
            is_temporary=True,
            category="rate_limit"
        )

class BufferNetworkError(BufferApiError):
    """Timeout or connection issues."""
    def __init__(self, message: str):
        super().__init__(
            message=message,
            status_code=None,
            error_code=None,
            is_temporary=True,
            category="network_error"
        )

class BufferServerError(BufferApiError):
    """5xx server side issues."""
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(
            message=message,
            status_code=status_code,
            error_code=None,
            is_temporary=True,
            category="server_error"
        )
