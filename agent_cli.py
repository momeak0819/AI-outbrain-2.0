"""Agent-friendly CLI for douyin-to-text.

This entry point exposes the GUI/portable capabilities as JSON commands that
coding agents can call from natural-language workflows.
"""

from __future__ import annotations

import argparse
import configparser
import getpass
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

from bootstrap_runtime import ensure_project_venv, runtime_environment


ensure_project_venv()


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


PROJECT_ROOT = app_root()
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from batch_pipeline import extract_urls  # noqa: E402
from pipeline import (  # noqa: E402
    ENGINE_CHOICES,
    EXPORT_CHOICES,
    PipelineOptions,
    PipelineResult,
    load_config,
)
from runtime_paths import default_audio_dir, portable_model_path, resolve_ffmpeg_path  # noqa: E402
from agent import reviews as review_service  # noqa: E402
from agent import route12 as route12_service  # noqa: E402
from layers.delivery import (  # noqa: E402
    attach_layered_response,
    build_batch_envelope,
    build_original_reply_text,
    format_knowledge_reply,
)
from layers.knowledge import create_knowledge_result  # noqa: E402
from layers.models import KnowledgeContext, ProcessingResult  # noqa: E402
from layers.project_memory import (  # noqa: E402
    ProjectMemoryContext,
    create_project_memory_draft,
    load_payload_file as load_project_memory_payload_file,
    match_idea_to_projects,
    payload_from_summary_file,
    project_memory_status,
    search_project_memory,
)
from layers.sources import DEFAULT_SOURCE_REGISTRY, SourceInput  # noqa: E402
from layers.workflow import execute_source_pipeline, ingest as run_layered_ingest  # noqa: E402
from update_checker import check_and_update  # noqa: E402
from web_console.server import DEFAULT_HOST as CONSOLE_DEFAULT_HOST  # noqa: E402
from web_console.server import DEFAULT_PORT as CONSOLE_DEFAULT_PORT  # noqa: E402
from web_console.server import console_payload, run_console  # noqa: E402


