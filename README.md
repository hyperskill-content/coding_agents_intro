# Coding agents: architecture and security intro

This is the hands-on part of the talk. You build a small coding agent in Python, one step at a time, by giving short specs to a coding agent you already use. Each step adds one piece of the architecture and ends with a few things to try.

The agent you build works with any OpenAI-compatible chat completions API and uses only the Python standard library, so each version fits on a screen or two.

Slides: [coding_agents.pdf](coding_agents.pdf)

## Repository layout

```
coding_agents.pdf      the slides
specs/                 the seven steps: a prompt for your coding agent, then things to try and notice
reference/             a working version of each step, in case you fall behind
demo/                  a tiny project for your agent to work on (it contains a planted prompt injection, see spec 5)
tools/mock_server.py   an offline fake model, for when the API or the Wi-Fi is down
.env.template          the environment variables the agent needs
opencode.json          example config for using opencode with the workshop endpoint
```

## Steps

| # | Spec | Topic |
|---|---|---|
| 1 | [Chat](specs/01-chat.md) | The model is stateless; the harness keeps the conversation |
| 2 | [Tools](specs/02-tools.md) | How tools are described to the model; the model only requests them |
| 3 | [Loop](specs/03-loop.md) | The agent loop: call the model, run tools, send results back |
| 4 | [Coding agent](specs/04-coding-agent.md) | Writing files and running commands, the system prompt, truncating output |
| 5 | [Guardrails](specs/05-guardrails.md) | Permissions, a path jail, a clean environment, prompt injection |
| 6 | [Sandbox](specs/06-sandbox.md) | Running commands in a Docker container as an isolation boundary |
| 7 | [Large codebase](specs/07-large-codebase.md) | A repo far bigger than the context window: search, partial reads, compaction, sub-agents |

## Setup

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/). On first run it installs the Python version pinned in `.python-version` (3.14). There are no packages to install.
2. Choose a coding agent. Any agent that can edit files and run commands works (Claude Code, Codex CLI, opencode, Cursor and so on). If you don't have one, use opencode with the workshop endpoint: install it from [opencode.ai](https://opencode.ai), replace `MODEL_ID` (twice) in `opencode.json` with the model id, and run `opencode` in this folder.
3. Set the environment variables, using the values from the instructor:

   ```bash
   cp .env.template .env      # then fill in the three values
   source .env                # in every new terminal
   ```

   On Windows, use WSL.
4. Make a working copy of the demo project, so you can reset it later: `cp -r demo playground`
5. Check that the API works: run `uv run reference/stage1_chat.py` and type `hi`.

Optional, before the session (both are large downloads):

- Spec 6 needs Docker and its base image: `docker pull python:3.14-slim`
- Spec 7 needs a Django checkout (about 85 MB): `git clone --depth 1 --branch 5.2 https://github.com/django/django.git ~/django`. The spec 7 commands point `REPO` at `~/django`; if you clone it somewhere else, use that path instead.

## Working through a step

1. Give the prompt at the top of the spec to your coding agent. It creates or updates `agent.py` in this folder.
2. Read the diff before you run anything.
3. Do the **Try it** and **Notice** parts.

If you fall behind, copy the reference version of the step you missed and continue from there, for example:

```bash
cp reference/stage3_loop.py agent.py
```

Two exceptions: stage 6 imports stage 5, so run it in place (`cd playground && uv run ../reference/stage6_sandbox.py`), and stage 7 is a separate program (`cp reference/stage7_large_codebase.py repo_agent.py`).

## Without API access

`tools/mock_server.py` is a fake model with a few scripted behaviours:

```bash
uv run tools/mock_server.py &
export OPENAI_BASE_URL=http://127.0.0.1:8765/v1 OPENAI_API_KEY=mock MODEL=mock
```

It handles requests like "list the files", "read calc.py", "create fizzbuzz.py and run it" and "run \`ls -la\`". It follows prompt injections on purpose, for spec 5, and it can answer the spec 7 Django question in all three modes.

## Safety

From spec 4 on, the agent you build runs shell commands as your user. Run it only inside `playground/`, not in your home folder or in a repo you care about, and don't give it credentials other than the workshop key. Keep `.env` in this folder, not in `playground/`.
