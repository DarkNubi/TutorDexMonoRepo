from __future__ import annotations

import asyncio
from typing import Any, Callable

from telethon.errors import FloodError, FloodWaitError, SlowModeWaitError


async def retry_with_backoff(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    MAX_RETRIES = 10
    INITIAL_RETRY_DELAY = 1.0
    BACKOFF_MULTIPLIER = 2.0
    MAX_RETRY_DELAY = 60.0

    last_exception: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            return await func(*args, **kwargs)
        except (FloodWaitError, SlowModeWaitError) as e:
            last_exception = e
            if attempt >= MAX_RETRIES:
                raise
            delay = float(getattr(e, "seconds", 0) or 0)
            delay = min(max(delay, INITIAL_RETRY_DELAY), MAX_RETRY_DELAY)
            await asyncio.sleep(delay)
        except FloodError as e:
            last_exception = e
            if attempt >= MAX_RETRIES:
                raise
            delay = min(INITIAL_RETRY_DELAY * (BACKOFF_MULTIPLIER**attempt), MAX_RETRY_DELAY)
            await asyncio.sleep(delay)
        except Exception as e:
            last_exception = e
            if attempt >= MAX_RETRIES:
                raise
            delay = min(INITIAL_RETRY_DELAY * (BACKOFF_MULTIPLIER**attempt), MAX_RETRY_DELAY)
            await asyncio.sleep(delay)
    if last_exception:
        raise last_exception

