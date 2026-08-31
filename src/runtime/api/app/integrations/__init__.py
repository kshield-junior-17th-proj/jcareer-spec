"""Default-off, provider-neutral outbound integration adapters."""

from .contracts import (
    DeliveryProvider,
    DeliveryReceipt,
    DeliveryState,
    IntegrationEvent,
    IntegrationStatusResponse,
    SyntheticSendRequest,
    SyntheticSendResponse,
)
from .service import IntegrationService

__all__ = [
    "DeliveryProvider",
    "DeliveryReceipt",
    "DeliveryState",
    "IntegrationEvent",
    "IntegrationService",
    "IntegrationStatusResponse",
    "SyntheticSendRequest",
    "SyntheticSendResponse",
]
