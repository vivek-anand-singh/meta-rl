"""Data models for the GitHub RL Environment."""

from openenv.core.env_server.types import Action, Observation
from pydantic import Field


class GithubRlAction(Action):
    """Action: agent sends a JSON-encoded tool call."""

    message: str = Field(..., description='JSON tool call, e.g. {"tool": "issue_write", "args": {...}}')


class GithubRlObservation(Observation):
    """Observation returned after each step."""

    result: str = Field(default="", description="Tool execution result or error message")
    available_tools: list[str] = Field(default_factory=list, description="Available tool names")
    task_instructions: str = Field(default="", description="Current task instructions")
    task_progress: str = Field(default="", description="Progress summary, e.g. '2/5 criteria met'")
