"""Label tools: label_write, list_labels, get_label."""

import json

from . import register_tool, resolve_repo


@register_tool("label_write")
def label_write(conn, method="create", owner="", repo="", name="",
                new_name=None, color=None, description=None, **kw):
    repo_id = resolve_repo(conn, owner, repo)

    if method == "create":
        existing = conn.execute(
            "SELECT id FROM labels WHERE repo_id = ? AND name = ?", (repo_id, name)
        ).fetchone()
        if existing:
            return json.dumps({"error": f"Label '{name}' already exists"})
        conn.execute(
            "INSERT INTO labels (repo_id, name, color, description) VALUES (?, ?, ?, ?)",
            (repo_id, name, color or "ededed", description or ""),
        )
        conn.commit()
        lid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        return json.dumps({"id": lid, "name": name, "message": f"Label '{name}' created"})

    if method == "update":
        lbl = conn.execute(
            "SELECT id FROM labels WHERE repo_id = ? AND name = ?", (repo_id, name)
        ).fetchone()
        if not lbl:
            return json.dumps({"error": f"Label '{name}' not found"})
        updates, vals = [], []
        if new_name:
            updates.append("name = ?"); vals.append(new_name)
        if color:
            updates.append("color = ?"); vals.append(color)
        if description is not None:
            updates.append("description = ?"); vals.append(description)
        if updates:
            vals.append(lbl["id"])
            conn.execute(f"UPDATE labels SET {', '.join(updates)} WHERE id = ?", vals)
            conn.commit()
        return json.dumps({"message": f"Label '{name}' updated"})

    if method == "delete":
        lbl = conn.execute(
            "SELECT id FROM labels WHERE repo_id = ? AND name = ?", (repo_id, name)
        ).fetchone()
        if not lbl:
            return json.dumps({"error": f"Label '{name}' not found"})
        conn.execute("DELETE FROM issue_labels WHERE label_id = ?", (lbl["id"],))
        conn.execute("DELETE FROM labels WHERE id = ?", (lbl["id"],))
        conn.commit()
        return json.dumps({"message": f"Label '{name}' deleted"})

    return json.dumps({"error": f"Unknown method '{method}'"})


@register_tool("list_labels")
def list_labels(conn, owner="", repo="", **kw):
    repo_id = resolve_repo(conn, owner, repo)
    rows = conn.execute("SELECT * FROM labels WHERE repo_id = ?", (repo_id,)).fetchall()
    return json.dumps({"labels": [dict(r) for r in rows], "total_count": len(rows)})


@register_tool("get_label")
def get_label(conn, owner="", repo="", name="", **kw):
    repo_id = resolve_repo(conn, owner, repo)
    row = conn.execute(
        "SELECT * FROM labels WHERE repo_id = ? AND name = ?", (repo_id, name)
    ).fetchone()
    if not row:
        return json.dumps({"error": f"Label '{name}' not found"})
    return json.dumps(dict(row))
