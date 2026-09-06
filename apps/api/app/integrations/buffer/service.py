from app.core.config import settings
from app.integrations.buffer.client import BaseBufferClient
from app.integrations.buffer.mock_client import MockBufferClient
from app.integrations.buffer.prod_client import ProductionBufferClient

def get_buffer_client() -> BaseBufferClient:
    """Factory to retrieve the configured Buffer API client."""
    if settings.BUFFER_INTEGRATION_MODE.lower() == "mock":
        return MockBufferClient()
    return ProductionBufferClient()
