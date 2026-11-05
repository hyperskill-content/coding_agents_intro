#!/usr/bin/env python3
"""
Stage 1 - The model is a stateless function.

A terminal chat loop that talks to an OpenAI-compatible /chat/completions
endpoint using only the Python standard library. The *harness* (this file)
owns the conversation history and re-sends all of it on every turn.

Run:  uv run reference/stage1_chat.py [--debug]
Env:  OPENAI_BASE_URL, OPENAI_API_KEY, MODEL
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


def call_model(messages):
    """One HTTP request = one model 'turn'. The model remembers nothing between calls."""
    body = {"model": MODEL, "messages": messages}
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


def main():
    if not API_KEY or not MODEL:
        raise SystemExit("Set OPENAI_API_KEY and MODEL (and OPENAI_BASE_URL if not using OpenAI).")
    messages = [{"role": "system", "content": "You are a concise, helpful assistant."}]
    print(f"Chatting with {MODEL}. Ctrl-D to quit.")
    while True:
        try:
            user = input("\nyou> ").strip()
        except EOFError:
            break
        if not user:
            continue
        messages.append({"role": "user", "content": user})
        reply = call_model(messages)  # send [messages[0], messages[-1]] instead and the model "forgets"
        messages.append(reply)
        print(f"model> {reply.get('content')}")


if __name__ == "__main__":
    main()
