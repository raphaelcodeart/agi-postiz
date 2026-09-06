class OpenAIApiError(Exception):
    """Raised when the OpenAI API call fails or is unavailable (no key configured, HTTP error, malformed response)."""
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
