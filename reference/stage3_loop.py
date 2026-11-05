#!/usr/bin/env python3
"""
Stage 3 - The agent loop.

Now the harness EXECUTES tool calls and feeds results back:

    user msg -> model -> tool_calls? --yes--> run tools -> append results -> model -> ...
                                     --no---> print answer, wait for user

This loop is the whole "agent". Everything after this stage is tools,
context management and safety around it.

Run:  uv run reference/stage3_loop.py [--debug]
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
API_KEY = os.environ.get("OPENAI_API_KEY", "")
MODEL = os.environ.get("MODEL", "")
DEBUG = "--debug" in sys.argv
MAX_STEPS = 10  # stop runaway loops


# ---------- tool implementations (plain Python functions) ----------
def list_dir(path):
    return "\n".join(sorted(os.listdir(path))) or "(empty)"


def read_file(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


TOOL_FUNCS = {"list_dir": list_dir, "read_file": read_file}

TOOLS = [
    {"type": "function", "function": {
        "name": "list_dir", "description": "List the files and folders in a directory.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Directory path, e.g. '.'"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "read_file", "description": "Read a UTF-8 text file and return its contents.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Path to the file"}}, "required": ["path"]}}},
]


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
    return data["choices"][0]["message"]


def run_tool(call):
    """Dispatch one tool call. Errors become text for the model - never crash the loop."""
    name = call["function"]["name"]
    try:
        args = json.loads(call["function"]["arguments"] or "{}")
    except json.JSONDecodeError as e:
        return f"Error: arguments were not valid JSON ({e})"
    func = TOOL_FUNCS.get(name)
    if func is None:
        return f"Error: unknown tool '{name}'"
    try:
        return str(func(**args))
    except Exception as e:  # the model can read the error and try again
        return f"Error: {type(e).__name__}: {e}"


def agent_turn(messages):
    """Run the loop until the model answers in plain text (or we hit MAX_STEPS)."""
    for step in range(1, MAX_STEPS + 1):
        reply = call_model(messages, TOOLS)
        messages.append(reply)  # the assistant message WITH its tool_calls goes into history
        calls = reply.get("tool_calls") or []
        if not calls:
            return reply.get("content") or ""
        for call in calls:
            print(f"  [{step}] -> {call['function']['name']}({call['function']['arguments']})")
            result = run_tool(call)
            print(f"      <- {len(result)} chars")
            # Each result is linked back to the request by tool_call_id.
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
    return f"(stopped after {MAX_STEPS} steps)"


def main():
    if not API_KEY or not MODEL:
        raise SystemExit("Set OPENAI_API_KEY and MODEL (and OPENAI_BASE_URL if not using OpenAI).")
    messages = [{"role": "system", "content": "You are a helpful assistant. Use tools to inspect files before answering."}]
    print(f"Agent on {MODEL}. Ctrl-D to quit.")
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
