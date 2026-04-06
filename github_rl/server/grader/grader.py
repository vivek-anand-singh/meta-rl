"""Grading engine: evaluate DB state against task criteria."""

import json
import os
import random
import sqlite3
from pathlib import Path

TASKS_DIR = Path(__file__).parent / "tasks"


def grade_task(conn: sqlite3.Connection, eval_criteria: list[dict]) -> tuple[float, str]:
    """Evaluate current DB state against criteria. Returns (reward, progress_str)."""
    if not eval_criteria:
        return 0.0, "0/0 criteria met"

    total_weight = 0.0
    weighted_score = 0.0
    passed = 0

    for criterion in eval_criteria:
        weight = criterion.get("weight", 1.0)
        total_weight += weight
        score = _evaluate_criterion(conn, criterion)
        weighted_score += score * weight
        if score >= 1.0:
            passed += 1

    reward = weighted_score / total_weight if total_weight > 0 else 0.0
    progress = f"{passed}/{len(eval_criteria)} criteria met"
    return round(reward, 4), progress


def _evaluate_criterion(conn: sqlite3.Connection, criterion: dict) -> float:
    check_type = criterion.get("check", "exists")
    table = criterion.get("table", "")
    params = criterion.get("params", {})

    try:
        if check_type == "exists":
            return _check_exists(conn, table, params)
        elif check_type == "not_exists":
            return 1.0 - _check_exists(conn, table, params)
        elif check_type == "field_equals":
            return _check_field_equals(conn, table, params)
        elif check_type == "field_contains":
            return _check_field_contains(conn, table, params)
        elif check_type == "count":
            return _check_count(conn, table, params)
        elif check_type == "row_count_gte":
            return _check_row_count_gte(conn, table, params)
        else:
            return 0.0
    except Exception:
        return 0.0


def _check_exists(conn: sqlite3.Connection, table: str, params: dict) -> float:
    where_clauses = []
    values = []
    for k, v in params.items():
        where_clauses.append(f"{k} = ?")
        values.append(v)
    if not where_clauses:
        return 0.0
    query = f"SELECT 1 FROM {table} WHERE {' AND '.join(where_clauses)} LIMIT 1"
    row = conn.execute(query, values).fetchone()
    return 1.0 if row else 0.0


def _check_field_equals(conn: sqlite3.Connection, table: str, params: dict) -> float:
    row_id = params.get("id")
    field = params.get("field", "")
    value = params.get("value")
    if row_id is None or not field:
        return 0.0
    row = conn.execute(f"SELECT {field} FROM {table} WHERE id = ?", (row_id,)).fetchone()
    if not row:
        return 0.0
    actual = row[0]
    if isinstance(value, str):
        return 1.0 if str(actual).lower() == value.lower() else 0.0
    return 1.0 if actual == value else 0.0


def _check_field_contains(conn: sqlite3.Connection, table: str, params: dict) -> float:
    row_id = params.get("id")
    field = params.get("field", "")
    substring = params.get("substring", "")
    if row_id is None or not field:
        return 0.0
    row = conn.execute(f"SELECT {field} FROM {table} WHERE id = ?", (row_id,)).fetchone()
    if not row or not row[0]:
        return 0.0
    return 1.0 if substring.lower() in str(row[0]).lower() else 0.0


def _check_count(conn: sqlite3.Connection, table: str, params: dict) -> float:
    expected = params.get("expected", 0)
    where = params.get("where", {})
    where_clauses = [f"{k} = ?" for k in where]
    values = list(where.values())
    query = f"SELECT COUNT(*) FROM {table}"
    if where_clauses:
        query += f" WHERE {' AND '.join(where_clauses)}"
    row = conn.execute(query, values).fetchone()
    actual = row[0] if row else 0
    return 1.0 if actual >= expected else actual / expected if expected > 0 else 0.0


def _check_row_count_gte(conn: sqlite3.Connection, table: str, params: dict) -> float:
    threshold = params.get("threshold", 1)
    where = params.get("where", {})
    where_clauses = [f"{k} = ?" for k in where]
    values = list(where.values())
    query = f"SELECT COUNT(*) FROM {table}"
    if where_clauses:
        query += f" WHERE {' AND '.join(where_clauses)}"
    row = conn.execute(query, values).fetchone()
    actual = row[0] if row else 0
    return 1.0 if actual >= threshold else 0.0


def load_task(task_id: str | None = None, difficulty: str | None = None,
              seed: int | None = None) -> dict:
    """Load a task JSON file. If task_id is None, pick randomly."""
    rng = random.Random(seed) if seed is not None else random.Random()

    all_tasks = []
    for diff_dir in TASKS_DIR.iterdir():
        if not diff_dir.is_dir():
            continue
        if difficulty and diff_dir.name != difficulty:
            continue
        for f in diff_dir.glob("*.json"):
            all_tasks.append(f)

    if task_id:
        for f in all_tasks:
            try:
                data = json.loads(f.read_text())
                if data.get("task_id") == task_id:
                    return data
            except (json.JSONDecodeError, KeyError):
                continue
        raise ValueError(f"Task '{task_id}' not found")

    if not all_tasks:
        return _fallback_task()

    chosen = rng.choice(all_tasks)
    return json.loads(chosen.read_text())


def _fallback_task() -> dict:
    """Fallback task if no JSON files found."""
    return {
        "task_id": "fallback-echo",
        "difficulty": "easy",
        "category": "issues",
        "instructions": "Close issue #1. It has been resolved.",
        "max_steps": 10,
        "seed": {
            "repos": [{"id": 1, "name": "backend", "description": "Backend API", "default_branch": "main"}],
            "branches": [{"id": 1, "repo_id": 1, "name": "main", "base_branch": "main"}],
            "issues": [{"id": 1, "repo_id": 1, "number": 1, "title": "Fix login bug", "body": "Login fails on mobile", "status": "open"}],
            "labels": [{"id": 1, "repo_id": 1, "name": "bug", "color": "d73a4a"}],
        },
        "eval_criteria": [
            {"description": "Issue #1 is closed", "table": "issues", "check": "field_equals",
             "params": {"id": 1, "field": "status", "value": "closed"}, "weight": 1.0}
        ],
    }
