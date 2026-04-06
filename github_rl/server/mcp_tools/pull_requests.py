"""Pull request tools."""

import json

from . import register_tool, resolve_repo, resolve_branch
from ..db import get_next_number, now_iso, make_sha


@register_tool("pull_request_read")
def pull_request_read(conn, owner="", repo="", pullNumber=None, **kw):
    repo_id = resolve_repo(conn, owner, repo)
    pr = conn.execute(
        "SELECT * FROM pull_requests WHERE repo_id = ? AND number = ?",
        (repo_id, pullNumber),
    ).fetchone()
    if not pr:
        return json.dumps({"error": f"PR #{pullNumber} not found"})
    d = dict(pr)
    reviews = conn.execute("SELECT * FROM pr_reviews WHERE pr_id = ?", (pr["id"],)).fetchall()
    d["reviews"] = [dict(r) for r in reviews]
    comments = conn.execute("SELECT * FROM pr_comments WHERE pr_id = ?", (pr["id"],)).fetchall()
    d["comments"] = [dict(r) for r in comments]
    linked = conn.execute(
        "SELECT i.number, i.title FROM issues i JOIN pr_linked_issues pl ON i.id = pl.issue_id WHERE pl.pr_id = ?",
        (pr["id"],),
    ).fetchall()
    d["linked_issues"] = [dict(r) for r in linked]
    return json.dumps(d)


@register_tool("create_pull_request")
def create_pull_request(conn, owner="", repo="", title="", head="", base="main",
                        body=None, draft=False, **kw):
    repo_id = resolve_repo(conn, owner, repo)
    resolve_branch(conn, repo_id, head)
    num = get_next_number(conn, "pull_requests", repo_id)
    conn.execute(
        "INSERT INTO pull_requests (repo_id, number, title, body, head_branch, base_branch, author) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (repo_id, num, title, body or "", head, base, "agent"),
    )
    conn.commit()
    pr_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return json.dumps({"id": pr_id, "number": num, "url": f"/{owner}/{repo}/pull/{num}"})


@register_tool("update_pull_request")
def update_pull_request(conn, owner="", repo="", pullNumber=None, title=None,
                        body=None, state=None, assignees=None, assignee=None,
                        linked_issues=None, **kw):
    repo_id = resolve_repo(conn, owner, repo)
    pr = conn.execute(
        "SELECT id FROM pull_requests WHERE repo_id = ? AND number = ?",
        (repo_id, pullNumber),
    ).fetchone()
    if not pr:
        return json.dumps({"error": f"PR #{pullNumber} not found"})

    updates, vals = [], []
    if title is not None:
        updates.append("title = ?"); vals.append(title)
    if body is not None:
        updates.append("body = ?"); vals.append(body)
    if state is not None:
        updates.append("status = ?"); vals.append(state.lower())
    assignee_val = assignee or (assignees[0] if assignees else None)
    if assignee_val is not None:
        updates.append("assignee = ?"); vals.append(assignee_val)

    if updates:
        vals.append(pr["id"])
        conn.execute(f"UPDATE pull_requests SET {', '.join(updates)} WHERE id = ?", vals)

    if linked_issues:
        for issue_num in linked_issues:
            issue = conn.execute(
                "SELECT id FROM issues WHERE repo_id = ? AND number = ?", (repo_id, issue_num)
            ).fetchone()
            if issue:
                conn.execute("INSERT OR IGNORE INTO pr_linked_issues VALUES (?, ?)", (pr["id"], issue["id"]))

    conn.commit()
    return json.dumps({"id": pr["id"], "url": f"/{owner}/{repo}/pull/{pullNumber}"})


@register_tool("merge_pull_request")
def merge_pull_request(conn, owner="", repo="", pullNumber=None, commit_title=None,
                       commit_message=None, merge_method="merge", **kw):
    repo_id = resolve_repo(conn, owner, repo)
    pr = conn.execute(
        "SELECT * FROM pull_requests WHERE repo_id = ? AND number = ?",
        (repo_id, pullNumber),
    ).fetchone()
    if not pr:
        return json.dumps({"error": f"PR #{pullNumber} not found"})
    if pr["status"] != "open":
        return json.dumps({"error": f"PR #{pullNumber} is {pr['status']}, cannot merge"})
    if pr["has_conflicts"]:
        return json.dumps({"error": f"PR #{pullNumber} has merge conflicts"})

    head_branch_id = resolve_branch(conn, repo_id, pr["head_branch"])
    _, base_branch_id = conn.execute(
        "SELECT name, id FROM branches WHERE repo_id = ? AND name = ?",
        (repo_id, pr["base_branch"]),
    ).fetchone() or (None, None)
    if base_branch_id is None:
        return json.dumps({"error": f"Base branch '{pr['base_branch']}' not found"})

    head_files = conn.execute("SELECT path, content FROM files WHERE branch_id = ?", (head_branch_id,)).fetchall()
    for f in head_files:
        existing = conn.execute(
            "SELECT id FROM files WHERE branch_id = ? AND path = ?",
            (base_branch_id, f["path"]),
        ).fetchone()
        if existing:
            conn.execute("UPDATE files SET content = ? WHERE id = ?", (f["content"], existing["id"]))
        else:
            conn.execute(
                "INSERT INTO files (branch_id, path, content) VALUES (?, ?, ?)",
                (base_branch_id, f["path"], f["content"]),
            )

    sha = make_sha(f"merge-{pullNumber}")
    conn.execute(
        "INSERT INTO commits (branch_id, message, author, sha, created_at) VALUES (?, ?, ?, ?, ?)",
        (base_branch_id, commit_title or f"Merge PR #{pullNumber}", "agent", sha, now_iso()),
    )
    conn.execute(
        "UPDATE pull_requests SET status = 'merged', merge_method = ? WHERE id = ?",
        (merge_method, pr["id"]),
    )
    conn.commit()
    return json.dumps({"sha": sha, "merged": True, "message": f"PR #{pullNumber} merged"})


