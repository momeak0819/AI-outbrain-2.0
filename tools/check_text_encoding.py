"""Read-only UTF-8 and mojibake health check for public project text files."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


TEXT_SUFFIXES = {".py", ".md", ".json", ".ini", ".txt"}
EXCLUDED_PARTS = {
    ".agents",
    ".cache",
    ".claude",
    ".claudian",
    ".cleanup_backup",
    ".git",
    ".mypy_cache",
    ".obsidian",
    ".ruff_cache",
    ".venv",
    ".workbuddy",
    ".workflow",
    "__pycache__",
    "logs",
    "outputs",
    "runtime",
    "tmp",
    "temp",
    "venv",
}
EXCLUDED_DIR_PREFIXES = (
    ".release_check",
    ".release_runtime_dev_check",
)
EXCLUDED_NAMES = {"config.ini", ".env"}
VAULT_ROOT = Path("Obsidian") / "AI外脑知识库"
PUBLIC_VAULT_FILES = {
    VAULT_ROOT / "_知识卡片模板.md",
    VAULT_ROOT / "🏠_AI学习外脑.md",
    VAULT_ROOT / "00_Inbox" / "_Inbox索引.md",
    VAULT_ROOT / "01_AI术语库" / "_术语库索引.md",
    VAULT_ROOT / "02_模型能力库" / "_模型库索引.md",
    VAULT_ROOT / "03_AI工具库" / "_工具库索引.md",
    VAULT_ROOT / "04_工作流库" / "_工作流库索引.md",
    VAULT_ROOT / "05_智能体库" / "_智能体库索引.md",
    VAULT_ROOT / "06_案例库" / "_案例库索引.md",
    VAULT_ROOT / "07_GitHub库" / "_GitHub库索引.md",
    VAULT_ROOT / "08_项目映射库" / "_项目映射索引.md",
    VAULT_ROOT / "09_输出库" / "_输出库索引.md",
}

# Keep the signatures escaped so this scanner does not match its own source.
MOJIBAKE_SIGNATURES = tuple(
    value.encode("ascii").decode("unicode_escape")
    for value in (
        r"\u93b6\u682d\u716d",
        r"\u95c3\u62bd\u4ff6",
        r"\u9433\u30e8\u7627",
        r"\u59af\u2033\u7037",
        r"\u6769\u64b3\u5686",
        r"\u5bee\u546d\u5bda\u93cd",
    )
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str
    snippet: str
    message: str


def should_scan(relative: Path) -> bool:
    if relative.suffix.lower() not in TEXT_SUFFIXES:
        return False
    if relative.name in EXCLUDED_NAMES or relative.name.endswith((".tmp", ".bak")):
        return False
    if any(part.lower() in EXCLUDED_PARTS for part in relative.parts):
        return False
    if any(
        part.lower().startswith(EXCLUDED_DIR_PREFIXES)
        for part in relative.parts[:-1]
    ):
        return False
    if relative.parts and relative.parts[0] == "Obsidian":
        return relative in PUBLIC_VAULT_FILES
    return True


def iter_text_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file() and should_scan(path.relative_to(root)):
            yield path


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _snippet(line: str, limit: int = 160) -> str:
    cleaned = line.replace("\x00", "\\0").strip()
    return cleaned if len(cleaned) <= limit else f"{cleaned[: limit - 1]}…"


def scan_file(path: Path, root: Path) -> tuple[list[Finding], list[Finding]]:
    relative = path.relative_to(root).as_posix()
    data = path.read_bytes()
    issues: list[Finding] = []
    warnings: list[Finding] = []

    if data.startswith(b"\xef\xbb\xbf"):
        warnings.append(
            Finding(relative, 1, "utf8_bom", "", "UTF-8 BOM present; no rewrite performed.")
        )

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        line = data[: exc.start].count(b"\n") + 1
        raw_line = data.splitlines()[line - 1] if data.splitlines() else data
        issues.append(
            Finding(
                relative,
                line,
                "invalid_utf8",
                _snippet(raw_line.decode("utf-8", errors="replace")),
                str(exc),
            )
        )
        return issues, warnings

    for kind, token, message in (
        ("replacement_character", "\ufffd", "Unicode replacement character U+FFFD found."),
        ("nul_character", "\x00", "NUL character found in a maintained text file."),
    ):
        start = 0
        while True:
            offset = text.find(token, start)
            if offset < 0:
                break
            line = _line_number(text, offset)
            issues.append(
                Finding(relative, line, kind, _snippet(text.splitlines()[line - 1]), message)
            )
            start = offset + len(token)

    for signature in MOJIBAKE_SIGNATURES:
        start = 0
        while True:
            offset = text.find(signature, start)
            if offset < 0:
                break
            line = _line_number(text, offset)
            issues.append(
                Finding(
                    relative,
                    line,
                    "mojibake",
                    _snippet(text.splitlines()[line - 1]),
                    f"High-confidence mojibake signature detected: {signature}",
                )
            )
            start = offset + len(signature)

    return issues, warnings


def scan_project(root: Path) -> dict[str, object]:
    root = root.resolve()
    files = list(iter_text_files(root))
    issues: list[Finding] = []
    warnings: list[Finding] = []
    for path in files:
        file_issues, file_warnings = scan_file(path, root)
        issues.extend(file_issues)
        warnings.extend(file_warnings)
    return {
        "ok": not issues,
        "root": str(root),
        "files_scanned": len(files),
        "issues": [asdict(item) for item in issues],
        "warnings": [asdict(item) for item in warnings],
    }


def format_report(report: dict[str, object]) -> str:
    lines = [
        f"UTF-8 text scan: {'clean' if report['ok'] else 'FAILED'}",
        f"Root: {report['root']}",
        f"Files scanned: {report['files_scanned']}",
    ]
    warnings = report["warnings"]
    issues = report["issues"]
    if warnings:
        lines.append(f"Warnings: {len(warnings)}")
        for item in warnings:
            lines.append(
                f"  [warning:{item['kind']}] {item['path']}:{item['line']} {item['message']}"
            )
    if issues:
        lines.append(f"Issues: {len(issues)}")
        for item in issues:
            lines.append(
                f"  [{item['kind']}] {item['path']}:{item['line']} "
                f"{item['message']} | {item['snippet']}"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check maintained project text for invalid UTF-8 and high-confidence mojibake."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Project root to scan.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args(argv)
    report = scan_project(args.root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_report(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
