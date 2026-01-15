from __future__ import annotations

from typing import Any, List

from collection.config import enqueue_enabled, pipeline_version


def enqueue_extraction_jobs(store: Any, *, cfg: Any, channel_link: str, message_ids: List[str], force: bool = False) -> None:
    if not enqueue_enabled(cfg):
        return
    ids = [str(x).strip() for x in (message_ids or []) if str(x).strip()]
    if not ids:
        return
    store.enqueue_extractions(channel_link=channel_link, message_ids=ids, pipeline_version=pipeline_version(cfg), force=bool(force))

