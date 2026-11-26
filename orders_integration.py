"""Future import boundary only. No credentials, network calls or active sync."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ExternalOrder:
    external_id: str
    source: str
    modified_at: str
    customer: dict
    order: dict
    items: list[dict]
    last_synced_version: int | None = None


class OrdersImportAdapter(Protocol):
    """A future adapter fetches drafts; it must never write directly to SQLite.

    A coordinator must validate using orders_store, deduplicate by source plus
    external_id and compare local version/remote modified_at against the last
    successful sync. Conflicts require explicit resolution. Absence from a sheet
    must never imply cancellation, deletion, payment, completion or a refund.
    """
    def fetch_changes(self, cursor: str | None) -> tuple[list[ExternalOrder], str]: ...
