"""File tools: get_file_contents, create_or_update_file, delete_file, push_files, get_repository_tree."""

import json

from . import register_tool, resolve_repo, resolve_branch, resolve_default_branch
from ..db import make_sha, now_iso


def _resolve_ref_branch(conn, repo_id, ref=None, branch=None):
    if branch:
        return resolve_branch(conn, repo_id, branch)
    if ref:
        name = ref.replace("refs/heads/", "")
        return resolve_branch(conn, repo_id, name)
    _, branch_id = resolve_default_branch(conn, repo_id)
    return branch_id


@register_tool("get_file_contents")
def get_file_contents(conn, owner="", repo="", path="/", ref=None, **kw):
    repo_id = resolve_repo(conn, owner, repo)
    branch_id = _resolve_ref_branch(conn, repo_id, ref=ref)

    if path == "/" or path == "":
        rows = conn.execute("SELECT path FROM files WHERE branch_id = ?", (branch_id,)).fetchall()
        return json.dumps([{"path": r["path"], "type": "file"} for r in rows])

    row = conn.execute(
        "SELECT * FROM files WHERE branch_id = ? AND path = ?", (branch_id, path)
    ).fetchone()
    if not row:
        return json.dumps({"error": f"File '{path}' not found"})
    return json.dumps({"path": row["path"], "content": row["content"], "size": len(row["content"] or "")})


@register_tool("create_or_update_file")
def create_or_update_file(conn, owner="", repo="", path="", content="",
                          message="", branch=None, sha=None, **kw):
    repo_id = resolve_repo(conn, owner, repo)
    if branch:
        branch_id = resolve_branch(conn, repo_id, branch)
    else:
        _, branch_id = resolve_default_branch(conn, repo_id)

    existing = conn.execute(
        "SELECT id FROM files WHERE branch_id = ? AND path = ?", (branch_id, path)
    ).fetchone()

    if existing:
        conn.execute("UPDATE files SET content = ? WHERE id = ?", (content, existing["id"]))
    else:
        conn.execute(
            "INSERT INTO files (branch_id, path, content) VALUES (?, ?, ?)",
            (branch_id, path, content),
        )

    commit_sha = make_sha(path + content)
    conn.execute(
        "INSERT INTO commits (branch_id, message, author, sha, created_at) VALUES (?, ?, ?, ?, ?)",
        (branch_id, message or f"Update {path}", "agent", commit_sha, now_iso()),
    )
    conn.commit()
    return json.dumps({"content": {"path": path, "sha": commit_sha}, "commit": {"sha": commit_sha, "message": message}})


@register_tool("delete_file")
def delete_file(conn, owner="", repo="", path="", message="", branch=None, sha=None, **kw):
    repo_id = resolve_repo(conn, owner, repo)
    if branch:
        branch_id = resolve_branch(conn, repo_id, branch)
    else:
        _, branch_id = resolve_default_branch(conn, repo_id)

    existing = conn.execute(
        "SELECT id FROM files WHERE branch_id = ? AND path = ?", (branch_id, path)
    ).fetchone()
    if not existing:
        return json.dumps({"error": f"File '{path}' not found"})

    conn.execute("DELETE FROM files WHERE id = ?", (existing["id"],))
    commit_sha = make_sha(f"delete-{path}")
    conn.execute(
        "INSERT INTO commits (branch_id, message, author, sha, created_at) VALUES (?, ?, ?, ?, ?)",
        (branch_id, message or f"Delete {path}", "agent", commit_sha, now_iso()),
    )
    conn.commit()
    return json.dumps({"commit": {"sha": commit_sha, "message": message}, "deleted": True})


@register_tool("push_files")
def push_files(conn, owner="", repo="", branch="", files=None, message="", **kw):
    repo_id = resolve_repo(conn, owner, repo)
    branch_id = resolve_branch(conn, repo_id, branch)

    if not files:
        return json.dumps({"error": "No files provided"})

    for f in files:
        path, content = f.get("path", ""), f.get("content", "")
        existing = conn.execute(
            "SELECT id FROM files WHERE branch_id = ? AND path = ?", (branch_id, path)
        ).fetchone()
        if existing:
            conn.execute("UPDATE files SET content = ? WHERE id = ?", (content, existing["id"]))
        else:
            conn.execute(
                "INSERT INTO files (branch_id, path, content) VALUES (?, ?, ?)",
                (branch_id, path, content),
            )

    commit_sha = make_sha(message)
    conn.execute(
        "INSERT INTO commits (branch_id, message, author, sha, created_at) VALUES (?, ?, ?, ?, ?)",
        (branch_id, message or "Push files", "agent", commit_sha, now_iso()),
    )
    conn.commit()
    return json.dumps({
        "sha": commit_sha,
        "url": f"/{owner}/{repo}/commit/{commit_sha}",
        "files_pushed": len(files),
    })


@register_tool("get_repository_tree")
def get_repository_tree(conn, owner="", repo="", ref=None, **kw):
    repo_id = resolve_repo(conn, owner, repo)
    branch_id = _resolve_ref_branch(conn, repo_id, ref=ref)
    rows = conn.execute("SELECT path FROM files WHERE branch_id = ?", (branch_id,)).fetchall()
    tree = [{"path": r["path"], "type": "blob"} for r in rows]
    return json.dumps({"tree": tree, "total_count": len(tree)})
