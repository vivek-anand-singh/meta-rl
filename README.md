---
title: GitHub RL Environment
emoji: 🔧
colorFrom: green
colorTo: pink
sdk: docker
pinned: false
app_port: 8000
base_path: /web
tags:
  - openenv
---

# GitHub RL Environment

A simulated GitHub environment for training RL agents on real-world repository operations. Agents interact with a sandboxed GitHub-like API to perform issue triage, incident response, project management, and pull request workflows.

## Motivation

DevOps and repository management tasks are a core part of software engineering, yet there are no standardized RL environments for training agents on these workflows. This environment fills that gap by providing a deterministic, graded simulation of GitHub operations with 10 tasks across 4 difficulty levels.

## Action Space

**GithubRlAction** - A single JSON-encoded tool call per step:

```python
class GithubRlAction(Action):
    message: str  # JSON tool call, e.g. {"tool": "issue_write", "args": {...}}
```

30 tools available: `issue_read`, `issue_write`, `list_issues`, `add_issue_comment`, `search_issues`, `sub_issue_write`, `pull_request_read`, `create_pull_request`, `update_pull_request`, `merge_pull_request`, `list_pull_requests`, `pull_request_review_write`, `add_reply_to_pull_request_comment`, `update_pull_request_branch`, `create_branch`, `list_branches`, `get_file_contents`, `create_or_update_file`, `delete_file`, `push_files`, `get_repository_tree`, `get_commits`, `projects_list`, `projects_get`, `projects_write`, `label_write`, `list_labels`, `get_label`, `search_code`, `search_pull_requests`.

## Observation Space

**GithubRlObservation** - Returned after each step:

```python
class GithubRlObservation(Observation):
    result: str              # Tool execution result (JSON)
    available_tools: list[str]  # Available tool names
    task_instructions: str   # Current task description
    task_progress: str       # e.g. "3/10 criteria met"
```

## Tasks (10 total, 4 difficulty levels)

### Easy (3 tasks, max 5 steps)
| Task ID | Description | Criteria |
|---------|-------------|----------|
| `close-resolved-issue` | Close a resolved issue | 1 criterion |
| `create-bug-report` | Create an issue with specific title and body | 2 criteria |
| `label-bug-issue` | Add correct label to an issue | 1 criterion |

### Medium (3 tasks, max 10 steps)
| Task ID | Description | Criteria |
|---------|-------------|----------|
| `triage-single-bug` | Label, assign, and comment on a bug | 4 criteria |
| `close-with-resolution` | Close one issue with comment, update another | 4 criteria |
| `hotfix-branch-and-pr` | Create branch, open PR, link to issue | 3 criteria |

### Hard (2 tasks, max 30 steps)
| Task ID | Description | Criteria |
|---------|-------------|----------|
| `triage-security-issues` | Read TEAM.md and SECURITY_POLICY.md, triage 5 security issues, skip 2 distractors, create summary | 24 criteria |
| `create-security-audit-board` | Read AUDIT_PLAN.md, set up project board with 5 issues in correct columns, close completed items, create final report | 17 criteria |

### Expert (2 tasks, max 40 steps)
| Task ID | Description | Criteria |
|---------|-------------|----------|
| `zero-day-incident-response` | Read INCIDENT_PLAYBOOK.md, investigate code, full incident response with advisory, sub-tasks, hotfix branch, patched code, PR, timeline | 19 criteria |
| `secure-feature-workflow` | Read CONTRIBUTING.md, full feature dev workflow with project board, sub-issues, feature branch, implementation, config, PR | 19 criteria |

## Reward Design

- Rewards are **weighted sums** of individual criteria scores, normalized to [0.0, 1.0]
- Each criterion contributes partial credit independently
- Progress is reported as "X/Y criteria met" after each step
- Episode ends when all criteria are met (reward >= 0.9999) or max steps reached
- No negative rewards; score monotonically increases unless the agent takes destructive actions (e.g., deleting project items)

## Baseline Scores (Qwen2.5-7B-Instruct)

| Difficulty | Expected Score Range |
|------------|---------------------|
| Easy | 0.8 - 1.0 |
| Medium | 0.5 - 0.8 |
| Hard | 0.1 - 0.4 |
| Expert | 0.2 - 0.5 |

## Setup

### Docker (recommended)

```bash
docker build -t github_rl .
docker run -d -p 8000:8000 github_rl
```

### Local development

```bash
uv sync
uv run server
```

### Running inference

```bash
API_BASE_URL="https://router.huggingface.co/v1" \
MODEL_NAME="Qwen/Qwen2.5-7B-Instruct" \
HF_TOKEN="your-hf-token" \
uv run inference.py
```

Select specific tasks:

```bash
TASK_ID=triage-security-issues HF_TOKEN=... uv run inference.py
DIFFICULTY=hard HF_TOKEN=... uv run inference.py
```

### Deploying to Hugging Face Spaces

```bash
openenv push
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `API_BASE_URL` | No | `https://router.huggingface.co/v1` | LLM API endpoint |
| `MODEL_NAME` | No | `Qwen/Qwen2.5-7B-Instruct` | Model identifier |
| `HF_TOKEN` | Yes | - | HuggingFace API token |
| `LOCAL_IMAGE_NAME` | No | `github_rl` | Docker image name |
| `TASK_ID` | No | - | Specific task to run |
| `DIFFICULTY` | No | - | Filter tasks by difficulty |

## Project Structure

```
github_rl/
├── inference.py              # Baseline inference script
├── openenv.yaml              # OpenEnv manifest
├── pyproject.toml            # Dependencies
├── Dockerfile                # Container definition
├── models.py                 # GithubRlAction, GithubRlObservation
├── client.py                 # GithubRlEnv client
├── __init__.py               # Module exports
└── server/
    ├── app.py                # FastAPI application
    ├── github_rl_environment.py  # Environment (reset/step/state)
    ├── db.py                 # SQLite schema and seeding
    ├── grader/
    │   ├── grader.py         # Evaluation engine
    │   └── tasks/            # 10 task definitions (JSON)
    │       ├── easy/         # 3 tasks
    │       ├── medium/       # 3 tasks
    │       ├── hard/         # 2 tasks
    │       └── expert/       # 2 tasks
    └── mcp_tools/            # 24 GitHub API tool implementations
        ├── issues.py
        ├── pull_requests.py
        ├── branches.py
        ├── files.py
        ├── projects.py
        ├── labels.py
        └── search.py
```
