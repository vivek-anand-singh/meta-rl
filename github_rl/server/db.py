"""SQLite database layer for the GitHub RL environment."""

import json
import hashlib
import sqlite3
from datetime import datetime, timezone


TABLES = [
    "repos", "branches", "commits", "files", "labels", "issues",
    "issue_labels", "issue_comments", "pull_requests", "pr_linked_issues",
    "pr_reviews", "pr_comments", "projects", "project_items",
]

DDL = """
CREATE TABLE IF NOT EXISTS repos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    default_branch TEXT DEFAULT 'main'
);
CREATE TABLE IF NOT EXISTS branches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    base_branch TEXT DEFAULT 'main',
    FOREIGN KEY (repo_id) REFERENCES repos(id)
);
CREATE TABLE IF NOT EXISTS commits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_id INTEGER NOT NULL,
    message TEXT NOT NULL,
    author TEXT DEFAULT 'agent',
    sha TEXT,
    created_at TEXT,
    FOREIGN KEY (branch_id) REFERENCES branches(id)
);
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_id INTEGER NOT NULL,
    path TEXT NOT NULL,
    content TEXT DEFAULT '',
    FOREIGN KEY (branch_id) REFERENCES branches(id)
);
CREATE TABLE IF NOT EXISTS labels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    color TEXT DEFAULT 'ededed',
    description TEXT DEFAULT '',
    FOREIGN KEY (repo_id) REFERENCES repos(id)
);
CREATE TABLE IF NOT EXISTS issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL,
    number INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT DEFAULT '',
    status TEXT DEFAULT 'open',
    assignee TEXT,
    parent_issue_id INTEGER,
    project_id INTEGER,
    created_by TEXT DEFAULT 'user',
    FOREIGN KEY (repo_id) REFERENCES repos(id)
);
CREATE TABLE IF NOT EXISTS issue_labels (
    issue_id INTEGER NOT NULL,
    label_id INTEGER NOT NULL,
    PRIMARY KEY (issue_id, label_id)
);
CREATE TABLE IF NOT EXISTS issue_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER NOT NULL,
    author TEXT DEFAULT 'agent',
    body TEXT NOT NULL,
    created_at TEXT,
    FOREIGN KEY (issue_id) REFERENCES issues(id)
);
CREATE TABLE IF NOT EXISTS pull_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL,
    number INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT DEFAULT '',
    status TEXT DEFAULT 'open',
    head_branch TEXT NOT NULL,
    base_branch TEXT DEFAULT 'main',
    author TEXT DEFAULT 'user',
    merge_method TEXT,
    has_conflicts INTEGER DEFAULT 0,
    assignee TEXT,
    FOREIGN KEY (repo_id) REFERENCES repos(id)
);
CREATE TABLE IF NOT EXISTS pr_linked_issues (
    pr_id INTEGER NOT NULL,
    issue_id INTEGER NOT NULL,
    PRIMARY KEY (pr_id, issue_id)
);
CREATE TABLE IF NOT EXISTS pr_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_id INTEGER NOT NULL,
    reviewer TEXT DEFAULT 'agent',
    status TEXT NOT NULL,
    body TEXT DEFAULT '',
    FOREIGN KEY (pr_id) REFERENCES pull_requests(id)
);
CREATE TABLE IF NOT EXISTS pr_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_id INTEGER NOT NULL,
    author TEXT DEFAULT 'agent',
    body TEXT NOT NULL,
    file_path TEXT,
    line_number INTEGER,
    reply_to_id INTEGER,
    FOREIGN KEY (pr_id) REFERENCES pull_requests(id)
);
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT DEFAULT 'open',
    FOREIGN KEY (repo_id) REFERENCES repos(id)
);
CREATE TABLE IF NOT EXISTS project_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    issue_id INTEGER NOT NULL,
    column_name TEXT DEFAULT 'Todo',
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (issue_id) REFERENCES issues(id)
);
"""


def create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    conn.commit()


def seed_database(conn: sqlite3.Connection, seed_data: dict) -> None:
    """Insert seed rows into tables. Keys in seed_data match table names."""
    table_columns = {
        "repos": ["id", "name", "description", "default_branch"],
        "branches": ["id", "repo_id", "name", "base_branch"],
        "commits": ["id", "branch_id", "message", "author", "sha", "created_at"],
        "files": ["id", "branch_id", "path", "content"],
        "labels": ["id", "repo_id", "name", "color", "description"],
        "issues": ["id", "repo_id", "number", "title", "body", "status", "assignee", "parent_issue_id", "project_id", "created_by"],
        "issue_labels": ["issue_id", "label_id"],
        "issue_comments": ["id", "issue_id", "author", "body", "created_at"],
        "pull_requests": ["id", "repo_id", "number", "title", "body", "status", "head_branch", "base_branch", "author", "merge_method", "has_conflicts", "assignee"],
        "pr_linked_issues": ["pr_id", "issue_id"],
        "pr_reviews": ["id", "pr_id", "reviewer", "status", "body"],
        "pr_comments": ["id", "pr_id", "author", "body", "file_path", "line_number", "reply_to_id"],
        "projects": ["id", "repo_id", "name", "description", "status"],
        "project_items": ["id", "project_id", "issue_id", "column_name"],
    }

    for table_name, columns in table_columns.items():
        rows = seed_data.get(table_name, [])
        for row in rows:
            present_cols = [c for c in columns if c in row]
            placeholders = ", ".join("?" for _ in present_cols)
            col_names = ", ".join(present_cols)
            values = [row[c] for c in present_cols]
            conn.execute(
                f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})",
                values,
            )
    conn.commit()


def get_next_number(conn: sqlite3.Connection, table: str, repo_id: int) -> int:
    row = conn.execute(
        f"SELECT COALESCE(MAX(number), 0) + 1 as next_num FROM {table} WHERE repo_id = ?",
        (repo_id,),
    ).fetchone()
    return row["next_num"] if row else 1


def make_sha(content: str = "") -> str:
    return hashlib.sha1(
        f"{content}{datetime.now(timezone.utc).isoformat()}".encode()
    ).hexdigest()[:12]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db_snapshot(conn: sqlite3.Connection) -> dict:
    snapshot = {}
    for table in TABLES:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        snapshot[table] = [dict(r) for r in rows]
    return snapshot


def reset_database(conn: sqlite3.Connection) -> None:
    for table in reversed(TABLES):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.commit()
    create_tables(conn)
