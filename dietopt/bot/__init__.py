"""Bot adapters."""

from .api_client import DietApiClient, DietApiClientError
from .telegram import TelegramAdapter

__all__ = ["DietApiClient", "DietApiClientError", "TelegramAdapter"]