MODEL_CHOICES = ["base", "small", "medium"]
INIT_ENGINE_CHOICES = [
    "faster_whisper",
    "mimo",
    "aliyun_qwen_asr",
    "tencent_asr",
    "volcengine_asr",
]
RESPONSE_MODE_CHOICES = ["desktop", "im"]
CONTENT_MODE_CHOICES = ["original", "card", "both"]
INTERACTION_CHANNEL_CHOICES = ["auto", "im", "terminal"]
REVIEW_STATUSES = ["pending", "revised", "approved", "cancelled", "failed"]
WORKFLOW_REVIEW_STATUSES = [
    "pending_draft",
    "awaiting_approval",
    "revision_requested",
    "approved",
    "finalized",
    "cancelled",
    "failed",
]
MCP_SETUP_STATUSES = ["configured", "skipped", "failed", "pending"]
MCP_TRANSPORT_CHOICES = ["streamable-http", "stdio", "manual"]
REQUIRED_MODEL_FILES = ["config.json", "model.bin", "tokenizer.json", "vocabulary.txt"]
CONFIG_PATH = PROJECT_ROOT / "config.ini"
REVIEW_DIR = PROJECT_ROOT / ".workflow" / "reviews"
DEFAULT_MIMO_API_URL = "https://api.xiaomimimo.com/v1/chat/completions"
DEFAULT_HF_ENDPOINT = "https://hf-mirror.com"
PYPI_MIRROR_URL = "https://pypi.tuna.tsinghua.edu.cn/simple"
ROUTE12_VAULT_DIR = PROJECT_ROOT / "Obsidian" / "AI外脑知识库"
ROUTE12_REVIEW_DIR = ROUTE12_VAULT_DIR / "00_Inbox" / "_待审核"
ROUTE12_REQUIRED_PATHS = [
    "00_Inbox",
    "00_Inbox/抖音链接",
    "00_Inbox/_待审核",
    "01_AI术语库",
    "02_模型能力库",
    "03_AI工具库",
    "04_工作流库",
    "05_智能体库",
    "06_案例库",
    "07_GitHub库",
    "08_项目映射库",
    "09_输出库",
    "_知识卡片模板.md",
]
ROUTE12_MCP_PLUGIN_IDS = ["cli-rest-mcp", "obsidian-local-rest-api"]
ROUTE12_MCP_DIR = PROJECT_ROOT / "mcp"
ROUTE12_MCP_SETUP_DOC = PROJECT_ROOT / "docs" / "mcp-setup.md"
ROUTE12_MCP_TEMPLATES = [
    {
        "id": "qoderwork-cn-http",
        "path": "mcp/qoderwork-cn-http-obsidian.example.json",
        "clients": ["QoderWork CN"],
        "transport": "streamable-http",
        "requires_credentials": True,
        "recommended_default": True,
    },
    {
        "id": "qoderwork-cn-stdio",
        "path": "mcp/qoderwork-cn-stdio-obsidian.example.json",
        "clients": ["QoderWork CN"],
        "transport": "stdio",
        "requires_credentials": True,
        "recommended_default": False,
    },
    {
        "id": "claude-code",
        "path": "mcp/claude-code.mcp.example.json",
        "clients": ["Claude Code"],
        "transport": "stdio",
        "requires_credentials": True,
        "recommended_default": False,
    },
    {
        "id": "vscode",
        "path": "mcp/vscode.mcp.example.json",
        "clients": ["VS Code", "GitHub Copilot"],
        "transport": "stdio",
        "requires_credentials": True,
        "recommended_default": False,
    },
    {
        "id": "trae",
        "path": "mcp/trae-mcp.example.md",
        "clients": ["Trae"],
        "transport": "manual",
        "requires_credentials": True,
        "recommended_default": False,
    },
    {
        "id": "generic-http",
        "path": "mcp/generic-http-obsidian-mcp.example.json",
        "clients": ["Any HTTP MCP client"],
        "transport": "streamable-http",
        "requires_credentials": True,
        "recommended_default": False,
    },
    {
        "id": "generic-stdio",
        "path": "mcp/generic-stdio-obsidian-mcp.example.json",
        "clients": ["Any STDIO MCP client"],
        "transport": "stdio",
        "requires_credentials": True,
        "recommended_default": False,
    },
]
DEFAULT_TRANSCRIPT_OUTPUT_DIR = r"Obsidian\AI外脑知识库\00_Inbox\抖音链接"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent_cli.py",
        description="JSON CLI for agent-driven Douyin transcription workflows.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Open the local Web Console for first-run setup.")
    init_parser.add_argument("--force", action="store_true", help="Overwrite an existing config.ini after confirmation.")

    console_parser = subparsers.add_parser("console", help="Start the local Web Console.")
    console_parser.add_argument("--host", default=CONSOLE_DEFAULT_HOST, help="Local bind host. Only 127.0.0.1/localhost is supported.")
    console_parser.add_argument("--port", type=int, default=CONSOLE_DEFAULT_PORT, help="Preferred local port.")
    console_parser.add_argument("--no-browser", action="store_true", help="Start without opening a browser window.")
    add_json_args(console_parser)

    update_parser = subparsers.add_parser("update-check", help="Check GitHub/source updates and pull when safe.")
    update_parser.add_argument("--no-pull", action="store_true", help="Only check; do not pull updates.")
    add_json_args(update_parser)

    init_config_parser = subparsers.add_parser("init-config", help="Internal Web Console setup handler.")
    init_config_parser.add_argument("--force", action="store_true", help="Overwrite existing config.ini.")
    init_config_parser.add_argument("--engine", choices=INIT_ENGINE_CHOICES, required=True, help="ASR engine to configure.")
    init_config_parser.add_argument("--model-size", choices=MODEL_CHOICES, default="base", help="Local faster-whisper model size.")
    init_config_parser.add_argument("--mimo-key", default="", help="MiMo API key when --engine mimo is used.")
    init_config_parser.add_argument("--mimo-url", default=DEFAULT_MIMO_API_URL, help="MiMo API URL.")
    init_config_parser.add_argument("--aliyun-qwen-asr-api-key", default="", help="Aliyun Qwen-ASR API key.")
    init_config_parser.add_argument("--aliyun-qwen-asr-base-url", default="", help="Aliyun Qwen-ASR API base URL.")
    init_config_parser.add_argument("--aliyun-qwen-asr-model", default="qwen-audio-asr", help="Aliyun Qwen-ASR model name.")
    init_config_parser.add_argument("--tencent-asr-secret-id", default="", help="Tencent Cloud ASR SecretId.")
    init_config_parser.add_argument("--tencent-asr-secret-key", default="", help="Tencent Cloud ASR SecretKey.")
    init_config_parser.add_argument("--tencent-asr-region", default="ap-guangzhou", help="Tencent Cloud ASR region.")
    init_config_parser.add_argument("--tencent-asr-engine-model-type", default="16k_zh", help="Tencent Cloud ASR engine model type.")
    init_config_parser.add_argument("--volcengine-asr-app-id", default="", help="Volcengine ASR App ID.")
    init_config_parser.add_argument("--volcengine-asr-access-token", default="", help="Volcengine ASR access token.")
    init_config_parser.add_argument("--volcengine-asr-cluster", default="", help="Volcengine ASR cluster.")
    init_config_parser.add_argument("--volcengine-asr-audio-url", default="", help="Volcengine public audio URL for URL-based recognition.")
    init_config_parser.add_argument("--output-dir", default=DEFAULT_TRANSCRIPT_OUTPUT_DIR, help="Transcript output directory.")
    init_config_parser.add_argument("--audio-output-dir", default="", help="Extracted audio directory. Defaults to <output-dir>/audio.")
    init_config_parser.add_argument("--export", choices=EXPORT_CHOICES, default="md", help="Default export format.")
    init_config_parser.add_argument("--reply-mode", choices=RESPONSE_MODE_CHOICES, default="im", help="Default agent reply mode.")
    init_config_parser.add_argument("--im-content-mode", choices=CONTENT_MODE_CHOICES, default="both", help="Content returned to interactive channels.")
    init_config_parser.add_argument("--interaction-channel", choices=INTERACTION_CHANNEL_CHOICES, default="auto", help="Review interaction channel.")
    init_config_parser.add_argument("--skip-local-setup", action="store_true", help=argparse.SUPPRESS)
    mcp_init_group = init_config_parser.add_mutually_exclusive_group()
    mcp_init_group.add_argument("--configure-mcp", action="store_true", help="Mark MCP setup pending and continue with guided setup.")
    mcp_init_group.add_argument("--skip-mcp", action="store_true", help="Skip MCP setup and force original content mode.")
    keep_audio_group = init_config_parser.add_mutually_exclusive_group()
    keep_audio_group.add_argument("--keep-audio", dest="keep_audio", action="store_true", default=False, help="Keep extracted audio.")
    keep_audio_group.add_argument("--no-keep-audio", dest="keep_audio", action="store_false", help="Delete extracted audio after transcription.")
    add_json_args(init_config_parser)

    env_parser = subparsers.add_parser("check-env", help="Check local transcription environment.")
    add_common_runtime_args(env_parser)
    env_parser.add_argument("--model-size", choices=MODEL_CHOICES, default="", help="Local model to check.")

    models_parser = subparsers.add_parser("models", help="List local faster-whisper model status.")
    add_json_args(models_parser)

    route12_parser = subparsers.add_parser("route12-check", help="Check Route 1.2 Obsidian MCP/vault readiness.")
    add_json_args(route12_parser)

    route12_templates_parser = subparsers.add_parser("route12-mcp-templates", help="List Route 1.2 MCP configuration templates.")
    add_json_args(route12_templates_parser)

    mcp_setup_parser = subparsers.add_parser("mcp-setup", help="Start or resume guided Obsidian MCP setup.")
    mcp_setup_parser.add_argument("--client", default="", help="Current AI agent or MCP client name.")
    mcp_setup_parser.add_argument("--transport", choices=MCP_TRANSPORT_CHOICES, default="", help="Preferred MCP transport.")
    mcp_setup_parser.add_argument("--skip", action="store_true", help="Skip MCP setup and force transcript-only mode.")
    add_json_args(mcp_setup_parser)

    mcp_verify_parser = subparsers.add_parser("mcp-verify", help="Record host-agent MCP verification results.")
    mcp_verify_parser.add_argument("--client", required=True, help="AI agent or MCP client that performed verification.")
    mcp_verify_parser.add_argument("--transport", choices=MCP_TRANSPORT_CHOICES, required=True)
    mcp_verify_parser.add_argument("--profile", default="", help="Current MCP client profile name.")
    mcp_verify_parser.add_argument("--vault-root", default="", help="Verified Obsidian vault root identity/path.")
    mcp_verify_parser.add_argument("--vault-identity", default="", help="Verified Obsidian vault identity.")
    mcp_verify_parser.add_argument("--listed-vault", action="store_true")
    mcp_verify_parser.add_argument("--read-template", action="store_true")
    mcp_verify_parser.add_argument("--created-test-note", action="store_true")
    mcp_verify_parser.add_argument("--deleted-test-note", action="store_true")
    mcp_verify_parser.add_argument("--error", default="", help="Non-secret verification failure summary.")
    add_json_args(mcp_verify_parser)

    mcp_status_parser = subparsers.add_parser("mcp-status", help="Show persisted MCP setup and readiness status.")
    add_json_args(mcp_status_parser)

    review_show_parser = subparsers.add_parser("review-show", help="Show one persisted review.")
    review_show_parser.add_argument("--review-id", required=True)
    add_json_args(review_show_parser)

    review_list_parser = subparsers.add_parser("review-list", help="List persisted reviews.")
    add_json_args(review_list_parser)

    review_revise_parser = subparsers.add_parser("review-revise", help="Record revision instructions for a review.")
    review_revise_parser.add_argument("--review-id", required=True)
    review_revise_parser.add_argument("--instruction", required=True)
    add_json_args(review_revise_parser)

    review_approve_parser = subparsers.add_parser("review-approve", help="Approve a review for final MCP filing.")
    review_approve_parser.add_argument("--review-id", required=True)
    add_json_args(review_approve_parser)

    review_cancel_parser = subparsers.add_parser("review-cancel", help="Cancel a review.")
    review_cancel_parser.add_argument("--review-id", required=True)
    add_json_args(review_cancel_parser)

    review_draft_ready_parser = subparsers.add_parser("review-draft-ready", help="Record that an MCP review draft is ready.")
    review_draft_ready_parser.add_argument("--review-id", required=True)
    review_draft_ready_parser.add_argument("--suggested-category", required=True)
    review_draft_ready_parser.add_argument("--target-path", required=True)
    review_draft_ready_parser.add_argument("--index-path", required=True)
    review_draft_ready_parser.add_argument("--draft-path", default="")
    add_json_args(review_draft_ready_parser)

    review_finalized_parser = subparsers.add_parser("review-finalized", help="Record completed MCP filing and index update.")
    review_finalized_parser.add_argument("--review-id", required=True)
    review_finalized_parser.add_argument("--final-card-path", required=True)
    review_finalized_parser.add_argument("--final-index-path", required=True)
    review_finalized_parser.add_argument("--mcp-card-written", action="store_true")
    review_finalized_parser.add_argument("--mcp-index-updated", action="store_true")
    review_finalized_parser.add_argument("--mcp-card-path", default="")
    review_finalized_parser.add_argument("--mcp-index-path", default="")
    add_json_args(review_finalized_parser)

    project_memory_capture_parser = subparsers.add_parser(
        "project-memory-capture",
        help="Create a reviewable project-memory draft for the Obsidian project map.",
    )
    project_memory_capture_parser.add_argument("--payload-file", default="", help="JSON payload file containing structured project memory.")
    project_memory_capture_parser.add_argument("--summary-file", default="", help="Markdown/text summary file to turn into a project memory.")
    project_memory_capture_parser.add_argument("--project", default="", help="Project name when using --summary-file.")
    project_memory_capture_parser.add_argument("--title", default="", help="Project memory title when using --summary-file.")
    project_memory_capture_parser.add_argument("--agent", default="", help="Source AI agent name. Defaults to current OS user.")
    project_memory_capture_parser.add_argument(
        "--session-type",
        choices=["development", "bugfix", "release", "architecture", "research", "handoff"],
        default="development",
    )
    add_json_args(project_memory_capture_parser)

    project_memory_search_parser = subparsers.add_parser(
        "project-memory-search",
        help="Search project memories in the Obsidian project map and review drafts.",
    )
    project_memory_search_parser.add_argument("--query", default="", help="Search query.")
    project_memory_search_parser.add_argument("--project", default="", help="Optional project filter.")
    project_memory_search_parser.add_argument("--tag", default="", help="Optional tag/topic filter.")
    project_memory_search_parser.add_argument("--limit", type=int, default=20)
    add_json_args(project_memory_search_parser)

    project_memory_match_parser = subparsers.add_parser(
        "project-memory-match",
        help="Match a new idea or knowledge point to related projects.",
    )
    project_memory_match_parser.add_argument("--idea", required=True, help="New idea or knowledge point.")
    project_memory_match_parser.add_argument("--limit", type=int, default=5)
    add_json_args(project_memory_match_parser)

    project_memory_status_parser = subparsers.add_parser(
        "project-memory-status",
        help="Check whether Skill + CLI project-memory capture is ready for external AI agents.",
    )
    project_memory_status_parser.add_argument("--agent", default="", help="External working AI agent name.")
    add_json_args(project_memory_status_parser)

    transcribe_parser = subparsers.add_parser("transcribe", help="Transcribe one Douyin link or share text.")
    transcribe_parser.add_argument("--url", help="Douyin URL to transcribe.")
    transcribe_parser.add_argument("--text", help="Share text that may contain a Douyin URL.")
    transcribe_parser.add_argument("--audio-file", help="Use an existing local audio file directly.")
    add_pipeline_args(transcribe_parser)

    ingest_parser = subparsers.add_parser("ingest", help="Ingest one supported content source through the five-layer workflow.")
    ingest_parser.add_argument("input", nargs="?", help="Optional local input path for local_audio ingestion.")
    ingest_parser.add_argument("--source-type", choices=["auto", *DEFAULT_SOURCE_REGISTRY.names()], default="auto")
    ingest_parser.add_argument("--url", help="Source URL. Currently implemented for Douyin.")
    ingest_parser.add_argument("--text", help="Share text containing a supported source URL.")
    ingest_parser.add_argument("--audio-file", help="Existing local audio file for the local_audio source.")
    ingest_parser.add_argument("--mode", choices=["original"], default="", help="Alias for --im-content-mode. Currently only original is supported.")
    add_pipeline_args(ingest_parser)

    batch_parser = subparsers.add_parser("batch", help="Transcribe multiple Douyin links sequentially.")
    batch_parser.add_argument("--text", help="Text containing one or more Douyin URLs.")
    batch_parser.add_argument("--input-file", help="UTF-8 text file containing one or more Douyin URLs.")
    add_pipeline_args(batch_parser)

    return parser


def add_json_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")


def add_common_runtime_args(parser: argparse.ArgumentParser) -> None:
    add_json_args(parser)
    parser.add_argument("--output-dir", default="", help="Transcript output directory.")
    parser.add_argument("--knowledge-dir", help="Alias for output directory when writing to a knowledge base.")
    parser.add_argument("--audio-output-dir", help="Extracted audio directory. Defaults to <output-dir>/audio.")


