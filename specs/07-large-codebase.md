# Spec 7 — A codebase bigger than the context window  (≈19 min)

**Concept:** coding agents never load the codebase. They **navigate** it: get the shape, search for exact places, read small slices, and throw away what they no longer need. Django 5.2 is ~5,500 text files and ~9 million tokens; even a 1M-token model can't read it.

**Before the session:** `git clone --depth 1 --branch 5.2 https://github.com/django/django.git ~/django`

**The question** (its answer is spread over 4 files):

> What is Django's default limit on the number of fields in a request, where is it defined, where is it enforced, and what HTTP status code does the client get when it is exceeded?

## 1. Watch it fail (instructor demo, 3 min)

```bash
REPO=~/django uv run reference/stage7_large_codebase.py --naive --ask "<the question>"
```

The naive agent reads whole files and has a tempting `read_folder` tool. If it calls `read_folder`, it gets ~9M tokens back and the next request can't fit. A model that already knows Django (most do) skips that tool and reads the right files whole, and the window still fills after three or four files. `CONTEXT_BUDGET` (default 16,000) is a pretend window the harness enforces so the failure shows up in seconds and costs little; set it to your model's real limit to see the real thing.

## 2. Make it navigate — give this to your coding agent

> Create `repo_agent.py`, a read-only agent for answering questions about a large code repository (standard library only; start from the loop in `agent.py`, but no write or shell tools).
> - `REPO` env var = repo root (default cwd); all paths are relative to it and must stay inside it. Skip `.git`, `__pycache__`, `node_modules`.
> - Tools: `list_dir(path, depth=1)` — folder tree up to depth 3, max 200 entries; `search_code(pattern, path=".", glob="*")` — Python regex over text files, returns up to 50 hits as `path:line: text` plus a "N more matches, narrow your search" note; `read_file(path, start_line=1, end_line=None)` — returns at most 200 numbered lines and says how many lines the file has.
> - Write tool descriptions that push the model to search before reading and to read only the lines it needs. System prompt: the repo is far bigger than your context; never try to read it all; cite file paths and line numbers.
> - Context meter: before every model call, estimate tokens as `len(json.dumps(request_body)) // 4` and print a bar like `ctx [####......] 12,345 / 16,000`. `CONTEXT_BUDGET` env var (default 16000): if a request would exceed it, stop with a clear CONTEXT OVERFLOW message.
> - Print each tool call and the size of its result in characters and estimated tokens.
> - `--ask "question"` runs one question non-interactively; otherwise a REPL.

## Try it

```bash
REPO=~/django uv run repo_agent.py --ask "<the question>"
```

## Notice

1. The trace: shape → search → read 25 lines → search for the exception → read 25 more → answer. Every step is chosen from the previous result.
2. The meter barely moves: a few thousand tokens to answer a question about a 9M-token repo.
3. `search_code` is doing what an IDE's "find in files" does. Better harnesses add a **repo map** (aider: an outline of every file's classes and functions via tree-sitter), an **embedding index** (Cursor), or the **language server** ("go to definition"). Same idea: find the right 25 lines cheaply.

## 3. When the context still fills up (≈6 min, build it)

> Add to `repo_agent.py`: (1) **Compaction** — when the next request would use more than 70% of `CONTEXT_BUDGET`, ask the model (with `tool_choice: "none"`) to summarize what it has found so far (files, line numbers, facts, open questions), then replace the history with `[system, user: original question + those notes]`. (2) **A sub-agent** behind a `--subagent` flag: an `explore(question)` tool that runs a fresh agent loop with its own empty history and the three navigation tools, and returns only its final answer to the main agent. In this mode the main agent gets only `explore` and a system prompt telling it to delegate, so it never reads code itself.

```bash
CONTEXT_BUDGET=6000 REPO=~/django uv run repo_agent.py --ask "<the question>"   # forces a compaction
REPO=~/django uv run repo_agent.py --subagent --ask "<the question>"
REPO=~/django uv run reference/compare.py                                       # scoreboard of all three
```

## Notice

1. Compaction is lossy. Whatever the summary leaves out is gone. Watch the trace after the compaction: the agent often searches and reads the same files again, because its notes didn't keep enough. That's why Claude Code's `/compact` accepts instructions about what to keep.
2. With the sub-agent, the main agent's context holds one question and one answer. The sub-agent did all the reading in its own context, which was then thrown away. Total tokens don't go down; what goes down is how full the *main* context gets, so it can keep working much longer.

**Meta:** ask your coding agent the same question in `~/django` and read its tool calls. You'll usually see a file search (glob), a text search (grep), reads with line offsets, and sometimes a sub-agent. You just built each of those.

Checkpoint: `reference/stage7_large_codebase.py` (+ `reference/compare.py`)