@register_tool("list_pull_requests")
def list_pull_requests(conn, owner="", repo="", state=None, **kw):
    repo_id = resolve_repo(conn, owner, repo)
    query = "SELECT * FROM pull_requests WHERE repo_id = ?"
    params: list = [repo_id]
    if state:
        query += " AND status = ?"
        params.append(state.lower())
    rows = conn.execute(query, params).fetchall()
    return json.dumps({"pull_requests": [dict(r) for r in rows], "total_count": len(rows)})


@register_tool("pull_request_review_write")
def pull_request_review_write(conn, owner="", repo="", pullNumber=None, body="",
                              event="COMMENT", reviewer=None, **kw):
    repo_id = resolve_repo(conn, owner, repo)
    pr = conn.execute(
        "SELECT id FROM pull_requests WHERE repo_id = ? AND number = ?",
        (repo_id, pullNumber),
    ).fetchone()
    if not pr:
        return json.dumps({"error": f"PR #{pullNumber} not found"})

    status_map = {"APPROVE": "approved", "REQUEST_CHANGES": "changes_requested", "COMMENT": "commented"}
    status = status_map.get(event.upper(), "commented")
    conn.execute(
        "INSERT INTO pr_reviews (pr_id, reviewer, status, body) VALUES (?, ?, ?, ?)",
        (pr["id"], reviewer or "agent", status, body),
    )
    conn.commit()
    rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return json.dumps({"id": rid, "status": status, "url": f"/{owner}/{repo}/pull/{pullNumber}#review-{rid}"})


@register_tool("add_reply_to_pull_request_comment")
def add_reply_to_pull_request_comment(conn, owner="", repo="", pullNumber=None,
                                      comment_id=None, body="", **kw):
    repo_id = resolve_repo(conn, owner, repo)
    pr = conn.execute(
        "SELECT id FROM pull_requests WHERE repo_id = ? AND number = ?",
        (repo_id, pullNumber),
    ).fetchone()
    if not pr:
        return json.dumps({"error": f"PR #{pullNumber} not found"})

    conn.execute(
        "INSERT INTO pr_comments (pr_id, author, body, reply_to_id) VALUES (?, ?, ?, ?)",
        (pr["id"], "agent", body, comment_id),
    )
    conn.commit()
    cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return json.dumps({"id": cid, "url": f"/{owner}/{repo}/pull/{pullNumber}#comment-{cid}"})


@register_tool("update_pull_request_branch")
def update_pull_request_branch(conn, owner="", repo="", pullNumber=None, **kw):
    repo_id = resolve_repo(conn, owner, repo)
    pr = conn.execute(
        "SELECT * FROM pull_requests WHERE repo_id = ? AND number = ?",
        (repo_id, pullNumber),
    ).fetchone()
    if not pr:
        return json.dumps({"error": f"PR #{pullNumber} not found"})

    head_branch_id = resolve_branch(conn, repo_id, pr["head_branch"])
    base_branch_id = resolve_branch(conn, repo_id, pr["base_branch"])

    base_files = conn.execute("SELECT path, content FROM files WHERE branch_id = ?", (base_branch_id,)).fetchall()
    for f in base_files:
        existing = conn.execute(
            "SELECT id FROM files WHERE branch_id = ? AND path = ?",
            (head_branch_id, f["path"]),
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO files (branch_id, path, content) VALUES (?, ?, ?)",
                (head_branch_id, f["path"], f["content"]),
            )

    conn.execute("UPDATE pull_requests SET has_conflicts = 0 WHERE id = ?", (pr["id"],))
    conn.commit()
    return json.dumps({"message": f"Branch '{pr['head_branch']}' updated with '{pr['base_branch']}'"})
