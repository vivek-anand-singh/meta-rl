"""Issue tools: issue_read, issue_write, list_issues, add_issue_comment, search_issues, sub_issue_write."""

import json

from . import register_tool, resolve_repo
from ..db import get_next_number, now_iso


@register_tool("issue_read")
def issue_read(conn, method="get", owner="", repo="", issue_number=None, **kw):
    repo_id = resolve_repo(conn, owner, repo)
    issue = conn.execute(
        "SELECT * FROM issues WHERE repo_id = ? AND number = ?",
        (repo_id, issue_number),
    ).fetchone()
    if not issue:
        return json.dumps({"error": f"Issue #{issue_number} not found"})

    if method == "get":
        d = dict(issue)
        lbls = conn.execute(
            "SELECT l.name FROM labels l JOIN issue_labels il ON l.id = il.label_id WHERE il.issue_id = ?",
            (issue["id"],),
        ).fetchall()
        d["labels"] = [r["name"] for r in lbls]
        return json.dumps(d)

    if method == "get_comments":
        rows = conn.execute(
            "SELECT * FROM issue_comments WHERE issue_id = ?", (issue["id"],)
        ).fetchall()
        return json.dumps([dict(r) for r in rows])

    if method == "get_sub_issues":
        rows = conn.execute(
            "SELECT * FROM issues WHERE parent_issue_id = ?", (issue["id"],)
        ).fetchall()
        return json.dumps([dict(r) for r in rows])

    if method == "get_labels":
        rows = conn.execute(
            "SELECT l.* FROM labels l JOIN issue_labels il ON l.id = il.label_id WHERE il.issue_id = ?",
            (issue["id"],),
        ).fetchall()
        return json.dumps([dict(r) for r in rows])

    return json.dumps({"error": f"Unknown method '{method}'"})


@register_tool("issue_write")
def issue_write(conn, method="create", owner="", repo="", title=None, body=None,
                assignees=None, labels=None, state=None, state_reason=None,
                issue_number=None, assignee=None, **kw):
    repo_id = resolve_repo(conn, owner, repo)
    assignee_val = assignee or (assignees[0] if assignees else None)

    if method == "create":
        if not title:
            return json.dumps({"error": "title is required for create"})
        num = get_next_number(conn, "issues", repo_id)
        conn.execute(
            "INSERT INTO issues (repo_id, number, title, body, assignee, created_by) VALUES (?, ?, ?, ?, ?, ?)",
            (repo_id, num, title, body or "", assignee_val, "agent"),
        )
        issue_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        if labels:
            for lbl_name in labels:
                lbl = conn.execute(
                    "SELECT id FROM labels WHERE repo_id = ? AND name = ?", (repo_id, lbl_name)
                ).fetchone()
                if lbl:
                    conn.execute("INSERT OR IGNORE INTO issue_labels VALUES (?, ?)", (issue_id, lbl["id"]))
                else:
                    conn.execute(
                        "INSERT INTO labels (repo_id, name) VALUES (?, ?)", (repo_id, lbl_name)
                    )
                    new_lbl_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    conn.execute("INSERT INTO issue_labels VALUES (?, ?)", (issue_id, new_lbl_id))

        conn.commit()
        return json.dumps({"id": issue_id, "number": num, "url": f"/{owner}/{repo}/issues/{num}"})

    if method == "update":
        if not issue_number:
            return json.dumps({"error": "issue_number required for update"})
        issue = conn.execute(
            "SELECT id FROM issues WHERE repo_id = ? AND number = ?", (repo_id, issue_number)
        ).fetchone()
        if not issue:
            return json.dumps({"error": f"Issue #{issue_number} not found"})

        updates = []
        vals = []
        if title is not None:
            updates.append("title = ?"); vals.append(title)
        if body is not None:
            updates.append("body = ?"); vals.append(body)
        if state is not None:
            updates.append("status = ?"); vals.append(state.lower())
        if assignee_val is not None:
            updates.append("assignee = ?"); vals.append(assignee_val)

        if updates:
            vals.append(issue["id"])
            conn.execute(f"UPDATE issues SET {', '.join(updates)} WHERE id = ?", vals)

        if labels:
            conn.execute("DELETE FROM issue_labels WHERE issue_id = ?", (issue["id"],))
            for lbl_name in labels:
                lbl = conn.execute(
                    "SELECT id FROM labels WHERE repo_id = ? AND name = ?", (repo_id, lbl_name)
                ).fetchone()
                if lbl:
                    conn.execute("INSERT OR IGNORE INTO issue_labels VALUES (?, ?)", (issue["id"], lbl["id"]))
                else:
                    conn.execute("INSERT INTO labels (repo_id, name) VALUES (?, ?)", (repo_id, lbl_name))
                    new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    conn.execute("INSERT INTO issue_labels VALUES (?, ?)", (issue["id"], new_id))

        conn.commit()
        return json.dumps({"id": issue["id"], "url": f"/{owner}/{repo}/issues/{issue_number}"})

    return json.dumps({"error": f"Unknown method '{method}'"})


