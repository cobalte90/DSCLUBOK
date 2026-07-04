from __future__ import annotations

from typing import Protocol
from ..models import ExternalSearchRequest, ExternalSourceHit


class ExternalSourceConnector(Protocol):
    """
    Contract every connector must satisfy.

    Rules (per module spec, section 2):
    - never bypass paywalls, captchas or login walls
    - never bulk-download PDFs without rights
    - on failure, raise ConnectorError (caught by the service layer) —
      never let an exception propagate raw into the API response
    - respect the per-connector timeout passed in via httpx client config
    """

    id: str
    label: str
    requires_api_key: bool

    def is_enabled(self) -> bool: ...

    async def search(self, request: ExternalSearchRequest) -> list[ExternalSourceHit]: ...


class ConnectorError(Exception):
    """Raised by a connector when it cannot complete a search.

    `reason` should be a short, user-safe string (no stack traces, no raw
    HTML) — it goes straight into the API's `warnings` list.
    """

    def __init__(self, connector_id: str, reason: str):
        self.connector_id = connector_id
        self.reason = reason
        super().__init__(f"{connector_id}: {reason}")


class ConnectorNotConfigured(ConnectorError):
    def __init__(self, connector_id: str):
        super().__init__(connector_id, "missing_api_key")
