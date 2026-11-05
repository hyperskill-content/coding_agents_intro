# Spec 2 — Presenting tools to the model  (≈12 min)

**Concept:** the model can't touch your computer. You *describe* tools to it as JSON Schemas; when it wants one, it replies with a structured **request** (`tool_calls`) instead of text. Nothing runs unless the harness runs it.

## Give this to your coding agent

> Update `agent.py` (keep standard library only):
> - Add a `TOOLS` list in the OpenAI Chat Completions `tools` format describing two functions: `list_dir(path)` — "List the files and folders in a directory", and `read_file(path)` — "Read a UTF-8 text file and return its contents". Each needs a JSON Schema `parameters` object with a required string `path`.
> - Send `tools` in every request.
> - Print the response's `finish_reason`.
> - If the assistant message has `tool_calls`, **do not execute anything**. For each call, print the tool name, the raw `arguments` string and the call `id`. Then remove that assistant message from history (an unanswered tool call would make the next request invalid).
> - Otherwise print the text reply as before.

## Try it

```bash
uv run agent.py --debug
you> what files are in this folder?
you> hi, how are you?
```

## Notice

1. In the request JSON, find your tool descriptions. **That text is all the model knows about the tool.** Names and descriptions are prompt engineering.
2. `finish_reason` is `tool_calls` vs `stop`. The model *chose* to ask for a tool. For "hi" it didn't.
3. `arguments` is a JSON **string**, not an object. The model generated it token by token — it can be malformed. Your harness must parse and validate it.
4. Experiment: rename `list_dir` to `x1` with description "does stuff". Ask again. Tool design matters.

**Meta:** coding agents send the model 10–20 tool schemas like these (read, edit, bash, grep, glob, …). Each one costs context tokens on every request.

Checkpoint: `reference/stage2_tools.py`