@register_tool("list_issues")
def list_issues(conn, owner="", repo="", state=None, labels=None, orderBy=None,
                direction=None, **kw):
    repo_id = resolve_repo(conn, owner, repo)
    query = "SELECT * FROM issues WHERE repo_id = ?"
    params: list = [repo_id]

    if state:
        query += " AND status = ?"
        params.append(state.lower())

    order_col = {"CREATED_AT": "id", "UPDATED_AT": "id", "COMMENTS": "id"}.get(
        (orderBy or "").upper(), "id"
    )
    order_dir = "DESC" if (direction or "").upper() == "DESC" else "ASC"
    query += f" ORDER BY {order_col} {order_dir}"

    rows = conn.execute(query, params).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        lbls = conn.execute(
            "SELECT l.name FROM labels l JOIN issue_labels il ON l.id = il.label_id WHERE il.issue_id = ?",
            (r["id"],),
        ).fetchall()
        d["labels"] = [l["name"] for l in lbls]
        result.append(d)

    if labels:
        label_set = set(l.lower() for l in labels)
        result = [r for r in result if label_set & set(l.lower() for l in r["labels"])]

    return json.dumps({"issues": result, "total_count": len(result)})


@register_tool("add_issue_comment")
def add_issue_comment(conn, owner="", repo="", issue_number=None, body="", **kw):
    repo_id = resolve_repo(conn, owner, repo)
    issue = conn.execute(
        "SELECT id FROM issues WHERE repo_id = ? AND number = ?", (repo_id, issue_number)
    ).fetchone()
    if not issue:
        return json.dumps({"error": f"Issue #{issue_number} not found"})

    conn.execute(
        "INSERT INTO issue_comments (issue_id, author, body, created_at) VALUES (?, ?, ?, ?)",
        (issue["id"], "agent", body, now_iso()),
    )
    conn.commit()
    cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return json.dumps({"id": cid, "url": f"/{owner}/{repo}/issues/{issue_number}#comment-{cid}"})


@register_tool("search_issues")
def search_issues(conn, owner="", repo="", query="", **kw):
    repo_id = resolve_repo(conn, owner, repo)
    rows = conn.execute(
        "SELECT * FROM issues WHERE repo_id = ? AND (title LIKE ? OR body LIKE ?)",
        (repo_id, f"%{query}%", f"%{query}%"),
    ).fetchall()
    return json.dumps({"issues": [dict(r) for r in rows], "total_count": len(rows)})


@register_tool("sub_issue_write")
def sub_issue_write(conn, owner="", repo="", issue_number=None, sub_issue_number=None, **kw):
    repo_id = resolve_repo(conn, owner, repo)
    parent = conn.execute(
        "SELECT id FROM issues WHERE repo_id = ? AND number = ?", (repo_id, issue_number)
    ).fetchone()
    child = conn.execute(
        "SELECT id FROM issues WHERE repo_id = ? AND number = ?", (repo_id, sub_issue_number)
    ).fetchone()
    if not parent:
        return json.dumps({"error": f"Parent issue #{issue_number} not found"})
    if not child:
        return json.dumps({"error": f"Sub-issue #{sub_issue_number} not found"})

    conn.execute("UPDATE issues SET parent_issue_id = ? WHERE id = ?", (parent["id"], child["id"]))
    conn.commit()
    return json.dumps({"parent": issue_number, "child": sub_issue_number, "linked": True})
