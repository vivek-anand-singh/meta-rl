"""Inference script for the GitHub RL environment.

Runs an LLM agent against the environment via the OpenAI client + HF Router.
Usage: uv run inference.py
"""

import asyncio
import json
import os
import subprocess
import sys
import time

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
HF_TOKEN = os.getenv("HF_TOKEN", "")
DOCKER_IMAGE_NAME = os.getenv("DOCKER_IMAGE_NAME", "github_rl")
ENV_URL = os.getenv("ENV_URL", "http://localhost:8000")
MAX_TURNS = 15

SYSTEM_PROMPT = """You are a GitHub operations agent. You interact with a simulated GitHub environment by sending JSON tool calls.

## Action Format
Send a single JSON object per turn:
{"tool": "<tool_name>", "args": {<arguments>}}

## Available Tools
- issue_read(method, owner, repo, issue_number) — method: get/get_comments/get_sub_issues/get_labels
- issue_write(method, owner, repo, title, body, assignees, labels, state, issue_number) — method: create/update
- list_issues(owner, repo, state, labels)
- add_issue_comment(owner, repo, issue_number, body)
- search_issues(owner, repo, query)
- sub_issue_write(owner, repo, issue_number, sub_issue_number)
- pull_request_read(owner, repo, pullNumber)
- create_pull_request(owner, repo, title, head, base, body)
- update_pull_request(owner, repo, pullNumber, title, body, state, assignee, linked_issues)
- merge_pull_request(owner, repo, pullNumber, commit_title, merge_method)
- list_pull_requests(owner, repo, state)
- pull_request_review_write(owner, repo, pullNumber, body, event) — event: APPROVE/REQUEST_CHANGES/COMMENT
- add_reply_to_pull_request_comment(owner, repo, pullNumber, comment_id, body)
- update_pull_request_branch(owner, repo, pullNumber)
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

## Rules
1. Respond with ONLY a JSON tool call. No explanations.
2. One tool call per turn.
3. Read the task instructions carefully and complete all required steps.
"""


def format_observation(obs: dict) -> str:
    parts = []
    if obs.get("task_instructions"):
        parts.append(f"TASK: {obs['task_instructions']}")
    if obs.get("result"):
        parts.append(f"RESULT: {obs['result']}")
    if obs.get("task_progress"):
        parts.append(f"PROGRESS: {obs['task_progress']}")
    return "\n".join(parts)


def run_inference():
    import requests

    client = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN)

    # Reset environment
    print("[START] Resetting environment...")
    resp = requests.post(f"{ENV_URL}/reset", json={}, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    obs = data.get("observation", data)
    reward = data.get("reward", 0.0)
    done = data.get("done", False)

    print(f"[RESET] Task: {obs.get('task_instructions', 'N/A')}")
    print(f"[RESET] Tools: {len(obs.get('available_tools', []))} available")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": format_observation(obs)},
    ]

    for turn in range(MAX_TURNS):
        if done:
            break

        print(f"\n[STEP {turn + 1}] Generating action...")
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                temperature=0.1,
                max_tokens=512,
            )
            action_text = response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[ERROR] LLM call failed: {e}")
            break

        print(f"[ACTION] {action_text[:200]}")
        messages.append({"role": "assistant", "content": action_text})

        # Step environment
        try:
            resp = requests.post(
                f"{ENV_URL}/step",
                json={"action": {"message": action_text}},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[ERROR] Step failed: {e}")
            break

        obs = data.get("observation", data)
        reward = data.get("reward", 0.0)
        done = data.get("done", False)

        print(f"[RESULT] {obs.get('result', 'N/A')[:200]}")
        print(f"[REWARD] {reward} | [PROGRESS] {obs.get('task_progress', 'N/A')} | [DONE] {done}")

        messages.append({"role": "user", "content": format_observation(obs)})

    print(f"\n[END] Final reward: {reward} | Steps: {turn + 1}")
    return reward


if __name__ == "__main__":
    run_inference()
