class ConnectorError(Exception):
    """Raised by any Connector implementation when a channel API call fails."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class WebhookVerificationError(Exception):
    """Raised when an inbound webhook fails signature/secret verification."""
    pass
