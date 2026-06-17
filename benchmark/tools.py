"""Sandboxed tool implementations for the goal-loop benchmark (Track 2B)."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

WORKING_DIR: Path | None = None
COMMAND_TIMEOUT = 30

ALLOWED_COMMANDS = [
    "cat ", "head ", "tail ",
    "ls ", "ls",
    "find ", "grep ", "rg ",
    "wc ", "diff ",
    "python ", "python3 ",
    "pytest ", "pytest",
    "pwd",
]

BLOCKED_PATTERNS = [
    r"\brm\b",
    r"\bmv\b",
    r"\bcurl\b",
    r"\bwget\b",
    r"\bpip\b",
    r"\bnpm\b",
    r"\bgit\b",
    r"\bchmod\b",
    r"\bchown\b",
    r"\bsudo\b",
    r"\bkill\b",
    r"\bexport\b",
    r">\s*/",
    r"\.\./\.\./",
]

TOOL_DEFINITIONS = [
    {
        "name": "read_file",
        "description": "Read the contents of a file",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "File path relative to project root"}},
            "required": ["path"],
        },
    },
    {
        "name": "edit_file",
        "description": "Replace text in a file (exact string match)",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to project root"},
                "old_text": {"type": "string", "description": "Exact text to find"},
                "new_text": {"type": "string", "description": "Replacement text"},
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
    {
        "name": "run_bash",
        "description": "Execute a bash command (sandboxed — only read commands and pytest allowed)",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string", "description": "Bash command to execute"}},
            "required": ["command"],
        },
    },
    {
        "name": "list_files",
        "description": "List files in a directory",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Directory path relative to project root"}},
            "required": ["path"],
        },
    },
]


def set_working_dir(path: Path) -> None:
    global WORKING_DIR
    WORKING_DIR = path


def execute_tool(name: str, args: dict) -> dict:
    """Dispatch a tool call to the appropriate handler."""
    handlers = {
        "read_file": _execute_read,
        "edit_file": _execute_edit,
        "run_bash": _execute_bash,
        "list_files": _execute_list,
    }
    handler = handlers.get(name)
    if not handler:
        return {"success": False, "output": f"Unknown tool: {name}"}
    return handler(**args)


def _execute_bash(command: str) -> dict:
    assert WORKING_DIR is not None

    command_stripped = command.strip()
    allowed = any(command_stripped.startswith(prefix) for prefix in ALLOWED_COMMANDS)
    if not allowed:
        return {
            "success": False,
            "output": f"Command not allowed. Permitted prefixes: {', '.join(ALLOWED_COMMANDS)}",
        }

    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, command):
            return {"success": False, "output": f"Command blocked by safety filter: {pattern}"}

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT,
            cwd=str(WORKING_DIR),
            env={**os.environ, "PATH": "/usr/local/bin:/usr/bin:/bin"},
        )
        output = result.stdout + result.stderr
        if len(output) > 5000:
            output = output[:2500] + "\n...[truncated]...\n" + output[-2500:]
        return {"success": result.returncode == 0, "output": output}
    except subprocess.TimeoutExpired:
        return {"success": False, "output": f"Command timed out after {COMMAND_TIMEOUT}s"}


def _execute_read(path: str) -> dict:
    assert WORKING_DIR is not None
    full_path = (WORKING_DIR / path).resolve()
    if not str(full_path).startswith(str(WORKING_DIR)):
        return {"success": False, "output": "Path traversal not allowed"}
    try:
        return {"success": True, "output": full_path.read_text()}
    except FileNotFoundError:
        return {"success": False, "output": f"File not found: {path}"}


def _execute_edit(path: str, old_text: str, new_text: str) -> dict:
    assert WORKING_DIR is not None
    full_path = (WORKING_DIR / path).resolve()
    if not str(full_path).startswith(str(WORKING_DIR)):
        return {"success": False, "output": "Path traversal not allowed"}

    if "test" in str(full_path) or "manifest" in str(full_path):
        return {"success": False, "output": "Cannot edit test or manifest files"}

    try:
        content = full_path.read_text()
        if old_text not in content:
            return {"success": False, "output": "old_text not found in file"}
        count = content.count(old_text)
        if count > 1:
            return {"success": False, "output": f"old_text matches {count} locations — be more specific"}
        full_path.write_text(content.replace(old_text, new_text, 1))
        return {"success": True, "output": f"Replaced in {path}"}
    except FileNotFoundError:
        return {"success": False, "output": f"File not found: {path}"}


def _execute_list(path: str) -> dict:
    assert WORKING_DIR is not None
    full_path = (WORKING_DIR / path).resolve()
    if not str(full_path).startswith(str(WORKING_DIR)):
        return {"success": False, "output": "Path traversal not allowed"}
    if not full_path.is_dir():
        return {"success": False, "output": f"Not a directory: {path}"}

    entries = []
    for item in sorted(full_path.iterdir()):
        if item.name.startswith(".") or "__pycache__" in item.name:
            continue
        prefix = "d" if item.is_dir() else "f"
        entries.append(f"[{prefix}] {item.relative_to(WORKING_DIR)}")
    return {"success": True, "output": "\n".join(entries)}
