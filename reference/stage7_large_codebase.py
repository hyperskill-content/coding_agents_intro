#!/usr/bin/env python3
"""
Stage 7 - Working in a codebase bigger than the context window.

Coding agents never load the codebase. They search, read small
slices, and throw away what they no longer need. This stage lets you run the
same question three ways and watch the context meter:

  --naive      tools that read whole files and whole folders  -> context overflow
  (default)    search_code + line-range read_file + depth-limited list_dir,
               plus compaction when the context gets full
  --subagent   the main agent only has explore(question): a fresh agent with its own
               empty history does the digging and returns only its conclusion

Read-only on purpose: no shell, no writes. Safe to point at any repo.

Run:  uv run reference/stage7_large_codebase.py [--naive|--subagent] [--ask "question"] [--debug]
Env:  REPO (repo root, default cwd), CONTEXT_BUDGET (tokens, default 16000)

CONTEXT_BUDGET is a pretend context window enforced by the harness. Real windows
are 128k-1M tokens; a small budget makes the effect visible in minutes and cheap.
Set it to your model's real limit to see the real thing.
"""
import fnmatch
import json
import os
import re
import sys
import urllib.error
import urllib.request

BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
API_KEY = os.environ.get("OPENAI_API_KEY", "")
MODEL = os.environ.get("MODEL", "")
REPO = os.path.realpath(os.environ.get("REPO", os.getcwd()))
BUDGET = int(os.environ.get("CONTEXT_BUDGET", "16000"))
COMPACT_AT = 0.7          # compact when the next request would use 70% of the budget
MAX_STEPS = 25
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build"}
DEBUG = False


class ContextOverflow(Exception):
    pass


def est_tokens(obj):
    """Rough count: ~4 characters per token. Good enough for a meter."""
    return len(json.dumps(obj)) // 4


def meter(tokens, label=""):
    filled = min(20, round(20 * tokens / BUDGET))
    bar = "#" * filled + "." * (20 - filled)
    print(f"  ctx [{bar}] {tokens:>8,} / {BUDGET:,} tokens {label}")


# ---------- helpers ----------
def check_repo():
    if not os.path.isdir(REPO):
        raise SystemExit(f"REPO folder not found: {REPO}\n"
                         "Clone Django first (see the README setup) or set REPO to an existing folder.")


def inside(path):
    """Resolve a path inside the repo; refuse anything outside it."""
    full = os.path.realpath(os.path.join(REPO, path))
    if full != REPO and not full.startswith(REPO + os.sep):
        raise ValueError(f"'{path}' is outside the repo")
    return full


def walk_files(root):
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for f in sorted(files):
            yield os.path.join(dirpath, f)


def read_text(path, limit=2_000_000):
    if os.path.getsize(path) > limit:
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (UnicodeDecodeError, OSError):
        return None


def repo_stats():
    n, chars = 0, 0
    for p in walk_files(REPO):
        t = read_text(p)
        if t is not None:
            n += 1
            chars += len(t)
    return n, chars // 4


# ---------- NAIVE tools: the "just read it all" approach ----------
def naive_list_dir(path="."):
    return "\n".join(sorted(os.listdir(inside(path))))


def naive_read_file(path):
    return read_text(inside(path), limit=10**9) or "(binary or unreadable)"


def read_folder(path="."):
    out = []
    for p in walk_files(inside(path)):
        t = read_text(p)
        if t is not None:
            out.append(f"===== {os.path.relpath(p, REPO)} =====\n{t}")
    return "\n".join(out)


# ---------- NAVIGATION tools: what real coding agents do ----------
def list_dir(path=".", depth=1):
    depth = max(1, min(int(depth), 3))
    lines = []

    def walk(folder, level):
        for name in sorted(os.listdir(folder)):
            full = os.path.join(folder, name)
            if os.path.isdir(full):
                if name in SKIP_DIRS:
                    continue
                lines.append(f"{'  ' * level}{name}/")
                if level + 1 < depth:
                    walk(full, level + 1)
            else:
                lines.append(f"{'  ' * level}{name}")

    walk(inside(path), 0)
    if len(lines) > 200:
        return "\n".join(lines[:200]) + "\n... (truncated at 200 entries; list a subfolder)"
    return "\n".join(lines) or "(empty)"


def search_code(pattern, path=".", glob="*"):
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return f"Error: invalid regex: {e}"
    hits, total = [], 0
    for p in walk_files(inside(path)):
        if not fnmatch.fnmatch(os.path.basename(p), glob):
            continue
        t = read_text(p)
        if t is None:
            continue
        for i, line in enumerate(t.splitlines(), 1):
            if rx.search(line):
                total += 1
                if len(hits) < 50:
                    hits.append(f"{os.path.relpath(p, REPO)}:{i}: {line.strip()[:160]}")
    if not hits:
        return "No matches."
    more = f"\n... {total - 50} more matches. Narrow the pattern, path or glob." if total > 50 else ""
    return "\n".join(hits) + more


