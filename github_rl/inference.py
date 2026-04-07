"""
Inference Script — GitHub RL Environment
===================================
MANDATORY
- Before submitting, ensure the following variables are defined in your environment configuration:
    API_BASE_URL       The API endpoint for the LLM.
    MODEL_NAME         The model identifier to use for inference.
    HF_TOKEN           Your Hugging Face / API key.
    IMAGE_NAME         The name of the local Docker image for the environment.

STDOUT FORMAT
- The script must emit exactly three line types to stdout, in this order:

    [START] task=<task_name> env=<benchmark> model=<model_name>
    [STEP]  step=<n> action=<action_str> reward=<0.00> done=<true|false> error=<msg|null>
    [END]   success=<true|false> steps=<n> score=<score> rewards=<r1,r2,...,rn>

  Rules:
    - One [START] line at episode begin.
    - One [STEP] line per step, immediately after env.step() returns.
    - One [END] line after env.close(), always emitted (even on exception).
    - reward and rewards are formatted to 2 decimal places.
    - done and success are lowercase booleans: true or false.
    - error is the raw error string, or null if none.
    - All fields on a single line with no newlines within a line.
    - Each task should return score in [0, 1]
"""

import asyncio
import os
import textwrap
from typing import List, Optional

from openai import OpenAI

try:
    from github_rl import GithubRlAction, GithubRlEnv
except ImportError:
    from models import GithubRlAction
    from client import GithubRlEnv

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Required environment variables
# ---------------------------------------------------------------------------
API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-7B-Instruct")
HF_TOKEN = os.getenv("HF_TOKEN")

# Optional — if you use from_docker_image():
IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME", "github_rl")

TASK_NAME = os.getenv("GITHUB_RL_TASK", "github-ops")
TASK_ID = os.getenv("TASK_ID", "")          # e.g. "triage-security-issues"
DIFFICULTY = os.getenv("DIFFICULTY", "")     # e.g. "hard", "expert"
BENCHMARK = "github_rl"
MAX_STEPS = 40
TEMPERATURE = 0.1
MAX_TOKENS = 512
SUCCESS_SCORE_THRESHOLD = 0.5

SYSTEM_PROMPT = textwrap.dedent("""\
    You are a GitHub operations agent. You interact with a simulated GitHub \
    environment by sending JSON tool calls.

    ## Action Format
    Send a single JSON object per turn:
    {"tool": "<tool_name>", "args": {<arguments>}}

    ## Available Tools
    - issue_read(method, owner, repo, issue_number) — method: get/get_comments/get_sub_issues/get_labels
    - issue_write(method, owner, repo, title, body, assignees, labels, state, issue_number, assignee) — method: create/update
    - list_issues(owner, repo, state, labels)
    - add_issue_comment(owner, repo, issue_number, body)
    - search_issues(owner, repo, query)
    - sub_issue_write(owner, repo, issue_number, sub_issue_number)
    - pull_request_read(owner, repo, pullNumber)
    - create_pull_request(owner, repo, title, head, base, body, assignee, linked_issues)
    - update_pull_request(owner, repo, pullNumber, title, body, state, assignee, linked_issues)
    - merge_pull_request(owner, repo, pullNumber, commit_title, merge_method)
    - list_pull_requests(owner, repo, state)
    - pull_request_review_write(owner, repo, pullNumber, body, event) — event: APPROVE/REQUEST_CHANGES/COMMENT
    - create_branch(owner, repo, branch, from_branch)
    - list_branches(owner, repo)
    - get_file_contents(owner, repo, path, ref)
    - create_or_update_file(owner, repo, path, content, message, branch)
    - delete_file(owner, repo, path, message, branch)
    - push_files(owner, repo, branch, files, message) — files: [{"path": "...", "content": "..."}]
    - get_repository_tree(owner, repo, ref)
    - get_commits(owner, repo, branch)
    - projects_list(method, owner, project_number) — method: list_projects/list_project_items
    - projects_get(owner, project_number)
    - projects_write(method, owner, repo, project_number, name, description, issue_number, item_id, column_name) — method: create_project/add_project_item/update_project_item/delete_project_item
    - label_write(method, owner, repo, name, color, description) — method: create/update/delete
    - list_labels(owner, repo)
    - get_label(owner, repo, name)
    - search_code(owner, repo, query)
    - search_pull_requests(owner, repo, query)
    - add_reply_to_pull_request_comment(owner, repo, pullNumber, comment_id, body)
    - update_pull_request_branch(owner, repo, pullNumber)

    ## Rules
    1. Respond with ONLY a JSON tool call. No explanations.
    2. One tool call per turn.
    3. Read the task instructions carefully and complete all required steps.
    4. IMPORTANT: Use the exact owner and repo names from the RESULT after reset. Do NOT guess repo names.
    5. Read error messages carefully and adjust your next action accordingly.
""")


