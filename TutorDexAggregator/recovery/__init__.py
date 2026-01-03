"""
Recovery and automation helpers for the TutorDex aggregator.

This package contains logic for automated "gap healing" after outages:
- use the raw message log (`telegram_messages_raw`) as source-of-truth
- backfill historical windows from Telegram when needed
- enqueue extraction work into `telegram_extractions`
"""

