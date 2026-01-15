"""
Thin entrypoint wrapper for broadcasting assignments.

Implementation lives under `TutorDexAggregator/delivery/`.
"""

from broadcast_assignments_impl import *  # noqa: F403


if __name__ == "__main__":  # pragma: no cover
    from delivery.send import main as _main

    _main()