# ---------------------------------------------------------------------------
# Structured stdout logging — [START], [STEP], [END]
# ---------------------------------------------------------------------------
def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    action_clean = action.replace("\n", " ").replace("\r", "")
    error_val = error if error else "null"
    done_val = str(done).lower()
    print(
        f"[STEP] step={step} action={action_clean} reward={reward:.2f} done={done_val} error={error_val}",
        flush=True,
    )


def log_end(success: bool, steps: int, score: float, rewards: List[float]) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} score={score:.3f} rewards={rewards_str}",
        flush=True,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def format_observation(obs) -> str:
    """Format observation into a user prompt for the LLM."""
    parts = []
    if obs.task_instructions:
        parts.append(f"TASK: {obs.task_instructions}")
    if obs.result:
        parts.append(f"RESULT: {obs.result}")
    if obs.task_progress:
        parts.append(f"PROGRESS: {obs.task_progress}")
    return "\n".join(parts)


def get_model_action(client: OpenAI, messages: list) -> tuple[str, bool]:
    """Call the LLM and return (action_string, success_bool)."""
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            stream=False,
        )
        text = (completion.choices[0].message.content or "").strip()
        if not text:
            return '{"tool": "list_issues", "args": {"owner": "acme", "repo": "backend"}}', True
        return text, True
    except Exception as exc:
        print(f"[DEBUG] Model request failed: {exc}", flush=True)
        return "", False


# ---------------------------------------------------------------------------
# Main inference loop
# ---------------------------------------------------------------------------
async def main() -> None:
    client = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN)
    env = await GithubRlEnv.from_docker_image(IMAGE_NAME)

    rewards: List[float] = []
    steps_taken = 0
    score = 0.0
    success = False

    log_start(task=TASK_ID or DIFFICULTY or TASK_NAME, env=BENCHMARK, model=MODEL_NAME)

    try:
        reset_kwargs = {}
        if TASK_ID:
            reset_kwargs["task_id"] = TASK_ID
        if DIFFICULTY:
            reset_kwargs["difficulty"] = DIFFICULTY
        result = await env.reset(**reset_kwargs)
        obs = result.observation

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": format_observation(obs)},
        ]

        consecutive_failures = 0
        max_consecutive_failures = 3

        for step in range(1, MAX_STEPS + 1):
            if result.done:
                break

            action_text, api_ok = get_model_action(client, messages)

            if not api_ok:
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive_failures:
                    print(f"[DEBUG] {max_consecutive_failures} consecutive API failures, stopping early", flush=True)
                    break
                continue
            consecutive_failures = 0

            messages.append({"role": "assistant", "content": action_text})

            result = await env.step(GithubRlAction(message=action_text))
            obs = result.observation

            reward = result.reward or 0.0
            done = result.done
            error = None

            rewards.append(reward)
            steps_taken = step

            log_step(step=step, action=action_text, reward=reward, done=done, error=error)

            messages.append({"role": "user", "content": format_observation(obs)})

            if done:
                break

        # Final reward is the task score (grader returns cumulative 0.0–1.0)
        score = rewards[-1] if rewards else 0.0
        score = min(max(score, 0.0), 1.0)
        success = score >= SUCCESS_SCORE_THRESHOLD

    finally:
        try:
            await env.close()
        except Exception as e:
            print(f"[DEBUG] env.close() error: {e}", flush=True)
        log_end(success=success, steps=steps_taken, score=score, rewards=rewards)


if __name__ == "__main__":
    asyncio.run(main())
