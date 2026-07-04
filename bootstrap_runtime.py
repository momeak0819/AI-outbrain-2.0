"""Project-local virtual environment bootstrap shared by CLI entry points."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


BOOTSTRAP_ENV = "AI_OUTBRAIN_VENV_BOOTSTRAPPED"
DISABLE_ENV = "AI_OUTBRAIN_DISABLE_VENV_BOOTSTRAP"
VENV_DIRNAME = ".venv"


def project_root() -> Path:
    return Path(__file__).resolve().parent


def venv_python(root: Path | None = None) -> Path:
    base = root or project_root()
    if os.name == "nt":
        return base / VENV_DIRNAME / "Scripts" / "python.exe"
    return base / VENV_DIRNAME / "bin" / "python"


def is_running_in_project_venv(root: Path | None = None) -> bool:
    expected = venv_python(root)
    try:
        return Path(sys.executable).resolve() == expected.resolve()
    except OSError:
        return False


def bootstrap_disabled() -> bool:
    value = os.environ.get(DISABLE_ENV, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def ensure_project_venv(argv: list[str] | None = None) -> None:
    """Create the project venv, install core dependencies, and re-exec once."""
    if getattr(sys, "frozen", False) or bootstrap_disabled() or is_running_in_project_venv():
        return

    if os.environ.get(BOOTSTRAP_ENV) == "1":
        raise RuntimeError(
            "Project virtual-environment bootstrap restarted once but is still "
            "running outside .venv. Refusing to install into the system Python."
        )

    root = project_root()
    python_path = venv_python(root)
    if not _python_executable_ready(python_path):
        result = subprocess.run(
            [sys.executable, "-m", "venv", "--clear", str(root / VENV_DIRNAME)],
            cwd=root,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"Failed to create project .venv: {detail}")

    requirements = root / "requirements.txt"
    if requirements.exists() and not _core_dependencies_ready(python_path):
        result = subprocess.run(
            [
                str(python_path),
                "-m",
                "pip",
                "install",
                "-r",
                str(requirements),
            ],
            cwd=root,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"Failed to install core dependencies into .venv: {detail}")

    env = os.environ.copy()
    env[BOOTSTRAP_ENV] = "1"
    command = [str(python_path), *(argv if argv is not None else sys.argv)]
    completed = subprocess.run(command, cwd=root, env=env)
    raise SystemExit(completed.returncode)


def runtime_environment() -> dict[str, object]:
    root = project_root()
    expected = venv_python(root)
    return {
        "executable": sys.executable,
        "prefix": sys.prefix,
        "base_prefix": getattr(sys, "base_prefix", sys.prefix),
        "in_virtualenv": sys.prefix != getattr(sys, "base_prefix", sys.prefix),
        "in_project_venv": is_running_in_project_venv(root),
        "project_venv": str(expected),
        "project_venv_exists": expected.exists(),
        "project_venv_healthy": _python_executable_ready(expected),
        "bootstrap_disabled": bootstrap_disabled(),
    }


def _core_dependencies_ready(python_path: Path) -> bool:
    try:
        result = subprocess.run(
            [str(python_path), "-c", "import requests"],
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        return result.returncode == 0
    except OSError:
        return False


def _python_executable_ready(python_path: Path) -> bool:
    if not python_path.exists():
        return False
    try:
        result = subprocess.run(
            [str(python_path), "-c", "import sys; print(sys.executable)"],
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