def add_pipeline_args(parser: argparse.ArgumentParser) -> None:
    add_common_runtime_args(parser)
    parser.add_argument(
        "--engine",
        choices=ENGINE_CHOICES,
        default="",
        help="ASR engine: mock, faster_whisper, mimo, custom_api (placeholder). Defaults to config.ini [asr] engine or faster_whisper.",
    )
    parser.add_argument("--model-size", choices=MODEL_CHOICES, default="", help="faster-whisper model size. Defaults to config.ini or base.")
    parser.add_argument("--device", default="", help="faster-whisper device. Defaults to config.ini or cpu.")
    parser.add_argument("--compute-type", default="", help="faster-whisper compute type. Defaults to config.ini or int8.")
    parser.add_argument("--language", default="", help="ASR language. Defaults to config.ini or zh. Use empty string in config for auto-detect.")
    parser.add_argument("--hf-endpoint", help="Hugging Face endpoint for model downloads.")
    parser.add_argument("--export", choices=EXPORT_CHOICES, default="", help="Export format. Leave empty to use config.ini [preferences] export_format.")
    keep_audio_group = parser.add_mutually_exclusive_group()
    keep_audio_group.add_argument("--keep-audio", dest="keep_audio", action="store_true", default=None, help="Keep extracted audio.")
    keep_audio_group.add_argument("--no-keep-audio", dest="keep_audio", action="store_false", help="Delete extracted audio after transcription.")
    parser.add_argument("--skip-audio", action="store_true", help="Skip audio extraction for mock tests.")
    parser.add_argument("--mock-metadata", action="store_true", help="Use mock metadata for tests.")
    parser.add_argument("--no-simplified", action="store_true", help="Disable Simplified Chinese normalization.")
    parser.add_argument("--include-transcript", action="store_true", help="Include full transcript text in JSON output.")
    parser.add_argument("--response-mode", choices=RESPONSE_MODE_CHOICES, default="", help="Reply mode for agent output. Use im to include transcript text.")
    parser.add_argument("--im-content-mode", choices=CONTENT_MODE_CHOICES, default="", help="Override original/card/both content routing.")
    parser.add_argument("--interaction-channel", choices=INTERACTION_CHANNEL_CHOICES, default="", help="Override auto/im/terminal interaction routing.")
    parser.add_argument("--mimo-key", help="MiMo API key. Prefer MIMO_API_KEY in normal use.")
    parser.add_argument("--mimo-url", help="MiMo API URL.")
    parser.add_argument("--custom-api-key", help="Custom ASR API key. Prefer CUSTOM_ASR_API_KEY in normal use.")
    parser.add_argument("--custom-api-url", help="Custom ASR API URL.")


def main() -> int:
    args = build_parser().parse_args()

    try:
        if args.command == "init":
            return handle_console(
                argparse.Namespace(
                    host=CONSOLE_DEFAULT_HOST,
                    port=CONSOLE_DEFAULT_PORT,
                    no_browser=False,
                    pretty=False,
                )
            )
        if args.command == "console":
            return handle_console(args)
        if args.command == "update-check":
            return emit_json(check_and_update(PROJECT_ROOT, auto_pull=not args.no_pull), args.pretty)
        if args.command == "init-config":
            return emit_json(handle_init_config(args), args.pretty)

        init_payload = ensure_initialized(args.command)
        if init_payload is not None:
            return emit_json(init_payload, getattr(args, "pretty", False))

        if args.command == "check-env":
            return emit_json(build_env_report(args), args.pretty)
        if args.command == "models":
            return emit_json(build_models_report(), args.pretty)
        if args.command == "route12-check":
            return emit_json(build_route12_report(), args.pretty)
        if args.command == "route12-mcp-templates":
            return emit_json(build_route12_template_report(), args.pretty)
        if args.command == "mcp-setup":
            return emit_json(handle_mcp_setup(args), args.pretty)
        if args.command == "mcp-verify":
            return emit_json(handle_mcp_verify(args), args.pretty)
        if args.command == "mcp-status":
            return emit_json(build_mcp_status(), args.pretty)
        if args.command == "review-show":
            return emit_json(handle_review_show(args.review_id), args.pretty)
        if args.command == "review-list":
            return emit_json(handle_review_list(), args.pretty)
        if args.command == "review-revise":
            return emit_json(handle_review_revise(args.review_id, args.instruction), args.pretty)
        if args.command == "review-approve":
            return emit_json(handle_review_approve(args.review_id), args.pretty)
        if args.command == "review-cancel":
            return emit_json(handle_review_cancel(args.review_id), args.pretty)
        if args.command == "review-draft-ready":
            return emit_json(
                handle_review_draft_ready(
                    args.review_id,
                    args.suggested_category,
                    args.target_path,
                    args.index_path,
                    args.draft_path,
                ),
                args.pretty,
            )
        if args.command == "review-finalized":
            return emit_json(
                handle_review_finalized(
                    args.review_id,
                    args.final_card_path,
                    args.final_index_path,
                    {
                        "card_written": args.mcp_card_written,
                        "index_updated": args.mcp_index_updated,
                        "card_path": args.mcp_card_path or args.final_card_path,
                        "index_path": args.mcp_index_path or args.final_index_path,
                    },
                ),
                args.pretty,
            )
        if args.command == "project-memory-capture":
            return emit_json(handle_project_memory_capture(args), args.pretty)
        if args.command == "project-memory-search":
            return emit_json(handle_project_memory_search(args), args.pretty)
        if args.command == "project-memory-match":
            return emit_json(handle_project_memory_match(args), args.pretty)
        if args.command == "project-memory-status":
            return emit_json(handle_project_memory_status(args), args.pretty)
        if args.command == "transcribe":
            return emit_json(handle_transcribe(args), args.pretty)
        if args.command == "ingest":
            return emit_json(handle_ingest(args), args.pretty)
        if args.command == "batch":
            return emit_json(handle_batch(args), args.pretty)
    except Exception as exc:  # Keep agent stdout parseable even on unexpected errors.
        return emit_json({"success": False, "stage": "agent_cli", "error": str(exc)}, getattr(args, "pretty", False))

    return emit_json({"success": False, "stage": "agent_cli", "error": f"Unknown command: {args.command}"}, False)


def handle_console(args: argparse.Namespace) -> int:
    payload = console_payload(args.host, args.port)
    payload["update"] = check_and_update(PROJECT_ROOT)
    if args.no_browser:
        return emit_json(payload, getattr(args, "pretty", False))
    print(json.dumps(payload, ensure_ascii=False, indent=2 if getattr(args, "pretty", False) else None))
    run_console(args.host, args.port, open_browser=True)
    return 0


def ensure_initialized(command: str) -> dict[str, Any] | None:
    if command in {
        "models",
        "route12-check",
        "route12-mcp-templates",
        "mcp-setup",
        "mcp-verify",
        "mcp-status",
        "review-show",
        "review-list",
        "review-revise",
        "review-approve",
        "review-cancel",
        "review-draft-ready",
        "review-finalized",
        "project-memory-capture",
        "project-memory-search",
        "project-memory-match",
        "project-memory-status",
    } or CONFIG_PATH.exists():
        return None

    if is_interactive_terminal():
        print("首次使用需要先完成初始化配置，正在打开本地 Web Console。")
        code = handle_console(
            argparse.Namespace(
                host=CONSOLE_DEFAULT_HOST,
                port=CONSOLE_DEFAULT_PORT,
                no_browser=False,
                pretty=False,
            )
        )
        if code == 0 and CONFIG_PATH.exists():
            return None
        return {
            "success": False,
            "stage": "init",
            "needs_init": True,
            "error": "初始化未完成，请先打开本地 Web Console：python -X utf8 agent_cli.py init",
            **init_instructions_payload(),
        }

    return {
        "success": False,
        "stage": "init",
        "needs_init": True,
        "error": "首次使用前请先通过本地 Web Console 完成初始化：python -X utf8 agent_cli.py init",
        **init_instructions_payload(),
    }


def is_interactive_terminal() -> bool:
    return bool(sys.stdin.isatty() and sys.stdout.isatty())


def init_instructions_payload() -> dict[str, Any]:
    manifest_path = PROJECT_ROOT / "initialization_manifest.json"
    return {
        "init_command": "python -X utf8 agent_cli.py init",
        "web_console_command": "python -X utf8 main.py",
        "initialization_mode": "web_console_only",
        "init_options": {
            "engines": INIT_ENGINE_CHOICES,
            "model_sizes": MODEL_CHOICES,
            "export_formats": EXPORT_CHOICES,
            "content_modes": CONTENT_MODE_CHOICES,
            "interaction_channels": INTERACTION_CHANNEL_CHOICES,
            "keep_audio": [True, False],
        },
        "initialization_manifest": str(manifest_path),
    }


def handle_init(force: bool = False) -> int:
    """Compatibility wrapper for the old init entry.

    First-run setup is now owned by the local Web Console. Keep this function
    only so older internal callers do not resurrect the chat/terminal wizard.
    """

    return handle_console(
        argparse.Namespace(
            host=CONSOLE_DEFAULT_HOST,
            port=CONSOLE_DEFAULT_PORT,
            no_browser=False,
            pretty=False,
        )
    )


