#!/usr/bin/env python3
"""
Stage 4 - A (tiny) coding agent.

Adds write_file and run_shell, a system prompt that tells the model where it
is, and output truncation so one noisy command can't blow the context window.

WARNING: this stage has NO guardrails. The model can run any shell command as
you. Only run it inside a throwaway folder. Stage 5 fixes this.

Run:  uv run reference/stage4_coding_agent.py [--debug]
"""
import json
import os
import platform
import subprocess
import sys
import urllib.error
import urllib.request

BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
API_KEY = os.environ.get("OPENAI_API_KEY", "")
MODEL = os.environ.get("MODEL", "")
DEBUG = "--debug" in sys.argv
MAX_STEPS = 15
MAX_OUTPUT = 4000  # characters of tool output we let back into the context


def truncate(text, limit=MAX_OUTPUT):
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + f"\n... [{len(text) - limit} chars truncated] ...\n" + text[-half:]


# ---------- tools ----------
def list_dir(path):
    return "\n".join(sorted(os.listdir(path))) or "(empty)"


def read_file(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write_file(path, content):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Wrote {len(content)} chars to {path}"


def run_shell(command):
    try:
        p = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return "Error: command timed out after 30s"
    return f"exit_code={p.returncode}\n--- stdout ---\n{p.stdout}\n--- stderr ---\n{p.stderr}"


TOOL_FUNCS = {"list_dir": list_dir, "read_file": read_file, "write_file": write_file, "run_shell": run_shell}


def fn(name, description, props, required):
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": props, "required": required}}}


TOOLS = [
    fn("list_dir", "List the files and folders in a directory.",
       {"path": {"type": "string", "description": "Directory path, e.g. '.'"}}, ["path"]),
    fn("read_file", "Read a UTF-8 text file and return its contents.",
       {"path": {"type": "string"}}, ["path"]),
    fn("write_file", "Create or overwrite a text file with the given content.",
       {"path": {"type": "string"}, "content": {"type": "string", "description": "Full file content"}}, ["path", "content"]),
    fn("run_shell", "Run a shell command in the project folder and return exit code, stdout and stderr. 30s timeout.",
       {"command": {"type": "string"}}, ["command"]),
]

SYSTEM_PROMPT = f"""You are a coding agent working in a project folder.
Working directory: {os.getcwd()}
OS: {platform.system()} {platform.release()}; Python {platform.python_version()}
Rules:
- Look before you act: list or read files before changing them.
- After writing code, run it to check it works, and fix errors you see.
- Keep answers short; say what you changed."""


def call_model(messages, tools=None):
    body = {"model": MODEL, "messages": messages}
    if tools:
        body["tools"] = tools
    if DEBUG:
        print("\n>>> REQUEST\n" + json.dumps(body, indent=2))
    req = urllib.request.Request(
        BASE_URL + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"API error {e.code}: {e.read().decode(errors='replace')}")
    if DEBUG:
        print("<<< RESPONSE\n" + json.dumps(data, indent=2))
    usage = data.get("usage") or {}
    if usage:
        print(f"  (tokens: prompt={usage.get('prompt_tokens')} completion={usage.get('completion_tokens')})")
    return data["choices"][0]["message"]


def run_tool(call):
    name = call["function"]["name"]
    try:
        args = json.loads(call["function"]["arguments"] or "{}")
    except json.JSONDecodeError as e:
        return f"Error: arguments were not valid JSON ({e})"
    func = TOOL_FUNCS.get(name)
    if func is None:
        return f"Error: unknown tool '{name}'"
    try:
        return truncate(str(func(**args)))
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"


def agent_turn(messages):
    for step in range(1, MAX_STEPS + 1):
        reply = call_model(messages, TOOLS)
        messages.append(reply)
        calls = reply.get("tool_calls") or []
        if not calls:
            return reply.get("content") or ""
        for call in calls:
            print(f"  [{step}] -> {call['function']['name']}({call['function']['arguments'][:200]})")
            result = run_tool(call)
            print(f"      <- {result.splitlines()[0] if result else ''}  ({len(result)} chars)")
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
    return f"(stopped after {MAX_STEPS} steps)"


def main():
    if not API_KEY or not MODEL:
        raise SystemExit("Set OPENAI_API_KEY and MODEL (and OPENAI_BASE_URL if not using OpenAI).")
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    print(f"Coding agent on {MODEL} in {os.getcwd()}. NO GUARDRAILS. Ctrl-D to quit.")
    while True:
        try:
            user = input("\nyou> ").strip()
        except EOFError:
            break
        if not user:
            continue
        messages.append({"role": "user", "content": user})
        print(f"model> {agent_turn(messages)}")


if __name__ == "__main__":
    main()
