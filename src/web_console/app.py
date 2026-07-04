"""FastAPI application for the local AI 外脑 Web Console.

The console is intentionally thin: it formats project status and delegates
workflow actions to the existing CLI handlers/five-layer pipeline. It must not
call ASR, yt-dlp, FFmpeg, MCP, or Vault APIs directly.
"""

from __future__ import annotations

import argparse
import configparser
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import agent_cli
from asr.provider_registry import providers_as_dicts
from bootstrap_runtime import runtime_environment
from layers.downloaders.ytdlp_downloader import YtdlpBackendError, YtdlpDownloader
from layers.models import SourceInput
from layers.sources import DEFAULT_SOURCE_REGISTRY


PROJECT_ROOT = Path(agent_cli.PROJECT_ROOT)
STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_ALIYUN_QWEN_ASR_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


SOURCE_DISPLAY_INFO: dict[str, dict[str, Any]] = {
    "douyin": {"display_name": "抖音", "backend": "dedicated_douyin", "status": "implemented", "cookie_required": False, "kind": "视频平台", "login_url": "https://www.douyin.com/"},
    "local_audio": {"display_name": "本地音频 / MP4", "backend": "local_file", "status": "implemented", "cookie_required": False, "kind": "本地文件", "login_url": ""},
    "youtube": {"display_name": "YouTube", "backend": "yt_dlp", "status": "basic_acquisition", "cookie_required": True, "kind": "视频平台", "login_url": "https://www.youtube.com/"},
    "bilibili": {"display_name": "B站", "backend": "yt_dlp", "status": "basic_acquisition", "cookie_required": True, "kind": "视频平台", "login_url": "https://www.bilibili.com/"},
    "tiktok": {"display_name": "TikTok", "backend": "yt_dlp", "status": "basic_acquisition", "cookie_required": False, "kind": "视频平台", "login_url": "https://www.tiktok.com/"},
    "instagram": {"display_name": "Instagram", "backend": "yt_dlp", "status": "basic_acquisition", "cookie_required": True, "kind": "视频平台", "login_url": "https://www.instagram.com/"},
    "xiaohongshu": {"display_name": "小红书", "backend": "yt_dlp", "status": "basic_acquisition", "cookie_required": True, "kind": "视频平台", "login_url": "https://www.xiaohongshu.com/"},
    "twitch": {"display_name": "Twitch", "backend": "yt_dlp", "status": "basic_acquisition", "cookie_required": False, "kind": "视频平台", "login_url": "https://www.twitch.tv/"},
    "vimeo": {"display_name": "Vimeo", "backend": "yt_dlp", "status": "basic_acquisition", "cookie_required": False, "kind": "视频平台", "login_url": "https://vimeo.com/"},
    "x_video": {"display_name": "X / Twitter", "backend": "yt_dlp", "status": "basic_acquisition", "cookie_required": True, "kind": "视频平台", "login_url": "https://x.com/"},
    "generic_video": {"display_name": "通用视频链接", "backend": "yt_dlp", "status": "basic_acquisition", "cookie_required": False, "kind": "视频网页", "login_url": ""},
}


KNOWLEDGE_CATEGORIES: list[dict[str, str]] = [
    {"id": "00_Inbox", "name": "00_Inbox", "index": "_Inbox索引.md", "description": "临时收集、待审核草稿与入口缓冲区。"},
    {"id": "01_AI术语库", "name": "01_AI术语库", "index": "_术语库索引.md", "description": "AI 概念、术语、定义与解释。"},
    {"id": "02_模型能力库", "name": "02_模型能力库", "index": "_模型库索引.md", "description": "模型能力、限制、评测与使用边界。"},
    {"id": "03_AI工具库", "name": "03_AI工具库", "index": "_工具库索引.md", "description": "AI 工具、平台、插件和集成方式。"},
    {"id": "04_工作流库", "name": "04_工作流库", "index": "_工作流库索引.md", "description": "可复用工作流、操作 SOP 与自动化链路。"},
    {"id": "05_智能体库", "name": "05_智能体库", "index": "_智能体库索引.md", "description": "Agent 角色、能力、提示词与协作分工。"},
    {"id": "06_案例库", "name": "06_案例库", "index": "_案例库索引.md", "description": "案例、复盘、实践样本与经验沉淀。"},
    {"id": "07_GitHub库", "name": "07_GitHub库", "index": "_GitHub库索引.md", "description": "开源项目、仓库、代码资产与技术映射。"},
    {"id": "08_项目映射库", "name": "08_项目映射库", "index": "_项目映射索引.md", "description": "项目结构、模块关系、系统设计与版本路线。"},
    {"id": "09_输出库", "name": "09_输出库", "index": "_输出库索引.md", "description": "最终文章、报告、发布物和外部交付成果。"},
]