def handle_init_config(args: argparse.Namespace) -> dict[str, Any]:
    if CONFIG_PATH.exists() and not args.force:
        return {
            "success": False,
            "stage": "init",
            "error": "config.ini 已存在。如需覆盖，请添加 --force。",
            "config_path": str(CONFIG_PATH),
        }

    if args.engine == "mimo" and not args.mimo_key:
        return {
            "success": False,
            "stage": "init",
            "error": "选择 mimo 时必须提供 --mimo-key。",
            **init_instructions_payload(),
        }

    output_dir = args.output_dir or DEFAULT_TRANSCRIPT_OUTPUT_DIR
    audio_output_dir = args.audio_output_dir or str(default_audio_dir(output_dir))
    mcp_setup_status = "pending" if args.configure_mcp else "skipped"
    effective_content_mode = args.im_content_mode if args.configure_mcp else "original"
    write_initial_config(
        engine=args.engine,
        model_size=args.model_size,
        mimo_key=args.mimo_key if args.engine == "mimo" else "",
        mimo_url=args.mimo_url or DEFAULT_MIMO_API_URL,
        aliyun_qwen_asr_api_key=args.aliyun_qwen_asr_api_key if args.engine == "aliyun_qwen_asr" else "",
        aliyun_qwen_asr_base_url=args.aliyun_qwen_asr_base_url,
        aliyun_qwen_asr_model=args.aliyun_qwen_asr_model,
        tencent_asr_secret_id=args.tencent_asr_secret_id if args.engine == "tencent_asr" else "",
        tencent_asr_secret_key=args.tencent_asr_secret_key if args.engine == "tencent_asr" else "",
        tencent_asr_region=args.tencent_asr_region,
        tencent_asr_engine_model_type=args.tencent_asr_engine_model_type,
        volcengine_asr_app_id=args.volcengine_asr_app_id if args.engine == "volcengine_asr" else "",
        volcengine_asr_access_token=args.volcengine_asr_access_token if args.engine == "volcengine_asr" else "",
        volcengine_asr_cluster=args.volcengine_asr_cluster,
        volcengine_asr_audio_url=args.volcengine_asr_audio_url,
        output_dir=output_dir,
        audio_output_dir=audio_output_dir,
        export_format=args.export,
        agent_reply_mode=args.reply_mode,
        im_content_mode=effective_content_mode,
        interaction_channel=args.interaction_channel,
        keep_audio=args.keep_audio,
        mcp_setup_status=mcp_setup_status,
    )

    setup_logs: list[str] = []
    local_setup_success = True
    if args.engine == "faster_whisper" and not args.skip_local_setup:
        local_setup_success = setup_local_asr(args.model_size, log=setup_logs.append)

    return {
        "success": True,
        "mode": "init-config",
        "config_path": str(CONFIG_PATH),
        "engine": args.engine,
        "model_size": args.model_size if args.engine == "faster_whisper" else "",
        "mimo_key_saved": bool(args.mimo_key) if args.engine == "mimo" else False,
        "aliyun_qwen_asr_key_saved": bool(args.aliyun_qwen_asr_api_key) if args.engine == "aliyun_qwen_asr" else False,
        "tencent_asr_key_saved": bool(args.tencent_asr_secret_id and args.tencent_asr_secret_key) if args.engine == "tencent_asr" else False,
        "volcengine_asr_key_saved": bool(args.volcengine_asr_app_id and args.volcengine_asr_access_token) if args.engine == "volcengine_asr" else False,
        "output_dir": output_dir,
        "audio_output_dir": audio_output_dir,
        "export_format": args.export,
        "agent_reply_mode": args.reply_mode,
        "im_content_mode": effective_content_mode,
        "interaction_channel": args.interaction_channel,
        "keep_audio": args.keep_audio,
        "mcp_setup_status": mcp_setup_status,
        "local_setup_success": local_setup_success if args.engine == "faster_whisper" else None,
        "setup_logs": setup_logs,
        **initialization_capabilities(
            engine=args.engine,
            local_setup_success=local_setup_success,
            mcp_setup_status=mcp_setup_status,
        ),
    }


def write_initial_config(
    engine: str,
    model_size: str,
    mimo_key: str,
    mimo_url: str,
    aliyun_qwen_asr_api_key: str = "",
    aliyun_qwen_asr_base_url: str = "",
    aliyun_qwen_asr_model: str = "qwen-audio-asr",
    tencent_asr_secret_id: str = "",
    tencent_asr_secret_key: str = "",
    tencent_asr_region: str = "ap-guangzhou",
    tencent_asr_engine_model_type: str = "16k_zh",
    volcengine_asr_app_id: str = "",
    volcengine_asr_access_token: str = "",
    volcengine_asr_cluster: str = "",
    volcengine_asr_audio_url: str = "",
    output_dir: str = "",
    audio_output_dir: str = "",
    export_format: str = "md",
    agent_reply_mode: str = "im",
    im_content_mode: str = "both",
    interaction_channel: str = "auto",
    keep_audio: bool = False,
    mcp_setup_status: str = "skipped",
    mcp_client: str = "",
    mcp_transport: str = "",
    mcp_verified_at: str = "",
) -> None:
    CONFIG_PATH.write_text(
        build_initial_config_text(
            engine=engine,
            model_size=model_size,
            mimo_key=mimo_key,
            mimo_url=mimo_url,
            aliyun_qwen_asr_api_key=aliyun_qwen_asr_api_key,
            aliyun_qwen_asr_base_url=aliyun_qwen_asr_base_url,
            aliyun_qwen_asr_model=aliyun_qwen_asr_model,
            tencent_asr_secret_id=tencent_asr_secret_id,
            tencent_asr_secret_key=tencent_asr_secret_key,
            tencent_asr_region=tencent_asr_region,
            tencent_asr_engine_model_type=tencent_asr_engine_model_type,
            volcengine_asr_app_id=volcengine_asr_app_id,
            volcengine_asr_access_token=volcengine_asr_access_token,
            volcengine_asr_cluster=volcengine_asr_cluster,
            volcengine_asr_audio_url=volcengine_asr_audio_url,
            output_dir=output_dir,
            audio_output_dir=audio_output_dir,
            export_format=export_format,
            agent_reply_mode=agent_reply_mode,
            im_content_mode=im_content_mode,
            interaction_channel=interaction_channel,
            keep_audio=keep_audio,
            mcp_setup_status=mcp_setup_status,
            mcp_client=mcp_client,
            mcp_transport=mcp_transport,
            mcp_verified_at=mcp_verified_at,
        ),
        encoding="utf-8",
    )


def build_initial_config_text(
    engine: str,
    model_size: str,
    mimo_key: str,
    mimo_url: str,
    aliyun_qwen_asr_api_key: str = "",
    aliyun_qwen_asr_base_url: str = "",
    aliyun_qwen_asr_model: str = "qwen-audio-asr",
    tencent_asr_secret_id: str = "",
    tencent_asr_secret_key: str = "",
    tencent_asr_region: str = "ap-guangzhou",
    tencent_asr_engine_model_type: str = "16k_zh",
    volcengine_asr_app_id: str = "",
    volcengine_asr_access_token: str = "",
    volcengine_asr_cluster: str = "",
    volcengine_asr_audio_url: str = "",
    output_dir: str = "",
    audio_output_dir: str = "",
    export_format: str = "md",
    agent_reply_mode: str = "im",
    im_content_mode: str = "both",
    interaction_channel: str = "auto",
    keep_audio: bool = False,
    mcp_setup_status: str = "skipped",
    mcp_client: str = "",
    mcp_transport: str = "",
    mcp_verified_at: str = "",
) -> str:
    parser = configparser.ConfigParser()
    parser["asr"] = {"engine": engine}
    parser["faster_whisper"] = {
        "model_size": model_size,
        "device": "cpu",
        "compute_type": "int8",
        "language": "zh",
        "hf_endpoint": DEFAULT_HF_ENDPOINT,
    }
    parser["mimo"] = {"api_key": mimo_key, "api_url": mimo_url}
    parser["custom_api"] = {"api_url": "", "api_key": ""}
    parser["aliyun_qwen_asr"] = {
        "api_key": aliyun_qwen_asr_api_key,
        "base_url": aliyun_qwen_asr_base_url,
        "model": aliyun_qwen_asr_model or "qwen-audio-asr",
    }
    parser["tencent_asr"] = {
        "secret_id": tencent_asr_secret_id,
        "secret_key": tencent_asr_secret_key,
        "region": tencent_asr_region or "ap-guangzhou",
        "engine_model_type": tencent_asr_engine_model_type or "16k_zh",
    }
    parser["volcengine_asr"] = {
        "app_id": volcengine_asr_app_id,
        "access_token": volcengine_asr_access_token,
        "cluster": volcengine_asr_cluster,
        "audio_url": volcengine_asr_audio_url,
    }
    parser["output"] = {"folder": output_dir, "audio_folder": audio_output_dir}
    parser["preferences"] = {
        "export_format": export_format,
        "agent_reply_mode": normalize_response_mode(agent_reply_mode) or "im",
        "im_content_mode": normalize_content_mode(im_content_mode) or "both",
        "interaction_channel": normalize_interaction_channel(interaction_channel) or "auto",
        "keep_audio": str(keep_audio).lower(),
    }
    parser["mcp"] = {
        "setup_status": normalize_mcp_status(mcp_setup_status) or "skipped",
        "client": mcp_client,
        "transport": mcp_transport,
        "verified_at": mcp_verified_at,
    }

    from io import StringIO

    buffer = StringIO()
    parser.write(buffer)
    return buffer.getvalue()


