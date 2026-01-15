"""
Thin entrypoint wrapper for DM delivery.

All implementation lives in `dm_assignments_impl.py` to keep this file small.
"""

from dm_assignments_impl import *  # noqa: F403


if __name__ == "__main__":  # pragma: no cover
    main()  # noqa: F405

