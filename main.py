"""User-facing entry point for AI 外脑.

Running ``python main.py`` starts the local Web Console. Agent automation and
JSON workflows should continue to use ``agent_cli.py`` subcommands directly.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bootstrap_runtime import ensure_project_venv


ensure_project_venv()


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from update_checker import check_and_update  # noqa: E402
from web_console.server import DEFAULT_HOST, DEFAULT_PORT, console_payload, run_console  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-outbrain",
        description="Start the local AI 外脑 Web Console.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Local bind host. Only localhost is supported.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Preferred local port.")
    parser.add_argument("--no-browser", action="store_true", help="Start without opening a browser window.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print startup JSON.")
    parser.add_argument("--version", action="version", version="AI 外脑 Web Console 0.1.0")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload = console_payload(args.host, args.port)
    payload["update"] = check_and_update(PROJECT_ROOT)
    print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None))
    if args.no_browser:
        return 0
    run_console(args.host, args.port, open_browser=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
