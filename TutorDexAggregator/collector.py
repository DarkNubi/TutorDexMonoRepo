"""
Thin entrypoint wrapper for the Telegram collector.

Implementation lives under `TutorDexAggregator/collection/` to keep the entrypoint stable and the logic modular.
"""

from collection.cli import main


if __name__ == "__main__":  # pragma: no cover
    main()

