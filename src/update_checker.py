"""Safe source update checks for local source deployments.

The updater is intentionally conservative:

* It only works inside a Git checkout with an ``origin`` remote.
* It fetches the current branch and compares ``HEAD`` with ``origin/<branch>``.
* It only pulls when tracked files are clean, using ``git pull --ff-only``.
* It never prints credentials embedded in a remote URL.

This keeps released source packages easy to update while avoiding accidental
overwrites of user-local changes.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


DISABLE_ENV = "AI_OUTBRAIN_DISABLE_UPDATE_CHECK"


def check_and_update(
    project_root: str | Path,
    *,
    auto_pull: bool = True,
    timeout_seconds: int = 8,
) -> dict[str, Any]:
    """Check the current Git checkout for updates and optionally pull them.

    The function is safe to call during startup. Missing Git, missing remotes,
    detached HEAD, network failures, and dirty worktrees are returned as
    structured JSON-like payloads instead of raising.
    """

    root = Path(project_root)
    payload: dict[str, Any] = {
        "success": True,
        "mode": "source-update-check",
        "enabled": os.environ.get(DISABLE_ENV, "").strip().lower()
        not in {"1", "true", "yes", "on"},
        "git_repo": False,
        "remote": "",
        "branch": "",
        "remote_ref": "",
        "update_available": False,
        "behind_count": 0,
        "auto_pull": auto_pull,
        "pulled": False,
        "restart_required": False,
        "skipped_reason": "",
        "error_code": "",
        "error": "",
        "recoverable": True,
    }

    if not payload["enabled"]:
        payload["skipped_reason"] = f"disabled_by_{DISABLE_ENV}"
        return payload

    if not root.exists():
        payload.update(
            success=False,
            error_code="project_root_missing",
            error="Project root does not exist.",
        )
        return payload

    repo_check = _git(root, ["rev-parse", "--is-inside-work-tree"], timeout_seconds)
    if repo_check.returncode != 0 or repo_check.stdout.strip().lower() != "true":
        payload["skipped_reason"] = "not_a_git_repository"
        return payload
    payload["git_repo"] = True

    remote = _git(root, ["remote", "get-url", "origin"], timeout_seconds)
    if remote.returncode != 0 or not remote.stdout.strip():
        payload["skipped_reason"] = "origin_remote_missing"
        return payload
    payload["remote"] = _sanitize_remote(remote.stdout.strip())

    branch = _git(root, ["branch", "--show-current"], timeout_seconds)
    if branch.returncode != 0 or not branch.stdout.strip():
        payload["skipped_reason"] = "detached_head_or_branch_missing"
        return payload
    branch_name = branch.stdout.strip()
    payload["branch"] = branch_name
    payload["remote_ref"] = f"origin/{branch_name}"

    fetch = _git(root, ["fetch", "origin", branch_name, "--quiet"], timeout_seconds)
    if fetch.returncode != 0:
        payload.update(
            success=False,
            error_code="update_fetch_failed",
            error=_safe_stderr(fetch),
        )
        return payload

    behind = _git(
        root,
        ["rev-list", "--count", f"HEAD..origin/{branch_name}"],
        timeout_seconds,
    )
    if behind.returncode != 0:
        payload.update(
            success=False,
            error_code="update_compare_failed",
            error=_safe_stderr(behind),
        )
        return payload

    try:
        behind_count = int(behind.stdout.strip() or "0")
    except ValueError:
        behind_count = 0
    payload["behind_count"] = behind_count
    payload["update_available"] = behind_count > 0

    if behind_count <= 0:
        return payload
    if not auto_pull:
        payload["skipped_reason"] = "auto_pull_disabled"
        return payload

    dirty = _git(root, ["status", "--porcelain", "--untracked-files=no"], timeout_seconds)
    if dirty.returncode != 0:
        payload.update(
            success=False,
            error_code="worktree_status_failed",
            error=_safe_stderr(dirty),
        )
        return payload
    if dirty.stdout.strip():
        payload["skipped_reason"] = "tracked_worktree_dirty"
        payload["recoverable"] = True
        return payload

    pull = _git(root, ["pull", "--ff-only", "origin", branch_name], timeout_seconds)
    if pull.returncode != 0:
        payload.update(
            success=False,
            error_code="update_pull_failed",
            error=_safe_stderr(pull),
        )
        return payload

    payload["pulled"] = True
    payload["restart_required"] = True
    return payload


def _git(root: Path, args: list[str], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(["git", *args], 127, "", "git executable not found")
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            ["git", *args],
            124,
            "",
            f"git command timed out after {timeout_seconds}s",
        )


def _safe_stderr(result: subprocess.CompletedProcess[str]) -> str:
    text = (result.stderr or result.stdout or "").strip()
    return _sanitize_remote(text)[:500]


def _sanitize_remote(text: str) -> str:
    """Redact credentials embedded in URLs while preserving useful context."""

    try:
        parsed = urlsplit(text)
    except ValueError:
        parsed = None
    if parsed and parsed.scheme and parsed.netloc and "@" in parsed.netloc:
        host = parsed.netloc.rsplit("@", 1)[1]
        return urlunsplit((parsed.scheme, f"***@{host}", parsed.path, parsed.query, parsed.fragment))
    return re.sub(r"([a-zA-Z][a-zA-Z0-9+.-]*://)([^/\s@]+)@([^\s/]+)", r"\1***@\3", text)
