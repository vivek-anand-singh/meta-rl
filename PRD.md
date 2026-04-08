# PRD: GitHub RL Environment (OpenEnv Hackathon)

## Overview
A fully sandboxed GitHub simulation environment for RL training.
Agents interact with a custom MCP server backed by a local SQLite DB —
no real GitHub API calls, unlimited parallel episodes, full state control.

---

## Network Architecture & Connectivity

| Component | Network Access | Details |
|-----------|---------------|---------|
| **Environment (reset/step/state)** | Strictly offline / air-gapped | All GitHub interactions are fully simulated against the local SQLite DB. Sub-millisecond, deterministic responses. No outbound calls. |
| **Inference Script (inference.py)** | Requires outbound internet | Routes agent LLM calls via the HuggingFace Router (`https://router.huggingface.co`) using the `HF_TOKEN`. |
| **Training (GRPO/TRL)** | Connects to environment via WebSocket | Training code connects to environment server at `/ws`. Environment itself remains offline. |
| **HF Space (deployed)** | Inbound only | Serves the environment API. Clients connect to it. The environment does not make outbound calls. |

---

## Architecture

```
Training Code / Inference Script
  ↓  WebSocket /ws (primary) or HTTP /reset /step /state
OpenEnv FastAPI Server (Docker container)
  ↓  dispatches
GitHub RL Environment (github_rl_environment.py)
  ↓  parses agent message into tool call
MCP Tool Handlers (issues.py, pull_requests.py, etc.)
  ↓  reads/writes
SQLite DB (seeded per episode on reset)
  ↓  state snapshot
Grader → reward (0.0 – 1.0)
  ↓
Observation returned to agent
```

### Key Protocol Details (from docs)
- **WebSocket (`/ws`)** is the primary protocol used by the Python client. Each connection gets its own isolated environment instance.
- **HTTP endpoints** (`/reset`, `/step`, `/state`, `/health`) are available for debugging and stateless use.
- **One container handles many concurrent sessions** via WebSocket — no need for 1 container per episode.
- Server-side session state is managed per WebSocket connection. No session IDs needed.

---

## MCP Tools to Implement

### KEEP — Core Workflow (Phase 1, must have)

#### Issues
| Tool | Description |
|------|-------------|
| `issue_read` | Get a specific issue by number |
| `issue_write` | Create or update an issue (title, body, status, assignee, labels) |
| `list_issues` | List issues with filters (open/closed, label, assignee) |
| `add_issue_comment` | Add a comment to an issue |
| `search_issues` | Search issues by keyword/filter |
| `sub_issue_write` | Link a sub-issue to a parent issue |

#### Pull Requests
| Tool | Description |
|------|-------------|
| `pull_request_read` | Get PR details |
| `create_pull_request` | Open a new PR (title, body, head branch, base branch) |
| `update_pull_request` | Edit PR (title, body, status, linked issues, assignees) |
| `merge_pull_request` | Merge a PR (merge/squash/rebase) |
| `list_pull_requests` | List PRs with filters |
| `pull_request_review_write` | Submit a review (approve/request changes/comment) |
| `add_reply_to_pull_request_comment` | Reply to a PR review comment |
| `update_pull_request_branch` | Update PR branch with base branch changes |

#### Branches & Code
| Tool | Description |
|------|-------------|
| `create_branch` | Create a new branch from base |
| `list_branches` | List all branches in repo |
| `get_file_contents` | Read file content from a branch |
| `create_or_update_file` | Create or edit a single file |
| `delete_file` | Delete a file from a branch |
| `push_files` | Push multiple files in one commit |
| `get_repository_tree` | Get directory structure of repo |
| `get_commits` | Get commit history |

#### Projects
| Tool | Description |
|------|-------------|
| `projects_list` | List projects in repo |
| `projects_get` | Get project details + columns |
| `projects_write` | Create project / add issue to project / move issue status |

#### Labels
| Tool | Description |
|------|-------------|
| `label_write` | Create or update a label |
| `list_labels` | List all labels |
| `get_label` | Get a specific label |

#### Search
| Tool | Description |
|------|-------------|
| `search_code` | Search code within repo |
| `search_pull_requests` | Search PRs |

---

### SKIP — Out of Scope (Phase 1)

