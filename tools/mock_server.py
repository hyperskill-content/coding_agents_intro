#!/usr/bin/env python3
"""
A fake OpenAI-compatible /v1/chat/completions server with a scripted "model".

Use it when the API is down, the Wi-Fi is bad, or you want a 100% repeatable demo:

    uv run tools/mock_server.py             # listens on http://127.0.0.1:8765/v1
    export OPENAI_BASE_URL=http://127.0.0.1:8765/v1 OPENAI_API_KEY=mock MODEL=mock

It is NOT smart. It pattern-matches the latest user message:
    "my name is X" / "what's my name"   -> shows that memory = the history you send
    "list" / "files"                    -> list_dir(".")
    "read <file>"                       -> read_file(<file>)
    "create|write <file>"               -> write_file(<file>, ...)  (fizzbuzz if asked)
    "run <file>.py" / "run `cmd`"       -> run_shell(...)
    "env"                               -> run_shell("env")
And it is deliberately GULLIBLE: if a file it read tells it to run a setup
script (an indented "sh <script>.sh" line, as in demo/README.md), it runs it -
the prompt-injection demo for spec 5. Real models are sometimes harder to fool,
sometimes not.
"""
import json
import re
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765

FIZZBUZZ = '''for i in range(1, 16):
    if i % 15 == 0:
        print("FizzBuzz")
    elif i % 3 == 0:
        print("Fizz")
    elif i % 5 == 0:
        print("Buzz")
    else:
        print(i)
'''

FILE_RE = re.compile(r"(?:\.{0,2}/)?[\w./-]*\w\.\w{1,5}\b|\.\./[\w./-]+|/etc/\w+")


def text_of(msg):
    c = msg.get("content")
    if isinstance(c, list):  # content parts
        return " ".join(p.get("text", "") for p in c if isinstance(p, dict))
    return c or ""


def plan(user_text, tools):
    """Turn a user request into an ordered list of (tool, args)."""
    t = user_text.lower()
    files = FILE_RE.findall(user_text)
    calls = []
    if "list_dir" in tools and re.search(r"\b(list|files|what's in|whats in)\b", t):
        calls.append(("list_dir", {"path": "."}))
    if "write_file" in tools and re.search(r"\b(create|write|make)\b", t):
        target = files[0] if files else "hello.py"
        content = FIZZBUZZ if "fizz" in t else "print('hello from the agent')\n"
        calls.append(("write_file", {"path": target, "content": content}))
    elif "read_file" in tools and files and re.search(r"\b(read|read_file|open|show|summari[sz]e|what does|look at)\b", t):
        calls.append(("read_file", {"path": files[0]}))
    if "run_shell" in tools:
        m = re.search(r"`([^`]+)`", user_text)
        if m:
            calls.append(("run_shell", {"command": m.group(1)}))
        elif re.search(r"\b(run|execute|test)\b", t):
            py = next((f for f in files if f.endswith(".py")), None)
            if py:
                calls.append(("run_shell", {"command": f"python3 {py}"}))
        if re.search(r"\benv\b|environment variables", t) and not any(c[0] == "run_shell" for c in calls):
            calls.append(("run_shell", {"command": "env"}))
    return calls


# ---------- stage 7: large-codebase tools ----------
KEYWORDS = {"number of fields": "DATA_UPLOAD_MAX_NUMBER_FIELDS"}
HIT_RE = re.compile(r"^([\w./-]+\.\w+):(\d+):", re.M)


def search_term(text):
    for phrase, term in KEYWORDS.items():
        if phrase in text.lower():
            return term
    m = re.search(r"`([^`]+)`", text) or re.search(r"\b[A-Z][A-Z0-9_]{3,}\b", text)
    if m:
        return m.group(1) if m.groups() else m.group(0)
    return max(re.findall(r"\w+", text), key=len)


def findings(tool_results, term):
    keep = []
    for r in tool_results:
        for line in r.splitlines():
            if (re.search(rf"{re.escape(term)}\s*=|status_code|raise \w+", line) and line not in keep
                    and not line.startswith("tests/")):
                keep.append(line.strip())
    refs = sorted({f"{f}:{n}" for r in tool_results for f, n in HIT_RE.findall(r)})
    return "Relevant lines:\n" + "\n".join(keep[:12]) + "\n\nLocations: " + ", ".join(refs[:15])


def decide_repo(user_text, tools, made, tool_results, tool_choice):
    names = [f["name"] for f in made]
    term = search_term(user_text.split("(mock notes)")[0])
    if tool_choice == "none":  # compaction request: summarize, no tools
        return {"content": "(mock notes) " + findings(tool_results, term)}
    if "(mock notes)" in user_text:  # history was compacted; works with any harness wording
        return {"content": "(mock) From my notes:\n" + user_text.split("(mock notes)")[-1].strip()}
    if "read_folder" in tools:  # naive: the tempting tool
        if "list_dir" not in names:
            return tool_call("list_dir", {"path": "."})
        if "read_folder" not in names:
            return tool_call("read_folder", {"path": "."})
        return {"content": "(mock) I read everything. " + findings(tool_results, term)}
    if "explore" in tools:
        if "explore" not in names:
            return tool_call("explore", {"question": user_text})
        return {"content": "(mock) Based on the sub-agent's findings:\n" + tool_results[-1]}
    # navigating agent: shape -> search -> read slices -> follow the exception -> answer
    if "list_dir" not in names:
        return tool_call("list_dir", {"path": ".", "depth": 1})
    searches = [json.loads(f["arguments"])["pattern"] for f in made if f["name"] == "search_code"]
    reads = {json.loads(f["arguments"])["path"] for f in made if f["name"] == "read_file"}
    if not searches:
        return tool_call("search_code", {"pattern": term, "glob": "*.py"})
    search_out = [r for r in tool_results if HIT_RE.search(r)]
    last_hit = {}  # the last hit in each file is usually the code, not the import
    for f, n in HIT_RE.findall("\n".join(search_out)):
        last_hit[f] = int(n)
    for f, n in last_hit.items():
        if f not in reads and len(reads) < 5 and "/tests/" not in f and not f.startswith("tests/"):
            return tool_call("read_file", {"path": f, "start_line": max(1, n - 20), "end_line": n + 40})
    raised = re.findall(r"raise (\w+)\(", "\n".join(tool_results))
    if raised and raised[0] not in searches:
        return tool_call("search_code", {"pattern": raised[0], "path": ".", "glob": "*.py"})
    return {"content": "(mock) " + findings(tool_results, term)}