AGENT_SETUP_DISPLAY_NAMES: dict[str, str] = {
    "codex": "Codex",
    "qoder": "QoderWork / Qoder",
    "claude_code": "Claude Code",
    "trae": "Trae",
    "cursor": "Cursor",
    "generic": "通用 AI Coding Agent",
}

AGENT_SETUP_NOTES: dict[str, str] = {
    "codex": "把完整配置说明放进 Codex 的项目规则或会话提示中；如果支持项目级 AGENTS.md，可引用本项目 Skill 路径。",
    "qoder": "把完整配置说明放进 QoderWork 项目规则 / Agent 指令中，并让它在阶段收尾时执行 CLI。",
    "claude_code": "把最小 prompt 放入 Claude Code 项目指令或会话开头；需要它能在本项目根目录运行命令。",
    "trae": "把完整配置说明复制到 Trae 的项目规则或 Agent 记忆中；保持正式归档走审核门。",
    "cursor": "把最小 prompt 放入 Cursor Rules / 项目说明中；由 Cursor Agent 生成 memory.json 后调用 CLI。",
    "generic": "适用于任何能读取文件并运行命令的 AI coding agent。",
}


def create_app() -> FastAPI:
    app = FastAPI(title="AI 外脑 Web Console", version="0.1.0")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        config = _read_config()
        payload = {
            "success": True,
            "mode": "web-console-status",
            "initialized": agent_cli.CONFIG_PATH.exists(),
            "config_path": str(agent_cli.CONFIG_PATH),
            "project_root": str(PROJECT_ROOT),
            "runtime": runtime_environment(),
            "config": config,
            "asr": config.get("asr", {}),
            "mimo": config.get("mimo", {}),
            "output": config.get("output", {}),
            "preferences": config.get("preferences", {}),
            "mcp": _sanitize_mapping(config.get("mcp", {})),
        }
        return payload

    @app.get("/api/capabilities")
    def capabilities() -> dict[str, Any]:
        manifest = _read_manifest()
        config = _read_config(raw=True)
        return {
            "success": True,
            "mode": "web-console-capabilities",
            "inventory": manifest.get("inventory", {}),
            "components": manifest.get("components", []),
            "source_matrix": _source_capability_matrix(manifest, config=config),
            "asr_providers": _asr_provider_matrix(config=config),
            "processing_capabilities": _processing_capabilities(),
        }

    @app.get("/api/dashboard")
    def dashboard() -> dict[str, Any]:
        manifest = _read_manifest()
        config = _read_config(raw=True)
        route_report = agent_cli.build_route12_report()
        source_matrix = _source_capability_matrix(manifest, config=config)
        asr_providers = _asr_provider_matrix(config=config)
        return {
            "success": True,
            "mode": "web-console-dashboard",
            "initialized": agent_cli.CONFIG_PATH.exists(),
            "status": {
                "asr": _sanitize_mapping(config.get("asr", {})),
                "output": _sanitize_mapping(config.get("output", {})),
                "preferences": _sanitize_mapping(config.get("preferences", {})),
            },
            "summary": {
                "source_count": len(source_matrix),
                "ytdlp_source_count": sum(1 for item in source_matrix if item.get("backend") == "yt_dlp"),
                "asr_provider_count": len(asr_providers),
                "mcp_ready": bool(route_report.get("mcp_ready")),
                "curation_ready": bool(route_report.get("curation_ready")),
            },
            "source_matrix": source_matrix,
            "asr_providers": asr_providers,
            "route12": route_report,
        }

    @app.get("/api/source-settings")
    def source_settings() -> dict[str, Any]:
        config = _read_config(raw=True)
        rows = _source_capability_matrix(_read_manifest(), config=config)
        return {
            "success": True,
            "mode": "web-console-source-settings",
            "sources": [
                {
                    "source_type": row["source_type"],
                    "display_name": row["display_name"],
                    "cookie_required": row["cookie_required"],
                    "cookie_configured": row["cookie_configured"],
                    "cookie_file": "***" if row["cookie_file_configured"] else "",
                    "cookie_file_configured": row["cookie_file_configured"],
                    "cookie_source": row["cookie_source"],
                    "cookies_from_browser": row["cookies_from_browser"],
                    "login_url": row["login_url"],
                }
                for row in rows
            ],
        }

    @app.post("/api/source-settings")
    def update_source_settings(payload: SourceSettingsRequest) -> dict[str, Any]:
        blocked = _blocked_payload("source-settings")
        if blocked:
            return blocked
        if not agent_cli.CONFIG_PATH.exists():
            return {
                "success": False,
                "stage": "init",
                "error_code": "config_missing",
                "error": "请先完成初始化配置，再保存信源 Cookies 路径。",
                "recoverable": True,
            }
        parser = configparser.ConfigParser()
        parser.read(agent_cli.CONFIG_PATH, encoding="utf-8")
        if not parser.has_section("source_cookies"):
            parser.add_section("source_cookies")
        file_key = _cookie_config_key(payload.source_type)
        browser_key = _browser_cookie_config_key(payload.source_type)
        value = payload.cookies_file.strip()
        if value:
            parser.set("source_cookies", file_key, value)
        elif parser.has_option("source_cookies", file_key):
            parser.remove_option("source_cookies", file_key)
        browser = payload.cookies_from_browser.strip().lower()
        if browser:
            parser.set("source_cookies", browser_key, browser)
        elif parser.has_option("source_cookies", browser_key):
            parser.remove_option("source_cookies", browser_key)
        with agent_cli.CONFIG_PATH.open("w", encoding="utf-8") as handle:
            parser.write(handle)
        return {
            "success": True,
            "mode": "web-console-source-settings",
            "source_type": payload.source_type,
            "cookie_configured": bool(value or browser),
            "cookie_file": "***" if value else "",
            "cookie_file_configured": bool(value),
            "cookie_source": "file" if value else "browser" if browser else "none",
            "cookies_from_browser": browser,
            "message": (
                f"已保存：yt-dlp 将从 {browser} 浏览器读取 Cookie。未保存或展示 Cookie 内容。"
                if browser
                else "已保存 Cookie 文件路径。未读取或展示 Cookie 内容。"
                if value
                else "已清空该信源的 Cookie 配置。"
            ),
        }

    @app.post("/api/source-settings/verify-browser")
    def verify_source_browser_cookie(payload: BrowserCookieVerifyRequest) -> dict[str, Any]:
        browser = payload.cookies_from_browser.strip().lower()
        if not browser:
            return {
                "success": False,
                "verified": False,
                "error_code": "browser_not_selected",
                "error": "请先选择一个浏览器。",
                "recoverable": True,
            }
        downloader = YtdlpDownloader()
        if not downloader.is_available():
            return {
                "success": False,
                "verified": False,
                "error_code": "ytdlp_unavailable",
                "error": "当前环境未安装或无法导入 yt-dlp，无法验证浏览器 Cookie 配置。",
                "recoverable": True,
            }
        try:
            downloader.validate_browser_cookies(browser)
        except YtdlpBackendError as exc:
            return {
                "success": False,
                "verified": False,
                "error_code": "browser_cookie_unavailable",
                "error": str(exc) or "yt-dlp 无法访问所选浏览器的 Cookie 存储。",
                "recoverable": True,
            }
        return {
            "success": True,
            "verified": True,
            "source_type": payload.source_type,
            "cookies_from_browser": browser,
            "message": "已验证 yt-dlp 可使用该浏览器作为 Cookie 来源；未读取或展示 Cookie 内容。",
        }

    @app.get("/api/knowledge-structure")
    def knowledge_structure() -> dict[str, Any]:
        return {
            "success": True,
            "mode": "web-console-knowledge-structure",
            "vault_root": str(_knowledge_root()),
            "categories": _knowledge_structure(),
        }

    @app.post("/api/select-directory")
    def select_directory() -> dict[str, Any]:
        return _select_local_path(kind="directory")

    @app.post("/api/select-file")
    def select_file() -> dict[str, Any]:
        return _select_local_path(kind="file")

    @app.get("/api/route12")
    def route12() -> dict[str, Any]:
        return agent_cli.build_route12_report()

    @app.get("/api/reviews")
    def reviews() -> dict[str, Any]:
        return agent_cli.handle_review_list()

    @app.get("/api/project-memory")
    def project_memory() -> dict[str, Any]:
        recent = agent_cli.handle_project_memory_search(
            argparse.Namespace(query="", project="", tag="", limit=12)
        )
        status = agent_cli.handle_project_memory_status(
            argparse.Namespace(agent="external-agent")
        )
        return {
            "success": True,
            "mode": "web-console-project-memory",
            "status": status,
            "recent": recent.get("results", []) if recent.get("success") else [],
            "search": recent,
        }

    @app.get("/api/project-memory/status")
    def project_memory_status(agent: str = "external-agent") -> dict[str, Any]:
        return agent_cli.handle_project_memory_status(
            argparse.Namespace(agent=agent or "external-agent")
        )

    @app.get("/api/project-memory/agent-setup")
    def project_memory_agent_setup(agent: str = "generic") -> dict[str, Any]:
        return _project_memory_agent_setup(agent)

    @app.post("/api/project-memory/connection-challenge")
    def project_memory_connection_challenge(payload: ProjectMemoryConnectionRequest) -> dict[str, Any]:
        return _project_memory_connection_challenge(payload.agent)

    @app.post("/api/project-memory/verify-connection")
    def project_memory_verify_connection(payload: ProjectMemoryConnectionRequest) -> dict[str, Any]:
        return _project_memory_verify_connection(payload.agent, payload.challenge)

    @app.get("/api/project-memory/search")
    def project_memory_search(q: str = "", project: str = "", tag: str = "", limit: int = 20) -> dict[str, Any]:
        return agent_cli.handle_project_memory_search(
            argparse.Namespace(query=q, project=project, tag=tag, limit=limit)
        )

    @app.post("/api/project-memory/match")
    def project_memory_match(payload: ProjectMemoryMatchRequest) -> dict[str, Any]:
        return agent_cli.handle_project_memory_match(
            argparse.Namespace(idea=payload.idea, limit=payload.limit)
        )

    @app.post("/api/init-config")
    def init_config(payload: InitConfigRequest) -> dict[str, Any]:
        blocked = _blocked_payload("init-config")
        if blocked:
            return blocked
        args = argparse.Namespace(
            force=payload.force,
            engine=payload.engine,
            model_size=payload.model_size,
            mimo_key=payload.mimo_key,
            mimo_url=payload.mimo_url or agent_cli.DEFAULT_MIMO_API_URL,
            aliyun_qwen_asr_api_key=payload.aliyun_qwen_asr_api_key,
            aliyun_qwen_asr_base_url=payload.aliyun_qwen_asr_base_url or DEFAULT_ALIYUN_QWEN_ASR_BASE_URL,
            aliyun_qwen_asr_model=payload.aliyun_qwen_asr_model,
            tencent_asr_secret_id=payload.tencent_asr_secret_id,
            tencent_asr_secret_key=payload.tencent_asr_secret_key,
            tencent_asr_region=payload.tencent_asr_region,
            tencent_asr_engine_model_type=payload.tencent_asr_engine_model_type,
            volcengine_asr_app_id=payload.volcengine_asr_app_id,
            volcengine_asr_access_token=payload.volcengine_asr_access_token,
            volcengine_asr_cluster=payload.volcengine_asr_cluster,
            volcengine_asr_audio_url=payload.volcengine_asr_audio_url,
            output_dir=payload.output_dir,
            audio_output_dir=payload.audio_output_dir,
            export=payload.export,
            reply_mode=payload.reply_mode,
            im_content_mode=payload.im_content_mode,
            interaction_channel=payload.interaction_channel,
            skip_local_setup=payload.skip_local_setup,
            configure_mcp=payload.configure_mcp,
            skip_mcp=not payload.configure_mcp,
            keep_audio=payload.keep_audio,
            pretty=False,
        )
        result = agent_cli.handle_init_config(args)
        result.pop("mimo_key", None)
        return _sanitize_payload(result)

    @app.post("/api/ingest")
    def ingest(payload: IngestRequest) -> dict[str, Any]:
        blocked = _blocked_payload("ingest")
        if blocked:
            return blocked
        args = _ingest_namespace(payload)
        cookie_metadata = _configured_cookie_metadata(_detect_ingest_source_type(payload))
        if cookie_metadata:
            args.source_metadata = cookie_metadata
        return _sanitize_payload(agent_cli.handle_ingest(args))

    @app.post("/api/review/{review_id}/approve")
    def review_approve(review_id: str) -> dict[str, Any]:
        blocked = _blocked_payload("review-approve")
        if blocked:
            return blocked
        return agent_cli.handle_review_approve(review_id)

    @app.post("/api/review/{review_id}/revise")
    def review_revise(review_id: str, payload: ReviewReviseRequest) -> dict[str, Any]:
        blocked = _blocked_payload("review-revise")
        if blocked:
            return blocked
        return agent_cli.handle_review_revise(review_id, payload.instruction)

    @app.post("/api/review/{review_id}/cancel")
    def review_cancel(review_id: str) -> dict[str, Any]:
        blocked = _blocked_payload("review-cancel")
        if blocked:
            return blocked
        return agent_cli.handle_review_cancel(review_id)

    @app.post("/api/review/{review_id}/finalized")
    def review_finalized(review_id: str, payload: ReviewFinalizedRequest) -> dict[str, Any]:
        blocked = _blocked_payload("review-finalized")
        if blocked:
            return blocked
        report = {
            "card_written": payload.mcp_card_written,
            "index_updated": payload.mcp_index_updated,
            "card_path": payload.mcp_card_path or payload.final_card_path,
            "index_path": payload.mcp_index_path or payload.final_index_path,
        }
        return agent_cli.handle_review_finalized(
            review_id,
            payload.final_card_path,
            payload.final_index_path,
            report,
        )

    return app


