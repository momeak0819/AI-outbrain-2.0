"""Route 1.2 MCP template selection and readiness reporting."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REQUIRED_MCP_CHECKS = (
    "listed_vault",
    "read_template",
    "created_test_note",
    "deleted_test_note",
)
DEFAULT_MCP_TTL_SECONDS = 7 * 24 * 60 * 60
MCP_VERIFICATION_SCHEMA_VERSION = 1


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _expires_at(verified_at: str, ttl_seconds: int) -> str:
    parsed = _parse_timestamp(verified_at)
    if parsed is None:
        return ""
    return (parsed + timedelta(seconds=ttl_seconds)).isoformat()


def _check_detail(name: str, ok: bool) -> dict[str, Any]:
    return {
        "name": name,
        "ok": bool(ok),
        "required": True,
        "error_code": "" if ok else "mcp_required_check_missing",
    }


def build_verification_record(
    *,
    client: str,
    transport: str,
    vault_root: str,
    vault_identity: str,
    checks: dict[str, bool],
    profile: str = "",
    verified_at: str = "",
    ttl_seconds: int = DEFAULT_MCP_TTL_SECONDS,
) -> dict[str, Any]:
    """Build the persisted structured MCP verification report."""
    timestamp = verified_at or utc_timestamp()
    normalized_checks = {
        name: _check_detail(name, bool(checks.get(name)))
        for name in REQUIRED_MCP_CHECKS
    }
    return {
        "schema_version": MCP_VERIFICATION_SCHEMA_VERSION,
        "stage": "knowledge",
        "client": client,
        "profile": profile or client,
        "transport": transport,
        "vault_root": vault_root,
        "vault_identity": vault_identity,
        "checks": normalized_checks,
        "verified_at": timestamp,
        "ttl_seconds": ttl_seconds,
        "expires_at": _expires_at(timestamp, ttl_seconds),
    }


def verification_record_from_json(value: str) -> dict[str, Any]:
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def validation_failure(
    error_code: str,
    error: str,
    *,
    recoverable: bool = True,
) -> dict[str, Any]:
    return {
        "stage": "knowledge",
        "error_code": error_code,
        "error": error,
        "recoverable": recoverable,
    }


def validate_vault_structure(vault_dir: Path, required_paths: list[str]) -> dict[str, Any]:
    checks = []
    missing = []
    missing_directories = []
    missing_templates = []
    missing_indexes = []
    for rel in required_paths:
        path = vault_dir / Path(rel)
        exists = path.exists()
        normalized = rel.replace("\\", "/")
        if normalized.endswith(".md"):
            kind = (
                "index"
                if "索引" in normalized or normalized.endswith("/index.md")
                else "template"
            )
        else:
            kind = "directory"
        item = {"path": rel, "kind": kind, "exists": exists}
        if not exists:
            item["error_code"] = f"vault_{kind}_missing"
            missing.append(rel)
            if kind == "directory":
                missing_directories.append(rel)
            elif kind == "index":
                missing_indexes.append(rel)
            else:
                missing_templates.append(rel)
        checks.append(item)

    valid = vault_dir.exists() and not missing
    error_code = ""
    error = ""
    if not vault_dir.exists():
        error_code = "vault_root_missing"
        error = "Obsidian vault root does not exist."
    elif missing:
        error_code = "vault_structure_invalid"
        error = "Required Vault paths are missing."

    return {
        "valid": valid,
        "vault_root": str(vault_dir),
        "vault_identity": vault_dir.name,
        "checks": checks,
        "missing_required_paths": missing,
        "missing_directories": missing_directories,
        "missing_templates": missing_templates,
        "missing_indexes": missing_indexes,
        "error_code": error_code,
        "error": error,
        "recoverable": True,
    }


def evaluate_mcp_readiness(
    *,
    persisted_mcp: dict[str, Any],
    vault_root: str,
    vault_identity: str,
    current_client: str = "",
    current_profile: str = "",
    current_transport: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return the single structured Route 1.2 MCP readiness result."""
    record = dict(persisted_mcp.get("verification_report") or {})
    ttl_seconds = int(record.get("ttl_seconds") or DEFAULT_MCP_TTL_SECONDS)
    verified_at = str(record.get("verified_at") or persisted_mcp.get("verified_at") or "")
    expires_at = str(record.get("expires_at") or _expires_at(verified_at, ttl_seconds))
    checks_payload = record.get("checks") if isinstance(record.get("checks"), dict) else {}
    checks = {
        name: (
            checks_payload.get(name)
            if isinstance(checks_payload.get(name), dict)
            else _check_detail(name, bool(checks_payload.get(name)))
        )
        for name in REQUIRED_MCP_CHECKS
    }

    client = str(record.get("client") or persisted_mcp.get("client") or "")
    profile = str(record.get("profile") or client)
    transport = str(record.get("transport") or persisted_mcp.get("transport") or "")
    readiness = {
        "ready": False,
        "stage": "knowledge",
        "checks": checks,
        "client": client,
        "profile": profile,
        "transport": transport,
        "vault_root": str(record.get("vault_root") or vault_root),
        "vault_identity": str(record.get("vault_identity") or vault_identity),
        "verified_at": verified_at,
        "expires_at": expires_at,
        "ttl_seconds": ttl_seconds,
        "error_code": "",
        "error": "",
        "recoverable": True,
    }

    if persisted_mcp.get("mcp_setup_status") != "configured":
        readiness.update(
            validation_failure(
                "mcp_unavailable",
                "MCP setup is not configured for this agent.",
            )
        )
        return readiness
    if not record:
        readiness.update(
            validation_failure(
                "mcp_verification_missing",
                "Structured MCP verification report is missing.",
            )
        )
        return readiness
    missing_checks = [
        name for name, item in checks.items()
        if not isinstance(item, dict) or not item.get("ok")
    ]
    if missing_checks:
        readiness.update(
            validation_failure(
                "mcp_verification_failed",
                "Required MCP verification checks are incomplete.",
            )
        )
        readiness["missing_checks"] = missing_checks
        return readiness
    if current_client and client != current_client:
        readiness.update(
            validation_failure("mcp_client_mismatch", "MCP verification client does not match the current client.")
        )
        return readiness
    if current_profile and profile != current_profile:
        readiness.update(
            validation_failure("mcp_profile_mismatch", "MCP verification profile does not match the current profile.")
        )
        return readiness
    if current_transport and transport != current_transport:
        readiness.update(
            validation_failure("mcp_transport_mismatch", "MCP verification transport does not match the current transport.")
        )
        return readiness
    if readiness["vault_root"] != vault_root or readiness["vault_identity"] != vault_identity:
        readiness.update(
            validation_failure("mcp_vault_mismatch", "MCP verification vault does not match the current Route 1.2 vault.")
        )
        return readiness
    parsed_verified_at = _parse_timestamp(verified_at)
    if parsed_verified_at is None:
        readiness.update(
            validation_failure("mcp_verification_expired", "MCP verification timestamp is missing or invalid.")
        )
        return readiness
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if parsed_verified_at + timedelta(seconds=ttl_seconds) < current_time:
        readiness.update(
            validation_failure("mcp_verification_expired", "MCP verification has expired.")
        )
        return readiness

    readiness["ready"] = True
    readiness["error_code"] = ""
    readiness["error"] = ""
    readiness["recoverable"] = False
    return readiness


