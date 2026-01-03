import unittest
from datetime import datetime, timezone


class DummyStore:
    def __init__(self, cursor_by_channel=None):
        self._cursor_by_channel = cursor_by_channel or {}

    def enabled(self):
        return True

    def get_latest_message_cursor(self, *, channel_link: str):
        return self._cursor_by_channel.get(channel_link, (None, None))


class TestRecoveryCatchupState(unittest.TestCase):
    def test_build_initial_state_uses_db_cursor(self):
        from TutorDexAggregator.recovery.catchup import CatchupConfig, build_initial_state

        store = DummyStore(
            cursor_by_channel={
                "t.me/ChanA": ("2025-12-31T00:00:00+00:00", "1"),
                "t.me/ChanB": ("2025-12-31T01:00:00+00:00", "2"),
            }
        )
        cfg = CatchupConfig(
            enabled=True,
            state_path=None,  # not used here
            target_lag_minutes=2,
            overlap_minutes=10,
            chunk_hours=6,
            low_watermark=0,
            check_interval_s=30.0,
            pipeline_version="2026-01-02_det_time_v1",
            recovery_session_name="tutordex_recovery.session",
        )
        st = build_initial_state(channels=["t.me/ChanA", "t.me/ChanB"], store=store, config=cfg)
        self.assertEqual(st["cursors"]["t.me/ChanA"], "2025-12-31T00:00:00+00:00")
        self.assertEqual(st["cursors"]["t.me/ChanB"], "2025-12-31T01:00:00+00:00")

    def test_build_initial_state_has_reasonable_target(self):
        from TutorDexAggregator.recovery.catchup import CatchupConfig, build_initial_state, _parse_iso_dt

        store = DummyStore()
        cfg = CatchupConfig(
            enabled=True,
            state_path=None,
            target_lag_minutes=2,
            overlap_minutes=10,
            chunk_hours=6,
            low_watermark=0,
            check_interval_s=30.0,
            pipeline_version="2026-01-02_det_time_v1",
            recovery_session_name="tutordex_recovery.session",
        )
        st = build_initial_state(channels=["t.me/ChanA"], store=store, config=cfg, default_lookback_hours=1)
        target = _parse_iso_dt(st["target_iso"])
        self.assertIsNotNone(target)
        self.assertLess(target, datetime.now(timezone.utc))


if __name__ == "__main__":
    unittest.main()
