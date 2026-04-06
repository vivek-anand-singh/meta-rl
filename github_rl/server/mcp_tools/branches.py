"""Branch tools: create_branch, list_branches, get_commits."""

import json

from . import register_tool, resolve_repo, resolve_default_branch, resolve_branch
from ..db import make_sha


@register_tool("create_branch")
def create_branch(conn, owner="", repo="", branch="", from_branch=None, **kw):
    repo_id = resolve_repo(conn, owner, repo)

    existing = conn.execute(
        "SELECT id FROM branches WHERE repo_id = ? AND name = ?", (repo_id, branch)
    ).fetchone()
    if existing:
        return json.dumps({"error": f"Branch '{branch}' already exists"})

    if from_branch:
        source_id = resolve_branch(conn, repo_id, from_branch)
    else:
        _, source_id = resolve_default_branch(conn, repo_id)

    conn.execute(
        "INSERT INTO branches (repo_id, name, base_branch) VALUES (?, ?, ?)",
        (repo_id, branch, from_branch or "main"),
    )
    new_branch_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    source_files = conn.execute("SELECT path, content FROM files WHERE branch_id = ?", (source_id,)).fetchall()
    for f in source_files:
        conn.execute(
            "INSERT INTO files (branch_id, path, content) VALUES (?, ?, ?)",
            (new_branch_id, f["path"], f["content"]),
        )

    conn.commit()
    sha = make_sha(branch)
    return json.dumps({
        "ref": f"refs/heads/{branch}",
        "url": f"/{owner}/{repo}/tree/{branch}",
        "object": {"sha": sha, "type": "commit"},
    })


@register_tool("list_branches")
def list_branches(conn, owner="", repo="", **kw):
    repo_id = resolve_repo(conn, owner, repo)
    rows = conn.execute("SELECT * FROM branches WHERE repo_id = ?", (repo_id,)).fetchall()
    return json.dumps({"branches": [{"name": r["name"], "base_branch": r["base_branch"]} for r in rows]})


@register_tool("get_commits")
def get_commits(conn, owner="", repo="", sha=None, branch=None, **kw):
    repo_id = resolve_repo(conn, owner, repo)

    if branch:
        branch_id = resolve_branch(conn, repo_id, branch)
        rows = conn.execute(
            "SELECT * FROM commits WHERE branch_id = ? ORDER BY id DESC", (branch_id,)
        ).fetchall()
    elif sha:
        rows = conn.execute("SELECT * FROM commits WHERE sha = ?", (sha,)).fetchall()
    else:
        rows = conn.execute(
            "SELECT c.* FROM commits c JOIN branches b ON c.branch_id = b.id WHERE b.repo_id = ? ORDER BY c.id DESC",
            (repo_id,),
        ).fetchall()

    return json.dumps({"commits": [dict(r) for r in rows]})