| Tool Group | Reason |
|------------|--------|
| `actions_*` | Needs CI runner simulation — too complex for now |
| `notifications_*` | Not core to dev workflow tasks |
| `gist_*` | Not relevant |
| `security_*` / `code_scanning_*` / `dependabot_*` | Too specialized |
| `discussions_*` | Nice to have, Phase 2 |
| `fork_repository` | Not needed for sandboxed env |
| `star_*` / `unstar_*` | Not relevant |
| `copilot_*` | Not relevant |
| `team_*` | Phase 2 |
| `search_orgs` / `search_users` | Not needed |
| `releases_*` / `tags_*` | Phase 2 |
| `hello_world` | Skip |

---

## SQLite Schema

```sql
-- Core repo
CREATE TABLE repos (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    default_branch TEXT DEFAULT 'main'
);

-- Branches
CREATE TABLE branches (
    id INTEGER PRIMARY KEY,
    repo_id INTEGER,
    name TEXT NOT NULL,
    base_branch TEXT DEFAULT 'main',
    FOREIGN KEY (repo_id) REFERENCES repos(id)
);

-- Commits
CREATE TABLE commits (
    id INTEGER PRIMARY KEY,
    branch_id INTEGER,
    message TEXT NOT NULL,
    author TEXT,
    sha TEXT,
    created_at TEXT,
    FOREIGN KEY (branch_id) REFERENCES branches(id)
);

-- Files (per branch)
CREATE TABLE files (
    id INTEGER PRIMARY KEY,
    branch_id INTEGER,
    path TEXT NOT NULL,
    content TEXT,
    FOREIGN KEY (branch_id) REFERENCES branches(id)
);

-- Labels
CREATE TABLE labels (
    id INTEGER PRIMARY KEY,
    repo_id INTEGER,
    name TEXT NOT NULL,
    color TEXT,
    description TEXT
);

-- Issues
CREATE TABLE issues (
    id INTEGER PRIMARY KEY,
    repo_id INTEGER,
    number INTEGER,
    title TEXT NOT NULL,
    body TEXT,
    status TEXT DEFAULT 'open',   -- open / closed
    assignee TEXT,
    parent_issue_id INTEGER,
    project_id INTEGER,
    created_by TEXT,
    FOREIGN KEY (repo_id) REFERENCES repos(id)
);

-- Issue Labels (many-to-many)
CREATE TABLE issue_labels (
    issue_id INTEGER,
    label_id INTEGER,
    PRIMARY KEY (issue_id, label_id)
);

-- Issue Comments
CREATE TABLE issue_comments (
    id INTEGER PRIMARY KEY,
    issue_id INTEGER,
    author TEXT,
    body TEXT,
    created_at TEXT,
    FOREIGN KEY (issue_id) REFERENCES issues(id)
);

-- Pull Requests
CREATE TABLE pull_requests (
    id INTEGER PRIMARY KEY,
    repo_id INTEGER,
    number INTEGER,
    title TEXT NOT NULL,
    body TEXT,
    status TEXT DEFAULT 'open',   -- open / closed / merged
    head_branch TEXT,
    base_branch TEXT DEFAULT 'main',
    author TEXT,
    merge_method TEXT,            -- merge / squash / rebase
    has_conflicts INTEGER DEFAULT 0,
    FOREIGN KEY (repo_id) REFERENCES repos(id)
);

-- PR Linked Issues
CREATE TABLE pr_linked_issues (
    pr_id INTEGER,
    issue_id INTEGER,
    PRIMARY KEY (pr_id, issue_id)
);

-- PR Reviews
CREATE TABLE pr_reviews (
    id INTEGER PRIMARY KEY,
    pr_id INTEGER,
    reviewer TEXT,
    status TEXT,                  -- approved / changes_requested / commented
    body TEXT,
    FOREIGN KEY (pr_id) REFERENCES pull_requests(id)
);

-- PR Comments
CREATE TABLE pr_comments (
    id INTEGER PRIMARY KEY,
    pr_id INTEGER,
    author TEXT,
    body TEXT,
    file_path TEXT,
    line_number INTEGER,
    reply_to_id INTEGER,
    FOREIGN KEY (pr_id) REFERENCES pull_requests(id)
);

-- Projects
CREATE TABLE projects (
    id INTEGER PRIMARY KEY,
    repo_id INTEGER,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'open',
    FOREIGN KEY (repo_id) REFERENCES repos(id)
);

-- Project Items (issues in a project with status column)
CREATE TABLE project_items (
    id INTEGER PRIMARY KEY,
    project_id INTEGER,
    issue_id INTEGER,
    column_name TEXT DEFAULT 'Todo',  -- Todo / In Progress / Done
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (issue_id) REFERENCES issues(id)
);
```

---

## Task Design

