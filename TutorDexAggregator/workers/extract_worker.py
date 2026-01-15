"""
Extraction worker entrypoint for the "raw collector + queue" pipeline.

Keep this file tiny and stable because it is used as the Docker/CLI entrypoint:
`python workers/extract_worker.py`
"""

from __future__ import annotations

import sys
from pathlib import Path


AGG_DIR = Path(__file__).resolve().parents[1]
if str(AGG_DIR) not in sys.path:
    sys.path.insert(0, str(AGG_DIR))


from workers.extract_worker_main import main  # noqa: E402


if __name__ == "__main__":
    main()

