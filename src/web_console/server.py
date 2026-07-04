"""Launcher for the local Web Console."""

from __future__ import annotations

import socket
import webbrowser
from dataclasses import dataclass
from typing import Any


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


@dataclass(frozen=True)
class ConsoleServerInfo:
    host: str
    port: int
    url: str


def find_available_port(host: str = DEFAULT_HOST, preferred_port: int = DEFAULT_PORT) -> int:
    for port in [preferred_port, *range(preferred_port + 1, preferred_port + 50)]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No available local port near {preferred_port}")


def run_console(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    open_browser: bool = True,
    log_level: str = "info",
) -> ConsoleServerInfo:
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("Web Console only supports localhost binding.")
    selected_port = find_available_port(host, port)
    url = f"http://{host}:{selected_port}"
    if open_browser:
        webbrowser.open(url)
    import uvicorn

    uvicorn.run(
        "web_console.app:app",
        host=host,
        port=selected_port,
        log_level=log_level,
        access_log=False,
    )
    return ConsoleServerInfo(host=host, port=selected_port, url=url)


def console_payload(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> dict[str, Any]:
    selected_port = find_available_port(host, port)
    return {
        "success": True,
        "mode": "console",
        "host": host,
        "port": selected_port,
        "url": f"http://{host}:{selected_port}",
    }