def setup_local_asr(model_size: str, log=print) -> bool:
    log("首次配置本地转写需要安装依赖并下载模型，可能耗时较久，请耐心等待。")
    log(f"Python 依赖将使用国内镜像：{PYPI_MIRROR_URL}")
    log(f"faster-whisper 模型将使用国内镜像：{DEFAULT_HF_ENDPOINT}")

    missing = [name for name in ["faster_whisper", "opencc"] if not check_import(name)["available"]]
    if missing:
        log(f"缺少 Python 依赖：{', '.join(missing)}")
        result = install_local_asr_dependencies()
        if result.returncode != 0:
            error_text = (result.stderr or result.stdout or "").strip()
            log(f"依赖安装失败。配置已保存，请修复环境后重新运行 init。{error_text[:500]}")
            return False
        log("Python 依赖安装完成。")
    else:
        log("Python 依赖已就绪。")

    ffmpeg = check_ffmpeg()
    ffprobe = check_command("ffprobe")
    if not ffmpeg["available"]:
        log("未检测到 ffmpeg，请安装 ffmpeg 后再转写真实视频。")
    if not ffprobe["available"]:
        log("未检测到 ffprobe，部分音频处理能力可能不可用。")

    success, message = ensure_local_model(model_size)
    log(message)
    return success


def install_local_asr_dependencies() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-r",
            str(PROJECT_ROOT / "requirements-asr.txt"),
            "-i",
            PYPI_MIRROR_URL,
        ],
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def ensure_local_model(model_size: str) -> tuple[bool, str]:
    target = portable_model_path(model_size)
    if is_model_ready(target):
        return True, f"本地模型已就绪：{target}"

    try:
        from huggingface_hub import snapshot_download
    except Exception as exc:
        return False, f"无法下载模型，缺少 huggingface_hub：{exc}"

    try:
        if DEFAULT_HF_ENDPOINT and not os.environ.get("HF_ENDPOINT"):
            os.environ["HF_ENDPOINT"] = DEFAULT_HF_ENDPOINT
        target.mkdir(parents=True, exist_ok=True)
        snapshot_download(
            repo_id=f"Systran/faster-whisper-{model_size}",
            local_dir=str(target),
            local_dir_use_symlinks=False,
        )
    except Exception as exc:
        return False, f"模型下载失败，配置已保存。可稍后重新运行 init。原始错误：{exc}"

    if is_model_ready(target):
        return True, f"模型下载完成：{target}"
    return False, f"模型下载结束但文件不完整，请检查目录：{target}"


def prompt_choice(label: str, choices: list[str], default: str) -> str:
    choice_text = " / ".join(choices)
    while True:
        value = input(f"{label} ({choice_text}) [{default}]: ").strip()
        if not value:
            return default
        normalized = value.lower().replace("-", "_")
        for choice in choices:
            if normalized == choice.lower().replace("-", "_"):
                return choice
        print(f"请输入以下选项之一：{choice_text}")


def prompt_text(label: str, default: str) -> str:
    value = input(f"{label} [{default}]: ").strip()
    return value or default


def prompt_secret(label: str) -> str:
    return getpass.getpass(f"{label}: ").strip()


def confirm(label: str, default: bool) -> bool:
    suffix = "Y/n" if default else "y/N"
    while True:
        value = input(f"{label} [{suffix}]: ").strip().lower()
        if not value:
            return default
        if value in {"y", "yes", "是", "true", "1"}:
            return True
        if value in {"n", "no", "否", "false", "0"}:
            return False
        print("请输入 y 或 n。")


def handle_transcribe(args: argparse.Namespace) -> dict[str, Any]:
    url = resolve_single_url(args.url, args.text)
    if not url:
        return attach_layered_response(
            {"success": False, "stage": "input", "error": "未从输入中找到抖音链接"},
            "douyin",
            args.url or args.text or "",
        )

    document = DEFAULT_SOURCE_REGISTRY.resolve(
        SourceInput(source_type="douyin", url=url, text=args.text or "")
    ).describe(SourceInput(source_type="douyin", url=url, text=args.text or ""))
    payload = _run_source_document(args, document)
    payload["mode"] = "transcribe"
    if args.text:
        payload["extracted_urls"] = extract_urls(args.text)
    return attach_layered_response(
        payload,
        "douyin",
        url,
        str(payload.pop("_processing_transcript", "") or payload.get("transcript") or ""),
    )


def handle_ingest(args: argparse.Namespace) -> dict[str, Any]:
    conflict = normalize_ingest_input(args)
    if conflict is not None:
        return attach_layered_response(conflict, "local_audio", getattr(args, "input", "") or "")
    return run_layered_ingest(
        args,
        _run_ingest_douyin,
        _run_ingest_local_audio,
        _run_source_document,
    )


def normalize_ingest_input(args: argparse.Namespace) -> dict[str, Any] | None:
    positional_input = str(getattr(args, "input", "") or "")
    audio_file = str(getattr(args, "audio_file", "") or "")
    url = str(getattr(args, "url", "") or "")
    mode_alias = str(getattr(args, "mode", "") or "")
    if mode_alias:
        args.im_content_mode = mode_alias
    if positional_input and _is_http_url(positional_input):
        if audio_file:
            return {
                "success": False,
                "mode": "ingest",
                "stage": "input",
                "error_code": "input_conflict",
                "error": "ingest positional URL cannot be combined with --audio-file.",
                "recoverable": True,
                "workflow_status": "failed",
                "workflow_complete": True,
            }
        if url and url != positional_input:
            return {
                "success": False,
                "mode": "ingest",
                "stage": "input",
                "error_code": "input_conflict",
                "error": "ingest positional URL and --url point to different inputs.",
                "recoverable": True,
                "workflow_status": "failed",
                "workflow_complete": True,
            }
        args.url = positional_input
        args.raw_input = positional_input
        args.input_kind = "url"
        return None
    if positional_input:
        extracted = extract_urls(positional_input)
        if extracted:
            first_url = extracted[0]
            if audio_file:
                return {
                    "success": False,
                    "mode": "ingest",
                    "stage": "input",
                    "error_code": "input_conflict",
                    "error": "ingest positional share text cannot be combined with --audio-file.",
                    "recoverable": True,
                    "workflow_status": "failed",
                    "workflow_complete": True,
                }
            if url and url != first_url:
                return {
                    "success": False,
                    "mode": "ingest",
                    "stage": "input",
                    "error_code": "input_conflict",
                    "error": "ingest positional share text and --url point to different inputs.",
                    "recoverable": True,
                    "workflow_status": "failed",
                    "workflow_complete": True,
                }
            args.url = first_url
            args.raw_input = positional_input
            args.input_kind = "url"
            return None
    if positional_input and audio_file and normalize_path_for_compare(positional_input) != normalize_path_for_compare(audio_file):
        return {
            "success": False,
            "mode": "ingest",
            "stage": "input",
            "error_code": "input_conflict",
            "error": "ingest positional input and --audio-file point to different paths.",
            "recoverable": True,
            "workflow_status": "failed",
            "workflow_complete": True,
        }
    if positional_input and not audio_file:
        args.audio_file = positional_input
        args.raw_input = positional_input
        args.input_kind = "path"
    return None


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def normalize_path_for_compare(value: str) -> str:
    return os.path.normcase(os.path.abspath(os.path.expanduser(value)))


def _run_ingest_douyin(args: argparse.Namespace, document) -> dict[str, Any]:
    return _run_source_document(args, document)


def _run_ingest_local_audio(args: argparse.Namespace, document) -> dict[str, Any]:
    return _run_source_document(args, document)


def _run_source_document(args: argparse.Namespace, document) -> dict[str, Any]:
    logs: list[str] = []
    options = build_options(args, document.original_url)
    if document.source_type == "local_audio":
        options.audio_file = document.original_url
    result, acquisition, processing = execute_source_pipeline(
        document.source_type,
        document,
        options,
        logs.append,
    )
    if document.status == "ready":
        document.status = "completed"
    payload = _route_pipeline_result(
        args,
        result,
        logs,
        document.original_url,
        document.source_type,
    )
    payload["_layer_source"] = document.__dict__.copy()
    payload["_layer_acquisition"] = acquisition.__dict__.copy()
    payload["_layer_processing"] = processing.__dict__.copy()
    return payload


def _route_pipeline_result(
    args: argparse.Namespace,
    result: PipelineResult,
    logs: list[str],
    input_value: str,
    source_type: str = "",
) -> dict[str, Any]:
    config = getattr(args, "_resolved_config", None) or build_config(args)
    response_mode = resolve_response_mode(args, config)
    content_mode = resolve_content_mode(args, config)
    if source_type == "local_audio" and not (
        getattr(args, "im_content_mode", "") or getattr(args, "mode", "")
    ):
        content_mode = "original"
    interaction_channel = resolve_interaction_channel(args, config)
    payload = result_to_payload(
        result,
        "ingest",
        logs,
        include_transcript=should_include_transcript(args, response_mode, content_mode),
        response_mode=response_mode,
    )
    payload["input_url"] = input_value
    routed = apply_content_routing(payload, result.transcript or "", content_mode, interaction_channel)
    routed["_processing_transcript"] = result.transcript or ""
    return routed


def handle_batch(args: argparse.Namespace) -> dict[str, Any]:
    text_parts: list[str] = []
    if args.text:
        text_parts.append(args.text)
    if args.input_file:
        try:
            text_parts.append(Path(args.input_file).read_text(encoding="utf-8"))
        except Exception as exc:
            payload = {"success": False, "stage": "input", "error": f"读取批量输入文件失败: {exc}", "items": []}
            return attach_layered_response(payload, "douyin_batch", args.input_file)

    urls = extract_urls("\n".join(text_parts))
    if not urls:
        payload = {"success": False, "stage": "input", "error": "未从输入中找到抖音链接", "items": []}
        return attach_layered_response(payload, "douyin_batch", "\n".join(text_parts))

    logs: list[str] = []
    base_options = build_options(args, "")
    response_mode = resolve_response_mode(args, base_options.config)
    content_mode = resolve_content_mode(args, base_options.config)
    interaction_channel = resolve_interaction_channel(args, base_options.config)
    items = []
    for index, url in enumerate(urls, start=1):
        adapter = DEFAULT_SOURCE_REGISTRY.resolve(SourceInput(source_type="douyin", url=url))
        document = adapter.describe(SourceInput(source_type="douyin", url=url))
        item = _run_source_document(args, document)
        item["mode"] = "batch_item"
        item["index"] = index
        item["input_url"] = url
        transcript = str(item.pop("_processing_transcript", "") or item.get("transcript") or "")
        items.append(attach_layered_response(item, "douyin", url, transcript))
    payload = build_batch_envelope(items)
    payload.update(
        {
        "content_mode": content_mode,
        "interaction_channel": interaction_channel,
        "logs": logs,
        }
    )
    return payload


