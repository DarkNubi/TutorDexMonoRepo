import asyncio

import pytest


backfill = pytest.importorskip("collection.backfill")


class _StallingIterator:
    def __init__(self):
        self._items = iter([1])

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration:
            await asyncio.sleep(60)
            raise StopAsyncIteration


class _FakeClient:
    def iter_messages(self, entity, *, reverse, offset_date):
        assert entity == "channel"
        assert reverse is False
        return _StallingIterator()

    async def disconnect(self):
        return None


def test_message_fetch_watchdog_bounds_a_stalled_telethon_iterator():
    async def run():
        values = []
        with pytest.raises(RuntimeError, match="timed out"):
            async for value in backfill.iter_messages_with_timeout(
                client=_FakeClient(),
                entity="channel",
                until=None,
                timeout_seconds=0.01,
            ):
                values.append(value)
        assert values == [1]

    asyncio.run(run())
