# Spec 1 — The model is a stateless function

**Concept:** an LLM API call is one HTTP request in, one message out. The model remembers nothing. "Memory" is the harness re-sending the whole conversation every time.

## Give this to your coding agent

> Create `agent.py`: a terminal chat program in Python 3 using **only the standard library** (`urllib.request`, `json`) — no `openai` SDK, no frameworks.
> - Read `OPENAI_BASE_URL`, `OPENAI_API_KEY` and `MODEL` from environment variables.
> - Keep a `messages` list starting with a short system message.
> - Loop: read a line from the user, append `{"role": "user", ...}`, POST `{"model", "messages"}` to `{OPENAI_BASE_URL}/chat/completions` with a Bearer token, append the returned assistant message to `messages`, print its content.
> - Put the HTTP call in a function `call_model(messages)`.
> - If `--debug` is passed, print the full request JSON and full response JSON.
> - On an HTTP error, print the status code and response body.
> Keep it under 60 lines and don't add anything I didn't ask for.

## Try it

```bash
uv run agent.py --debug
you> my name is Ana
you> what is my name?
```

## Notice

1. In `--debug`, the second request contains **both** turns. The model didn't "remember" — you re-sent it.
2. Now change the call to `call_model([messages[0], messages[-1]])` (system prompt + latest message only) and ask again. The model "forgets". (Deleting only the line that appends the assistant reply is not enough: your own "my name is Ana" is still in the history.)
3. Look at `usage.prompt_tokens` in the response. It grows every turn. Long chats cost more and eventually hit the context limit — that's a harness problem, not a model problem.

**Meta:** your coding agent just did the same thing you're building: it sent your message to a model and got back a request to write a file.

Checkpoint: `reference/stage1_chat.py`
