"""
One-click A/B experiment runner for:
- model comparison (LLM_API_URL / LLM_MODEL_NAME)
- system prompt comparison (LLM_SYSTEM_PROMPT_TEXT / LLM_SYSTEM_PROMPT_FILE)
- examples comparison (LLM_INCLUDE_EXAMPLES + LLM_EXAMPLES_VARIANT / LLM_EXAMPLES_DIR)

Workflow:
1) Enqueue from raw for pipeline A (collector enqueue)
2) Drain queue for pipeline A (worker oneshot; no side effects)
3) Repeat for pipeline B
4) Generate stats + side-by-side CSV

Edit the CONFIG section and run this file in VS Code.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from ab_compare_extractions import CompareConfig, compare_runs, write_reports


# --------------------------------------------------------------------------------------
# CONFIG (edit these)
# --------------------------------------------------------------------------------------

CHANNELS: Optional[str] = None  # defaults to CHANNEL_LIST if None

# If both are None, this script defaults to "last 7 days (UTC)" at runtime.
SINCE_ISO: Optional[str] = None
UNTIL_ISO: Optional[str] = None

PAGE_SIZE: int = 500
MAX_MESSAGES_PER_CHANNEL: Optional[int] = 2000  # set None for unlimited

MAX_JOBS_DRAIN: Optional[int] = None  # optional safety cap per run (e.g. 200)

OUT_DIR: Optional[str] = None  # default: utilities/out/ab_experiment_<ts>/


@dataclass(frozen=True)
class RunConfig:
    name: str
    pipeline_version: str

    llm_api_url: Optional[str] = None
    llm_model_name: Optional[str] = None

    # System prompt overrides (choose at most one style per run)
    system_prompt_file: Optional[str] = None
    system_prompt_text: Optional[str] = None

    # Examples overrides
    include_examples: bool = False
    examples_variant: Optional[str] = None
    examples_dir: Optional[str] = None


RUN_A = RunConfig(
    name="A",
    pipeline_version="ab_promptA_last7d",
    llm_model_name=None,  # default to env/.env if None
    include_examples=True,
)

RUN_B = RunConfig(
    name="B",
    pipeline_version="ab_promptB_last7d",
    llm_model_name=None,
    include_examples=True,
)


def _base_env() -> Dict[str, str]:
    env = dict(os.environ)
    # Ensure we never side-effect during experiments.
    env["EXTRACTION_WORKER_BROADCAST"] = "0"
    env["EXTRACTION_WORKER_DMS"] = "0"
    env["EXTRACTION_WORKER_ONESHOT"] = "1"
    if MAX_JOBS_DRAIN is not None:
        env["EXTRACTION_WORKER_MAX_JOBS"] = str(int(MAX_JOBS_DRAIN))
    return env


def _apply_run_env(env: Dict[str, str], run: RunConfig) -> Dict[str, str]:
    e = dict(env)
    e["EXTRACTION_PIPELINE_VERSION"] = run.pipeline_version

    if run.llm_api_url:
        e["LLM_API_URL"] = run.llm_api_url
    if run.llm_model_name:
        e["LLM_MODEL_NAME"] = run.llm_model_name

    # Clear all system prompt selectors, then apply run choice.
    e.pop("LLM_SYSTEM_PROMPT_FILE", None)
    e.pop("LLM_SYSTEM_PROMPT_TEXT", None)
    if run.system_prompt_file:
        e["LLM_SYSTEM_PROMPT_FILE"] = run.system_prompt_file
    if run.system_prompt_text:
        e["LLM_SYSTEM_PROMPT_TEXT"] = run.system_prompt_text

    # Examples
    e["LLM_INCLUDE_EXAMPLES"] = "1" if run.include_examples else "0"
    if run.examples_variant:
        e["LLM_EXAMPLES_VARIANT"] = run.examples_variant
    else:
        e.pop("LLM_EXAMPLES_VARIANT", None)
    if run.examples_dir:
        e["LLM_EXAMPLES_DIR"] = run.examples_dir
    else:
        e.pop("LLM_EXAMPLES_DIR", None)

    return e


def _run(cmd: list[str], *, cwd: Path, env: Dict[str, str]) -> None:
    print(f"\n$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(cwd), env=env, check=True)


def _collector_enqueue(agg_dir: Path, env: Dict[str, str]) -> None:
    collector_py = agg_dir / "collector.py"
    cmd = [sys.executable, str(collector_py), "enqueue"]
    if CHANNELS:
        cmd.extend(["--channels", CHANNELS])
    if SINCE_ISO:
        cmd.extend(["--since", SINCE_ISO])
    if UNTIL_ISO:
        cmd.extend(["--until", UNTIL_ISO])
    cmd.extend(["--page-size", str(int(PAGE_SIZE))])
    if MAX_MESSAGES_PER_CHANNEL is not None:
        cmd.extend(["--max-messages", str(int(MAX_MESSAGES_PER_CHANNEL))])
    cmd.append("--force")
    _run(cmd, cwd=agg_dir, env=env)


def _drain_worker(agg_dir: Path, env: Dict[str, str]) -> None:
    worker_py = agg_dir / "workers" / "extract_worker.py"
    cmd = [sys.executable, str(worker_py)]
    _run(cmd, cwd=agg_dir, env=env)


def main() -> int:
    agg_dir = Path(__file__).resolve().parents[1]
    out_dir = Path(OUT_DIR) if OUT_DIR else (agg_dir / "utilities" / "out" / f"ab_experiment_{int(time.time())}")

    base_env = _base_env()

    global SINCE_ISO, UNTIL_ISO
    if SINCE_ISO is None and UNTIL_ISO is None:
        now = datetime.now(timezone.utc)
        UNTIL_ISO = now.isoformat()
        SINCE_ISO = (now - timedelta(days=7)).isoformat()

    for run in (RUN_A, RUN_B):
        print(f"\n=== RUN {run.name} ===")
        env = _apply_run_env(base_env, run)
        _collector_enqueue(agg_dir, env)
        _drain_worker(agg_dir, env)

    # Compare & write reports.
    cmp_cfg = CompareConfig(
        pipeline_a=RUN_A.pipeline_version,
        pipeline_b=RUN_B.pipeline_version,
        since_iso=SINCE_ISO,
        until_iso=UNTIL_ISO,
        channels=None,
    )
    res = compare_runs(cmp_cfg)
    paths = write_reports(out_dir, cmp_cfg, res)
    print("\n=== REPORTS ===")
    print(f"- {paths['summary']}")
    print(f"- {paths['csv']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
