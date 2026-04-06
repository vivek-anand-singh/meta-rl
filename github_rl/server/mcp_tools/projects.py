"""Project tools: projects_list, projects_get, projects_write."""

import json

from . import register_tool, resolve_repo


@register_tool("projects_list")
def projects_list(conn, method="list_projects", owner="", project_number=None, **kw):
    if method == "list_projects":
        rows = conn.execute("SELECT * FROM projects").fetchall()
        return json.dumps({"projects": [dict(r) for r in rows], "total_count": len(rows)})

    if method == "list_project_items":
        if not project_number:
            return json.dumps({"error": "project_number required"})
        proj = conn.execute("SELECT id FROM projects WHERE id = ?", (project_number,)).fetchone()
        if not proj:
            return json.dumps({"error": f"Project #{project_number} not found"})
        rows = conn.execute(
            "SELECT pi.*, i.number as issue_number, i.title as issue_title, i.status as issue_status "
            "FROM project_items pi JOIN issues i ON pi.issue_id = i.id WHERE pi.project_id = ?",
            (proj["id"],),
        ).fetchall()
        return json.dumps({"items": [dict(r) for r in rows], "total_count": len(rows)})

    return json.dumps({"error": f"Unknown method '{method}'"})


@register_tool("projects_get")
def projects_get(conn, owner="", project_number=None, **kw):
    proj = conn.execute("SELECT * FROM projects WHERE id = ?", (project_number,)).fetchone()
    if not proj:
        return json.dumps({"error": f"Project #{project_number} not found"})
    d = dict(proj)
    items = conn.execute(
        "SELECT pi.*, i.number as issue_number, i.title as issue_title "
        "FROM project_items pi JOIN issues i ON pi.issue_id = i.id WHERE pi.project_id = ?",
        (proj["id"],),
    ).fetchall()
    d["items"] = [dict(r) for r in items]
    return json.dumps(d)


@register_tool("projects_write")
def projects_write(conn, method="create_project", owner="", repo="", project_number=None,
                   name=None, description=None, item_type=None, item_owner=None,
                   item_repo=None, issue_number=None, item_id=None, updated_field=None,
                   column_name=None, **kw):
    if method == "create_project":
        if not name:
            return json.dumps({"error": "name required"})
        repo_row = conn.execute("SELECT id FROM repos WHERE name = ?", (repo or item_repo or "",)).fetchone()
        repo_id = repo_row["id"] if repo_row else 1
        conn.execute(
            "INSERT INTO projects (repo_id, name, description) VALUES (?, ?, ?)",
            (repo_id, name, description or ""),
        )
        conn.commit()
        pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        return json.dumps({"id": pid, "name": name})

    if method == "add_project_item":
        if not project_number:
            return json.dumps({"error": "project_number required"})
        if not issue_number:
            return json.dumps({"error": "issue_number required"})
        r_repo = item_repo or repo
        repo_id = resolve_repo(conn, item_owner or owner, r_repo)
        issue = conn.execute(
            "SELECT id FROM issues WHERE repo_id = ? AND number = ?", (repo_id, issue_number)
        ).fetchone()
        if not issue:
            return json.dumps({"error": f"Issue #{issue_number} not found"})
        conn.execute(
            "INSERT INTO project_items (project_id, issue_id, column_name) VALUES (?, ?, ?)",
            (project_number, issue["id"], column_name or "Todo"),
        )
        conn.execute("UPDATE issues SET project_id = ? WHERE id = ?", (project_number, issue["id"]))
        conn.commit()
        iid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        return json.dumps({"id": iid, "project_number": project_number, "issue_number": issue_number})

    if method == "update_project_item":
        if not item_id:
            return json.dumps({"error": "item_id required"})
        if column_name:
            conn.execute("UPDATE project_items SET column_name = ? WHERE id = ?", (column_name, item_id))
        if updated_field and isinstance(updated_field, dict):
            if "value" in updated_field and updated_field.get("id") == "column_name":
                conn.execute("UPDATE project_items SET column_name = ? WHERE id = ?", (updated_field["value"], item_id))
        conn.commit()
        return json.dumps({"id": item_id, "updated": True})

    if method == "delete_project_item":
        if not item_id:
            return json.dumps({"error": "item_id required"})
        conn.execute("DELETE FROM project_items WHERE id = ?", (item_id,))
        conn.commit()
        return json.dumps({"id": item_id, "deleted": True})

    return json.dumps({"error": f"Unknown method '{method}'"})
