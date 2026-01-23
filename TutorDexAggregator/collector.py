"""
Thin entrypoint wrapper for the Telegram collector.

Implementation lives under `TutorDexAggregator/collection/` to keep the entrypoint stable and the logic modular.
"""

from shared.config import load_aggregator_config, validate_environment_integrity

from collection.cli import main


if __name__ == "__main__":  # pragma: no cover
    validate_environment_integrity(load_aggregator_config())
    main()