def validate_mcp_finalization_report(
    report: dict[str, Any] | None,
    final_card_path: str,
    final_index_path: str,
) -> dict[str, Any]:
    """Validate that fake/real MCP write report confirms both final writes."""
    payload = dict(report or {})
    card_path = str(payload.get("card_path") or payload.get("final_card_path") or "")
    index_path = str(payload.get("index_path") or payload.get("final_index_path") or "")
    card_written = bool(payload.get("card_written") or payload.get("card_path_written"))
    index_updated = bool(payload.get("index_updated") or payload.get("index_path_updated"))
    if card_path != final_card_path or index_path != final_index_path:
        return validation_failure(
            "mcp_finalization_incomplete",
            "MCP finalization report paths do not match the requested final paths.",
        )
    if not card_written or not index_updated:
        return validation_failure(
            "vault_write_not_confirmed",
            "MCP finalization report does not confirm both card write and index update.",
        )
    return {"success": True}


def build_template_report(
    project_root: Path,
    templates: list[dict[str, Any]],
    setup_doc: Path,
    templates_dir: Path,
) -> dict[str, Any]:
    items = []
    for template in templates:
        item = dict(template)
        full_path = project_root / template["path"]
        item["full_path"] = str(full_path)
        item["exists"] = full_path.exists()
        items.append(item)
    return {
        "success": True,
        "mode": "route12-mcp-templates",
        "recommended_agent": "QoderWork CN",
        "setup_doc": str(setup_doc),
        "templates_dir": str(templates_dir),
        "templates": items,
        "auto_registration_guaranteed": False,
        "notes": [
            "Choose the template matching the current AI coding agent.",
            "QoderWork CN HTTP is the recommended default.",
            "Store real credentials in the agent or MCP client's secure configuration.",
        ],
    }


