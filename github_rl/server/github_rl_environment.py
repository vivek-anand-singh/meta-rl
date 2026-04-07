"""GitHub RL Environment Implementation."""

import json
import sqlite3
from typing import Any, Optional
from uuid import uuid4

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import State

try:
    from ..models import GithubRlAction, GithubRlObservation
except (ImportError, ModuleNotFoundError):
    from models import GithubRlAction, GithubRlObservation

try:
    from .db import create_tables, seed_database, reset_database
    from .mcp_tools import dispatch_tool, get_available_tools
    from .grader import grade_task, load_task
except (ImportError, ModuleNotFoundError):
    from server.db import create_tables, seed_database, reset_database
    from server.mcp_tools import dispatch_tool, get_available_tools
    from server.grader import grade_task, load_task


class GithubRlEnvironment(Environment):
    """Sandboxed GitHub simulation environment for RL training.

    Each instance owns an in-memory SQLite DB. Agents interact via JSON tool
    calls that mirror the GitHub MCP server API.
    """

    SUPPORTS_CONCURRENT_SESSIONS: bool = True
    MAX_STEPS: int = 20

    def __init__(self):
        super().__init__()
        self._state = State(episode_id=None, step_count=0)
        self.conn: Optional[sqlite3.Connection] = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        create_tables(self.conn)
        self.current_task: Optional[dict] = load_task()
        seed_database(self.conn, self.current_task.get("seed", {}))

    def reset(
        self,
        seed: Optional[int] = None,
        episode_id: Optional[str] = None,
        **kwargs: Any,
    ) -> GithubRlObservation:
        if self.conn:
            self.conn.close()

        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        create_tables(self.conn)

        difficulty = kwargs.get("difficulty")
        task_id = kwargs.get("task_id")
        self.current_task = load_task(task_id=task_id, difficulty=difficulty, seed=seed)
        seed_database(self.conn, self.current_task.get("seed", {}))

        self._state = State(
            episode_id=episode_id or str(uuid4()),
            step_count=0,
        )

        criteria = self.current_task.get("eval_criteria", [])

        # Provide repo context so the agent knows valid owner/repo names
        repos = self.conn.execute("SELECT name, description FROM repos").fetchall()
        repo_lines = [f"  - owner=acme repo={r['name']} ({r['description']})" for r in repos]
        repo_context = "\n".join(repo_lines)
        reset_msg = (
            "Environment reset. Available repositories:\n"
            f"{repo_context}\n"
            "Use owner='acme' and the repo name shown above in all tool calls."
        )

        return GithubRlObservation(
            result=reset_msg,
            available_tools=get_available_tools(),
            task_instructions=self.current_task.get("instructions", ""),
            task_progress=f"0/{len(criteria)} criteria met",
            done=False,
            reward=0.0,
        )

    def step(
        self,
        action: GithubRlAction,
        timeout_s: Optional[float] = None,
        **kwargs: Any,
    ) -> GithubRlObservation:
        self._state.step_count += 1

        # Parse JSON tool call from action message
        try:
            parsed = json.loads(action.message)
            tool_name = parsed.get("tool", "")
            tool_args = parsed.get("args", {})
        except (json.JSONDecodeError, AttributeError) as e:
            return self._make_obs(
                result=f"Error: Invalid JSON — {e}. Expected format: {{\"tool\": \"name\", \"args\": {{...}}}}",
                reward=0.0,
            )

        if not tool_name:
            return self._make_obs(
                result="Error: Missing 'tool' field. Expected: {\"tool\": \"name\", \"args\": {...}}",
                reward=0.0,
            )

        # Dispatch tool
        result = dispatch_tool(self.conn, tool_name, tool_args)

        # Grade
        criteria = self.current_task.get("eval_criteria", []) if self.current_task else []
        reward, progress = grade_task(self.conn, criteria)

        # Done conditions
        max_steps = self.current_task.get("max_steps", self.MAX_STEPS) if self.current_task else self.MAX_STEPS
        all_done = reward >= 0.9999
        out_of_steps = self._state.step_count >= max_steps
        done = all_done or out_of_steps

        return self._make_obs(result=result, reward=reward, progress=progress, done=done)

    def _make_obs(self, result: str, reward: float = 0.0, progress: str = "", done: bool = False) -> GithubRlObservation:
        return GithubRlObservation(
            result=result,
            available_tools=get_available_tools(),
            task_instructions=self.current_task.get("instructions", "") if self.current_task else "",
            task_progress=progress,
            done=done,
            reward=reward,
        )

    @property
    def state(self) -> State:
        return self._state

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None