### Task JSON Structure
```json
{
  "task_id": "uuid",
  "difficulty": "easy|medium|hard|expert",
  "category": "issues|prs|projects|code|secops|multi_step",
  "instructions": "Natural language task for the agent",
  "seed": {
    "repos": [...],
    "branches": [...],
    "files": [...],
    "labels": [...],
    "issues": [...],
    "pull_requests": [...],
    "projects": [...]
  }
}
```

---

### Task Categories & Examples

#### Easy (single action)
- Triage a simulated Dependabot alert by opening an issue and assigning the security team.
- Close issue #5 — it's a confirmed duplicate of #2.
- Add label "critical" to issue #3 after triaging.
- Assign issue #7 to user "alice" — she owns the auth module.
- Create a branch called "hotfix/cve-2025-1234" from main.

#### Medium (2–4 actions)
- Search the codebase for a leaked AWS access key in `config.py`, delete the file, and push a fix to a new branch.
- Create an issue for a security vulnerability, label it "security" + "urgent", assign to the security team.
- Review PR #6, request changes citing an insecure `eval()` call, add an inline comment explaining the risk.
- Create a branch, push a patched dependency file, open a PR linking to the CVE issue.

#### Hard (5+ actions)
- Audit a PR that updates an npm package. Identify the vulnerable version, request changes, add an inline comment explaining the CVE, and reject the PR.
- Triage 5 open issues: label by severity (critical/high/medium/low), assign to correct owners, add triage comments.
- Full PR lifecycle: review → request changes → author fixes → re-review → approve → merge.
- Create a project board for "Q2 Security Audit", add existing vulnerability issues, move them through triage columns.

#### Expert (full workflow)
- Respond to a simulated zero-day incident:
  1. Create a security advisory issue with full CVE details
  2. Create a project board for incident response
  3. Break into sub-issues (isolate, patch, test, deploy)
  4. Create a hotfix branch
  5. Push patched code files
  6. Open PR linked to all sub-issues
  7. Assign reviewers from security team
  8. Add review with approval after verifying fix
- Full feature development workflow:
  1. Create a project
  2. Break feature request into sub-issues
  3. Create feature branch
  4. Write implementation code
  5. Push files with meaningful commit messages
  6. Open PR with description linking issues
  7. Assign reviewer

---

## Reward Design

### Per-step partial rewards (grader checks DB state)

```python
# Example: Expert task (zero-day incident response) reward breakdown
advisory_issue_created    = 0.10
project_board_created     = 0.05
sub_issues_created        = 0.10  # (num_created / num_expected) * 0.10
issues_linked_to_project  = 0.05
hotfix_branch_created     = 0.05
patched_files_pushed      = 0.15
commit_message_meaningful = 0.05
pr_opened                 = 0.10
pr_linked_to_issues       = 0.10
reviewers_assigned        = 0.10
correct_base_branch       = 0.05
review_approved           = 0.10
# total = 1.00
```

### Multiple Reward Functions (following TRL/GRPO pattern from docs)
The Wordle training example shows that GRPO supports **multiple independent reward functions**. We can use:
```python
reward_funcs = [
    reward_task_completion,   # Did the agent complete the overall task?
    reward_tool_accuracy,     # Did the agent call the correct tools?
    reward_state_correctness, # Is the final DB state correct?
    reward_efficiency,        # Did the agent complete in minimal steps?
]
```

### Reward Rules
- Always returns float between 0.0 and 1.0
- Partial credit for partial completion
- Never returns same score every time (diversity requirement)
- Penalize wrong actions (e.g. merging a PR with conflicts)

---

## Action Format

Following the Wordle/TextArena pattern from the docs, the agent sends a **text message** as its action, which the environment parses into a tool call:

```python
# Agent sends:
GithubRlAction(message='{"tool": "issue_write", "args": {"title": "Fix auth bug", "labels": ["bug"]}}')

# Environment parses → executes tool → returns observation
GithubRlObservation(
    result="Issue #8 created: 'Fix auth bug' with labels ['bug']",
    available_tools=["issue_read", "issue_write", "create_branch", ...],
    task_progress="2/5 steps completed",
    done=False,
    reward=0.3,
)
```

---

## OpenEnv Integration

### reset()
- Pick a random task from tasks/
- Seed fresh SQLite DB from task's seed data
- Return: `GithubRlObservation` with task instructions, repo info, available tools

### step(action)
- Parse action message into tool name + args
- Execute tool handler against SQLite DB
- Run grader against current DB state
- Return: `GithubRlObservation` with tool result, reward, done flag

### state()
- Return full DB snapshot as JSON (episode_id, step_count, db state)