def resolve_single_url(url: str | None, text: str | None) -> str:
    if url:
        return url.strip()
    urls = extract_urls(text or "")
    return urls[0] if urls else ""


def build_options(args: argparse.Namespace, url: str) -> PipelineOptions:
    config = build_config(args)
    output_dir = resolve_output_dir(args, config)
    audio_output_dir = resolve_audio_output_dir(args, config, output_dir)
    engine = resolve_engine(args, config)
    prefs = config.get("preferences", {})
    export_format = args.export if args.export else prefs.get("export_format", "md")
    keep_audio = args.keep_audio if args.keep_audio is not None else parse_bool(prefs.get("keep_audio"), False)
    return PipelineOptions(
        url=url,
        engine=engine,
        export_format=export_format,
        output_dir=output_dir,
        audio_output_dir=audio_output_dir,
        audio_file=getattr(args, "audio_file", "") or "",
        skip_audio=args.skip_audio,
        keep_audio=keep_audio,
        mock_metadata=args.mock_metadata,
        to_simplified=not args.no_simplified,
        config=config,
    )


def build_config(args: argparse.Namespace) -> dict[str, dict[str, Any]]:
    config = load_config()
    config.setdefault("faster_whisper", {})
    if args.model_size:
        config["faster_whisper"]["model_size"] = args.model_size
    config["faster_whisper"].setdefault("model_size", "base")
    if args.device:
        config["faster_whisper"]["device"] = args.device
    config["faster_whisper"].setdefault("device", "cpu")
    if args.compute_type:
        config["faster_whisper"]["compute_type"] = args.compute_type
    config["faster_whisper"].setdefault("compute_type", "int8")
    if args.language:
        config["faster_whisper"]["language"] = args.language
    config["faster_whisper"].setdefault("language", "zh")
    if args.hf_endpoint:
        config["faster_whisper"]["hf_endpoint"] = args.hf_endpoint

    if args.mimo_key or args.mimo_url:
        config.setdefault("mimo", {})
        if args.mimo_key:
            config["mimo"]["api_key"] = args.mimo_key
        if args.mimo_url:
            config["mimo"]["api_url"] = args.mimo_url

    if args.custom_api_key or args.custom_api_url:
        config.setdefault("custom_api", {})
        if args.custom_api_key:
            config["custom_api"]["api_key"] = args.custom_api_key
        if args.custom_api_url:
            config["custom_api"]["api_url"] = args.custom_api_url

    return config


def resolve_engine(args: argparse.Namespace, config: dict[str, dict[str, Any]]) -> str:
    if args.engine:
        return args.engine
    configured = config.get("asr", {}).get("engine", "")
    return normalize_engine(configured) or "faster_whisper"


def normalize_engine(engine_name: str) -> str:
    return (engine_name or "").strip().lower().replace("-", "_")


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "保留"}


def normalize_response_mode(value: str) -> str:
    normalized = (value or "").strip().lower().replace("-", "_")
    return normalized if normalized in RESPONSE_MODE_CHOICES else ""


def normalize_content_mode(value: str) -> str:
    normalized = (value or "").strip().lower().replace("-", "_")
    return normalized if normalized in CONTENT_MODE_CHOICES else ""


def normalize_interaction_channel(value: str) -> str:
    normalized = (value or "").strip().lower().replace("-", "_")
    return normalized if normalized in INTERACTION_CHANNEL_CHOICES else ""


def normalize_mcp_status(value: str) -> str:
    normalized = (value or "").strip().lower().replace("-", "_")
    return normalized if normalized in MCP_SETUP_STATUSES else ""


def initialization_capabilities(
    engine: str,
    local_setup_success: bool,
    mcp_setup_status: str,
) -> dict[str, bool]:
    transcription_ready = engine != "faster_whisper" or local_setup_success
    mcp_ready = mcp_setup_status == "configured"
    return {
        "transcription_ready": transcription_ready,
        "mcp_ready": mcp_ready,
        "curation_ready": transcription_ready and mcp_ready,
    }


def resolve_response_mode(args: argparse.Namespace, config: dict[str, dict[str, Any]]) -> str:
    requested = normalize_response_mode(getattr(args, "response_mode", ""))
    if requested:
        return requested
    configured = normalize_response_mode(config.get("preferences", {}).get("agent_reply_mode", ""))
    return configured or "desktop"


def resolve_content_mode(args: argparse.Namespace, config: dict[str, dict[str, Any]]) -> str:
    requested = normalize_content_mode(getattr(args, "im_content_mode", ""))
    if requested:
        return requested
    configured = normalize_content_mode(config.get("preferences", {}).get("im_content_mode", ""))
    return configured or "original"


def resolve_interaction_channel(args: argparse.Namespace, config: dict[str, dict[str, Any]]) -> str:
    requested = normalize_interaction_channel(getattr(args, "interaction_channel", ""))
    if requested:
        return requested
    configured = normalize_interaction_channel(config.get("preferences", {}).get("interaction_channel", ""))
    return configured or "auto"


def should_include_transcript(args: argparse.Namespace, response_mode: str, content_mode: str) -> bool:
    return bool(
        getattr(args, "include_transcript", False)
        or response_mode == "im"
        or content_mode in CONTENT_MODE_CHOICES
    )


def resolve_output_dir(args: argparse.Namespace, config: dict[str, dict[str, Any]] | None = None) -> str:
    output_config = (config or {}).get("output", {})
    return args.knowledge_dir or args.output_dir or output_config.get("folder", "") or DEFAULT_TRANSCRIPT_OUTPUT_DIR


def resolve_audio_output_dir(
    args: argparse.Namespace,
    config: dict[str, dict[str, Any]] | None,
    output_dir: str,
) -> str:
    output_config = (config or {}).get("output", {})
    return args.audio_output_dir or output_config.get("audio_folder", "") or str(default_audio_dir(output_dir))


def result_to_payload(
    result: PipelineResult,
    mode: str,
    logs: list[str],
    index: int | None = None,
    input_url: str = "",
    include_transcript: bool = False,
    response_mode: str = "desktop",
) -> dict[str, Any]:
    metadata = result.metadata or {}
    paths = result.exported_paths or []
    payload: dict[str, Any] = {
        "success": result.success,
        "mode": mode,
        "title": metadata.get("title", ""),
        "author": metadata.get("author", ""),
        "md_path": first_path_with_suffix(paths, ".md"),
        "txt_path": first_path_with_suffix(paths, ".txt"),
        "exported_paths": paths,
        "audio_path": result.audio_path,
        "engine": result.engine,
        "transcript_chars": len(result.transcript or ""),
        "reply_mode": response_mode,
        "error": result.error,
        "logs": logs,
    }
    if index is not None:
        payload["index"] = index
    if input_url:
        payload["input_url"] = input_url
    if include_transcript:
        payload["transcript"] = result.transcript or ""
    if response_mode == "im" and result.success:
        payload["reply_text"] = build_im_reply_text(payload, result.transcript or "")
    if not result.success and not payload["error"]:
        payload["error"] = "转写失败"
    return payload


def build_im_reply_text(payload: dict[str, Any], transcript: str) -> str:
    return build_original_reply_text(payload, transcript)


def apply_content_routing(
    payload: dict[str, Any],
    transcript: str,
    content_mode: str,
    interaction_channel: str,
) -> dict[str, Any]:
    payload["interaction_channel"] = interaction_channel
    payload["interaction_channel_resolution"] = "agent_context" if interaction_channel == "auto" else "explicit"
    processing = ProcessingResult(
        status="completed" if payload.get("success") else "failed",
        engine=str(payload.get("engine") or ""),
        transcript=transcript,
        transcript_chars=len(transcript),
        normalized=bool(payload.get("success")),
        artifacts=list(payload.get("exported_paths") or []),
        normalized_text=transcript,
        markdown_path=str(payload.get("md_path") or ""),
        txt_path=str(payload.get("txt_path") or ""),
        metadata={
            "title": str(payload.get("title") or ""),
            "author": str(payload.get("author") or ""),
        },
    )
    context = KnowledgeContext(
        content_mode=content_mode,
        interaction_channel=interaction_channel,
        route_report_provider=build_route12_report,
        review_creator=create_review_record,
    )
    decision = create_knowledge_result(processing, context, payload)
    legacy_fields = decision.legacy_fields()
    if not payload.get("success"):
        legacy_fields["workflow_status"] = "failed"
    payload.update(legacy_fields)
    reply_text = format_knowledge_reply(payload, decision.normalized_text, decision)
    if reply_text:
        payload["reply_text"] = reply_text
    return payload


def create_review_record(
    payload: dict[str, Any],
    content_mode: str,
    interaction_channel: str,
) -> dict[str, Any]:
    return review_service.create_review_record(
        REVIEW_DIR,
        ROUTE12_REVIEW_DIR,
        payload,
        content_mode,
        interaction_channel,
    )