class InitConfigRequest(BaseModel):
    engine: str = "mimo"
    model_size: str = "base"
    mimo_key: str = ""
    mimo_url: str = ""
    aliyun_qwen_asr_api_key: str = ""
    aliyun_qwen_asr_base_url: str = ""
    aliyun_qwen_asr_model: str = "qwen-audio-asr"
    tencent_asr_secret_id: str = ""
    tencent_asr_secret_key: str = ""
    tencent_asr_region: str = "ap-guangzhou"
    tencent_asr_engine_model_type: str = "16k_zh"
    volcengine_asr_app_id: str = ""
    volcengine_asr_access_token: str = ""
    volcengine_asr_cluster: str = ""
    volcengine_asr_audio_url: str = ""
    output_dir: str = agent_cli.DEFAULT_TRANSCRIPT_OUTPUT_DIR
    audio_output_dir: str = ""
    export: str = "md"
    reply_mode: str = "im"
    im_content_mode: str = "both"
    interaction_channel: str = "auto"
    configure_mcp: bool = False
    keep_audio: bool = False
    skip_local_setup: bool = True
    force: bool = False


class IngestRequest(BaseModel):
    input: str = ""
    source_type: str = "auto"
    url: str = ""
    text: str = ""
    audio_file: str = ""
    mode: str = ""
    engine: str = "mock"
    export: str = "both"
    output_dir: str = ""
    audio_output_dir: str = ""
    include_transcript: bool = True
    response_mode: str = "im"
    im_content_mode: str = "original"
    interaction_channel: str = "auto"
    keep_audio: bool | None = None
    skip_audio: bool = True
    mock_metadata: bool = True
    no_simplified: bool = False


