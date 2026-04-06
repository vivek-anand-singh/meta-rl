# OpenEnv Hackathon Context

## What is OpenEnv (OpenM)?
- Short for "Open Environment" — collaboration between **Meta/PyTorch, Hugging Face, and Unsloth**
- A standard interface/library for building RL environments that LLMs can train on
- Goal: make RL environments interoperable, discoverable, and scalable (like HuggingFace Hub did for models)

## Core Concept
- Agent → takes **Action** → Environment → returns **Observation + Reward**
- Reward is a score (0 to 1) indicating how well the agent performed
- Environments replace static datasets: they can dynamically generate tasks matched to model capability

## Why RL Environments Matter
- Static SFT datasets: fixed difficulty, models can't self-correct over time
- RL environments: dynamic difficulty, multi-turn trajectories, richer reward signals
- Frontier labs (DeepSeek V3.2) use ~2000 environments + 85K prompts
- MiniMax used 100K+ envs from real GitHub repos

## Good Environment Criteria
- Must simulate a **real-world task** (NOT games, toys, or gamified scenarios)
- Should have a valid, non-trivial reward signal
- Long-running tasks with multiple trajectories preferred
- Reward must return a value **between 0 and 1**
- Must NOT return same score every time (diversity required)
- Model must be able to occasionally get reward (not impossibly hard)

## OpenEnv Technical Structure
Each environment is a Python package with 5 components:
1. `models.py` — Action, Observation, State (Pydantic objects)
2. `environment.py` — `reset()`, `step()`, `state()` methods
3. HTTP client
4. FastAPI server wrapper
5. Dockerfile

### CLI Commands
```bash
pip install openm-core[cli]        # Install
openm init <env-name>              # Create environment scaffold (11 files)
openm validate                     # Validate everything is in place
openm push <hf-username>/<env-name> # Deploy to HuggingFace Spaces
openm skills add codex             # Add agent skills
```

### Key Files After `openm init`
- `server/app.py` — FastAPI server
- `models.py` — Action/Observation/State definitions
- `Dockerfile` — **must be moved to root folder (outside /server)**
- `openm.yaml` — config
- `pyproject.toml` — Python project deps

### Docker Commands
```bash
docker build -t <env-name> .
openm run <env-name>               # Starts server
```

### Web UI
Add `ENABLE_WEB_INTERFACE=true` in Dockerfile env vars → access at `http://localhost/web`

## Inference Script (MANDATORY for submission)
- Copy from hackathon dashboard
- Uses **HuggingFace token** (not OpenAI token) — free credits available
- Uses **HF Router** as base URL (auto-selects model provider)
- Must be updated to match your environment's action/observation schema
- Run with: `uv run inference.py`

### Key Config in Inference Script
```python
DOCKER_IMAGE_NAME = "<your-env-name>"
HF_TOKEN = os.getenv("HF_TOKEN")  # from .env file
BASE_URL = "https://router.huggingface.co/..."  # use HF router
MODEL = "Qwen/Qwen2.5-72B-Instruct"  # or any model on HF Hub
```

## Deployment to HuggingFace
- Environments deploy as **HuggingFace Spaces** (Docker-based)
- They appear under "Agent Environment" filter on HF Spaces (~900+ environments)
- Version controlled, has API + UI, private spaces supported
- After push: submit the Space URL on the hackathon dashboard

## Hackathon Submission Rules
- **Deadline: April 8th**
- Multiple submissions allowed; **latest submission is used for evaluation**
- Must be **real-world task** — healthcare, productivity, code, APIs, etc.
- No plagiarism — must build your own environment
- Grader diversity required (must not return same score always)
- Use AI (Claude, Cursor, Codex) to help write/update inference script
- Model used in inference must be available on HuggingFace Hub

## Scoring Criteria
1. **Utility of the idea** — is it a real-world, valuable use case?
2. **Quality of the grader** — well-designed reward signal
3. **Environment design** — correctness, multi-turn support, complexity

## Common Failure Modes
- Reward hacking (model games the verifier)
- Wrong formatting → model never gets reward → no learning
- Task too hard → model can never produce correct output
- Docker file left inside `/server` instead of root
- Missing mandatory inference script steps

## Example Environments to Reference
- Wordle (educational, not submittable)
- GPU Kernel Sandbox (benchmarks PyTorch kernels for speed)
- Connect 4 (educational)
- Number guessing game (already exists on HF — don't copy)
- Real targets: calendar management, email triage, healthcare tools, code review

## Tips
- Start with echo environment to verify pipeline works end-to-end
- Use `openm skills add codex` so AI agents know how to build OpenEnv environments
- Check HuggingFace Spaces → filter "agent environment" for inspiration (900+ envs)
- Use LLM-as-judge for subjective rewards that can't be verified programmatically
- Add Gradio custom UI for complex environments (helps debugging)