def review_record_path(review_id: str) -> Path:
    return review_service.review_record_path(REVIEW_DIR, review_id)


def save_review_record(record: dict[str, Any]) -> None:
    review_service.save_review_record(REVIEW_DIR, record)


def load_review_record(review_id: str) -> dict[str, Any] | None:
    return review_service.load_review_record(REVIEW_DIR, review_id)


def utc_timestamp() -> str:
    return review_service.utc_timestamp()


def handle_review_show(review_id: str) -> dict[str, Any]:
    return review_service.handle_review_show(REVIEW_DIR, review_id)


def handle_review_list() -> dict[str, Any]:
    return review_service.handle_review_list(REVIEW_DIR)


def handle_review_revise(review_id: str, instruction: str) -> dict[str, Any]:
    return review_service.handle_review_revise(REVIEW_DIR, review_id, instruction)


def handle_review_approve(review_id: str) -> dict[str, Any]:
    return review_service.handle_review_approve(REVIEW_DIR, review_id)


def handle_review_cancel(review_id: str) -> dict[str, Any]:
    return review_service.handle_review_cancel(REVIEW_DIR, review_id)


def handle_review_draft_ready(
    review_id: str,
    suggested_category: str,
    target_path: str,
    index_path: str,
    draft_path: str = "",
) -> dict[str, Any]:
    return review_service.handle_review_draft_ready(
        REVIEW_DIR,
        review_id,
        suggested_category,
        target_path,
        index_path,
        draft_path,
    )


