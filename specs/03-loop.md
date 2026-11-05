# Spec 3 — The agent loop  (≈18 min)

**Concept:** an agent is a loop. Call the model → if it asked for tools, run them, append the results, call again → stop when it answers in plain text.

```
user ─▶ model ─▶ tool_calls? ──yes──▶ harness runs tools ─▶ append results ─┐
                     │                                                      │
                     no                         ◀───────────────────────────┘
                     ▼
                  answer
```

## Give this to your coding agent

> Update `agent.py` to actually execute tools (standard library only):
> - Implement `list_dir(path)` and `read_file(path)` as plain Python functions and a dict `TOOL_FUNCS` mapping names to functions.
> - Write `run_tool(call)`: parse `call["function"]["arguments"]` with `json.loads`, look up the function, call it with the arguments, return the result as a string. If the JSON is invalid, the tool is unknown, or the function raises, return an `"Error: ..."` string instead of crashing — the model will read it.
> - Write `agent_turn(messages)`: loop up to `MAX_STEPS = 10` times. Each step: call the model with tools and append the assistant message (including its `tool_calls`) to `messages`. If there are no tool calls, return the text. Otherwise, for each call, run it and append `{"role": "tool", "tool_call_id": call["id"], "content": result}`.
> - Print a one-line trace per tool call, e.g. `[1] -> read_file({"path": "calc.py"})` and `<- 69 chars`.
> - The main loop calls `agent_turn` for each user message and prints the final answer.

## Try it  (inside `playground/`)

```bash
cd playground && uv run ../agent.py
you> what does this project do? look at the files.
you> read nope.txt
```

## Notice

1. Count the steps. The model looked at the folder, *then* decided which file to read — it plans one step at a time based on results.
2. Ask for a missing file. The error goes back to the model as text and it adapts. Errors are context, not crashes.
3. The `tool_call_id` links each result to its request. Remove it and see what the API says.
4. Why `MAX_STEPS`? What happens if a tool always fails and the model keeps retrying?

**This loop is the core of opencode, Claude Code, Cursor's agent, etc.** Everything else is better tools, better context management and safety.

Checkpoint: `reference/stage3_loop.py`
