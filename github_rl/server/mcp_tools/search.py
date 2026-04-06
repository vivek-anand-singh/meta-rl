"""Search tools: search_code, search_pull_requests."""

import json

from . import register_tool, resolve_repo


@register_tool("search_code")
def search_code(conn, owner="", repo="", query="", **kw):
    repo_id = resolve_repo(conn, owner, repo)
    rows = conn.execute(
        "SELECT f.path, f.content, b.name as branch FROM files f "
        "JOIN branches b ON f.branch_id = b.id "
        "WHERE b.repo_id = ? AND f.content LIKE ?",
        (repo_id, f"%{query}%"),
    ).fetchall()
    results = []
    for r in rows:
        content = r["content"] or ""
        lines = content.split("\n")
        matches = [
            {"line_number": i + 1, "line": line}
            for i, line in enumerate(lines) if query.lower() in line.lower()
        ]
        results.append({"path": r["path"], "branch": r["branch"], "matches": matches})
    return json.dumps({"results": results, "total_count": len(results)})


@register_tool("search_pull_requests")
def search_pull_requests(conn, owner="", repo="", query="", **kw):
    repo_id = resolve_repo(conn, owner, repo)
    rows = conn.execute(
        "SELECT * FROM pull_requests WHERE repo_id = ? AND (title LIKE ? OR body LIKE ?)",
        (repo_id, f"%{query}%", f"%{query}%"),
    ).fetchall()
    return json.dumps({"pull_requests": [dict(r) for r in rows], "total_count": len(rows)})