### Endpoints (auto-generated by OpenEnv app.py)
| Endpoint | Protocol | Description |
|----------|----------|-------------|
| `/ws` | WebSocket | Primary — persistent session per connection |
| `/health` | HTTP GET | Health check |
| `/reset` | HTTP POST | Reset environment (stateless) |
| `/step` | HTTP POST | Execute action (stateless) |
| `/state` | HTTP GET | Get current state |
| `/docs` | HTTP GET | OpenAPI documentation |
| `/web` | HTTP GET | Interactive Gradio web UI |

---

## Inference & Evaluation

### Requirements
- File must be named exactly `inference.py` in the root directory.
- Must use the **OpenAI Python Client** (as required by hackathon rules).
- Must run successfully: `uv run inference.py`

### Environment Variables Required
```env
API_BASE_URL=https://router.huggingface.co/v1
MODEL_NAME=Qwen/Qwen2.5-72B-Instruct
HF_TOKEN=<your_huggingface_token>
DOCKER_IMAGE_NAME=github_rl
```

### Validation (3-step check from hackathon)
The `validate-submission.sh` script checks:
1. **HF Space is live** — `POST /reset` returns HTTP 200
2. **Docker build succeeds** — `docker build` completes within 600s
3. **`openenv validate` passes** — Structure and configuration are correct

Run locally before submitting:
```bash
openenv validate
docker build -t github_rl .
```

---

## Difficulty Curriculum

```
Training step 0–1000:   Easy tasks only
Training step 1000–3000: Easy + Medium
Training step 3000+:     All difficulties
```

---

## File Structure

```
github_rl/
├── Dockerfile                         ← MUST be in root (not server/)
│                                        Inject: ENV ENABLE_WEB_INTERFACE=true
├── PRD.md
├── models.py                          ← Action / Observation (Pydantic)
├── client.py                          ← HTTPEnvClient subclass
├── pyproject.toml                     ← Python deps (add sqlite, etc.)
├── openenv.yaml                       ← Environment manifest
├── server/
│   ├── app.py                         ← FastAPI server (auto-generated)
│   ├── github_rl_environment.py       ← reset/step/state logic
│   ├── db.py                          ← SQLite schema + seed + reset
│   ├── mcp_tools/
│   │   ├── __init__.py
│   │   ├── issues.py
│   │   ├── pull_requests.py
│   │   ├── branches.py
│   │   ├── files.py
│   │   ├── projects.py
│   │   └── labels.py
│   └── grader/
│       ├── grader.py                  ← reward calculation
│       └── tasks/
│           ├── easy/
│           ├── medium/
│           ├── hard/
│           └── expert/
└── inference.py                       ← MANDATORY — OpenAI client + HF Router
```

**Notes:**
- `Dockerfile` MUST be in the root directory, NOT inside `server/`.
- Add `ENV ENABLE_WEB_INTERFACE=true` in Dockerfile to expose the Gradio testing UI on HuggingFace Spaces.
- Models use **Pydantic** `Field()` (not dataclasses) — extending `openenv.core.env_server.types.Action` and `Observation`.
- Client extends `HTTPEnvClient` and implements `_step_payload()`, `_parse_result()`, `_parse_state()`.

---

## Scaling Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `WORKERS` | 4 | Uvicorn worker processes |
| `PORT` | 8000 | Server port |
| `HOST` | 0.0.0.0 | Bind address |
| `MAX_CONCURRENT_ENVS` | 100 | Max WebSocket sessions per worker |
| `ENABLE_WEB_INTERFACE` | Auto | Enable Gradio web UI |

Each WebSocket session gets its own isolated SQLite DB. No cross-session interference.

---

## Phase Plan

### Phase 1 (Hackathon — by Apr 8)
- [ ] SQLite schema + seeding
- [ ] Core MCP tools: issues, PRs, branches, files, labels, projects
- [ ] 10+ tasks across easy/medium/hard/expert (SecOps flavored)
- [ ] Grader with multiple reward functions
- [ ] OpenEnv reset/step/state with WebSocket support
- [ ] Inference script (OpenAI client + HF Router)
- [ ] Dockerfile with ENABLE_WEB_INTERFACE=true
- [ ] `openenv validate` passes
- [ ] Docker build succeeds
- [ ] Push to HuggingFace Spaces

### Phase 2 (Post-hackathon)
- [ ] CI/CD actions simulation
- [ ] Discussions support
- [ ] Team management tools
- [ ] 100+ tasks with curriculum
- [ ] Custom Gradio UI for visualization
- [ ] Multi-node scaling with Docker Swarm / Envoy
