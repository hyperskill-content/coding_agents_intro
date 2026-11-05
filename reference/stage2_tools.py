#!/usr/bin/env python3
"""
Stage 2 - Presenting tools to the model.

Same chat loop, but every request now carries a `tools` array of JSON Schemas.
When the model wants a tool, it does NOT run anything: it returns a structured
request (`tool_calls`). This stage only PRINTS those requests.

Run:  uv run reference/stage2_tools.py [--debug]
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

# The model only ever sees this description. Name, description and parameter
# docs ARE the interface - they are prompt text, so write them carefully.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List the files and folders in a directory.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Directory path, e.g. '.'"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a UTF-8 text file and return its contents.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Path to the file"}},
                "required": ["path"],
            },
        },
    },
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
    choice = data["choices"][0]
    return choice["message"], choice.get("finish_reason")


def main():
    if not API_KEY or not MODEL:
        raise SystemExit("Set OPENAI_API_KEY and MODEL (and OPENAI_BASE_URL if not using OpenAI).")
    messages = [{"role": "system", "content": "You are a helpful assistant with file tools."}]
    print(f"Chatting with {MODEL} (tools offered, NOT executed). Ctrl-D to quit.")
    while True:
        try:
            user = input("\nyou> ").strip()
        except EOFError:
            break
        if not user:
            continue
        messages.append({"role": "user", "content": user})
        reply, finish = call_model(messages, TOOLS)
        print(f"[finish_reason={finish}]")
        if reply.get("tool_calls"):
            for call in reply["tool_calls"]:
                fn = call["function"]
                # NOTE: arguments arrive as a JSON *string* - it may even be invalid JSON.
                print(f"model wants -> {fn['name']}({fn['arguments']})   id={call['id']}")
            print("(Nothing ran. The harness decides what happens next - see stage 3.)")
            # Don't keep the reply: an assistant tool_call with no tool result would make
            # the next request invalid. (The reply was never appended; we also drop the
            # user message so the history doesn't hold an unanswered question.)
            messages.pop()
        else:
            messages.append(reply)
            print(f"model> {reply.get('content')}")


if __name__ == "__main__":
    main()