class SourceSettingsRequest(BaseModel):
    source_type: str
    cookies_file: str = ""
    cookies_from_browser: str = ""


class BrowserCookieVerifyRequest(BaseModel):
    source_type: str
    cookies_from_browser: str = ""


class ProjectMemoryMatchRequest(BaseModel):
    idea: str = Field(min_length=1)
    limit: int = 5


class ProjectMemoryConnectionRequest(BaseModel):
    agent: str = "generic"
    challenge: str = ""


class ReviewReviseRequest(BaseModel):
    instruction: str = Field(min_length=1)


class ReviewFinalizedRequest(BaseModel):
    final_card_path: str
    final_index_path: str
    mcp_card_written: bool = False
    mcp_index_updated: bool = False
    mcp_card_path: str = ""
    mcp_index_path: str = ""


def _read_config(raw: bool = False) -> dict[str, dict[str, str]]:
    if not agent_cli.CONFIG_PATH.exists():
        return {}
    parser = configparser.ConfigParser()
    parser.read(agent_cli.CONFIG_PATH, encoding="utf-8")
    data = {section: dict(parser[section]) for section in parser.sections()}
    if raw:
        return data
    return {section: _sanitize_mapping(values) for section, values in data.items()}


def _read_manifest() -> dict[str, Any]:
    path = PROJECT_ROOT / "initialization_manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _source_capability_matrix(
    manifest: dict[str, Any],
    config: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    source_adapters = manifest.get("inventory", {}).get("source_adapters", [])
    config = config if config is not None else _read_config(raw=True)
    rows: list[dict[str, Any]] = []
    for source_type in source_adapters:
        info = SOURCE_DISPLAY_INFO.get(
            source_type,
            {
                "display_name": source_type,
                "backend": "unknown",
                "status": "planned",
                "cookie_required": False,
                "kind": "未分类",
            },
        )
        cookie_file = _configured_cookie_path(source_type, config=config)
        cookies_from_browser = _configured_cookie_browser(source_type, config=config)
        cookie_configured = bool(cookie_file or cookies_from_browser)
        cookie_required = bool(info["cookie_required"])
        if cookie_required and not cookie_configured:
            health, score = "needs_cookie", 45
        elif info["status"] == "implemented":
            health, score = "ready", 92
        elif info["status"] == "basic_acquisition":
            health, score = ("configured", 78) if cookie_configured else ("ready", 70)
        else:
            health, score = "reserved", 24
        rows.append(
            {
                "source_type": source_type,
                "display_name": info["display_name"],
                "kind": info["kind"],
                "login_url": info.get("login_url", ""),
                "backend": info["backend"],
                "status": info["status"],
                "display_status": _display_status(str(info["status"]), health),
                "may_require_cookies": cookie_required,
                "cookie_required": cookie_required,
                "cookie_configured": cookie_configured,
                "cookie_file_configured": bool(cookie_file),
                "cookie_source": "file" if cookie_file else "browser" if cookies_from_browser else "none",
                "cookies_from_browser": cookies_from_browser,
                "health": health,
                "health_score": score,
            }
        )
    rows.append(
        {
            "source_type": "text_input",
            "display_name": "普通文字输入",
            "kind": "文本",
            "login_url": "",
            "backend": "text_protocol",
            "status": "reserved",
            "display_status": "输入协议已存在，处理链路预留",
            "may_require_cookies": False,
            "cookie_required": False,
            "cookie_configured": False,
            "cookie_file_configured": False,
            "cookie_source": "none",
            "cookies_from_browser": "",
            "health": "reserved",
            "health_score": 22,
        }
    )
    return rows


