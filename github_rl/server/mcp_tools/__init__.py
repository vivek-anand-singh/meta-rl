"""MCP tool registry and dispatcher."""

import json
import sqlite3
from typing import Callable

TOOL_REGISTRY: dict[str, Callable] = {}


def register_tool(name: str):
    def decorator(func):
        TOOL_REGISTRY[name] = func
        return func
    return decorator


def dispatch_tool(conn: sqlite3.Connection, tool_name: str, args: dict) -> str:
    handler = TOOL_REGISTRY.get(tool_name)
    if handler is None:
        return json.dumps({
            "error": f"Unknown tool '{tool_name}'",
            "available_tools": sorted(TOOL_REGISTRY.keys()),
        })
    try:
        return handler(conn, **args)
    except Exception as e:
        return json.dumps({"error": f"{tool_name} failed: {str(e)}"})


def get_available_tools() -> list[str]:
    return sorted(TOOL_REGISTRY.keys())


def resolve_repo(conn: sqlite3.Connection, owner: str, repo: str) -> int:
    row = conn.execute("SELECT id FROM repos WHERE name = ?", (repo,)).fetchone()
    if not row:
        raise ValueError(f"Repository '{owner}/{repo}' not found")
    return row["id"]


def resolve_branch(conn: sqlite3.Connection, repo_id: int, branch_name: str) -> int:
    row = conn.execute(
        "SELECT id FROM branches WHERE repo_id = ? AND name = ?",
        (repo_id, branch_name),
    ).fetchone()
    if not row:
        raise ValueError(f"Branch '{branch_name}' not found")
    return row["id"]


def resolve_default_branch(conn: sqlite3.Connection, repo_id: int) -> tuple[str, int]:
    repo = conn.execute("SELECT default_branch FROM repos WHERE id = ?", (repo_id,)).fetchone()
    branch_name = repo["default_branch"] if repo else "main"
    branch_id = resolve_branch(conn, repo_id, branch_name)
    return branch_name, branch_id


# Import all tool modules to register them
from . import issues  # noqa: E402, F401
from . import pull_requests  # noqa: E402, F401
from . import branches  # noqa: E402, F401
from . import files  # noqa: E402, F401
from . import projects  # noqa: E402, F401
from . import labels  # noqa: E402, F401
from . import search  # noqa: E402, F401
