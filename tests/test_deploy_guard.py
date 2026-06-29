from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _fake_path(tmp_path: Path) -> str:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("docker", "curl"):
        exe = bin_dir / name
        exe.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"


def _run(script: str, tmp_path: Path, *args: str, **env_overrides: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(env_overrides)
    env["PATH"] = _fake_path(tmp_path)
    return subprocess.run(
        ["bash", script, *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        timeout=10,
        check=False,
    )


def _run_guard(tmp_path: Path, **env_overrides: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(env_overrides)
    env["PATH"] = _fake_path(tmp_path)
    return subprocess.run(
        ["bash", "-c", "source scripts/ops/_lib.sh; require_actions_deploy_guard deploy"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        timeout=10,
        check=False,
    )


def test_ops_deploy_refuses_manual_deploy_without_override(tmp_path: Path) -> None:
    result = _run("scripts/ops/deploy.sh", tmp_path, "--env", "staging")

    assert result.returncode == 1
    assert "Refusing manual TutorDex deploy" in result.stderr
    assert "Use GitHub Actions deploy paths" in result.stderr


def test_manual_override_requires_reason(tmp_path: Path) -> None:
    result = _run(
        "scripts/ops/deploy.sh",
        tmp_path,
        "--env",
        "staging",
        TD_DEPLOY_OVERRIDE="yes",
    )

    assert result.returncode == 1
    assert "TD_DEPLOY_OVERRIDE_REASON" in result.stderr


def test_override_with_reason_reaches_next_preflight_without_deploying(tmp_path: Path) -> None:
    result = _run_guard(
        tmp_path,
        TD_DEPLOY_OVERRIDE="yes",
        TD_DEPLOY_OVERRIDE_REASON="Nubi approved emergency manual deploy in chat",
    )

    assert result.returncode == 0
    assert "manual TutorDex deploy override accepted" in result.stderr


def test_legacy_staging_deploy_refuses_manual_deploy_without_override(tmp_path: Path) -> None:
    result = _run("scripts/deploy_staging.sh", tmp_path)

    assert result.returncode == 1
    assert "Refusing manual TutorDex legacy staging deploy" in result.stderr