def _asr_provider_matrix(config: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    rows = []
    for provider in providers_as_dicts():
        section = config.get(str(provider["engine_id"]), {})
        configured = any(bool(value) for value in section.values())
        score = 86 if configured and provider["status"] == "implemented" else 66 if provider["status"] == "implemented" else 30
        rows.append(
            {
                **provider,
                "configured": configured,
                "health": "configured" if configured else "not_configured",
                "health_score": score,
            }
        )
    return rows


def _processing_capabilities() -> list[dict[str, str]]:
    return [
        {"name": "音视频转文字", "status": "implemented", "description": "通过 ASR Core 统一处理音频与派生音频。"},
        {"name": "简体中文规范化", "status": "implemented", "description": "Processing Core 内置可选文本规范化。"},
        {"name": "Markdown / TXT 导出", "status": "implemented", "description": "统一导出器保留旧字段兼容。"},
        {"name": "segments 保留", "status": "implemented", "description": "ProcessingResult 支持 JSON-safe 时间片段。"},
        {"name": "纯文本直通", "status": "reserved", "description": "输入协议已存在，完整 text-only 链路预留。"},
        {"name": "文档解析", "status": "reserved", "description": "未来可接 PDF / Word / Markdown 等文档信源。"},
        {"name": "网页正文", "status": "reserved", "description": "未来用于非视频网页正文抽取。"},
        {"name": "图片 OCR", "status": "reserved", "description": "未来接入图片文字识别能力。"},
    ]


def _display_status(status: str, health: str) -> str:
    if health == "needs_cookie":
        return "需要配置 Cookies"
    if status == "implemented":
        return "已实现"
    if status == "basic_acquisition":
        return "基础获取已接入"
    if status == "reserved":
        return "预留"
    return status


def _cookie_config_key(source_type: str) -> str:
    return f"{source_type}_cookies_file"


def _browser_cookie_config_key(source_type: str) -> str:
    return f"{source_type}_cookies_from_browser"


def _configured_cookie_path(
    source_type: str,
    config: dict[str, dict[str, str]] | None = None,
) -> str:
    config = config if config is not None else _read_config(raw=True)
    return config.get("source_cookies", {}).get(_cookie_config_key(source_type), "").strip()


def _configured_cookie_browser(
    source_type: str,
    config: dict[str, dict[str, str]] | None = None,
) -> str:
    config = config if config is not None else _read_config(raw=True)
    return config.get("source_cookies", {}).get(_browser_cookie_config_key(source_type), "").strip()


def _configured_cookie_metadata(source_type: str) -> dict[str, str]:
    config = _read_config(raw=True)
    metadata: dict[str, str] = {}
    cookiefile = _configured_cookie_path(source_type, config=config)
    browser = _configured_cookie_browser(source_type, config=config)
    if cookiefile:
        metadata.update({"cookies_file": cookiefile, "cookiefile": cookiefile})
    if browser:
        metadata["cookies_from_browser"] = browser
    return metadata


def _detect_ingest_source_type(payload: IngestRequest) -> str:
    source_type = payload.source_type or "auto"
    source_input = SourceInput(
        source_type=source_type,
        url=payload.url or "",
        text=payload.text or "",
        audio_file=payload.audio_file or "",
        raw_input=payload.input or "",
        input_kind="url" if payload.input.startswith(("http://", "https://")) else "unknown",
    ).normalized()
    adapter, _ = DEFAULT_SOURCE_REGISTRY.resolve_match(source_input)
    return adapter.name if adapter else source_type


def _knowledge_root() -> Path:
    return PROJECT_ROOT / "Obsidian" / "AI外脑知识库"


def _knowledge_structure() -> list[dict[str, Any]]:
    root = _knowledge_root()
    rows: list[dict[str, Any]] = []
    for item in KNOWLEDGE_CATEGORIES:
        folder = root / item["id"]
        index_path = folder / item["index"]
        rows.append(
            {
                **item,
                "path": str(folder),
                "exists": folder.exists(),
                "index_exists": index_path.exists(),
                "requires_review": item["id"] != "00_Inbox",
            }
        )
    return rows


def _project_memory_agent_setup(agent: str) -> dict[str, Any]:
    normalized = _normalize_agent_id(agent)
    display_name = AGENT_SETUP_DISPLAY_NAMES[normalized]
    skill_path = PROJECT_ROOT / "skills" / "project-memory-capture" / "SKILL.md"
    capture_command = "python agent_cli.py project-memory-capture --payload-file memory.json --pretty"
    status_command = f"python agent_cli.py project-memory-status --agent {normalized} --pretty"
    search_command = 'python agent_cli.py project-memory-search --query "关键词" --pretty'
    match_command = 'python agent_cli.py project-memory-match --idea "新知识点" --pretty'
    memory_json_example = {
        "type": "project_memory",
        "project": "项目名称",
        "repo_path": str(PROJECT_ROOT),
        "agent": display_name,
        "source_agent": display_name,
        "session_type": "development",
        "title": "阶段标题",
        "summary": "用三到五句话总结本轮开发成果、关键变化和当前状态。",
        "completed": ["完成的功能或修复"],
        "decisions": ["已经确定的架构或产品决策"],
        "changed_areas": ["Source / Acquisition / Processing / Knowledge / Delivery / Web Console"],
        "files_touched": [],
        "tests": [],
        "risks": [],
        "technical_debt": [],
        "next_steps": [],
        "related_topics": [],
        "linked_projects": [],
    }
    minimal_prompt = (
        "当我要求记录项目记忆、阶段总结、收尾、写入项目映射库或准备切上下文时，请读取：\n"
        f"{skill_path}\n\n"
        "然后生成 memory.json，并在项目根目录执行：\n"
        f"{capture_command}\n\n"
        "不要保存原始聊天流水账，不要保存密钥、登录态或私密配置。正式归档必须走审核门。"
    )
    setup_prompt = "\n".join(
        [
            f"你现在要为 {display_name} 配置 AI 外脑项目记忆沉淀能力。",
            "",
            f"项目根目录：{PROJECT_ROOT}",
            f"Skill 路径：{skill_path}",
            "",
            "硬规则：",
            "1. 不保存原始聊天流水账，只保存结构化项目记忆。",
            "2. 不保存密钥、登录态、凭据或私密配置。",
            "3. 阶段性总结必须包含目标、成果、决策、修改范围、测试、风险、技术债和下一步。",
            "4. 工作 Agent 只调用 CLI，不直接写正式 Obsidian 分类目录。",
            "5. 正式进入 08_项目映射库 必须走 _待审核 -> approve -> finalized 审核门。",
            "",
            "触发词：记录项目记忆、阶段总结、收尾、写入项目映射库、整理这个项目、准备切上下文、生成交接。",
            "",
            "Capture 命令：",
            capture_command,
            "",
            "状态检查命令：",
            status_command,
            "",
            "搜索命令：",
            search_command,
            "",
            "新知识匹配项目命令：",
            match_command,
            "",
            AGENT_SETUP_NOTES[normalized],
        ]
    )
    return {
        "success": True,
        "mode": "project-memory-agent-setup",
        "agent": normalized,
        "display_name": display_name,
        "project_root": str(PROJECT_ROOT),
        "skill_path": str(skill_path),
        "setup_prompt": setup_prompt,
        "minimal_prompt": minimal_prompt,
        "capture_command": capture_command,
        "status_command": status_command,
        "search_command": search_command,
        "match_command": match_command,
        "memory_json_example": memory_json_example,
        "verification_steps": [
            f"在 {display_name} 中复制完整配置说明或最小 prompt。",
            f"让 {display_name} 在项目根目录运行：{status_command}",
            "让工作 Agent 生成 memory.json 并运行 capture 命令。",
            "回到 Web Console 查看最近项目记忆草稿和 Review 队列。",
        ],
    }


def _project_memory_connection_challenge(agent: str) -> dict[str, Any]:
    normalized = _normalize_agent_id(agent)
    display_name = AGENT_SETUP_DISPLAY_NAMES[normalized]
    challenge = f"pm-verify-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}"
    capture_command = "python agent_cli.py project-memory-capture --payload-file memory.json --pretty"
    memory_json_example = {
        "type": "project_memory",
        "project": "AI外脑2.0",
        "repo_path": str(PROJECT_ROOT),
        "agent": display_name,
        "source_agent": display_name,
        "session_type": "handoff",
        "title": f"项目记忆连接验证 {challenge}",
        "summary": f"这是工作 AI Agent 的项目记忆连接验证。验证码：{challenge}",
        "completed": ["工作 Agent 已读取项目记忆接入说明", "工作 Agent 正在验证 project-memory-capture CLI 落盘能力"],
        "decisions": ["项目记忆正式归档仍走 _待审核 -> approve -> finalized 审核门"],
        "changed_areas": ["Project Memory", "Web Console", "Agent Setup"],
        "files_touched": [],
        "tests": [capture_command],
        "risks": [],
        "technical_debt": [],
        "next_steps": ["回到 Web Console 点击“测试连接”"],
        "related_topics": ["project-memory", "agent-connection", challenge],
        "linked_projects": ["AI外脑2.0"],
    }
    instruction = "\n".join(
        [
            f"请在项目根目录执行一次项目记忆连接验证。验证码：{challenge}",
            "",
            "1. 创建 memory.json，内容使用下面 JSON。",
            "2. 运行：",
            capture_command,
            "3. 成功后告诉用户回到 Web Console 点击“测试连接”。",
            "",
            json.dumps(memory_json_example, ensure_ascii=False, indent=2),
        ]
    )
    return {
        "success": True,
        "mode": "project-memory-connection-challenge",
        "agent": normalized,
        "display_name": display_name,
        "challenge": challenge,
        "capture_command": capture_command,
        "instruction": instruction,
        "memory_json_example": memory_json_example,
    }


def _project_memory_verify_connection(agent: str, challenge: str) -> dict[str, Any]:
    normalized = _normalize_agent_id(agent)
    clean_challenge = (challenge or "").strip()
    if not clean_challenge:
        return {
            "success": True,
            "mode": "project-memory-verify-connection",
            "agent": normalized,
            "connected": False,
            "status": "pending",
            "message": "请先生成验证指令，再让工作 Agent 执行 capture。",
        }
    draft = _find_project_memory_draft(clean_challenge)
    review = _find_project_memory_review(clean_challenge, draft.get("path", "") if draft else "")
    if draft and review:
        return {
            "success": True,
            "mode": "project-memory-verify-connection",
            "agent": normalized,
            "connected": True,
            "status": "verified",
            "challenge": clean_challenge,
            "draft_path": draft["path"],
            "review_id": review.get("review_id", ""),
            "review_status": review.get("status", ""),
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "message": "已检测到工作 Agent 写入的项目记忆草稿和 Review 记录。",
        }
    return {
        "success": True,
        "mode": "project-memory-verify-connection",
        "agent": normalized,
        "connected": False,
        "status": "pending",
        "challenge": clean_challenge,
        "draft_path": draft.get("path", "") if draft else "",
        "review_id": review.get("review_id", "") if review else "",
        "message": "还没有发现工作 Agent 写入的验证项目记忆。",
    }


def _normalize_agent_id(agent: str) -> str:
    normalized = (agent or "generic").strip().lower().replace("-", "_")
    return normalized if normalized in AGENT_SETUP_DISPLAY_NAMES else "generic"


def _find_project_memory_draft(challenge: str) -> dict[str, str] | None:
    draft_dir = PROJECT_ROOT / "Obsidian" / "AI外脑知识库" / "00_Inbox" / "_待审核"
    if not draft_dir.exists():
        return None
    for path in sorted(draft_dir.glob("*.md"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if challenge in text and ("type: project_memory" in text or "项目记忆" in text[:500]):
            return {"path": str(path), "title": path.stem}
    return None


def _find_project_memory_review(challenge: str, draft_path: str = "") -> dict[str, Any] | None:
    review_dir = PROJECT_ROOT / ".workflow" / "reviews"
    if not review_dir.exists():
        return None
    for path in sorted(review_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        haystack = json.dumps(record, ensure_ascii=False)
        if challenge in haystack or (draft_path and str(record.get("draft_path", "")) == draft_path):
            return record
    return None


def _select_local_path(kind: str) -> dict[str, Any]:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        if kind == "directory":
            selected = filedialog.askdirectory(title="选择本地文件夹")
        else:
            selected = filedialog.askopenfilename(title="选择本地文件")
        root.destroy()
        if not selected:
            return {"success": False, "cancelled": True, "path": ""}
        return {"success": True, "path": selected}
    except Exception as exc:
        return {
            "success": False,
            "error_code": "local_picker_unavailable",
            "error": str(exc),
            "recoverable": True,
        }


def _blocked_payload(command: str) -> dict[str, Any] | None:
    return None




def _ingest_namespace(payload: IngestRequest) -> argparse.Namespace:
    return argparse.Namespace(
        input=payload.input,
        source_type=payload.source_type,
        url=payload.url,
        text=payload.text,
        audio_file=payload.audio_file,
        mode=payload.mode,
        pretty=False,
        output_dir=payload.output_dir,
        knowledge_dir=None,
        audio_output_dir=payload.audio_output_dir,
        engine=payload.engine,
        model_size="",
        device="",
        compute_type="",
        language="",
        hf_endpoint=None,
        export=payload.export,
        keep_audio=payload.keep_audio,
        skip_audio=payload.skip_audio,
        mock_metadata=payload.mock_metadata,
        no_simplified=payload.no_simplified,
        include_transcript=payload.include_transcript,
        response_mode=payload.response_mode,
        im_content_mode=payload.im_content_mode,
        interaction_channel=payload.interaction_channel,
        mimo_key=None,
        mimo_url=None,
        custom_api_key=None,
        custom_api_url=None,
        source_metadata={},
    )


SENSITIVE_MARKERS = (
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "header",
    "mimo_key",
    "password",
    "private",
    "secret",
    "secret_id",
    "secret_key",
    "token",
)


def _sanitize_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in mapping.items():
        key_text = str(key).lower()
        if key_text.endswith("_saved"):
            clean[key] = value
        elif any(marker in key_text for marker in SENSITIVE_MARKERS):
            clean[key] = "***"
        elif isinstance(value, dict):
            clean[key] = _sanitize_mapping(value)
        elif isinstance(value, list):
            clean[key] = [_sanitize_payload(item) for item in value]
        else:
            clean[key] = value
    return clean


def _sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return _sanitize_mapping(value)
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value]
    return value


app = create_app()
