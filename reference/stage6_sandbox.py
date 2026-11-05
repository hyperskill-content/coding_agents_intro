#!/usr/bin/env python3
"""
Stage 6 - Sandboxing: from policy to a real boundary.

Stage 5's checks live in the same process, with the same permissions, as the
code the model writes. A sandbox moves execution into an isolated environment
so the worst case is "the container got trashed", not "my laptop did".

Notice what changes: ONLY the function that executes shell commands.
The loop, the tools the model sees and the permission prompts stay the same.

The container gets:
  --network none            no exfiltration, no `curl | sh`
  -v WORKSPACE:/workspace   the ONLY host folder it can see
  --read-only + tmpfs /tmp  everything else is immutable
  --cap-drop ALL, no-new-privileges, non-root user
  --memory / --cpus / --pids-limit   no fork bombs or memory exhaustion
  a clean environment       no API keys inside

Run:  uv run reference/stage6_sandbox.py [--debug]      (needs Docker running)
Env:  SANDBOX_IMAGE (default python:3.14-slim), SANDBOX=off to fall back to stage 5
"""
import os
import shutil
import subprocess

import stage5_guardrails as h  # reuse everything from stage 5

IMAGE = os.environ.get("SANDBOX_IMAGE", "python:3.14-slim")


def docker_cmd(command):
    cmd = [
        "docker", "run", "--rm", "-i",
        "--network", "none",
        "--read-only", "--tmpfs", "/tmp:rw,size=64m",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--memory", "512m", "--cpus", "1", "--pids-limit", "128",
        "-v", f"{h.WORKSPACE}:/workspace", "-w", "/workspace",
        "-e", "HOME=/tmp",
    ]
    if hasattr(os, "getuid"):  # run as your user so files aren't root-owned (Linux/macOS)
        cmd += ["--user", f"{os.getuid()}:{os.getgid()}"]
    return cmd + [IMAGE, "sh", "-c", command]


def sandboxed_run_shell(command):
    # Stage 5's blocklist still runs before this (spec 6 changes only run_shell), but it
    # is no longer what protects you: the container is the boundary, not string matching.
    try:
        p = subprocess.run(docker_cmd(command), capture_output=True, text=True, timeout=60,
                           stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return "Error: command timed out after 60s"
    return (f"[sandbox: {IMAGE}, no network]\nexit_code={p.returncode}\n"
            f"--- stdout ---\n{p.stdout}\n--- stderr ---\n{p.stderr}")


def main():
    if os.environ.get("SANDBOX", "docker") == "off":
        print("SANDBOX=off -> running stage 5 behaviour (no isolation).")
    elif shutil.which("docker") is None:
        raise SystemExit("Docker not found. Install/start Docker, or run with SANDBOX=off.")
    else:
        h.TOOL_FUNCS["run_shell"] = sandboxed_run_shell
        # With a real boundary we can afford to auto-approve shell commands.
        # (Many harnesses do exactly this: 'ask' outside a sandbox, 'allow' inside.)
        if os.environ.get("SANDBOX_AUTO_APPROVE") == "1":
            h.POLICY["run_shell"] = "allow"
        print(f"run_shell is sandboxed in Docker ({IMAGE}, --network none).")
    h.main()


if __name__ == "__main__":
    main()
