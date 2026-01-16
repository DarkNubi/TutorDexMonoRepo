"""
Thin entrypoint wrapper for DM delivery.

All implementation lives in `dm_assignments_impl.py` to keep this file small.
"""

from dm_assignments_impl import *  # noqa: F403
from dm_assignments_impl import _get_or_geocode_assignment_coords  # noqa: F401


if __name__ == "__main__":  # pragma: no cover
    main()  # noqa: F405