def select_templates(report: dict[str, Any], client: str, transport: str = "") -> list[dict[str, Any]]:
    normalized_client = (client or "").strip().lower()
    selected = []
    for template in report["templates"]:
        client_match = not normalized_client or any(
            normalized_client in item.lower() or item.lower() in normalized_client
            for item in template["clients"]
        )
        transport_match = not transport or template["transport"] == transport
        if client_match and transport_match:
            selected.append(template)
    if not selected:
        selected = [
            item for item in report["templates"]
            if item["id"].startswith("generic-") and (not transport or item["transport"] == transport)
        ]
    return selected


def detect_agent_client() -> str:
    explicit = os.environ.get("AI_AGENT_CLIENT", "").strip()
    if explicit:
        return explicit
    if os.environ.get("CODEX_HOME"):
        return "Codex"
    if os.environ.get("CLAUDE_CODE"):
        return "Claude Code"
    return "Generic MCP client"


def read_enabled_obsidian_plugins(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return sorted(str(item) for item in payload) if isinstance(payload, list) else []


def build_route_report(
    vault_dir: Path,
    review_dir: Path,
    required_paths: list[str],
    plugin_ids: list[str],
    setup_doc: Path,
    template_report: dict[str, Any],
    persisted_mcp: dict[str, Any],
    current_client: str = "",
    current_profile: str = "",
    current_transport: str = "",
) -> dict[str, Any]:
    obsidian_dir = vault_dir / ".obsidian"
    plugins_dir = obsidian_dir / "plugins"
    installed = sorted(path.name for path in plugins_dir.iterdir() if path.is_dir()) if plugins_dir.exists() else []
    enabled = read_enabled_obsidian_plugins(obsidian_dir / "community-plugins.json")
    claudian_present = "realclaudian" in installed or "realclaudian" in enabled
    bridge_plugins = sorted(item for item in plugin_ids if item in installed or item in enabled)
    paths = [{"path": rel, "exists": (vault_dir / Path(rel)).exists()} for rel in required_paths]
    missing = [item["path"] for item in paths if not item["exists"]]
    bridge_detected = bool(bridge_plugins)
    templates = template_report["templates"]
    qoderwork = [item for item in templates if "QoderWork CN" in item["clients"]]
    vault_validation = validate_vault_structure(vault_dir, required_paths)
    readiness = evaluate_mcp_readiness(
        persisted_mcp=persisted_mcp,
        vault_root=str(vault_dir),
        vault_identity=vault_dir.name,
        current_client=current_client or str(persisted_mcp.get("client") or ""),
        current_profile=current_profile or str(persisted_mcp.get("profile") or persisted_mcp.get("client") or ""),
        current_transport=current_transport or str(persisted_mcp.get("transport") or ""),
    )

    if not vault_dir.exists():
        next_step = "Create or restore the Obsidian vault before testing Route 1.2."
    elif missing:
        next_step = "Restore missing vault folders or template files before MCP curation."
    elif not bridge_detected:
        next_step = "Read docs/mcp-setup.md, then use a matching template under mcp/."
    elif not readiness["ready"]:
        next_step = "Connect the AI coding agent and complete real MCP verification."
    else:
        next_step = "Route 1.2 MCP verification is complete."

    return {
        "success": True,
        "mode": "route12-check",
        "route": "AI外脑1.2 Agent direct Obsidian MCP",
        "vault_path": str(vault_dir),
        "vault_exists": vault_dir.exists(),
        "review_dir": str(review_dir),
        "required_paths": paths,
        "missing_required_paths": missing,
        "obsidian_plugins_dir": str(plugins_dir),
        "installed_plugin_dirs": installed,
        "enabled_plugins": enabled,
        "claudian_present": claudian_present,
        "claudian_used_in_route12": False,
        "mcp_bridge_detected": bridge_detected,
        "obsidian_bridge_plugin_detected": bridge_detected,
        "mcp_bridge_plugins": bridge_plugins,
        "agent_mcp_verified": readiness["ready"],
        "mcp_setup_status": persisted_mcp["mcp_setup_status"],
        "mcp_client": persisted_mcp["client"],
        "mcp_transport": persisted_mcp["transport"],
        "mcp_verified_at": readiness["verified_at"],
        "mcp_setup_doc": str(setup_doc),
        "mcp_templates": templates,
        "recommended_agent": "QoderWork CN",
        "qoderwork_templates": qoderwork,
        "can_transcribe_without_mcp": True,
        "can_finalize_without_mcp": False,
        "mcp_ready": readiness["ready"],
        "readiness": readiness,
        "vault_validation": vault_validation,
        "curation_ready": readiness["ready"] and vault_validation["valid"],
        "recommended_next_step": next_step,
    }
