"""GitHub RL Environment Client."""

from typing import Dict

from openenv.core import EnvClient
from openenv.core.client_types import StepResult
from openenv.core.env_server.types import State

from .models import GithubRlAction, GithubRlObservation


class GithubRlEnv(
    EnvClient[GithubRlAction, GithubRlObservation, State]
):
    """Client for the GitHub RL Environment.

    Maintains a persistent WebSocket connection to the environment server.
    Each client instance has its own dedicated environment session.

    Example:
        >>> async with GithubRlEnv(base_url="http://localhost:8000") as client:
        ...     result = await client.reset()
        ...     print(result.observation.task_instructions)
        ...     result = await client.step(GithubRlAction(
        ...         message='{"tool": "list_issues", "args": {"owner": "acme", "repo": "backend"}}'
        ...     ))
        ...     print(result.observation.result)
    """

    def _step_payload(self, action: GithubRlAction) -> Dict:
        return {"message": action.message}

    def _parse_result(self, payload: Dict) -> StepResult[GithubRlObservation]:
        obs_data = payload.get("observation", {})
        observation = GithubRlObservation(
            result=obs_data.get("result", ""),
            available_tools=obs_data.get("available_tools", []),
            task_instructions=obs_data.get("task_instructions", ""),
            task_progress=obs_data.get("task_progress", ""),
            done=payload.get("done", False),
            reward=payload.get("reward"),
        )
        return StepResult(
            observation=observation,
            reward=payload.get("reward"),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: Dict) -> State:
        return State(
            episode_id=payload.get("episode_id"),
            step_count=payload.get("step_count", 0),
        )