def handle_review_finalized(
    review_id: str,
    final_card_path: str,
    final_index_path: str,
    mcp_write_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    confirmation = route12_service.validate_mcp_finalization_report(
        mcp_write_report,
        final_card_path,
        final_index_path,
    )
    if not confirmation.get("success"):
        return {
            "success": False,
            "mode": "review-finalized",
            **confirmation,
            "workflow_status": "approved",
            "workflow_complete": False,
            "next_skill": "douyin-curate-via-obsidian-mcp",
        }
    return review_service.handle_review_finalized(
        REVIEW_DIR,
        review_id,
        final_card_path,
        final_index_path,
    )


def project_memory_context(agent: str = "") -> ProjectMemoryContext:
    return ProjectMemoryContext(
        project_root=PROJECT_ROOT,
        vault_root=ROUTE12_VAULT_DIR,
        review_dir=REVIEW_DIR,
        review_draft_dir=ROUTE12_REVIEW_DIR,
        agent=agent or getpass.getuser() or "unknown",
    )


def handle_project_memory_capture(args: argparse.Namespace) -> dict[str, Any]:
    payload_file = Path(args.payload_file) if args.payload_file else None
    summary_file = Path(args.summary_file) if args.summary_file else None
    if bool(payload_file) == bool(summary_file):
        return {
            "success": False,
            "stage": "knowledge",
            "mode": "project-memory-capture",
            "error_code": "project_memory_payload_invalid",
            "error": "必须且只能提供 --payload-file 或 --summary-file。",
            "recoverable": True,
        }
    try:
        if payload_file:
            payload = load_project_memory_payload_file(payload_file)
        else:
            if not args.project or not args.title:
                return {
                    "success": False,
                    "stage": "knowledge",
                    "mode": "project-memory-capture",
                    "error_code": "project_memory_payload_invalid",
                    "error": "使用 --summary-file 时必须同时提供 --project 和 --title。",
                    "recoverable": True,
                }
            payload = payload_from_summary_file(
                summary_file,
                project=args.project,
                title=args.title,
                agent=args.agent or getpass.getuser(),
                session_type=args.session_type,
            )
    except Exception as exc:
        return {
            "success": False,
            "stage": "knowledge",
            "mode": "project-memory-capture",
            "error_code": "project_memory_payload_invalid",
            "error": f"项目记忆输入读取失败：{exc}",
            "recoverable": True,
        }
    if args.agent:
        payload["agent"] = args.agent
        payload.setdefault("source_agent", args.agent)
    if args.session_type:
        payload.setdefault("session_type", args.session_type)
    return create_project_memory_draft(payload, project_memory_context(args.agent))


def handle_project_memory_search(args: argparse.Namespace) -> dict[str, Any]:
    return search_project_memory(
        args.query,
        project_memory_context(),
        project=args.project,
        tag=args.tag,
        limit=max(1, int(args.limit or 20)),
    )


def handle_project_memory_match(args: argparse.Namespace) -> dict[str, Any]:
    return match_idea_to_projects(
        args.idea,
        project_memory_context(),
        limit=max(1, int(args.limit or 5)),
    )


def handle_project_memory_status(args: argparse.Namespace) -> dict[str, Any]:
    return project_memory_status(project_memory_context(getattr(args, "agent", "") or "external-agent"))


def first_path_with_suffix(paths: list[str], suffix: str) -> str:
    for path in paths:
        if path.lower().endswith(suffix):
            return path
    return ""


def build_route12_template_report() -> dict[str, Any]:
    return route12_service.build_template_report(
        PROJECT_ROOT,
        ROUTE12_MCP_TEMPLATES,
        ROUTE12_MCP_SETUP_DOC,
        ROUTE12_MCP_DIR,
    )


def select_mcp_templates(client: str, transport: str = "") -> list[dict[str, Any]]:
    return route12_service.select_templates(build_route12_template_report(), client, transport)


def handle_mcp_setup(args: argparse.Namespace) -> dict[str, Any]:
    if args.skip:
        update_mcp_config("skipped", args.client, args.transport, "")
        force_original_content_mode()
        return {
            "success": True,
            "mode": "mcp-setup",
            "mcp_setup_status": "skipped",
            "content_mode": "original",
            "mcp_ready": False,
            "curation_ready": False,
            "next_action": "transcription_only",
        }

    client = args.client or detect_agent_client()
    transport = args.transport or ""
    templates = select_mcp_templates(client, transport)
    selected_transport = transport or (templates[0]["transport"] if templates else "")
    update_mcp_config("pending", client, selected_transport, "")
    return {
        "success": True,
        "mode": "mcp-setup",
        "mcp_setup_status": "pending",
        "client": client,
        "transport": selected_transport,
        "templates": templates,
        "setup_doc": str(ROUTE12_MCP_SETUP_DOC),
        "credential_storage": "agent_secure_configuration_only",
        "steps": [
            "Open Obsidian and the AI外脑知识库 vault.",
            "Enable REST and MCP server, or Local REST API with obsidian-mcp-server.",
            "Apply the matching template in the current AI agent's secure MCP settings.",
            "Use the current agent's MCP tools to list the vault root.",
            "Read _知识卡片模板.md through MCP.",
            "Create and delete a temporary note under 00_Inbox/_待审核 through MCP.",
            "After all four checks succeed, call mcp-verify with the corresponding flags.",
        ],
        "verification_command": (
            f'python -X utf8 agent_cli.py mcp-verify --client "{client}" '
            f'--transport "{selected_transport or "stdio"}" --listed-vault --read-template '
            "--created-test-note --deleted-test-note --pretty"
        ),
        "mcp_ready": False,
        "curation_ready": False,
        "next_action": "configure_client_and_verify_with_real_mcp_tools",
    }


def handle_mcp_verify(args: argparse.Namespace) -> dict[str, Any]:
    checks = {
        "listed_vault": bool(args.listed_vault),
        "read_template": bool(args.read_template),
        "created_test_note": bool(args.created_test_note),
        "deleted_test_note": bool(args.deleted_test_note),
    }
    verified = all(checks.values()) and not args.error
    status = "configured" if verified else "failed"
    verified_at = utc_timestamp() if verified else ""
    verification_report = route12_service.build_verification_record(
        client=args.client,
        profile=getattr(args, "profile", "") or args.client,
        transport=args.transport,
        vault_root=getattr(args, "vault_root", "") or str(ROUTE12_VAULT_DIR),
        vault_identity=getattr(args, "vault_identity", "") or ROUTE12_VAULT_DIR.name,
        checks=checks,
        verified_at=verified_at or utc_timestamp(),
    )
    update_mcp_config(
        status,
        args.client,
        args.transport,
        verified_at,
        verification_report,
    )
    payload = {
        "success": verified,
        "mode": "mcp-verify",
        "mcp_setup_status": status,
        "client": args.client,
        "profile": getattr(args, "profile", "") or args.client,
        "transport": args.transport,
        "checks": checks,
        "verification_report": verification_report,
        "error": args.error or ("" if verified else "必须完成全部真实 MCP 验证检查。"),
        "mcp_ready": verified,
        "curation_ready": verified,
        "verified_at": verified_at,
        "next_action": "ready_for_card_or_both" if verified else "fix_mcp_and_retry_verification",
    }
    if not verified:
        payload.update(
            {
                "stage": "knowledge",
                "error_code": "mcp_verification_failed",
                "recoverable": True,
            }
        )
    return payload


def build_mcp_status() -> dict[str, Any]:
    parser = read_config_parser()
    mcp = parser["mcp"] if parser.has_section("mcp") else {}
    status = normalize_mcp_status(mcp.get("setup_status", "")) or "skipped"
    verification_report = route12_service.verification_record_from_json(
        mcp.get("verification_report", "")
    )
    profile = mcp.get("profile", "") or mcp.get("client", "")
    readiness = route12_service.evaluate_mcp_readiness(
        persisted_mcp={
            "mcp_setup_status": status,
            "client": mcp.get("client", ""),
            "profile": profile,
            "transport": mcp.get("transport", ""),
            "verified_at": mcp.get("verified_at", ""),
            "verification_report": verification_report,
        },
        vault_root=str(ROUTE12_VAULT_DIR),
        vault_identity=ROUTE12_VAULT_DIR.name,
        current_client=mcp.get("client", ""),
        current_profile=profile,
        current_transport=mcp.get("transport", ""),
    )
    verified = readiness["ready"]
    return {
        "success": True,
        "mode": "mcp-status",
        "mcp_setup_status": status,
        "client": mcp.get("client", ""),
        "profile": profile,
        "transport": mcp.get("transport", ""),
        "verified_at": readiness["verified_at"],
        "mcp_ready": verified,
        "curation_ready": verified,
        "readiness": readiness,
        "verification_report": verification_report,
        "credentials_stored_in_project": False,
    }


def update_mcp_config(
    status: str,
    client: str,
    transport: str,
    verified_at: str,
    verification_report: dict[str, Any] | None = None,
) -> None:
    parser = read_config_parser()
    if not parser.has_section("mcp"):
        parser.add_section("mcp")
    parser["mcp"]["setup_status"] = normalize_mcp_status(status) or "failed"
    parser["mcp"]["client"] = client
    parser["mcp"]["profile"] = str(
        (verification_report or {}).get("profile")
        or parser["mcp"].get("profile", "")
        or client
    )
    parser["mcp"]["transport"] = transport
    parser["mcp"]["verified_at"] = verified_at
    if verification_report is not None:
        parser["mcp"]["verification_report"] = json.dumps(
            verification_report,
            ensure_ascii=False,
            sort_keys=True,
        )
    write_config_parser(parser)


def force_original_content_mode() -> None:
    parser = read_config_parser()
    if not parser.has_section("preferences"):
        parser.add_section("preferences")
    parser["preferences"]["im_content_mode"] = "original"
    write_config_parser(parser)


def read_config_parser() -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    if CONFIG_PATH.exists():
        parser.read(CONFIG_PATH, encoding="utf-8-sig")
    return parser


def write_config_parser(parser: configparser.ConfigParser) -> None:
    with CONFIG_PATH.open("w", encoding="utf-8") as handle:
        parser.write(handle)


def detect_agent_client() -> str:
    return route12_service.detect_agent_client()


def build_route12_report() -> dict[str, Any]:
    persisted_mcp = build_mcp_status()
    return route12_service.build_route_report(
        ROUTE12_VAULT_DIR,
        ROUTE12_REVIEW_DIR,
        ROUTE12_REQUIRED_PATHS,
        ROUTE12_MCP_PLUGIN_IDS,
        ROUTE12_MCP_SETUP_DOC,
        build_route12_template_report(),
        persisted_mcp,
        current_client=persisted_mcp.get("client", ""),
        current_profile=persisted_mcp.get("profile", ""),
        current_transport=persisted_mcp.get("transport", ""),
    )
    obsidian_dir = ROUTE12_VAULT_DIR / ".obsidian"
    plugins_dir = obsidian_dir / "plugins"
    community_plugins_path = obsidian_dir / "community-plugins.json"

    installed_plugin_dirs = sorted(
        path.name for path in plugins_dir.iterdir() if path.is_dir()
    ) if plugins_dir.exists() else []
    enabled_plugins = read_enabled_obsidian_plugins(community_plugins_path)

    claudian_present = "realclaudian" in installed_plugin_dirs or "realclaudian" in enabled_plugins
    mcp_bridge_plugins = sorted(
        plugin_id
        for plugin_id in ROUTE12_MCP_PLUGIN_IDS
        if plugin_id in installed_plugin_dirs or plugin_id in enabled_plugins
    )
    required_paths = [
        {
            "path": rel_path,
            "exists": (ROUTE12_VAULT_DIR / Path(rel_path)).exists(),
        }
        for rel_path in ROUTE12_REQUIRED_PATHS
    ]
    missing_required = [item["path"] for item in required_paths if not item["exists"]]
    mcp_bridge_detected = bool(mcp_bridge_plugins)
    persisted_mcp = build_mcp_status()
    template_report = build_route12_template_report()
    mcp_templates = template_report["templates"]
    qoderwork_templates = [
        item for item in mcp_templates if "QoderWork CN" in item["clients"]
    ]

    if not ROUTE12_VAULT_DIR.exists():
        next_step = "Create or restore Obsidian/AI外脑知识库 before testing Route 1.2."
    elif missing_required:
        next_step = "Restore missing vault folders or template files before MCP curation."
    elif not mcp_bridge_detected:
        next_step = "Read docs/mcp-setup.md, then use a template under mcp/. QoderWork CN should prefer its HTTP template."
    elif not persisted_mcp["mcp_ready"]:
        next_step = "Connect your AI coding agent to the Obsidian MCP bridge and test listing vault files."
    else:
        next_step = "Route 1.2 MCP verification is complete."

    return {
        "success": True,
        "mode": "route12-check",
        "route": "AI外脑1.2 Agent direct Obsidian MCP",
        "vault_path": str(ROUTE12_VAULT_DIR),
        "vault_exists": ROUTE12_VAULT_DIR.exists(),
        "review_dir": str(ROUTE12_REVIEW_DIR),
        "required_paths": required_paths,
        "missing_required_paths": missing_required,
        "obsidian_plugins_dir": str(plugins_dir),
        "installed_plugin_dirs": installed_plugin_dirs,
        "enabled_plugins": enabled_plugins,
        "claudian_present": claudian_present,
        "claudian_used_in_route12": False,
        "mcp_bridge_detected": mcp_bridge_detected,
        "obsidian_bridge_plugin_detected": mcp_bridge_detected,
        "mcp_bridge_plugins": mcp_bridge_plugins,
        "agent_mcp_verified": persisted_mcp["mcp_ready"],
        "mcp_setup_status": persisted_mcp["mcp_setup_status"],
        "mcp_client": persisted_mcp["client"],
        "mcp_transport": persisted_mcp["transport"],
        "mcp_verified_at": persisted_mcp["verified_at"],
        "mcp_setup_doc": str(ROUTE12_MCP_SETUP_DOC),
        "mcp_templates": mcp_templates,
        "recommended_agent": "QoderWork CN",
        "qoderwork_templates": qoderwork_templates,
        "can_transcribe_without_mcp": True,
        "can_finalize_without_mcp": False,
        "mcp_ready": persisted_mcp["mcp_ready"],
        "curation_ready": persisted_mcp["curation_ready"] and not missing_required,
        "recommended_next_step": next_step,
    }


def read_enabled_obsidian_plugins(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    return sorted(str(item) for item in payload)


def build_env_report(args: argparse.Namespace) -> dict[str, Any]:
    config = load_config()
    output_dir = Path(resolve_output_dir(args, config))
    audio_dir = Path(resolve_audio_output_dir(args, config, str(output_dir)))
    ffmpeg = check_ffmpeg()
    ffprobe = check_command("ffprobe")
    models = build_models_report()["models"]
    selected_model_name = args.model_size or config.get("faster_whisper", {}).get("model_size", "base")
    selected_model = models.get(selected_model_name, {})
    faster_whisper = check_import("faster_whisper")
    output_writable = check_writable_dir(output_dir)
    audio_writable = check_writable_dir(audio_dir)
    ready = bool(ffmpeg["available"] and faster_whisper["available"] and selected_model.get("ready"))
    return {
        "success": ready,
        "mode": "check-env",
        "python": sys.version.split()[0],
        "python_environment": runtime_environment(),
        "ffmpeg": ffmpeg,
        "ffprobe": ffprobe,
        "faster_whisper": faster_whisper,
        "selected_model": selected_model_name,
        "models": models,
        "output_dir": {"path": str(output_dir), "writable": output_writable},
        "audio_output_dir": {"path": str(audio_dir), "writable": audio_writable},
        "ready_for_local_asr": ready,
    }


def build_models_report() -> dict[str, Any]:
    return {
        "success": True,
        "mode": "models",
        "models": {model: model_status(model) for model in MODEL_CHOICES},
    }


def model_status(model_name: str) -> dict[str, Any]:
    path = portable_model_path(model_name)
    cache_path = find_hf_cache_model_path(model_name)
    ready_path = path if is_model_ready(path) else cache_path
    files_base = ready_path or path
    files = {name: (files_base / name).exists() for name in REQUIRED_MODEL_FILES}
    return {
        "name": model_name,
        "path": str(path),
        "cache_path": str(cache_path) if cache_path else "",
        "exists": path.exists(),
        "ready": bool(ready_path),
        "files": files,
    }


def is_model_ready(path: Path) -> bool:
    return path.exists() and all((path / name).exists() for name in REQUIRED_MODEL_FILES)


def find_hf_cache_model_path(model_name: str) -> Path | None:
    cache_root = PROJECT_ROOT / "runtime" / "models" / f"models--Systran--faster-whisper-{model_name}" / "snapshots"
    if not cache_root.exists():
        return None
    for candidate in sorted(cache_root.iterdir(), reverse=True):
        if candidate.is_dir() and is_model_ready(candidate):
            return candidate
    return None


def check_ffmpeg() -> dict[str, Any]:
    path = resolve_ffmpeg_path()
    return check_command(path)


def check_command(command: str) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [command, "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        return {
            "available": result.returncode == 0,
            "path": command,
            "version": (result.stdout.splitlines() or [""])[0],
            "error": "" if result.returncode == 0 else result.stderr[:500],
        }
    except Exception as exc:
        return {"available": False, "path": command, "version": "", "error": str(exc)}


def check_import(module_name: str) -> dict[str, Any]:
    try:
        __import__(module_name)
        return {"available": True, "error": ""}
    except Exception as exc:
        return {"available": False, "error": str(exc)}


def check_writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, delete=True):
            pass
        return True
    except Exception:
        return False


def emit_json(payload: dict[str, Any], pretty: bool) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None))
    return 0 if payload.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