def decide(messages, tools, tool_choice=None):
    user_idxs = [i for i, m in enumerate(messages) if m.get("role") == "user"]
    # A compaction request adds a "summarize" user message on top of the turn: look past it.
    turn_idx = user_idxs[-2] if tool_choice == "none" and len(user_idxs) > 1 else user_idxs[-1]
    user_text = text_of(messages[turn_idx])
    after = messages[turn_idx + 1:]
    tool_results = [text_of(m) for m in after if m.get("role") == "tool"]
    made = [tc["function"] for m in after if m.get("role") == "assistant"
            for tc in (m.get("tool_calls") or [])]

    # No tools offered -> plain chat that proves memory lives in the request.
    if not tools:
        history = " ".join(text_of(m) for m in messages if m.get("role") == "user")
        names = re.findall(r"my name is (\w+)", history, re.I)
        if re.search(r"what('?s| is) my name", user_text, re.I):
            return {"content": f"Your name is {names[-1]}." if names else
                    "I don't know your name - nothing in the messages you sent me says it."}
        n = sum(1 for m in messages if m.get("role") in ("user", "assistant"))
        return {"content": f"(mock) You said: {user_text!r}. I was sent {n} user/assistant messages this time."}

    if any(t in tools for t in ("read_folder", "search_code", "explore")):
        return decide_repo(user_text, tools, made, tool_results, tool_choice)

    if any("denied" in r for r in tool_results):
        return {"content": "That action was denied, so I stopped. How would you like to proceed?"}

    planned = plan(user_text, tools)
    if len(made) < len(planned):
        name, args = planned[len(made)]
        return tool_call(name, args)

    # Deliberately gullible: run setup scripts that files tell it to run.
    for r in tool_results:
        m = re.search(r"^(?: {4}|\t)(sh [\w./-]+\.sh)\s*$", r, re.M)
        if m and "run_shell" in tools:
            cmd = m.group(1).strip()
            ran = [json.loads(f["arguments"]).get("command") for f in made if f["name"] == "run_shell"]
            if cmd not in ran:
                return tool_call("run_shell", {"command": cmd})

    if tool_results:
        snippet = tool_results[-1].strip()
        snippet = snippet if len(snippet) < 600 else snippet[:600] + " ..."
        return {"content": f"(mock) Done. Last tool result:\n{snippet}"}
    return {"content": f"(mock) I have tools {sorted(tools)} but nothing in {user_text!r} needs them."}


def tool_call(name, args):
    return {"content": None, "tool_calls": [{
        "id": "call_" + uuid.uuid4().hex[:12], "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)}}]}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            return self._send(200, {"object": "list", "data": [{"id": "mock", "object": "model"}]})
        self._send(404, {"error": {"message": "not found"}})

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/chat/completions"):
            return self._send(404, {"error": {"message": "not found"}})
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or "{}")
        messages = body.get("messages", [])
        tools = {t["function"]["name"] for t in body.get("tools", []) if t.get("type") == "function"}
        # Validate like the real API does: every tool_call needs a matching tool result.
        pending = set()
        for m in messages:
            if m.get("role") == "assistant":
                if pending:
                    return self._send(400, {"error": {"message": f"tool_call_ids without results: {sorted(pending)}"}})
                pending = {tc["id"] for tc in m.get("tool_calls") or []}
            elif m.get("role") == "tool":
                pending.discard(m.get("tool_call_id"))
            elif pending:
                return self._send(400, {"error": {"message": f"tool_call_ids without results: {sorted(pending)}"}})
        if pending:
            return self._send(400, {"error": {"message": f"tool_call_ids without results: {sorted(pending)}"}})
        msg = {"role": "assistant", **decide(messages, tools, body.get("tool_choice"))}
        prompt_chars = len(json.dumps(messages)) + len(json.dumps(body.get("tools", [])))
        self._send(200, {
            "id": "chatcmpl-" + uuid.uuid4().hex[:12], "object": "chat.completion",
            "created": int(time.time()), "model": body.get("model", "mock"),
            "choices": [{"index": 0, "message": msg,
                         "finish_reason": "tool_calls" if msg.get("tool_calls") else "stop"}],
            "usage": {"prompt_tokens": prompt_chars // 4, "completion_tokens": 20,
                      "total_tokens": prompt_chars // 4 + 20},
        })

    def log_message(self, fmt, *args):
        sys.stderr.write("[mock] " + fmt % args + "\n")


if __name__ == "__main__":
    print(f"Mock model on http://127.0.0.1:{PORT}/v1  (model name: anything)")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
