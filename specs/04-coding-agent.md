# Spec 4 — Make it a coding agent  (≈12 min)

**Concept:** two more tools — write a file, run a command — and the loop becomes a coding agent. The harness also has to steer (system prompt) and protect the context window (truncation).

> ⚠️ After this spec your agent can run **any** shell command as you. Only run it inside `playground/`.

## Give this to your coding agent

> Update `agent.py` (standard library only):
> - Add tools `write_file(path, content)` (creates parent folders, overwrites) and `run_shell(command)` (uses `subprocess.run` with `shell=True`, 30 s timeout, returns exit code, stdout and stderr in one string).
> - Add a `truncate(text, limit=4000)` helper that keeps the start and end of long outputs with a `[N chars truncated]` marker in the middle, and apply it to every tool result.
> - Replace the system message with a short coding-agent system prompt that includes the current working directory, the OS and the Python version, and tells the model to look at files before changing them and to run code after writing it.
> - After each model call, print the `usage` token counts if present.
> - Raise `MAX_STEPS` to 15.

## Try it  (inside `playground/`)

```bash
uv run ../agent.py
you> add a multiply function to calc.py and write a test file that checks it, then run the test
you> what happens if I divide by zero in calc.py? fix it so it raises a clear ValueError, and prove it
```

## Notice

1. Watch the model *write → run → see an error → fix → run again*. Nobody coded that behaviour; it emerges from the loop plus feedback.
2. Watch `prompt_tokens` climb with each step. Every tool result stays in the history. Truncation is why one `cat` of a huge log doesn't kill the session. (Real harnesses also summarize/"compact" old turns.)
3. The system prompt is the harness's main steering wheel. Delete the "run code after writing it" line and compare.

Checkpoint: `reference/stage4_coding_agent.py`