def read_file(path, start_line=1, end_line=None):
    t = read_text(inside(path), limit=10**9)
    if t is None:
        return "(binary or unreadable)"
    lines = t.splitlines()
    start = max(1, int(start_line))
    end = min(len(lines), int(end_line) if end_line else start + 199, start + 199)
    body = "\n".join(f"{i:>6}  {lines[i - 1]}" for i in range(start, end + 1))
    note = f"\n(lines {start}-{end} of {len(lines)}; ask for another range to see more)" if end < len(lines) else ""
    return f"{path} lines {start}-{end} of {len(lines)}\n{body}{note}"


def fn(name, description, props, required):
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": props, "required": required}}}


NAIVE_TOOLS = [
    fn("list_dir", "List the files and folders in a directory.", {"path": {"type": "string"}}, ["path"]),
    fn("read_file", "Read a whole file.", {"path": {"type": "string"}}, ["path"]),
    fn("read_folder", "Read EVERY file in a folder at once. The fastest way to understand a codebase.",
       {"path": {"type": "string"}}, ["path"]),
]
NAIVE_FUNCS = {"list_dir": naive_list_dir, "read_file": naive_read_file, "read_folder": read_folder}

NAV_TOOLS = [
    fn("list_dir", "Show the folder tree under a path, up to `depth` levels (1-3). Start here to get the shape of the repo.",
       {"path": {"type": "string"}, "depth": {"type": "integer", "description": "1-3, default 1"}}, ["path"]),
    fn("search_code", "Regex search across files. Returns up to 50 hits as path:line: text. Use it to find definitions and callers before reading anything.",
       {"pattern": {"type": "string", "description": "Python regex"},
        "path": {"type": "string", "description": "Folder to search, default '.'"},
        "glob": {"type": "string", "description": "Filename filter, e.g. '*.py'"}}, ["pattern"]),
    fn("read_file", "Read a slice of a file with line numbers, at most 200 lines per call. Read only the lines you need.",
       {"path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}, ["path"]),
]
NAV_FUNCS = {"list_dir": list_dir, "search_code": search_code, "read_file": read_file}

EXPLORE_TOOL = fn(
    "explore",
    "Delegate a focused investigation to a sub-agent with its own fresh context. It searches and reads code and returns only its findings (files, line numbers, facts). Ask one focused question per call.",
    {"question": {"type": "string", "description": "A specific, self-contained question"}}, ["question"])

SYSTEM = f"""You answer questions about the code repository at {REPO}.
The repository is far bigger than your context window, so never try to read it all.
Work like an engineer: get the shape with list_dir, find exact places with search_code,
then read only the relevant line ranges. Cite file paths and line numbers in your answer."""

NAIVE_SYSTEM = f"You answer questions about the code repository at {REPO}. Read whatever you need."

SUBAGENT_SYSTEM = f"""You answer questions about the code repository at {REPO}.
The repository is far bigger than your context window, and you can't read it yourself.
Delegate each investigation to explore with a specific, self-contained question,
then combine the findings into your answer. Cite file paths and line numbers from the findings."""


# ---------- the harness ----------
class Agent:
    def __init__(self, mode="nav", name="main", compact=True):
        self.mode, self.name, self.compact_on = mode, name, compact and mode != "naive"
        if mode == "naive":
            self.tools, self.funcs, self.system = NAIVE_TOOLS, NAIVE_FUNCS, NAIVE_SYSTEM
        elif mode == "subagent":
            # The main agent can only delegate: all reading happens in the sub-agents' own contexts.
            self.tools, self.funcs, self.system = [EXPLORE_TOOL], {"explore": self.explore}, SUBAGENT_SYSTEM
        else:
            self.tools, self.funcs, self.system = NAV_TOOLS, NAV_FUNCS, SYSTEM
        self.stats = {"steps": 0, "peak": 0, "sent": 0, "compactions": 0, "subagent_tokens": 0}

    def call_model(self, messages, tool_choice=None):
        body = {"model": MODEL, "messages": messages, "tools": self.tools}
        if tool_choice:
            body["tool_choice"] = tool_choice
        tokens = est_tokens(body)
        if tokens > BUDGET:
            raise ContextOverflow(f"request is ~{tokens:,} tokens, budget is {BUDGET:,}")
        self.stats["peak"] = max(self.stats["peak"], tokens)
        self.stats["sent"] += tokens
        if DEBUG:
            print(">>> REQUEST\n" + json.dumps(body, indent=2)[:4000])
        req = urllib.request.Request(
            BASE_URL + "/chat/completions", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"})
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.load(resp)
        except urllib.error.HTTPError as e:
            err = e.read().decode(errors="replace")
            if "context" in err.lower() or "too long" in err.lower() or "maximum" in err.lower():
                raise ContextOverflow(f"API refused: {err[:200]}")
            raise SystemExit(f"API error {e.code}: {err}")
        if DEBUG:
            print("<<< RESPONSE\n" + json.dumps(data, indent=2)[:4000])
        return data["choices"][0]["message"]

    def compact(self, messages, task):
        """Replace the history with a model-written summary. What /compact does."""
        self.stats["compactions"] += 1
        print(f"  [{self.name}] compacting history ...")
        for keep in (1500, 300):
            if est_tokens({"m": messages, "t": self.tools}) <= 0.9 * BUDGET:
                break
            # Too full even to ask for a summary: clip old tool outputs, harder if needed.
            messages = [dict(m, content=m["content"][:keep] + " ...[clipped]")
                        if m.get("role") == "tool" and len(m.get("content") or "") > keep else m
                        for m in messages]
        ask = messages + [{"role": "user", "content":
                           "Context is nearly full. Summarize what you have found so far for yourself: "
                           "relevant files with line numbers, facts established, and what is still unknown. "
                           "Be concise; this summary will replace the whole history."}]
        summary = self.call_model(ask, tool_choice="none").get("content") or ""
        new = [messages[0], {"role": "user", "content": f"{task}\n\n[Notes from your earlier work - history was compacted]\n{summary}"}]
        meter(est_tokens(new), "(after compaction)")
        return new

    def run_tool(self, call):
        name = call["function"]["name"]
        try:
            args = json.loads(call["function"]["arguments"] or "{}")
        except json.JSONDecodeError as e:
            return f"Error: arguments were not valid JSON ({e})"
        func = self.funcs.get(name)
        if func is None:
            return f"Error: unknown tool '{name}'"
        try:
            return str(func(**args))
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"

    def explore(self, question):
        sub = Agent(mode="nav", name="sub-agent")
        answer = sub.ask(question)
        self.stats["subagent_tokens"] += sub.stats["sent"]
        return (f"[sub-agent: {sub.stats['steps']} steps, its context peaked at ~{sub.stats['peak']:,} tokens; "
                f"you only see this summary]\n{answer}")

    def ask(self, task, messages=None):
        messages = messages if messages is not None else [{"role": "system", "content": self.system}]
        messages.append({"role": "user", "content": task})
        pad = "      " if self.name != "main" else ""
        for _ in range(MAX_STEPS):
            if self.compact_on and est_tokens({"m": messages, "t": self.tools}) > COMPACT_AT * BUDGET:
                messages[:] = self.compact(messages, task)
            reply = self.call_model(messages)
            self.stats["steps"] += 1
            meter(est_tokens({"m": messages, "t": self.tools}), f"{pad}[{self.name} step {self.stats['steps']}]")
            messages.append(reply)
            calls = reply.get("tool_calls") or []
            if not calls:
                return reply.get("content") or ""
            for call in calls:
                print(f"  {pad}-> {call['function']['name']}({call['function']['arguments'][:120]})")
                result = self.run_tool(call)
                print(f"  {pad}<- {len(result):,} chars (~{len(result) // 4:,} tokens)")
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
        return f"(stopped after {MAX_STEPS} steps)"


def main():
    global DEBUG
    DEBUG = "--debug" in sys.argv
    mode = "naive" if "--naive" in sys.argv else "subagent" if "--subagent" in sys.argv else "nav"
    if not API_KEY or not MODEL:
        raise SystemExit("Set OPENAI_API_KEY and MODEL (and OPENAI_BASE_URL if not using OpenAI).")
    check_repo()
    files, tokens = repo_stats()
    print(f"Repo {REPO}: {files:,} text files, ~{tokens:,} tokens = {tokens / BUDGET:,.0f}x the context budget.")
    print(f"Mode: {mode}. Budget: {BUDGET:,} tokens.")
    agent = Agent(mode)
    messages = [{"role": "system", "content": agent.system}]
    questions = [sys.argv[sys.argv.index("--ask") + 1]] if "--ask" in sys.argv else None
    while True:
        if questions is not None:
            if not questions:
                break
            q = questions.pop()
            print(f"\nyou> {q}")
        else:
            try:
                q = input("\nyou> ").strip()
            except EOFError:
                break
            if not q:
                continue
        try:
            print(f"model> {agent.ask(q, messages)}")
        except ContextOverflow as e:
            print(f"\n  !! CONTEXT OVERFLOW after {agent.stats['steps']} steps: {e}")
            print("  !! The agent is dead: nothing more fits."
                  + (" This is what 'just read it all' gets you." if mode == "naive" else ""))
            break
    s = agent.stats
    print(f"\nsteps={s['steps']} peak_context~{s['peak']:,} tokens_sent~{s['sent']:,} "
          f"compactions={s['compactions']} subagent_tokens~{s['subagent_tokens']:,}")


if __name__ == "__main__":
    main()
